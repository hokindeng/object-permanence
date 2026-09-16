"""One Mixture-of-Transformers decoder layer, flat and static-shape (Cosmos3-Nano ``two_way`` joint
attention; no memory/CP/NATTEN/MoE).

    text rows  (und tower) ── norm1 ─ q/k/v ─ q_norm/k_norm ─ RoPE ─┐
                                                                     ├─ two-way attention ─ o ─ +res ─ norm2 ─ SwiGLU ─ +res
    vision rows (gen tower) ── norm1 ─ q/k/v ─ q_norm/k_norm ─ RoPE ─┘

Every weight exists twice: ``und`` (upstream ``*``) processes the text slice, ``gen`` (upstream
``*_moe_gen``) the vision slice. Text is a contiguous prefix of length ``Lt`` and vision a contiguous
suffix, so tower selection is static slicing ``h[:Lt]`` / ``h[Lt:]`` — no routing or index gathers.

Numerics match upstream: RMSNorm computes in fp32 and multiplies the gain in the activation dtype;
q/k norm is over ``head_dim`` before RoPE; RoPE runs in the activation dtype; SwiGLU is
``down(silu(gate(x)) * up(x))``.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn

from pwm.configs.config import ModelConfig
from pwm.model.attention import expand_kv, two_way_attention
from pwm.model.rope import apply_rope

__all__ = ["RMSNorm", "SwiGLU", "Tower", "MoTBlock", "COLWISE", "ROWWISE"]

# Per-tower linears by TP placement (``pwm.parallel.tp`` shards them, ``pwm.model.consolidate`` reassembles):
# Colwise = weight split on dim 0 (heads / ffn per rank), Rowwise = split on dim 1 (all-reduce after).
COLWISE = ("q", "k", "v", "mlp.gate", "mlp.up")
ROWWISE = ("o", "mlp.down")


class RMSNorm(nn.Module):
    """Upstream ``Qwen3VLTextRMSNorm``: fp32 variance, ``weight * x.to(input_dtype)``."""

    def __init__(self, dim: int, eps: float = 1e-6):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(dim))
        self.eps = eps

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        dt = x.dtype
        xf = x.to(torch.float32)
        xf = xf * torch.rsqrt(xf.pow(2).mean(-1, keepdim=True) + self.eps)
        # Forward is bit-identical to upstream's ``weight * x.to(dt)`` (x rounded to dt first, one more
        # rounding after the product). Doing the product in fp32 makes autograd accumulate the gain
        # gradient in fp32; the fused compiled backward on Neuron otherwise reduces it in bf16 and the
        # small q_norm/k_norm gain gradients lose precision against an fp32 reference.
        return (self.weight.to(torch.float32) * xf.to(dt).to(torch.float32)).to(dt)


class SwiGLU(nn.Module):
    """Upstream ``Qwen3VLTextMLP`` (bias-free gate/up/down, SiLU)."""

    def __init__(self, dim: int, ffn_dim: int):
        super().__init__()
        self.gate = nn.Linear(dim, ffn_dim, bias=False)
        self.up = nn.Linear(dim, ffn_dim, bias=False)
        self.down = nn.Linear(ffn_dim, dim, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.down(F.silu(self.gate(x)) * self.up(x))


class Tower(nn.Module):
    """The per-modality weight set of one layer (und = text, gen = vision)."""

    def __init__(self, cfg: ModelConfig):
        super().__init__()
        d, hd = cfg.dim, cfg.head_dim
        self.norm1 = RMSNorm(d, cfg.rms_eps)
        self.q = nn.Linear(d, cfg.heads * hd, bias=False)
        self.k = nn.Linear(d, cfg.kv_heads * hd, bias=False)
        self.v = nn.Linear(d, cfg.kv_heads * hd, bias=False)
        self.o = nn.Linear(cfg.heads * hd, d, bias=False)
        self.q_norm = RMSNorm(hd, cfg.rms_eps)
        self.k_norm = RMSNorm(hd, cfg.rms_eps)
        self.norm2 = RMSNorm(d, cfg.rms_eps)
        self.mlp = SwiGLU(d, cfg.ffn_dim)
        # Head counts are attributes (not config reads) so the TP plan can divide them per rank.
        self.heads, self.kv_heads, self.head_dim = cfg.heads, cfg.kv_heads, hd

    def qkv(
        self, x: torch.Tensor, cos: torch.Tensor, sin: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """``x`` ``[n, D]`` (already norm1'd) → q ``[n,H,hd]``, k/v ``[n,Hkv,hd]`` with q/k-norm + RoPE applied."""
        n = x.shape[0]
        q = self.q_norm(self.q(x).view(n, self.heads, self.head_dim))
        k = self.k_norm(self.k(x).view(n, self.kv_heads, self.head_dim))
        v = self.v(x).view(n, self.kv_heads, self.head_dim)
        return apply_rope(q, cos, sin), apply_rope(k, cos, sin), v


class MoTBlock(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.und = Tower(cfg)
        self.gen = Tower(cfg)
        self.backend = cfg.attention_backend

    def forward(
        self,
        h: torch.Tensor,
        text_len: int,
        cos: torch.Tensor,
        sin: torch.Tensor,
        key_bias: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """``h`` ``[N, D]`` = ``[text (Lt) | vision]``; ``cos/sin`` ``[N, hd]`` in ``h.dtype``; ``key_bias`` ``[N]`` hides
        padded text keys at inference (``attention.pad_key_bias``). Returns ``[N, D]``."""
        ht, hv = h[:text_len], h[text_len:]
        qt, kt, vt = self.und.qkv(self.und.norm1(ht), cos[:text_len], sin[:text_len])
        qv, kv, vv = self.gen.qkv(self.gen.norm1(hv), cos[text_len:], sin[text_len:])
        groups = self.und.heads // self.und.kv_heads
        q = torch.cat([qt, qv], dim=0)
        k = expand_kv(torch.cat([kt, kv], dim=0), groups)
        v = expand_kv(torch.cat([vt, vv], dim=0), groups)
        a = two_way_attention(self.backend, q, k, v, text_len, key_bias)  # [N,H,hd]
        a = a.reshape(a.shape[0], -1)
        ht = ht + self.und.o(a[:text_len])
        hv = hv + self.gen.o(a[text_len:])
        ht = ht + self.und.mlp(self.und.norm2(ht))
        hv = hv + self.gen.mlp(self.gen.norm2(hv))
        return torch.cat([ht, hv], dim=0)


if __name__ == "__main__":
    from pwm.model.rope import mrope_cos_sin

    cfg = ModelConfig(layers=1, dim=64, heads=4, kv_heads=2, head_dim=16, ffn_dim=96, vocab_size=64)
    blk = MoTBlock(cfg)
    Lt, Nv = 5, 12
    N = Lt + Nv
    pos = torch.stack([torch.arange(N, dtype=torch.float32)] * 3)
    cos, sin = mrope_cos_sin(pos, head_dim=16, theta=cfg.rope_theta, section=(4, 2, 2))
    h = torch.randn(N, 64)
    out = blk(h, Lt, cos, sin)
    assert out.shape == (N, 64) and torch.isfinite(out).all()
    # Text outputs are independent of vision content (causal text-only attention).
    h2 = h.clone()
    h2[Lt:] += 1.0
    out2 = blk(h2, Lt, cos, sin)
    assert torch.allclose(out[:Lt], out2[:Lt], atol=1e-5) and not torch.allclose(
        out[Lt:], out2[Lt:]
    )
    n_params = sum(p.numel() for p in blk.parameters())
    print(f"block smoke OK ({n_params} params, 22 tensors: {len(list(blk.parameters())) == 22})")
