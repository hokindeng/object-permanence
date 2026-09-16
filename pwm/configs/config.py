"""Typed configuration for pwm (torch-free; loadable on any machine).

Nested dataclasses whose defaults describe the production model; ``Config.from_yaml`` applies a
*partial* YAML override (only the keys named change; unknown keys raise, a value of the wrong type raises),
then ``validate()`` rejects values the code cannot run (bad enums, non-positive degrees, geometry that is
not a whole number of patches). Everything fails at config load, before any weight is read. Parallel degrees
live here and nowhere else — the CLI relaunches itself under ``torchrun`` with ``parallel.tp * parallel.fsdp`` ranks.

Model constants come from the Cosmos3-Nano checkpoint (``transformer/config.json``, a Qwen3-VL-8B text
config). Constants no run ever changes (latent channels, patch size, timestep-embedding width, rope
defaults) are module constants in ``pwm.model.patchify`` / ``diffusion`` / ``rope``, not config keys.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "ModelConfig",
    "DataConfig",
    "DiffusionConfig",
    "ParallelConfig",
    "TrainingConfig",
    "InferenceConfig",
    "Config",
    "load_yaml",
]


@dataclass
class ModelConfig:
    layers: int = 36
    dim: int = 4096
    heads: int = 32
    kv_heads: int = 8
    head_dim: int = 128
    ffn_dim: int = 12288
    vocab_size: int = 151936
    rms_eps: float = 1e-6
    rope_theta: float = 5_000_000.0
    mrope_section: tuple[int, int, int] = (24, 20, 20)
    attention_backend: str = "sdpa"  # "sdpa" | "nki_flash"
    dtype: str = "bfloat16"  # model/activation dtype; time_embedder stays fp32
    rope_dtype: str = "model"  # "model" (upstream: cos/sin cast to activation dtype) | "float32"
    gradient_checkpointing: bool = True


@dataclass
class DataConfig:
    clips_dir: str = ""  # directory of encoded clips (<id>.pt, written by pwm.cli encode)
    latent_t: int = 30
    height: int = 288  # pixels; latent = /16, patches = /32
    width: int = 512
    cond_latent_frames: int = 0  # v2v clean-prefix frames (0 = t2v)
    text_len: int = 128  # fixed templated token length (static shape)
    fps: float = 24.0
    temporal_margin: int = 15000  # mRoPE temporal offset between text and vision


@dataclass
class DiffusionConfig:
    sigma_kind: str = "waver"  # waver | logitnormal | uniform
    train_shift: float = 5.0  # upstream: 256→3, 480→5, 720→10 (by height)


@dataclass
class ParallelConfig:
    tp: int = 1
    fsdp: int = 1
    compile: bool = False  # per-block torch.compile(backend="neuron", dynamic=False)
    reshard_after_forward: bool = True
    # Apply the non-default reshard policy to the first N blocks only (None = every block + island + root).
    # 24 of 36 at tp4 x fsdp16: 5.69 -> 5.20 s/step, peak 13.1 GiB/rank; all 36 resident OOMs (README, Performance notes).
    reshard_after_forward_blocks: int | None = None
    fsdp_mixed_precision: bool = True  # fp32 shards, bf16 all-gather, fp32 reduce
    # Average the grads of TP-replicated params (norm gains, embed, time_embedder, vae2llm/llm2vae)
    # over the TP group each step; without it the TP copies drift apart on Neuron, where the bf16
    # all-reduce order differs per rank.
    tp_sync_replicated_grads: bool = True
    # FSDP2 explicit prefetch on the block units (blocks ahead in forward / behind in backward); 0 = FSDP2 default.
    fsdp_forward_prefetch: int = 0
    fsdp_backward_prefetch: int = 0


@dataclass
class TrainingConfig:
    lr: float = 1e-5
    betas: tuple[float, float] = (0.9, 0.95)
    weight_decay: float = 0.0
    eps: float = 1e-8
    # Neuron AdamW pacing: "chunk_sync" (single-tensor, one device sync per optimizer_sync_every params) |
    # "foreach" (multi-tensor kernels, one sync per step; ~10x faster) | "flat" (AdamW on one padded flat fp32
    # buffer per group; on pwm measured 2% SLOWER than foreach, kept opt-in).
    # Off Neuron: stock AdamW for chunk_sync/foreach; "flat" runs its own class everywhere (CPU-testable).
    optimizer_mode: str = "chunk_sync"
    optimizer_sync_every: int = 32
    warmup_steps: int = 10
    max_steps: int = 1000
    grad_accum: int = 1
    max_grad_norm: float = 1.0
    skip_step_grad_norm: float = 1000.0
    # Abort (after a final checkpoint) once this many CONSECUTIVE steps were refused by the skip guard: a sustained
    # storm is a diverged model and skipping it to max_steps burns days for nothing (on a sibling model the guard
    # caught a 2e-4 explosion at step 705 instead of idling all night). None = never abort.
    skip_step_abort_after: int | None = 50
    save_every: int = 100
    ckpt_dir: str = ""
    seed: int = 1234
    log_every: int = 1


@dataclass
class InferenceConfig:
    steps: int = 35
    guidance: float = 6.0
    shift: float = 5.0
    seed: int = 1234
    negative_prompt: str = ""


@dataclass
class Config:
    model: ModelConfig = field(default_factory=ModelConfig)
    data: DataConfig = field(default_factory=DataConfig)
    diffusion: DiffusionConfig = field(default_factory=DiffusionConfig)
    parallel: ParallelConfig = field(default_factory=ParallelConfig)
    training: TrainingConfig = field(default_factory=TrainingConfig)
    inference: InferenceConfig = field(default_factory=InferenceConfig)
    checkpoint_dir: str = (
        ""  # Cosmos3-Nano diffusers checkpoint (transformer/, vae/, text_tokenizer/)
    )
    # Transformer weights to load instead of checkpoint_dir's (e.g. the released fine-tune Hokin/PWM-WROP, flat
    # training layout); checkpoint_dir still supplies vae/ and text_tokenizer/. "" = the base transformer.
    weights_dir: str = ""
    device: str = "cpu"

    @classmethod
    def from_yaml(cls, path: str | Path | None) -> Config:
        cfg = cls()
        if path is None:
            return cfg.validate()
        override = load_yaml(path)
        return _apply(cfg, override, prefix="").validate()

    @classmethod
    def from_dict(cls, override: dict[str, Any]) -> Config:
        return _apply(cls(), override, prefix="").validate()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def validate(self) -> Config:
        """Raise ``ValueError`` listing every value the code cannot run with. Called by ``from_yaml`` /
        ``from_dict``, by the CLI after its flag overrides, and by ``pwm.cli.build_model``."""
        m, d, df, p, t, i = self.model, self.data, self.diffusion, self.parallel, self.training, self.inference
        bad: list[str] = []

        def need(ok: bool, msg: str) -> None:
            if not ok:
                bad.append(msg)

        for k in ("layers", "dim", "heads", "kv_heads", "head_dim", "ffn_dim", "vocab_size"):
            need(getattr(m, k) >= 1, f"model.{k} must be >= 1, got {getattr(m, k)}")
        need(m.kv_heads >= 1 and m.heads % m.kv_heads == 0, f"model.heads {m.heads} must be a multiple of kv_heads {m.kv_heads}")
        need(m.head_dim % 2 == 0, f"model.head_dim must be even, got {m.head_dim}")
        need(len(m.mrope_section) == 3 and sum(m.mrope_section) == m.head_dim // 2,
             f"model.mrope_section {m.mrope_section} must have 3 entries summing to head_dim/2 = {m.head_dim // 2}")
        need(m.rms_eps > 0 and m.rope_theta > 0, "model.rms_eps and model.rope_theta must be > 0")
        need(m.attention_backend in ("sdpa", "nki_flash"), f"model.attention_backend {m.attention_backend!r}: sdpa | nki_flash")
        need(m.dtype in ("float32", "bfloat16"), f"model.dtype {m.dtype!r}: float32 | bfloat16")
        need(m.rope_dtype in ("model", "float32"), f"model.rope_dtype {m.rope_dtype!r}: model | float32")
        need(d.latent_t >= 1, f"data.latent_t must be >= 1, got {d.latent_t}")
        need(d.height % 32 == 0 and d.width % 32 == 0 and d.height > 0 and d.width > 0,
             f"data.height/width must be positive multiples of 32 (VAE 16 x patch 2), got {d.height}x{d.width}")
        need(0 <= d.cond_latent_frames < d.latent_t,
             f"data.cond_latent_frames {d.cond_latent_frames} must be in [0, latent_t={d.latent_t})")
        need(d.text_len >= 1, f"data.text_len must be >= 1, got {d.text_len}")
        need(d.fps > 0 and d.temporal_margin >= 0, "data.fps must be > 0 and data.temporal_margin >= 0")
        need(df.sigma_kind in ("waver", "logitnormal", "uniform"), f"diffusion.sigma_kind {df.sigma_kind!r}: waver | logitnormal | uniform")
        need(df.train_shift > 0, f"diffusion.train_shift must be > 0, got {df.train_shift}")
        need(p.tp >= 1 and p.fsdp >= 1, f"parallel.tp/fsdp must be >= 1, got tp={p.tp} fsdp={p.fsdp}")
        need(p.tp >= 1 and m.heads % p.tp == 0 and m.kv_heads % p.tp == 0,
             f"parallel.tp {p.tp} must divide model.heads {m.heads} and model.kv_heads {m.kv_heads}")
        need(p.fsdp_forward_prefetch >= 0 and p.fsdp_backward_prefetch >= 0, "parallel.fsdp_*_prefetch must be >= 0")
        need(t.lr > 0 and t.eps > 0 and t.weight_decay >= 0, "training.lr, eps must be > 0 and weight_decay >= 0")
        need(len(t.betas) == 2 and all(0 <= b < 1 for b in t.betas), f"training.betas {t.betas} must be two values in [0, 1)")
        need(t.optimizer_mode in ("chunk_sync", "foreach", "flat"), f"training.optimizer_mode {t.optimizer_mode!r}: chunk_sync | foreach | flat")
        need(t.skip_step_abort_after is None or t.skip_step_abort_after >= 1,
             f"training.skip_step_abort_after must be null or >= 1, got {t.skip_step_abort_after}")
        need(p.reshard_after_forward_blocks is None or p.reshard_after_forward_blocks >= 0,
             f"parallel.reshard_after_forward_blocks must be null or >= 0, got {p.reshard_after_forward_blocks}")
        need(t.optimizer_sync_every >= 1, f"training.optimizer_sync_every must be >= 1, got {t.optimizer_sync_every}")
        need(t.warmup_steps >= 0 and t.max_steps >= 1, "training.warmup_steps must be >= 0 and max_steps >= 1")
        need(t.grad_accum >= 1, f"training.grad_accum must be >= 1, got {t.grad_accum}")
        need(t.max_grad_norm > 0 and t.skip_step_grad_norm > 0, "training.max_grad_norm and skip_step_grad_norm must be > 0")
        need(t.save_every >= 1 and t.log_every >= 1, "training.save_every and log_every must be >= 1")
        need(i.steps >= 1 and i.guidance >= 0 and i.shift > 0, "inference.steps >= 1, guidance >= 0, shift > 0")
        need(self.device in ("cpu", "neuron"), f"device {self.device!r}: cpu | neuron")
        if bad:
            raise ValueError("invalid config:\n  " + "\n  ".join(bad))
        return self


def load_yaml(path: str | Path) -> dict[str, Any]:
    import yaml  # noqa: PLC0415 — lazy so the dataclasses stay importable without PyYAML

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top level must be a mapping")
    return data


def _apply(obj: Any, override: dict[str, Any], prefix: str) -> Any:
    names = {f.name: f for f in fields(obj)}
    for key, val in override.items():
        if key not in names:
            raise KeyError(f"unknown config key {prefix + key!r}")
        cur = getattr(obj, key)
        if is_dataclass(cur):
            if not isinstance(val, dict):
                raise TypeError(f"config key {prefix + key!r} must be a mapping, got {val!r}")
            setattr(obj, key, _apply(cur, val, prefix=f"{prefix}{key}."))
        else:
            setattr(obj, key, _coerce(prefix + key, cur, val))
    return obj


def _coerce(name: str, cur: Any, val: Any) -> Any:
    """``val`` must have the type of the default ``cur``; ints widen to floats, lists become tuples of the
    default's length. Anything else raises here, not in the first forward."""
    num = (int, float)
    if isinstance(cur, bool):
        if not isinstance(val, bool):
            raise TypeError(f"{name}: expected true/false, got {val!r}")
        return val
    if isinstance(cur, int):
        if isinstance(val, bool) or not isinstance(val, int):
            raise TypeError(f"{name}: expected an integer, got {val!r}")
        return val
    if isinstance(cur, float):
        if isinstance(val, bool) or not isinstance(val, num):
            hint = " (YAML reads 1e-5 as a string; write 1.0e-5)" if isinstance(val, str) else ""
            raise TypeError(f"{name}: expected a number, got {val!r}{hint}")
        return float(val)
    if isinstance(cur, str):
        if not isinstance(val, str):
            hint = " (use '' for none)" if val is None else ""
            raise TypeError(f"{name}: expected a string, got {val!r}{hint}")
        return val
    if isinstance(cur, tuple):
        if (not isinstance(val, (list, tuple)) or len(val) != len(cur)
                or not all(isinstance(x, num) and not isinstance(x, bool) for x in val)):
            raise TypeError(f"{name}: expected {len(cur)} numbers, got {val!r}")
        return tuple(type(c)(x) for c, x in zip(cur, val, strict=True))
    return val


