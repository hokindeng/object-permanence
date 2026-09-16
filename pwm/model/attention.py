"""Two-way attention for the MoT block: explicit-fp32 path and NKI flash path, with GQA.

Within one sample the sequence is ``[text (Lt) | vision (Nv)]``, ``N = Lt + Nv`` (upstream Cosmos3
``two_way_attention`` semantics): text queries attend causally over text keys only (``[0, i+1)``);
vision queries attend over all ``N`` keys. Softmax scale ``1/sqrt(head_dim)``; GQA 32 q-heads over
8 kv-heads in ``repeat_interleave`` order (q head ``j`` ↔ kv head ``j // 4``).

Both rows are contiguous KV ranges, so the NKI path is one nkilib ``attention_cte`` call with
per-query ``bound_min/bound_max`` and no ``(N, N)`` mask. The explicit path (backend name ``sdpa``,
kept for config compatibility) is two mask-free fp32 attentions (causal ``Lt×Lt``, full ``Nv×N``):
an additive/boolean mask is never built because masked-SDPA backward is imprecise on Neuron.
Inference padding: a prompt shorter than the trained ``text_len`` is padded to it and ``key_bias`` (``[N]``
fp32, ``-inf`` on the pad keys) hides those keys from the vision rows — forward only, so the mask has no
backward to be imprecise; real text rows never reach the pads (causal). The NKI path takes contiguous bounds
and cannot express it: it raises. Layout: token-major ``[N, H, D]`` per sample; backends transpose to
``(1, H, N, D)`` internally.
NKI constraints: K seqlen padded to a multiple of 512, Q tiled in groups of 128, backward capped at
seqlen 8,192 on the current nkilib.
"""

from __future__ import annotations

import math
from enum import Enum

import torch
import torch.nn.functional as F

__all__ = [
    "AttentionKind",
    "causal_text_attention",
    "full_attention_explicit",
    "expand_kv",
    "two_way_bounds",
    "sdpa_two_way",
    "nki_two_way",
    "two_way_attention",
    "pad_key_bias",
]


class AttentionKind(str, Enum):
    SDPA = "sdpa"
    NKI_FLASH = "nki_flash"


# ------------------------------------------------------------------------------------ helpers
def expand_kv(x: torch.Tensor, groups: int) -> torch.Tensor:
    """``[N, Hkv, D]`` → ``[N, Hkv*groups, D]`` in ``repeat_interleave`` order (q head j ↔ kv head j//groups).

    ``expand`` + ``reshape`` (one copy, no index ops) — the same result as upstream ``repeat_kv``.
    """
    if groups == 1:
        return x
    n, hkv, d = x.shape
    return x[:, :, None, :].expand(n, hkv, groups, d).reshape(n, hkv * groups, d)


def two_way_bounds(text_len: int, total_len: int, device=None) -> tuple[torch.Tensor, torch.Tensor]:
    """Per-query contiguous KV range: text row i → ``[0, i+1)``; vision row → ``[0, N)``. Shapes ``[N]`` long."""
    bmin = torch.zeros(total_len, dtype=torch.long, device=device)
    bmax = torch.full((total_len,), total_len, dtype=torch.long, device=device)
    bmax[:text_len] = torch.arange(1, text_len + 1, device=device)
    return bmin, bmax


def _to_bhtd(x: torch.Tensor) -> torch.Tensor:  # [N,H,D] -> (1,H,N,D)
    return x.transpose(0, 1).unsqueeze(0)


def _from_bhtd(x: torch.Tensor) -> torch.Tensor:  # (1,H,N,D) -> [N,H,D]
    return x.squeeze(0).transpose(0, 1)


