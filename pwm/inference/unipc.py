# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES.
# Copyright 2024 TSAIL Team and The HuggingFace Team. Copyright 2024-2025 The Alibaba Wan Team Authors.
# Adapted from https://github.com/NVIDIA/cosmos-framework
# (cosmos_framework/model/generator/diffusion/samplers/fm_solvers_unipc.py, itself from the HuggingFace Diffusers
# UniPC scheduler); upstream terms apply to the original portions.
"""Compact UniPC (bh2, order 2, x0-prediction) for rectified flow, matching upstream Cosmos3's
``FlowUniPCMultistepScheduler`` (the Wan/diffusers solver) restricted to the configuration Cosmos3 uses:
``prediction_type="flow_prediction"``, ``predict_x0=True``, ``solver_type="bh2"``, ``solver_order=2``,
``lower_order_final=True``, ``final_sigmas_type="zero"``, no dynamic shifting, no thresholding, no
disabled correctors. Bit-identical to upstream on the same velocity function. No dependency outside torch/numpy.

Numerics that matter for bit-equality (all copied from upstream):
- base sigmas ``1 - linspace(1, 1/1000, 1000)[::-1]`` → ``sigma_max = 0.999, sigma_min = 0``;
- ``set_timesteps``: ``linspace(sigma_max, sigma_min, n+1)[:-1]`` in **float64**, shift warp
  ``s*σ/(1+(s-1)σ)``, integer timesteps ``int64(σ·1000)`` (truncation!) — the network is evaluated at
  those truncated timesteps — then sigmas cast to float32 with a trailing 0;
- x0 prediction ``x0 = x - σ·v``; ``λ = log(1-σ) - log(σ)``; ``h = λ_t - λ_s0``; ``hh = -h``;
  ``B_h = expm1(hh)``; predictor order 2 uses ``rho = 0.5``; corrector order 2 solves the 2×2 system.

Usage: ``FlowUniPC(steps, shift).sample(velocity_fn, x0_latent)`` with
``velocity_fn(latent, timestep[1,1] int64) -> velocity`` (same contract as upstream ``UniPCSampler``).
"""

from __future__ import annotations

import numpy as np
import torch

from pwm.model.diffusion import NUM_TRAIN_TIMESTEPS

__all__ = ["FlowUniPC"]


def _lambda(sigma: torch.Tensor) -> torch.Tensor:
    return torch.log(1 - sigma) - torch.log(sigma)


