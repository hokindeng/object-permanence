"""Sampling: UniPC on CPU fp32 driving ``NanoMoT`` with classifier-free guidance.

- initial latent = ``numpy.random.RandomState(seed).standard_normal`` (upstream's seeded noise), with
  the v2v clean prefix copied in;
- per step: two network forwards (conditional and unconditional/negative prompt) combined as
  ``v = v_uncond + guidance * (v_cond - v_uncond)``; one forward when ``guidance == 1``;
- the solver is the vendored ``FlowUniPC`` (``inference/unipc.py``), run on CPU in fp32: the latent is
  tiny and this sidesteps every device/dtype hazard of the solver;
- conditioning frames receive exactly zero velocity from the network (``unpatchify`` zero-fill), so
  UniPC never moves them; a final masked copy makes the prefix bit-exact.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch

from pwm.data.pack import TEMPORAL_MARGIN, pack
from pwm.inference.unipc import FlowUniPC
from pwm.model.diffusion import NUM_TRAIN_TIMESTEPS
from pwm.model.patchify import unpatchify

__all__ = ["Prompt", "SampleConfig", "initial_latent", "make_velocity_fn", "unipc_sample"]


@dataclass
class Prompt:
    """Text ids as the network sees them; ``valid`` = number of real ids when padded to the trained length
    (``pack.pad_text_ids``), ``None`` when every id is real."""

    ids: torch.Tensor
    valid: int | None = None


def as_prompt(x) -> Prompt:
    return x if isinstance(x, Prompt) else Prompt(torch.as_tensor(x))


@dataclass
class SampleConfig:
    steps: int = 35
    guidance: float = 6.0
    shift: float = 5.0
    seed: int = 1234
    cond_frames: int = 0
    fps: float = 24.0
    temporal_margin: int = TEMPORAL_MARGIN


def initial_latent(
    shape: tuple[int, ...], seed: int, x0_clean: torch.Tensor | None = None, cond_frames: int = 0
) -> torch.Tensor:
    """``[1,C,T,H,W]`` fp32 CPU: seeded Gaussian noise, v2v prefix copied from ``x0_clean``."""
    noise = torch.from_numpy(np.random.RandomState(seed).standard_normal(shape).astype(np.float32))
    if x0_clean is not None and cond_frames > 0:
        noise[:, :, :cond_frames] = x0_clean.to(torch.float32)[:, :, :cond_frames]
    return noise


def _predict(
    model, text: Prompt, latent: torch.Tensor, sigma: float, cfg: SampleConfig, device
) -> torch.Tensor:
    mc = model.cfg
    pk = pack(
        text.ids,
        latent,
        sigma,
        cond_frames=cfg.cond_frames,
        fps=cfg.fps,
        temporal_margin=cfg.temporal_margin,
        head_dim=mc.head_dim,
        rope_theta=mc.rope_theta,
        mrope_section=mc.mrope_section,
        text_valid=text.valid,
    )
    with torch.no_grad():
        pred = model(*pk.model_inputs(device), text_valid=pk.text_valid)  # [Nv,192]
    v = unpatchify(pred.to(torch.float32).cpu(), pk.grid)
    return v * pk.noisy_frame_mask.reshape(1, 1, -1, 1, 1)  # zero velocity on the clean prefix


def make_velocity_fn(
    model,
    cond_ids,
    uncond_ids,
    cfg: SampleConfig,
    device,
    shape: tuple[int, ...],
):
    """``velocity_fn(latent_flat, timestep)`` in the sampler's contract (CPU fp32 in/out); ``shape`` is the
    ``[1,C,T,H,W]`` latent shape the flat vector is viewed as. ``cond_ids``/``uncond_ids``: id tensors or
    :class:`Prompt` (padded ids + valid count)."""
    cond = as_prompt(cond_ids)
    uncond = None if uncond_ids is None else as_prompt(uncond_ids)

    def velocity_fn(latent_flat: torch.Tensor, timestep: torch.Tensor) -> torch.Tensor:
        sigma = float(timestep.reshape(-1)[0].item()) / NUM_TRAIN_TIMESTEPS
        latent = latent_flat.reshape(shape).to(torch.float32)
        v_cond = _predict(model, cond, latent, sigma, cfg, device)
        if cfg.guidance == 1.0 or uncond is None:
            return v_cond.reshape(-1)
        v_uncond = _predict(model, uncond, latent, sigma, cfg, device)
        return (v_uncond + cfg.guidance * (v_cond - v_uncond)).reshape(-1)

    return velocity_fn


def unipc_sample(
    model,
    cond_ids,
    uncond_ids,
    latent0: torch.Tensor,
    cfg: SampleConfig,
    device="cpu",
    x0_clean=None,
) -> torch.Tensor:
    """UniPC on CPU fp32. ``latent0`` ``[1,C,T,H,W]`` from :func:`initial_latent`. Returns the clean latent."""
    vf = make_velocity_fn(model, cond_ids, uncond_ids, cfg, device, tuple(latent0.shape))
    flat = latent0.reshape(-1).to(torch.float32)
    latent = FlowUniPC(cfg.steps, cfg.shift).sample(vf, flat).reshape(latent0.shape)
    if x0_clean is not None and cfg.cond_frames > 0:
        latent[:, :, : cfg.cond_frames] = x0_clean.to(torch.float32)[:, :, : cfg.cond_frames]
    return latent


if __name__ == "__main__":
    # Hardware-free smoke with a tiny random model: UniPC loop runs with CFG, prefix stays bit-exact.
    from pwm.configs.config import ModelConfig
    from pwm.model.mot import NanoMoT
    from pwm.model.patchify import LATENT_CHANNELS

    mc = ModelConfig(
        layers=1,
        dim=64,
        heads=4,
        kv_heads=2,
        head_dim=16,
        ffn_dim=96,
        vocab_size=64,
        mrope_section=(4, 2, 2),
        gradient_checkpointing=False,
    )
    m = NanoMoT(mc).eval()
    x0 = torch.randn(1, LATENT_CHANNELS, 3, 4, 6)
    cfg = SampleConfig(steps=3, guidance=2.0, shift=3.0, cond_frames=1)
    ids, uids = torch.arange(5), torch.arange(3)
    lat0 = initial_latent(x0.shape, cfg.seed, x0, cfg.cond_frames)
    assert torch.equal(lat0[:, :, 0], x0[:, :, 0])
    out = unipc_sample(m, ids, uids, lat0, cfg, x0_clean=x0)
    assert (
        out.shape == x0.shape
        and torch.isfinite(out).all()
        and torch.equal(out[:, :, 0], x0[:, :, 0])
    )
    assert torch.equal(initial_latent(x0.shape, 7), initial_latent(x0.shape, 7))
    # Padded prompts: the pad ids do not reach the sample.
    from pwm.data.pack import pad_text_ids

    pa, na = pad_text_ids(torch.arange(5), 8, pad_id=60)
    pb, nb = pad_text_ids(torch.arange(5), 8, pad_id=61)
    ua, nu = pad_text_ids(torch.arange(3), 8, pad_id=60)
    sa = unipc_sample(m, Prompt(pa, na), Prompt(ua, nu), lat0, cfg, x0_clean=x0)
    sb = unipc_sample(m, Prompt(pb, nb), Prompt(ua, nu), lat0, cfg, x0_clean=x0)
    assert torch.equal(sa, sb) and torch.isfinite(sa).all()
    print("sample smoke OK")