# ----------------------------------------------------------------------------------- explicit
def full_attention_explicit(
    qv: torch.Tensor, ka: torch.Tensor, va: torch.Tensor, key_bias: torch.Tensor | None = None
) -> torch.Tensor:
    """Mask-free attention of ``qv`` ``[Nv, H, D]`` over all keys ``ka/va`` ``[N, H, D]``, fp32 scores/softmax.
    ``key_bias`` ``[N]`` fp32 (0 / -inf) is added to every row's scores — inference-only padding, see module doc.

    Explicit scores/softmax rather than ``F.scaled_dot_product_attention``: the compiled SDPA backward on
    Neuron loses precision on the small q_norm/k_norm gain gradients. O(Nv·N) fp32 memory per head,
    transient under activation checkpointing; fine up to ~8k tokens, beyond that use the NKI path
    (``AttentionKind.NKI_FLASH``).
    """
    dt = qv.dtype
    d = qv.shape[-1]
    q = qv.transpose(0, 1).to(torch.float32)  # [H,Nv,D]
    k = ka.transpose(0, 1).to(torch.float32)  # [H,N,D]
    v = va.transpose(0, 1).to(torch.float32)
    scores = torch.matmul(q, k.transpose(-1, -2)) * (1.0 / math.sqrt(d))
    if key_bias is not None:
        scores = scores + key_bias.to(torch.float32)[None, None, :]
    probs = torch.softmax(scores, dim=-1)
    return torch.matmul(probs, v).transpose(0, 1).to(dt)


def causal_text_attention(qt: torch.Tensor, kt: torch.Tensor, vt: torch.Tensor) -> torch.Tensor:
    """Causal attention over the (short) text block, written out explicitly in fp32.

    ``qt, kt, vt`` ``[Lt, H, D]`` → ``[Lt, H, D]`` in the input dtype. Equivalent to
    ``F.scaled_dot_product_attention(..., is_causal=True)``; used instead because a causal mask lowered
    inside a compiled Neuron graph gives an imprecise backward. ``Lt ≤ 128`` so the ``[H, Lt, Lt]`` fp32
    scores cost nothing.
    """
    dt = qt.dtype
    lt, h, d = qt.shape
    q = qt.transpose(0, 1).to(torch.float32)  # [H,Lt,D]
    k = kt.transpose(0, 1).to(torch.float32)
    v = vt.transpose(0, 1).to(torch.float32)
    scores = torch.matmul(q, k.transpose(-1, -2)) * (1.0 / math.sqrt(d))  # [H,Lt,Lt]
    future = torch.triu(torch.ones(lt, lt, dtype=torch.bool, device=qt.device), diagonal=1)
    scores = torch.where(future, torch.full_like(scores, float("-inf")), scores)
    probs = torch.softmax(scores, dim=-1)
    return torch.matmul(probs, v).transpose(0, 1).to(dt)  # [Lt,H,D]


def sdpa_two_way(
    q: torch.Tensor, k: torch.Tensor, v: torch.Tensor, text_len: int, key_bias: torch.Tensor | None = None
) -> torch.Tensor:
    """Text rows: explicit fp32 causal attention. Vision rows: explicit fp32 attention over all keys (minus the
    ``key_bias`` pads). ``q, k, v`` ``[N, H, D]`` (k/v already GQA-expanded). Returns ``[N, H, D]``."""
    out_text = causal_text_attention(q[:text_len], k[:text_len], v[:text_len])
    out_vis = full_attention_explicit(q[text_len:], k, v, key_bias)
    return torch.cat([out_text, out_vis], dim=0)


# ---------------------------------------------------------------------------------- NKI flash
_nki_kernel = None
_nki_bwd_kernel = None


def _load_nki_kernel():
    global _nki_kernel
    if _nki_kernel is None:
        from nkilib.core.attention.attention_cte import attention_cte  # noqa: PLC0415

        _nki_kernel = attention_cte
    return _nki_kernel


def _load_nki_bwd_kernel():
    global _nki_bwd_kernel
    if _nki_bwd_kernel is None:
        from nkilib.core.attention.attention_bwd import attention_bwd  # noqa: PLC0415

        _nki_bwd_kernel = attention_bwd
    return _nki_bwd_kernel


_NKI_Q_GRP_SZ = 128  # kernel tiles Q in groups of this size
_NKI_SEQ_PAD = 512  # nkilib requires key seq_len % 512 == 0


