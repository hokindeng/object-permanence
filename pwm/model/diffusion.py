"""Rectified-flow primitives for Cosmos3-Nano — stateless, no model, no device assumptions.

Matches upstream Cosmos3 semantics: sigma draws ``uniform`` / ``logitnormal`` / ``waver`` followed by
the shift warp ``sigma = s*t / (1 + (s-1)*t)`` (video training uses ``waver`` with shift 3/5/10 at
256p/480p/720p); interpolation ``x_t = eps*sigma + x0*(1-sigma)`` with ``sigma_eff = sigma*(1-cond_mask)``
so conditioning frames stay ``x0``; target ``v = eps - x0``; loss ``((pred-target)^2 * noisy_mask).mean()``
over the whole ``[C,T,H,W]`` tensor; timestep sinusoid of ``sigma`` with ``dim=256, max_period=10000``,
computed on CPU in fp32 by the packer so ``arange``/``exp`` stay out of the compiled graph.
"""

from __future__ import annotations

import math

import torch

__all__ = [
    "NUM_TRAIN_TIMESTEPS",
    "TIME_FREQ_DIM",
    "sample_sigma",
    "shift_sigma",
    "add_noise",
    "velocity_target",
    "flow_loss",
    "timestep_sinusoid",
]

NUM_TRAIN_TIMESTEPS = 1000
TIME_FREQ_DIM = 256
_WAVER_MODE_S = 1.29


def shift_sigma(t: torch.Tensor, shift: float) -> torch.Tensor:
    """Upstream shift warp ``s*t / (1 + (s-1)*t)``; identity for ``shift == 1``."""
    return shift * t / (1.0 + (shift - 1.0) * t)


def sample_sigma(
    kind: str,
    batch: int,
    shift: float = 1.0,
    generator: torch.Generator | None = None,
) -> torch.Tensor:
    """Draw ``sigma`` ``[batch]`` fp32 on CPU.

    ``kind``: ``uniform`` | ``logitnormal`` | ``waver`` (upstream video default).
    """
    if kind == "uniform":
        t = torch.rand((batch,), generator=generator)
    elif kind == "logitnormal":
        t = torch.sigmoid(torch.randn((batch,), generator=generator))
    elif kind == "waver":
        u = torch.rand((batch,), dtype=torch.float32, generator=generator)
        t = 1.0 - u - _WAVER_MODE_S * (torch.cos(torch.pi / 2.0 * u) ** 2 - 1 + u)
    else:
        raise ValueError(f"unknown sigma distribution {kind!r}")
    return shift_sigma(t.to(torch.float32), shift)


def add_noise(
    x0: torch.Tensor, eps: torch.Tensor, sigma: float | torch.Tensor, noisy_frame_mask: torch.Tensor
) -> torch.Tensor:
    """``x0, eps`` ``[1,C,T,H,W]``; ``noisy_frame_mask`` ``[T]`` (1 = noisy). Clean frames keep ``x0``."""
    s = torch.as_tensor(sigma, dtype=x0.dtype).reshape(1, 1, 1, 1, 1)
    m = noisy_frame_mask.to(x0.dtype).reshape(1, 1, -1, 1, 1)
    s_eff = s * m
    return eps * s_eff + x0 * (1.0 - s_eff)


def velocity_target(x0: torch.Tensor, eps: torch.Tensor) -> torch.Tensor:
    return eps - x0


def flow_loss(
    pred: torch.Tensor, target: torch.Tensor, noisy_frame_mask: torch.Tensor
) -> torch.Tensor:
    """Masked MSE over the full ``[1,C,T,H,W]`` tensor (upstream semantics, uniform time weight).

    Reduced in fp32 regardless of ``pred.dtype``.
    """
    m = noisy_frame_mask.to(torch.float32).reshape(1, 1, -1, 1, 1)
    sq = (pred.to(torch.float32) - target.to(torch.float32)) ** 2
    return (sq * m).mean()


def timestep_sinusoid(
    t: torch.Tensor, dim: int = TIME_FREQ_DIM, max_period: float = 10000.0
) -> torch.Tensor:
    """``t`` ``[B]`` (already scaled, i.e. ``sigma``) → ``[B, dim]`` fp32, upstream ``[cos | sin]`` order."""
    assert dim % 2 == 0, dim
    half = dim // 2
    freqs = torch.exp(-math.log(max_period) * torch.arange(0, half, dtype=torch.float32) / half)
    args = t.to(torch.float32)[:, None] * freqs[None]
    return torch.cat([torch.cos(args), torch.sin(args)], dim=-1)


if __name__ == "__main__":
    g = torch.Generator().manual_seed(0)
    for kind in ("uniform", "logitnormal", "waver"):
        s = sample_sigma(kind, 4096, shift=5.0, generator=g)
        assert (
            s.shape == (4096,) and s.dtype == torch.float32 and (s >= 0).all() and (s <= 1).all()
        ), kind
    assert torch.allclose(shift_sigma(torch.tensor([0.5]), 1.0), torch.tensor([0.5]))
    x0, eps = torch.randn(1, 48, 3, 4, 4), torch.randn(1, 48, 3, 4, 4)
    m = torch.tensor([0.0, 1.0, 1.0])
    xt = add_noise(x0, eps, 0.25, m)
    assert torch.equal(xt[:, :, 0], x0[:, :, 0])
    assert torch.allclose(xt[:, :, 1], 0.25 * eps[:, :, 1] + 0.75 * x0[:, :, 1])
    loss = flow_loss(torch.zeros_like(x0), velocity_target(x0, eps), m)
    ref = (((eps - x0) ** 2) * m.reshape(1, 1, -1, 1, 1)).mean()
    assert torch.allclose(loss, ref)
    emb = timestep_sinusoid(torch.tensor([0.5]))
    assert emb.shape == (1, 256) and torch.allclose(emb[0, 0], torch.tensor(math.cos(0.5)))
    print("diffusion smoke OK")
