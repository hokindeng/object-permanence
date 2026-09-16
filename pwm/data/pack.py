"""Static-shape ``NanoMoT`` inputs for one sample: ``[text (Lt) | vision (Nv)]``, ``N = Lt + Nv``.

Text ids = chat-templated caption (user role, generation prompt appended) + ``eos`` + ``<|vision_start|>``;
Qwen has no BOS. Positions ``[3, N]`` fp32: text ``t = h = w = arange(Lt)``; vision T-major ``(t, h, w)`` with
``t = frame / (fps/4) * (24/4) + Lt + temporal_margin`` (15000 for Nano), ``h``/``w`` reset per segment.
Noisy frames carry ``timestep = sigma * 1000`` (the net sees ``sigma`` through the 256-dim sinusoid); clean
conditioning frames carry none and stay out of the MSE. CPU fp32; cos/sin cached per geometry; the tokenizer
is loaded lazily — training never needs it because ``data/encode.py`` stores ``text_ids`` at a fixed length.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import torch

from pwm.model.diffusion import NUM_TRAIN_TIMESTEPS, add_noise, timestep_sinusoid, velocity_target
from pwm.model.patchify import grid_of, noisy_token_mask, patchify
from pwm.model.rope import HEAD_DIM, MROPE_SECTION, ROPE_THETA, mrope_cos_sin

__all__ = [
    "Packed",
    "text_positions",
    "vision_positions",
    "build_positions",
    "rope_table",
    "pack",
    "load_tokenizer",
    "caption_ids",
    "text_ids_for",
    "fit_text_ids",
    "pad_text_ids",
]

BASE_FPS = 24.0
TEMPORAL_COMPRESSION = 4
TEMPORAL_MARGIN = 15000
MIN_USER_TOKENS = 8  # fit_text_ids never trims a caption below this many raw tokens


@dataclass
class Packed:
    """One sample's network inputs (CPU, static shapes). ``target`` present for training packs."""

    text_ids: torch.Tensor  # [Lt] long
    patches: torch.Tensor  # [Nv, 192] fp32 (x_t patchified)
    t_freq: torch.Tensor  # [1, 256] fp32
    noisy_mask: torch.Tensor  # [Nv, 1] fp32
    cos: torch.Tensor  # [N, hd] fp32
    sin: torch.Tensor  # [N, hd] fp32
    position_ids: torch.Tensor  # [3, N] fp32
    grid: tuple[int, int, int]
    noisy_frame_mask: torch.Tensor  # [T] fp32
    x_t: torch.Tensor  # [1,C,T,H,W]
    target: torch.Tensor | None = None  # [1,C,T,H,W] velocity target (eps - x0)
    text_valid: int | None = None  # inference: real text ids before the padding (``pad_text_ids``)

    @property
    def text_len(self) -> int:
        return int(self.text_ids.shape[0])

    @property
    def total_len(self) -> int:
        return int(self.cos.shape[0])

    def model_inputs(self, device=None) -> tuple[torch.Tensor, ...]:
        ts = (self.text_ids, self.patches, self.t_freq, self.noisy_mask, self.cos, self.sin)
        return tuple(t.to(device) for t in ts) if device is not None else ts


# ------------------------------------------------------------------------------------ positions
def text_positions(text_len: int) -> torch.Tensor:
    ids = torch.arange(text_len, dtype=torch.float32)
    return ids.unsqueeze(0).expand(3, -1).contiguous()


def vision_positions(
    grid: tuple[int, int, int], offset: float, fps: float = BASE_FPS
) -> torch.Tensor:
    T, h, w = grid
    tps = fps / TEMPORAL_COMPRESSION
    base_tps = BASE_FPS / TEMPORAL_COMPRESSION
    scaled_t = torch.arange(T, dtype=torch.float32) / tps * base_tps + offset  # [T]
    t_index = scaled_t.view(-1, 1).expand(-1, h * w).flatten()
    h_index = torch.arange(h, dtype=torch.float32).view(1, -1, 1).expand(T, -1, w).flatten()
    w_index = torch.arange(w, dtype=torch.float32).view(1, 1, -1).expand(T, h, -1).flatten()
    return torch.stack([t_index, h_index, w_index], dim=0)


def build_positions(
    text_len: int,
    grid: tuple[int, int, int],
    fps: float = BASE_FPS,
    temporal_margin: int = TEMPORAL_MARGIN,
) -> torch.Tensor:
    """``[3, Lt + T*h*w]`` fp32 — text first, then vision after the temporal margin."""
    text = text_positions(text_len)
    offset = float(text_len) + float(temporal_margin)
    return torch.cat([text, vision_positions(grid, offset, fps)], dim=1)