def _nki_prepare(q, k, v, bmin, bmax, pad_bmax_value):
    """Shared ``attention_cte`` input prep: pre-scale q by ``1/sqrt(dh)`` (kernel runs ``scale=1.0``),
    pad T to a 512-multiple, fold ``(B, H, tp, dh)`` → ``(B*H, tp, dh)``, expand bounds to
    ``(B*H, tp, 1)`` int32. Padded query rows are bounded ``[0, pad_bmax_value)``.

    Returns ``(qf, kf, vf, bmin_f, bmax_f, tp, need)``.
    """
    b, h, t, dh = q.shape
    need = (_NKI_SEQ_PAD - t % _NKI_SEQ_PAD) % _NKI_SEQ_PAD
    tp = t + need
    q = q * (1.0 / math.sqrt(dh))
    if need:
        q, k, v = (F.pad(x, (0, 0, 0, need)) for x in (q, k, v))
        bmin = F.pad(bmin, (0, need), value=0)
        bmax = F.pad(bmax, (0, need), value=pad_bmax_value)

    def fold(x):  # (B,H,tp,dh) -> (B*H, tp, dh)
        return x.reshape(b * h, tp, dh).contiguous()

    def exp(bt):  # (B,tp) -> (B*H, tp, 1) int32
        return bt.to(torch.int32).unsqueeze(1).expand(b, h, tp).reshape(b * h, tp, 1).contiguous()

    return fold(q), fold(k), fold(v), exp(bmin), exp(bmax), tp, need


def nki_flash_attention(q, k, v, bounds):
    """nkilib ``attention_cte`` on ``(B, H, T, dh)`` with per-query ``bounds = (bmin, bmax)`` ``(B, T)``.

    Routes through :class:`_NkiFlashAttnFn` whenever a gradient is required. Forward-only path:
    q pre-scaled, ``scale=1.0`` (kernel contract for bounds), seqlen padded to a 512-multiple with
    padded rows bounded ``[0, 0)``.
    """
    if torch.is_grad_enabled() and (q.requires_grad or k.requires_grad or v.requires_grad):
        return _NkiFlashAttnFn.apply(q, k, v, bounds[0], bounds[1])
    b, h, t, dh = q.shape
    kernel = _load_nki_kernel()
    qf, kf, vf, bmin_f, bmax_f, tp, need = _nki_prepare(q, k, v, bounds[0], bounds[1], 0)
    of = kernel(
        qf,
        kf,
        vf,
        causal_mask=False,
        tp_q=True,
        tp_k=True,
        tp_out=False,
        scale=1.0,
        bound_min=bmin_f,
        bound_max=bmax_f,
    )
    if isinstance(of, dict):
        of = of["out"]
    of = of.reshape(b, h, tp, dh)
    if need:
        of = of[:, :, :t, :]
    return of.to(v.dtype)