if __name__ == "__main__":
    import tempfile

    c = Config()
    assert c.model.head_dim == 128 and c.training.optimizer_sync_every == 32
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write("model:\n  layers: 2\n  mrope_section: [24, 20, 20]\nparallel:\n  tp: 4\n")
        p = f.name
    c2 = Config.from_yaml(p)
    assert c2.model.layers == 2 and c2.parallel.tp == 4 and c2.model.dim == 4096
    assert c2.model.mrope_section == (24, 20, 20)
    try:
        _apply(Config(), {"model": {"nope": 1}}, "")
        raise AssertionError("unknown key must raise")
    except KeyError:
        pass
    for bad_override, exc in (
        ({"training": {"lr": "1e-5"}}, TypeError),  # YAML 1.1 string
        ({"checkpoint_dir": None}, TypeError),
        ({"model": {"mrope_section": "24,20,20"}}, TypeError),
        ({"parallel": 4}, TypeError),
        ({"model": {"attention_backend": "spda"}}, ValueError),
        ({"model": {"rope_dtype": "fp32"}}, ValueError),
        ({"training": {"optimizer_mode": "forEach"}}, ValueError),
        ({"training": {"grad_accum": 0}}, ValueError),
        ({"parallel": {"tp": 0}}, ValueError),
        ({"parallel": {"tp": 3}}, ValueError),  # 32 heads % 3
        ({"model": {"heads": 5}}, ValueError),  # 5 % kv_heads 8
        ({"data": {"height": 100}}, ValueError),
        ({"data": {"text_len": 0}}, ValueError),
        ({"data": {"cond_latent_frames": 30}}, ValueError),
        ({"device": "gpu"}, ValueError),
    ):
        try:
            Config.from_dict(bad_override)
            raise AssertionError(f"{bad_override} must raise {exc.__name__}")
        except exc:
            pass
    c3 = Config.from_dict({"training": {"lr": 1, "betas": [0.9, 0.95]}, "model": {"mrope_section": [24, 20, 20]}})
    assert c3.training.lr == 1.0 and isinstance(c3.training.lr, float) and c3.model.mrope_section == (24, 20, 20)
    print("config smoke OK")