@lru_cache(maxsize=8)
def rope_table(
    text_len: int,
    grid: tuple[int, int, int],
    fps: float,
    temporal_margin: int,
    head_dim: int,
    theta: float,
    section: tuple[int, int, int],
):
    pos = build_positions(text_len, grid, fps, temporal_margin)
    cos, sin = mrope_cos_sin(pos, head_dim=head_dim, theta=theta, section=section)
    return pos, cos, sin


# ----------------------------------------------------------------------------------------- pack
def pack(
    text_ids: torch.Tensor,
    latent: torch.Tensor,
    sigma: float,
    *,
    cond_frames: int = 0,
    eps: torch.Tensor | None = None,
    is_x0: bool = False,
    fps: float = BASE_FPS,
    temporal_margin: int = TEMPORAL_MARGIN,
    head_dim: int = HEAD_DIM,
    rope_theta: float = ROPE_THETA,
    mrope_section: tuple[int, int, int] = MROPE_SECTION,
    text_valid: int | None = None,
) -> Packed:
    """Pack one sample.

    ``latent`` ``[1,C,T,H,W]`` is ``x_t`` (inference) or, with ``is_x0=True`` and ``eps`` given, the clean
    ``x0`` — then ``x_t = eps*sigma + x0*(1-sigma)`` on the noisy frames and ``target = eps - x0`` are
    built here (training). ``cond_frames`` = number of clean leading frames (v2v prefix).
    """
    text_ids = text_ids.to(torch.long).reshape(-1)
    if text_valid is not None and not 0 < text_valid <= text_ids.shape[0]:
        raise ValueError(f"text_valid={text_valid} must be in (0, {text_ids.shape[0]}]")
    grid = grid_of(latent.shape)
    T = grid[0]
    assert 0 <= cond_frames < T, f"cond_frames={cond_frames} must leave >= 1 noisy frame of T={T}"
    noisy_frame_mask = torch.ones(T, dtype=torch.float32)
    noisy_frame_mask[:cond_frames] = 0.0
    latent = latent.to(torch.float32)
    target = None
    if is_x0:
        assert eps is not None, "training pack needs eps"
        x0 = latent
        x_t = add_noise(x0, eps.to(torch.float32), sigma, noisy_frame_mask)
        target = velocity_target(x0, eps.to(torch.float32))
    else:
        x_t = latent
    pos, cos, sin = rope_table(
        int(text_ids.shape[0]),
        grid,
        float(fps),
        int(temporal_margin),
        head_dim,
        rope_theta,
        tuple(mrope_section),
    )
    timestep = float(sigma) * NUM_TRAIN_TIMESTEPS
    t_freq = timestep_sinusoid(torch.tensor([timestep / NUM_TRAIN_TIMESTEPS], dtype=torch.float32))
    return Packed(
        text_ids=text_ids,
        patches=patchify(x_t),
        t_freq=t_freq,
        noisy_mask=noisy_token_mask(grid, noisy_frame_mask),
        cos=cos,
        sin=sin,
        position_ids=pos,
        grid=grid,
        noisy_frame_mask=noisy_frame_mask,
        x_t=x_t,
        target=target,
        text_valid=text_valid,
    )


# ------------------------------------------------------------------------------------ tokenizer
def load_tokenizer(tokenizer_dir: str):
    """Qwen3-VL tokenizer from ``<ckpt>/text_tokenizer`` with the two vision markers registered."""
    from transformers import AutoTokenizer  # noqa: PLC0415

    tok = AutoTokenizer.from_pretrained(tokenizer_dir)
    existing = {v for v in tok.special_tokens_map.values() if isinstance(v, str)}
    for vals in tok.special_tokens_map.values():
        if isinstance(vals, list):
            existing.update(vals)
    missing = [
        t
        for t in ("<|vision_start|>", "<|vision_end|>")
        if t not in existing and tok.convert_tokens_to_ids(t) == tok.unk_token_id
    ]
    if missing:
        tok.add_tokens(missing)
    return tok


def caption_ids(tok, caption: str) -> list[int]:
    """Upstream ``tokenize_caption``: chat template, user role (no system prompt), generation prompt appended."""
    conv = [{"role": "user", "content": caption}]
    out = tok.apply_chat_template(
        conv, tokenize=True, add_generation_prompt=True, add_vision_id=False, return_dict=False
    )
    return list(out)


def text_ids_for(tok, caption: str) -> torch.Tensor:
    """Full text slice: caption ids + ``eos`` + ``<|vision_start|>`` (``pack_text_tokens`` with generation)."""
    ids = caption_ids(tok, caption) + [
        tok.eos_token_id,
        tok.convert_tokens_to_ids("<|vision_start|>"),
    ]
    return torch.tensor(ids, dtype=torch.long)