class _NkiFlashAttnFn(torch.autograd.Function):
    """Differentiable NKI attention: ``attention_cte(cache_softmax=True)`` forward + ``attention_bwd``.

    Forward layout folded-3D ``(B*H, T, dh)``; backward explicit-4D ``(B, H, dh, T)``; lse
    ``(B, H, 128, T/128)``. Padded query rows carry ``dy = 0`` so they add nothing to dK/dV; real rows
    never attend padded KV because their bounds end at ``t``.
    """

    @staticmethod
    def forward(ctx, q, k, v, bmin, bmax):
        b, h, t, dh = q.shape
        scale = 1.0 / math.sqrt(dh)
        kernel = _load_nki_kernel()
        qf, kf, vf, bmin_f, bmax_f, tp, need = _nki_prepare(q, k, v, bmin, bmax, float(t))
        ret = kernel(
            qf,
            kf,
            vf,
            causal_mask=False,
            tp_q=True,
            tp_k=True,
            tp_out=False,
            cache_softmax=True,
            scale=1.0,
            bound_min=bmin_f,
            bound_max=bmax_f,
        )
        if isinstance(ret, dict):  # torch ref returns a dict
            out, neg_max, recip = (
                ret["out"],
                ret["out_cached_negative_max"],
                ret["out_cached_sum_reciprocal"],
            )
        else:
            out, neg_max, recip = ret
        out = out.reshape(b, h, tp, dh)
        out = out[:, :, :t, :] if need else out
        ctx.save_for_backward(q, k, v, out, neg_max, recip, bmin, bmax)
        ctx.scale = scale
        ctx.dims = (b, h, t, dh, tp, need)
        return out.to(v.dtype)

    @staticmethod
    def backward(ctx, dout):
        bwd_kernel = _load_nki_bwd_kernel()
        q, k, v, out, neg_max, recip, bmin, bmax = ctx.saved_tensors
        b, h, t, dh, tp, need = ctx.dims
        lse = (
            (-neg_max - torch.log(recip))
            .reshape(b, h, _NKI_Q_GRP_SZ, tp // _NKI_Q_GRP_SZ)
            .contiguous()
        )

        def tp_pad(x):  # (B,H,T,dh) -> (B,H,dh,tp)
            if need:
                x = F.pad(x, (0, 0, 0, need))
            return x.transpose(-1, -2).contiguous()

        qb, kb, vb, ob, dyb = tp_pad(q), tp_pad(k), tp_pad(v), tp_pad(out), tp_pad(dout)
        bmin_p = F.pad(bmin, (0, need), value=0.0) if need else bmin
        bmax_p = (
            F.pad(bmax, (0, need), value=float(tp)) if need else bmax
        )  # padded rows: finite, dy=0
        res = bwd_kernel(
            qb,
            kb,
            vb,
            ob,
            dyb,
            lse,
            use_causal_mask=False,
            softmax_scale=ctx.scale,
            bound_min=bmin_p.to(torch.float32).contiguous(),
            bound_max=bmax_p.to(torch.float32).contiguous(),
        )
        if isinstance(res, dict):
            dQ, dK, dV = res["out_dq_ref"], res["out_dk_ref"], res["out_dv_ref"]
        else:
            dQ, dK, dV = res[0], res[1], res[2]

        def unpad(g):  # (B,H,dh,tp) -> (B,H,T,dh)
            g = g.reshape(b, h, dh, tp).transpose(-1, -2)
            return (g[:, :, :t, :] if need else g).contiguous().to(q.dtype)

        return unpad(dQ), unpad(dK), unpad(dV), None, None


def nki_two_way(q: torch.Tensor, k: torch.Tensor, v: torch.Tensor, text_len: int) -> torch.Tensor:
    """One ``attention_cte`` call with two-way bounds. ``q, k, v`` ``[N, H, D]`` (k/v GQA-expanded)."""
    n = q.shape[0]
    bmin, bmax = two_way_bounds(text_len, n, device=q.device)
    out = nki_flash_attention(_to_bhtd(q), _to_bhtd(k), _to_bhtd(v), (bmin[None], bmax[None]))
    return _from_bhtd(out)


# ------------------------------------------------------------------------------------ dispatch
def two_way_attention(
    kind: AttentionKind | str,
    q: torch.Tensor,
    k: torch.Tensor,
    v: torch.Tensor,
    text_len: int,
    key_bias: torch.Tensor | None = None,
) -> torch.Tensor:
    kind = AttentionKind(kind)
    if kind is AttentionKind.SDPA:
        return sdpa_two_way(q, k, v, text_len, key_bias)
    if key_bias is not None:
        raise ValueError("nki_flash attention takes contiguous bounds and cannot hide padded text keys; "
                         "infer with a padded prompt needs model.attention_backend: sdpa")
    return nki_two_way(q, k, v, text_len)


def pad_key_bias(text_len: int, text_valid: int, total_len: int, device=None) -> torch.Tensor:
    """``[N]`` fp32: ``-inf`` on text keys ``[text_valid, text_len)`` (padding), 0 elsewhere."""
    if not 0 < text_valid <= text_len:
        raise ValueError(f"text_valid={text_valid} must be in (0, text_len={text_len}]")
    bias = torch.zeros(total_len, dtype=torch.float32, device=device)
    bias[text_valid:text_len] = float("-inf")
    return bias


if __name__ == "__main__":
    # Hardware-free smoke: dense-mask bounds reference == two-call explicit path; GQA expansion order.
    def dense_mask_from_bounds(
        bounds: tuple[torch.Tensor, torch.Tensor], seq_len_k: int
    ) -> torch.Tensor:
        """``(bmin, bmax)`` ``[N]`` → bool ``[N, Tk]`` (True = attend)."""
        bmin, bmax = bounds
        j = torch.arange(seq_len_k, device=bmin.device)
        return (j[None, :] >= bmin[:, None]) & (j[None, :] < bmax[:, None])

    def sdpa_bounds(
        q: torch.Tensor, k: torch.Tensor, v: torch.Tensor, bounds: tuple[torch.Tensor, torch.Tensor]
    ) -> torch.Tensor:
        """Dense-mask rendering of the bounds semantics (reference only)."""
        mask = dense_mask_from_bounds(bounds, k.shape[0])[None, None]  # (1,1,N,Tk)
        return _from_bhtd(
            F.scaled_dot_product_attention(_to_bhtd(q), _to_bhtd(k), _to_bhtd(v), attn_mask=mask)
        )

    torch.manual_seed(0)
    Lt, Nv, H, Hkv, D = 5, 12, 8, 2, 16
    N = Lt + Nv
    q = torch.randn(N, H, D)
    k = expand_kv(torch.randn(N, Hkv, D), H // Hkv)
    v = expand_kv(torch.randn(N, Hkv, D), H // Hkv)
    assert torch.equal(k[:, 0], k[:, 3]) and not torch.equal(
        k[:, 0], k[:, 4]
    )  # repeat_interleave order
    a = sdpa_two_way(q, k, v, Lt)
    b = sdpa_bounds(q, k, v, two_way_bounds(Lt, N))
    assert a.shape == (N, H, D) and torch.allclose(a, b, atol=1e-6), (a - b).abs().max()
    # Text rows must not see vision keys: perturbing vision K/V leaves text outputs unchanged.
    k2, v2 = k.clone(), v.clone()
    k2[Lt:] += 1.0
    v2[Lt:] += 1.0
    a2 = sdpa_two_way(q, k2, v2, Lt)
    assert torch.allclose(a[:Lt], a2[:Lt]) and not torch.allclose(a[Lt:], a2[Lt:])
    # Padded text: with key_bias the vision rows equal attention over [real text | vision] keys only, and
    # perturbing the pad K/V changes nothing; without the bias it does.
    n_valid = 3
    bias = pad_key_bias(Lt, n_valid, N)
    keep = torch.cat([torch.arange(n_valid), torch.arange(Lt, N)])
    ref = full_attention_explicit(q[Lt:], k[keep], v[keep])
    got = sdpa_two_way(q, k, v, Lt, bias)[Lt:]
    assert torch.allclose(got, ref, atol=1e-6), (got - ref).abs().max()
    k3, v3 = k.clone(), v.clone()
    k3[n_valid:Lt] += 5.0
    v3[n_valid:Lt] += 5.0
    assert torch.equal(sdpa_two_way(q, k3, v3, Lt, bias)[Lt:], got)
    assert not torch.allclose(sdpa_two_way(q, k3, v3, Lt)[Lt:], sdpa_two_way(q, k, v, Lt)[Lt:])
    assert torch.equal(sdpa_two_way(q, k, v, Lt, torch.zeros(N)), sdpa_two_way(q, k, v, Lt))  # zero bias = no-op
    try:
        two_way_attention("nki_flash", q, k, v, Lt, bias)
        raise AssertionError("nki_flash + key_bias must raise")
    except ValueError:
        pass
    print("attention smoke OK")
