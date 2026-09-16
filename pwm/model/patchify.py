"""Latent ⇄ patch-token conversion for Cosmos3-Nano.

Reproduces upstream Cosmos3 ``patchify_and_pack_latents`` / ``unpatchify_and_unpack_latents`` for one
sample with a static geometry:

- latent ``[1, C=48, T, H, W]`` → tokens ``[T*h*w, p*p*C]`` with ``h = H/p``, ``w = W/p``, last-dim
  order ``(p_h, p_w, c)`` (upstream ``einsum("cthpwq->thwpqc")``), token order ``(t, h, w)``.
- the inverse for the prediction, followed by **zero-filling every clean (conditioning) frame** —
  upstream only writes predictions for ``noisy_frame_indexes`` into a zero canvas.

Upstream pads ``H, W`` up to a multiple of ``p``; we require them to be multiples already (the VAE
stride 16 × patch 2 = 32 rule is enforced by the data pipeline) so the shapes are static.
"""

from __future__ import annotations

import torch

__all__ = [
    "LATENT_CHANNELS",
    "PATCH",
    "PATCH_DIM",
    "grid_of",
    "patchify",
    "unpatchify",
    "noisy_token_mask",
]

LATENT_CHANNELS = 48
PATCH = 2
PATCH_DIM = PATCH * PATCH * LATENT_CHANNELS  # 192


def grid_of(latent_shape: tuple[int, ...], p: int = PATCH) -> tuple[int, int, int]:
    """``(T, h, w)`` patch grid of a ``[1,C,T,H,W]`` (or ``[C,T,H,W]``) latent."""
    T, H, W = latent_shape[-3], latent_shape[-2], latent_shape[-1]
    assert H % p == 0 and W % p == 0, f"latent H,W must be multiples of patch {p}: got {(H, W)}"
    return T, H // p, W // p


def patchify(latent: torch.Tensor, p: int = PATCH) -> torch.Tensor:
    """``[1,C,T,H,W]`` → ``[T*h*w, p*p*C]`` (order ``thw`` outer, ``(p_h, p_w, c)`` inner)."""
    if latent.ndim == 5:
        assert latent.shape[0] == 1, "one sample per call"
        latent = latent[0]
    C = latent.shape[0]
    T, h, w = grid_of(latent.shape, p)
    x = latent.reshape(C, T, h, p, w, p)  # [C,T,h,p,w,p]
    x = x.permute(1, 2, 4, 3, 5, 0)  # thwpqc
    return x.reshape(T * h * w, p * p * C)


def unpatchify(
    tokens: torch.Tensor, grid: tuple[int, int, int], p: int = PATCH, C: int = LATENT_CHANNELS
) -> torch.Tensor:
    """``[T*h*w, p*p*C]`` → ``[1,C,T,h*p,w*p]``. Exact inverse of :func:`patchify`."""
    T, h, w = grid
    x = tokens.reshape(T, h, w, p, p, C)  # thwpqc
    x = x.permute(5, 0, 1, 3, 2, 4)  # cthpwq
    return x.reshape(1, C, T, h * p, w * p)


def noisy_token_mask(grid: tuple[int, int, int], noisy_frame_mask: torch.Tensor) -> torch.Tensor:
    """Per-token ``[T*h*w, 1]`` float mask from a per-frame ``[T]`` mask (1 = noisy/generated)."""
    T, h, w = grid
    assert noisy_frame_mask.shape == (T,), noisy_frame_mask.shape
    return noisy_frame_mask.to(torch.float32).repeat_interleave(h * w)[:, None]


if __name__ == "__main__":
    lat = torch.randn(1, LATENT_CHANNELS, 3, 4, 6)
    tok = patchify(lat)
    assert tok.shape == (3 * 2 * 3, PATCH_DIM)
    # Upstream reference ordering via einsum.
    ref = torch.einsum("cthpwq->thwpqc", lat[0].reshape(LATENT_CHANNELS, 3, 2, 2, 3, 2)).reshape(
        -1, PATCH_DIM
    )
    assert torch.equal(tok, ref)
    assert torch.equal(unpatchify(tok, grid_of(lat.shape)), lat)
    m = noisy_token_mask((3, 2, 3), torch.tensor([0.0, 1.0, 1.0]))
    assert m.shape == (18, 1) and m[:6].sum() == 0 and m[6:].sum() == 12
    print("patchify smoke OK")
