"""Interleaved 3-D mRoPE for Cosmos3-Nano (Qwen3-VL text tower), without HF plumbing.

Matches upstream ``Qwen3VLTextRotaryEmbedding`` + ``apply_interleaved_mrope``:
``inv_freq = theta ** (-arange(0,D,2)/D)``, ``attention_scaling = 1.0``, rotate-half apply with no
fp32 upcast (the multiply runs in the activation dtype, as the text path does upstream).

Design for Neuron: cos/sin are computed on CPU in fp32 once per geometry by the packer and fed to
the model as plain ``[N, head_dim]`` inputs, cast to the model dtype at the boundary. Nothing here
runs ``arange``/``cos`` inside the compiled graph, there are no complex ops, and the interleave is a
pure gather (upstream's stride-3 in-place slice write produces inf/NaN on Neuron).

Interleave layout for ``section=(24,20,20)`` over ``D/2 = 64`` frequency slots: slot ``i < 60`` takes
axis ``i % 3`` (0=T, 1=H, 2=W); slots ``60..63`` take T. That yields 24 T, 20 H, 20 W.
"""

from __future__ import annotations

import torch

__all__ = ["mrope_inv_freq", "mrope_axis_index", "mrope_cos_sin", "rotate_half", "apply_rope"]

HEAD_DIM = 128
ROPE_THETA = 5_000_000.0
MROPE_SECTION = (24, 20, 20)


def mrope_inv_freq(head_dim: int = HEAD_DIM, theta: float = ROPE_THETA) -> torch.Tensor:
    """``[head_dim/2]`` fp32, identical to upstream ``_default_rope_init``."""
    exponent = torch.arange(0, head_dim, 2, dtype=torch.int64).to(torch.float32) / head_dim
    return 1.0 / (theta**exponent)


def mrope_axis_index(
    head_dim: int = HEAD_DIM, section: tuple[int, int, int] = MROPE_SECTION
) -> torch.Tensor:
    """``[head_dim/2]`` long: which position axis (0=T,1=H,2=W) feeds each frequency slot."""
    half = head_dim // 2
    assert sum(section) == half, f"mrope_section {section} must sum to head_dim/2={half}"
    axis = torch.zeros(half, dtype=torch.long)  # default T
    for ax, offset in ((1, 1), (2, 2)):
        length = section[ax] * 3
        axis[offset:length:3] = ax
    counts = [(axis == a).sum().item() for a in range(3)]
    assert tuple(counts) == tuple(section), f"interleave produced {counts}, expected {section}"
    return axis


def mrope_cos_sin(
    position_ids: torch.Tensor,
    head_dim: int = HEAD_DIM,
    theta: float = ROPE_THETA,
    section: tuple[int, int, int] = MROPE_SECTION,
) -> tuple[torch.Tensor, torch.Tensor]:
    """``position_ids`` ``[3, N]`` (float32 or long) → ``cos, sin`` each ``[N, head_dim]`` fp32.

    ``freqs[a, n, j] = pos[a, n] * inv_freq[j]``; slot ``j`` is taken from axis ``axis_index[j]``;
    ``emb = cat(freqs, freqs)`` (rotate-half layout); ``attention_scaling = 1``.
    """
    assert position_ids.ndim == 2 and position_ids.shape[0] == 3, position_ids.shape
    pos = position_ids.to(torch.float32)  # [3,N]
    inv_freq = mrope_inv_freq(head_dim, theta)  # [D/2]
    freqs = pos[:, :, None] * inv_freq[None, None, :]  # [3,N,D/2]  (== inv_freq @ pos, transposed)
    axis = mrope_axis_index(head_dim, section)  # [D/2]
    sel = torch.gather(freqs, 0, axis[None, None, :].expand(1, pos.shape[1], -1)).squeeze(
        0
    )  # [N,D/2]
    emb = torch.cat((sel, sel), dim=-1)  # [N,D]
    return emb.cos(), emb.sin()


def rotate_half(x: torch.Tensor) -> torch.Tensor:
    x1 = x[..., : x.shape[-1] // 2]
    x2 = x[..., x.shape[-1] // 2 :]
    return torch.cat((-x2, x1), dim=-1)


def apply_rope(x: torch.Tensor, cos: torch.Tensor, sin: torch.Tensor) -> torch.Tensor:
    """``x`` ``[N, H, D]``, ``cos/sin`` ``[N, D]`` (already in ``x.dtype``) → ``[N, H, D]``.

    Out-of-place; same dtype semantics as upstream's text-path ``apply_rotary_pos_emb``.
    """
    cos = cos.unsqueeze(1)  # [N,1,D]
    sin = sin.unsqueeze(1)
    return (x * cos) + (rotate_half(x) * sin)


if __name__ == "__main__":
    # Hardware-free smoke: interleave counts, shapes, and a rotation-invariance check.
    axis = mrope_axis_index()
    assert axis[:6].tolist() == [0, 1, 2, 0, 1, 2] and axis[60:].tolist() == [0, 0, 0, 0]
    pos = torch.stack(
        [torch.arange(10.0), torch.arange(10.0) * 2, torch.arange(10.0) * 3]
    )  # [3,10]
    cos, sin = mrope_cos_sin(pos)
    assert cos.shape == (10, HEAD_DIM) and sin.dtype == torch.float32
    assert torch.allclose(cos**2 + sin**2, torch.ones_like(cos), atol=1e-6)
    x = torch.randn(10, 4, HEAD_DIM)
    y = apply_rope(x, cos, sin)
    assert y.shape == x.shape and torch.allclose(y.norm(dim=-1), x.norm(dim=-1), atol=1e-4)
    # Position 0 on every axis is the identity rotation.
    cos0, sin0 = mrope_cos_sin(torch.zeros(3, 1))
    assert torch.allclose(apply_rope(x[:1], cos0, sin0), x[:1])
    print("rope smoke OK")