class FlowUniPC:
    ORDER = 2  # only the Cosmos configuration (order 2, bh2, predict_x0) is vendored

    def __init__(self, num_steps: int, shift: float):
        self.order = self.ORDER
        alphas = np.linspace(1, 1 / NUM_TRAIN_TIMESTEPS, NUM_TRAIN_TIMESTEPS)[::-1].copy()
        base = torch.from_numpy(1.0 - alphas).to(
            torch.float32
        )  # constructor shift == 1.0 → identity
        sigma_max, sigma_min = base[0].item(), base[-1].item()
        sig = np.linspace(sigma_max, sigma_min, num_steps + 1).copy()[:-1]  # float64
        sig = shift * sig / (1 + (shift - 1) * sig)
        timesteps = sig * NUM_TRAIN_TIMESTEPS
        self.sigmas = torch.from_numpy(np.concatenate([sig, [0.0]]).astype(np.float32))  # [n+1]
        self.timesteps = torch.from_numpy(timesteps).to(torch.int64)  # [n] (truncated)
        self.num_steps = num_steps
        self.reset()

    def reset(self) -> None:
        self.model_outputs: list[torch.Tensor | None] = [None] * self.order
        self.lower_order_nums = 0
        self.last_sample: torch.Tensor | None = None
        self.step_index = 0
        self.this_order = 1

    # --------------------------------------------------------------------------- B(h) coefficients
    def _coeffs(self, order: int, h: torch.Tensor, rks: list[torch.Tensor], device):
        rks = torch.tensor([*rks, 1.0], device=device)
        hh = -h  # predict_x0
        h_phi_1 = torch.expm1(hh)
        h_phi_k = h_phi_1 / hh - 1
        B_h = torch.expm1(hh)  # == h_phi_1 under bh2; kept separate to mirror upstream
        R, b, factorial_i = [], [], 1
        for i in range(1, order + 1):
            R.append(torch.pow(rks, i - 1))
            b.append(h_phi_k * factorial_i / B_h)
            factorial_i *= i + 1
            h_phi_k = h_phi_k / hh - 1 / factorial_i
        return torch.stack(R), torch.tensor(b, device=device), h_phi_1, B_h

    def _predictor(self, x: torch.Tensor, order: int) -> torch.Tensor:
        m0 = self.model_outputs[-1]
        sigma_t, sigma_s0 = self.sigmas[self.step_index + 1], self.sigmas[self.step_index]
        alpha_t = 1 - sigma_t
        h = _lambda(sigma_t) - _lambda(sigma_s0)
        rks, D1s = [], []
        for i in range(1, order):
            si = self.step_index - i
            mi = self.model_outputs[-(i + 1)]
            rk = (_lambda(self.sigmas[si]) - _lambda(sigma_s0)) / h
            rks.append(rk)
            D1s.append((mi - m0) / rk)
        R, b, h_phi_1, B_h = self._coeffs(order, h, rks, x.device)
        x_t_ = sigma_t / sigma_s0 * x - alpha_t * h_phi_1 * m0
        if D1s:
            D1s_ = torch.stack(D1s, dim=1)  # [B,order-1,...]
            rhos_p = torch.tensor([0.5], dtype=x.dtype, device=x.device)  # order == 2 (ORDER cap)
            pred_res = torch.einsum("k,bkc...->bc...", rhos_p, D1s_)
        else:
            pred_res = 0
        return (x_t_ - alpha_t * B_h * pred_res).to(x.dtype)

    def _corrector(
        self, model_t: torch.Tensor, last_sample: torch.Tensor, order: int
    ) -> torch.Tensor:
        m0 = self.model_outputs[-1]
        x = last_sample
        sigma_t, sigma_s0 = self.sigmas[self.step_index], self.sigmas[self.step_index - 1]
        alpha_t = 1 - sigma_t
        h = _lambda(sigma_t) - _lambda(sigma_s0)
        rks, D1s = [], []
        for i in range(1, order):
            si = self.step_index - (i + 1)
            mi = self.model_outputs[-(i + 1)]
            rk = (_lambda(self.sigmas[si]) - _lambda(sigma_s0)) / h
            rks.append(rk)
            D1s.append((mi - m0) / rk)
        R, b, h_phi_1, B_h = self._coeffs(order, h, rks, x.device)
        D1s_ = torch.stack(D1s, dim=1) if D1s else None
        rhos_c = (
            torch.tensor([0.5], dtype=x.dtype, device=x.device)
            if order == 1
            else torch.linalg.solve(R, b).to(x.dtype)
        )
        x_t_ = sigma_t / sigma_s0 * x - alpha_t * h_phi_1 * m0
        corr_res = torch.einsum("k,bkc...->bc...", rhos_c[:-1], D1s_) if D1s_ is not None else 0
        D1_t = model_t - m0
        return (x_t_ - alpha_t * B_h * (corr_res + rhos_c[-1] * D1_t)).to(x.dtype)

    # ------------------------------------------------------------------------------------- step
    def step(self, velocity: torch.Tensor, sample: torch.Tensor) -> torch.Tensor:
        """One UniPC step on ``sample`` ``[B, ...]`` given the network velocity at ``self.timesteps[step_index]``."""
        use_corrector = self.step_index > 0 and self.last_sample is not None
        x0_pred = (
            sample - self.sigmas[self.step_index] * velocity
        )  # convert_model_output (flow → x0)
        if use_corrector:
            sample = self._corrector(x0_pred, self.last_sample, self.this_order)
        self.model_outputs = self.model_outputs[1:] + [x0_pred]
        this_order = min(self.order, self.num_steps - self.step_index)  # lower_order_final
        self.this_order = min(this_order, self.lower_order_nums + 1)  # multistep warm-up
        self.last_sample = sample
        prev = self._predictor(sample, self.this_order)
        if self.lower_order_nums < self.order:
            self.lower_order_nums += 1
        self.step_index += 1
        return prev

    @torch.no_grad()
    def sample(self, velocity_fn, latent: torch.Tensor) -> torch.Tensor:
        """Full loop, upstream ``UniPCSampler.forward`` semantics (``latent`` = initial noise, any shape)."""
        self.reset()
        x = latent
        for t in self.timesteps:
            v = velocity_fn(x, t.reshape(1, 1))
            x = self.step(v.unsqueeze(0), x.unsqueeze(0)).squeeze(0)
        return x


if __name__ == "__main__":
    # Hardware-free smoke: schedule shape, truncated timesteps, and an analytic linear velocity field
    # (v = x - x0 ⇒ the exact solution reaches x0; order-2 UniPC lands close after a few steps).
    s = FlowUniPC(5, shift=5.0)
    assert s.sigmas.shape == (6,) and s.sigmas[-1] == 0 and s.timesteps.dtype == torch.int64
    assert s.timesteps[0] == int(s.sigmas[0].item() * 1000) or s.timesteps[0] == 999
    torch.manual_seed(0)
    x0 = torch.randn(4, 3)
    noise = torch.randn(4, 3)

    def vf(x, t):  # flow x_t = (1-σ)x0 + σ ε  ⇒  v = ε - x0 = (x - x0) / σ
        sigma = float(t.item()) / 1000.0
        return (x - x0) / max(sigma, 1e-3)

    out = FlowUniPC(20, shift=1.0).sample(vf, noise)
    assert torch.isfinite(out).all() and (out - x0).abs().max() < 0.3, (out - x0).abs().max()
    print("unipc smoke OK")
