"""NanoMoT — the Cosmos3-Nano 16B video network as one flat ``nn.Module``.

    text_ids  ─ embed ──────────────────────────────┐
    patches   ─ vae2llm ─ + time_embedder(t) · noisy_mask ┴─ cat ─ 36 × MoTBlock ─ norm_gen(vision) ─ llm2vae

Inputs are plain tensors with static shapes (one sample): ``text_ids [Lt]``, ``patches [Nv, 192]``,
``t_freq [1, 256]`` (sinusoid of sigma, built on CPU by ``diffusion.timestep_sinusoid``),
``noisy_mask [Nv, 1]`` (1 on generated-frame tokens, 0 on clean-prefix tokens — only noisy tokens receive
the timestep embedding, as upstream), ``cos/sin [N, hd]`` (mRoPE, built on CPU). Output: velocity for
every vision token ``[Nv, 192]``; the caller (``patchify.unpatchify`` + zero-fill of clean frames)
reproduces upstream's zero canvas.

Dropped relative to upstream: ``lm_head`` and the und final ``norm`` (text-token prediction only),
action/audio heads. Kept fp32 island: the timestep MLP (upstream runs it under an fp32 autocast,
which is a no-op off CUDA, so the cast is explicit here). TP hooks: ``Tower.heads/kv_heads`` are plain
attributes the TP plan divides per rank; the vocab embedding is replicated across TP.
"""

from __future__ import annotations

import torch
from torch import nn
from torch.utils.checkpoint import checkpoint

from pwm.configs.config import ModelConfig
from pwm.model.block import MoTBlock, RMSNorm
from pwm.model.attention import pad_key_bias
from pwm.model.diffusion import TIME_FREQ_DIM
from pwm.model.patchify import LATENT_CHANNELS, PATCH_DIM

__all__ = ["NanoMoT"]

_DTYPES = {"float32": torch.float32, "bfloat16": torch.bfloat16}