def fit_text_ids(tok, caption: str, text_len: int) -> torch.Tensor:
    """Trim the caption so the full text slice has exactly ``text_len`` tokens (static shape).

    Cut the raw caption to ``n`` tokens, re-template, nudge ``n`` until the templated length hits the target.
    Raises if the caption is too short to reach ``text_len`` (``text_ids_and_valid`` pads that case instead).
    """
    raw = tok(caption, add_special_tokens=False)["input_ids"]
    n = min(len(raw), max(text_len, 1))
    seen: set[int] = set()
    while n >= MIN_USER_TOKENS and n not in seen:
        seen.add(n)
        ids = text_ids_for(tok, tok.decode(raw[:n]))
        if ids.shape[0] == text_len:
            return ids
        n += 1 if ids.shape[0] < text_len else -1
        if n > len(raw):
            break
    raise ValueError(f"cannot fit caption ({len(raw)} raw tokens) to templated length {text_len}")


def text_ids_and_valid(tok, caption: str, text_len: int) -> tuple[torch.Tensor, int]:
    """Training: the caption's text slice at exactly ``text_len``. A caption that templates to ``text_len`` or
    fewer tokens is right-padded (``pad_text_ids``; the pads are hidden from the vision rows via ``text_valid``,
    as at inference); a longer one is trimmed (``fit_text_ids``). Returns ``(ids, text_valid)``."""
    ids = text_ids_for(tok, caption)
    if ids.shape[0] <= text_len:
        if tok.pad_token_id is None:
            raise ValueError("tokenizer has no pad token; cannot pad captions to text_len")
        return pad_text_ids(ids, text_len, tok.pad_token_id)
    return fit_text_ids(tok, caption, text_len), text_len


def pad_text_ids(ids: torch.Tensor, text_len: int, pad_id: int) -> tuple[torch.Tensor, int]:
    """Inference: right-pad ``ids`` to the trained ``text_len`` with ``pad_id``. Returns ``(padded, n_real)``;
    the model gets ``text_valid=n_real`` so the pads keep their positions but are hidden from every vision
    row. A prompt longer than ``text_len`` is an error, not a truncation."""
    n = int(ids.shape[0])
    if n > text_len:
        raise ValueError(f"prompt is {n} tokens after templating, the model was trained with text_len={text_len}; shorten it")
    if n == text_len:
        return ids, n
    return torch.cat([ids, torch.full((text_len - n,), int(pad_id), dtype=ids.dtype)]), n


if __name__ == "__main__":
    # Hardware-free smoke: positions match the upstream rules; training pack is self-consistent.
    Lt, grid = 13, (2, 6, 10)
    pos = build_positions(Lt, grid, fps=24.0, temporal_margin=15000)
    N = Lt + 2 * 6 * 10
    assert pos.shape == (3, N) and pos.dtype == torch.float32
    assert torch.equal(pos[:, :Lt], torch.arange(Lt, dtype=torch.float32).expand(3, -1))
    assert pos[0, Lt] == Lt + 15000 and pos[0, Lt + 60] == Lt + 15000 + 1  # frame 1 at fps 24
    assert pos[1, Lt : Lt + 10].sum() == 0 and torch.equal(pos[2, Lt : Lt + 10], torch.arange(10.0))
    pos12 = build_positions(Lt, grid, fps=12.0, temporal_margin=15000)
    assert pos12[0, Lt + 60] == Lt + 15000 + 2  # slower video → frames spaced 2 apart
    x0 = torch.randn(1, 48, 2, 12, 20)
    eps = torch.randn_like(x0)
    ids = torch.arange(Lt)
    pk = pack(ids, x0, 0.5, cond_frames=1, eps=eps, is_x0=True)
    assert pk.patches.shape == (120, 192) and pk.noisy_mask.sum() == 60 and pk.total_len == N
    assert torch.equal(pk.x_t[:, :, 0], x0[:, :, 0]) and torch.allclose(
        pk.x_t[:, :, 1], 0.5 * eps[:, :, 1] + 0.5 * x0[:, :, 1]
    )
    assert torch.equal(pk.target, eps - x0) and pk.t_freq.shape == (1, 256)
    assert rope_table.cache_info().hits >= 0
    inf = pack(ids, pk.x_t, 0.5)
    assert torch.equal(inf.patches, pk.patches) and inf.target is None
    padded, n = pad_text_ids(torch.arange(5), 8, pad_id=99)
    assert n == 5 and padded.tolist() == [0, 1, 2, 3, 4, 99, 99, 99]
    assert pack(padded, pk.x_t, 0.5, text_valid=n).text_valid == 5
    for bad in (lambda: pad_text_ids(torch.arange(9), 8, 99), lambda: pack(padded, pk.x_t, 0.5, text_valid=9)):
        try:
            bad()
            raise AssertionError("must raise")
        except ValueError:
            pass
    print("pack smoke OK")