class NanoMoT(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.cfg = cfg
        d = cfg.dim
        self.embed = nn.Embedding(cfg.vocab_size, d)
        self.vae2llm = nn.Linear(PATCH_DIM, d, bias=True)
        self.time_embedder = nn.Sequential(
            nn.Linear(TIME_FREQ_DIM, d, bias=True), nn.SiLU(), nn.Linear(d, d, bias=True)
        )
        self.blocks = nn.ModuleList([MoTBlock(cfg) for _ in range(cfg.layers)])
        self.norm_gen = RMSNorm(d, cfg.rms_eps)
        self.llm2vae = nn.Linear(d, PATCH_DIM, bias=True)
        self.gradient_checkpointing = cfg.gradient_checkpointing
        self.rope_fp32 = cfg.rope_dtype == "float32"

    # ------------------------------------------------------------------ dtype handling
    def to_dtype(self, dtype: torch.dtype | str) -> NanoMoT:
        """Cast the whole model to ``dtype`` **except** the fp32 timestep MLP."""
        dtype = _DTYPES[dtype] if isinstance(dtype, str) else dtype
        self.to(dtype)
        self.time_embedder.to(torch.float32)
        return self

    @property
    def activation_dtype(self) -> torch.dtype:
        return self.embed.weight.dtype

    # ------------------------------------------------------------------------- forward
    def forward(
        self,
        text_ids: torch.Tensor,
        patches: torch.Tensor,
        t_freq: torch.Tensor,
        noisy_mask: torch.Tensor,
        cos: torch.Tensor,
        sin: torch.Tensor,
        text_valid: int | None = None,
    ) -> torch.Tensor:
        """``text_valid`` (inference): only the first ``text_valid`` text ids are real, the rest is padding to the
        trained ``text_len``; the pads keep their positions but no vision row attends to them."""
        text_len = text_ids.shape[0]
        dt = self.activation_dtype
        key_bias = None
        if text_valid is not None and text_valid < text_len:
            key_bias = pad_key_bias(text_len, text_valid, text_len + patches.shape[0], device=text_ids.device)
        ht = self.embed(text_ids)  # [Lt,D]
        hv = self.vae2llm(patches.to(dt))  # [Nv,D]
        t_emb = self.time_embedder(t_freq.to(torch.float32)).to(dt)  # [1,D] fp32 island
        hv = hv + t_emb * noisy_mask.to(dt)
        h = torch.cat([ht, hv], dim=0)  # [N,D]
        if not self.rope_fp32:
            cos, sin = cos.to(dt), sin.to(dt)
        for blk in self.blocks:
            if self.gradient_checkpointing and self.training and torch.is_grad_enabled():
                h = checkpoint(blk, h, text_len, cos, sin, key_bias, use_reentrant=False)
            else:
                h = blk(h, text_len, cos, sin, key_bias)
        return self.llm2vae(self.norm_gen(h[text_len:]))  # [Nv,192]


if __name__ == "__main__":
    from pwm.model.diffusion import timestep_sinusoid
    from pwm.model.patchify import noisy_token_mask, patchify
    from pwm.model.rope import mrope_cos_sin

    cfg = ModelConfig(
        layers=2,
        dim=64,
        heads=4,
        kv_heads=2,
        head_dim=16,
        ffn_dim=96,
        vocab_size=64,
        mrope_section=(4, 2, 2),
        gradient_checkpointing=True,
    )
    m = NanoMoT(cfg)
    assert len(m.state_dict()) == 10 + 22 * 2, len(m.state_dict())
    latent = torch.randn(1, LATENT_CHANNELS, 2, 4, 6)  # T=2, h=2, w=3 -> Nv=12
    patches = patchify(latent)
    Lt, Nv = 5, patches.shape[0]
    N = Lt + Nv
    pos = torch.stack([torch.arange(N, dtype=torch.float32)] * 3)
    cos, sin = mrope_cos_sin(pos, head_dim=16, theta=cfg.rope_theta, section=cfg.mrope_section)
    mask = noisy_token_mask((2, 2, 3), torch.tensor([0.0, 1.0]))
    t_freq = timestep_sinusoid(torch.tensor([0.5]))
    ids = torch.randint(0, 64, (Lt,))
    out = m(ids, patches, t_freq, mask, cos, sin)
    assert out.shape == (Nv, PATCH_DIM) and torch.isfinite(out).all()
    # Gradient checkpointing path == plain path, and every parameter gets a gradient.
    m.train()
    out.sum().backward()
    missing = [n for n, p in m.named_parameters() if p.grad is None]
    assert not missing, missing
    m.eval()
    out_eval = m(ids, patches, t_freq, mask, cos, sin)
    assert torch.allclose(out, out_eval, atol=1e-6)
    # bf16 cast keeps the timestep MLP in fp32.
    m.to_dtype("bfloat16")
    assert (
        m.embed.weight.dtype == torch.bfloat16 and m.time_embedder[0].weight.dtype == torch.float32
    )
    out_bf16 = m(ids, patches, t_freq, mask, cos, sin)
    assert out_bf16.dtype == torch.bfloat16 and torch.isfinite(out_bf16).all()
    # Padded prompt: the output does not depend on the pad ids when text_valid hides them, and does without.
    ids2 = ids.clone()
    ids2[3:] = (ids2[3:] + 7) % 64
    o1, o2 = m(ids, patches, t_freq, mask, cos, sin, text_valid=3), m(ids2, patches, t_freq, mask, cos, sin, text_valid=3)
    assert torch.equal(o1, o2), "pad ids leaked into the vision output"
    assert not torch.equal(m(ids, patches, t_freq, mask, cos, sin), m(ids2, patches, t_freq, mask, cos, sin))
    assert torch.equal(m(ids, patches, t_freq, mask, cos, sin, text_valid=Lt), m(ids, patches, t_freq, mask, cos, sin))
    print(f"mot smoke OK ({sum(p.numel() for p in m.parameters())} params)")
