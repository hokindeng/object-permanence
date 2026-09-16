"""Stream a Cosmos3-Nano checkpoint into a (possibly meta, possibly TP-sharded) ``NanoMoT``.

Two layouts are accepted (``read_index`` tells them apart by the index file it finds): the diffusers
layout (``transformer/diffusion_pytorch_model.safetensors.index.json``; ``nvidia/Cosmos3-Nano``, and what
``consolidate`` writes) and the flat training layout (``model.safetensors.index.json`` at the root;
``Hokin/PWM-WROP``), whose keys are renamed by ``pwm.model.convert.training_key_to_diffusers``.

Each parameter is read from its shard file with ``safe_open(...).get_slice`` and sliced **at read
time** per its DTensor placement (``Shard(d)`` → contiguous range along ``d``; ``Replicate`` / plain →
full), so a rank never holds a full tensor. Flow: ``NanoMoT(cfg)`` on ``torch.device("meta")`` →
optional ``parallel.tp.parallelize`` (params become meta DTensors) → :func:`load_checkpoint` →
optional FSDP2 wrap. Tensors are cast (``time_embedder`` stays fp32), moved to ``device`` and swapped
into the owning module's ``_parameters`` (``param.data = ...`` refuses meta→real). Keys are mapped by
``pwm.model.convert``; every pwm parameter must exist in the checkpoint (raises otherwise).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import torch
from torch import nn
from torch.distributed.tensor import DTensor, Shard

from pwm.model.convert import pwm_key_to_diffusers, training_key_to_diffusers

__all__ = ["read_index", "load_checkpoint", "checkpoint_layers"]

_INDEX = "transformer/diffusion_pytorch_model.safetensors.index.json"
_INDEX_TRAINING = "model.safetensors.index.json"


def read_index(ckpt_dir: str | os.PathLike) -> dict[str, tuple[str, str]]:
    """``{diffusers_key: (absolute shard path, key inside that file)}``.

    Diffusers layout when ``transformer/…index.json`` exists, else the flat training layout
    (``model.safetensors.index.json``; keys renamed, so callers only ever see diffusers names)."""
    root = Path(ckpt_dir)
    if (root / _INDEX).exists():
        idx = json.loads((root / _INDEX).read_text())
        return {k: (str(root / "transformer" / v), k) for k, v in idx["weight_map"].items()}
    if (root / _INDEX_TRAINING).exists():
        idx = json.loads((root / _INDEX_TRAINING).read_text())
        return {training_key_to_diffusers(k): (str(root / v), k) for k, v in idx["weight_map"].items()}
    raise FileNotFoundError(f"{root}: neither {_INDEX} nor {_INDEX_TRAINING} — not a Cosmos3-Nano checkpoint")


def checkpoint_layers(ckpt_dir: str | os.PathLike) -> int:
    cfg = json.loads((Path(ckpt_dir) / "transformer" / "config.json").read_text())
    for k in ("num_hidden_layers", "num_layers"):
        if k in cfg:
            return int(cfg[k])
    text = cfg.get("text_config", {})
    return int(text.get("num_hidden_layers", 36))


def _slice_range(p: torch.Tensor) -> tuple[int, int, int] | None:
    """``(dim, start, stop)`` for a sharded DTensor parameter, else ``None`` (full tensor)."""
    if not isinstance(p, DTensor):
        return None
    mesh = p.device_mesh
    for pl in p.placements:
        if isinstance(pl, Shard):
            world, rank = mesh.size(), mesh.get_local_rank()
            full = p.shape[pl.dim]
            if full % world:
                raise ValueError(f"dim {pl.dim} of size {full} not divisible by TP world {world}")
            step = full // world
            return pl.dim, rank * step, (rank + 1) * step
    return None


def _set_param(model: nn.Module, dotted: str, value: torch.Tensor, template: torch.Tensor) -> None:
    parent, _, leaf = dotted.rpartition(".")
    mod = model.get_submodule(parent) if parent else model
    if isinstance(template, DTensor):
        value = DTensor.from_local(
            value, template.device_mesh, template.placements, run_check=False
        )
    mod._parameters[leaf] = nn.Parameter(value)


def load_checkpoint(
    model: nn.Module,
    ckpt_dir: str | os.PathLike,
    *,
    device: torch.device | str = "cpu",
    dtype: torch.dtype = torch.bfloat16,
    prefix: str | None = None,
) -> dict[str, int]:
    """Materialise every parameter of ``model`` from the checkpoint. Returns ``{"loaded", "sharded"}`` counts.

    The checkpoint's 36 layers are read only up to ``len(model.blocks)``. The timestep MLP
    (``time_embedder.*``) is always loaded in fp32 (the model's fp32 island). ``prefix`` restricts the
    pass to parameters whose name starts with it **and are still on ``meta``** — the hook
    :func:`pwm.parallel.fsdp.apply_fsdp2` uses to materialise one block right before ``fully_shard``,
    so a device never holds the whole unsharded TP shard at once. ``prefix=""`` loads whatever is
    still on ``meta``.
    """
    from safetensors import safe_open  # noqa: PLC0415

    device = torch.device(device)
    layers = len(model.blocks)
    key_map = pwm_key_to_diffusers(layers)
    index = read_index(ckpt_dir)
    handles: dict[str, object] = {}

    def handle(path: str):
        if path not in handles:
            handles[path] = safe_open(path, framework="pt", device="cpu")
        return handles[path]

    stats = {"loaded": 0, "sharded": 0}
    try:
        for name, p in list(model.named_parameters()):
            if prefix is not None and (not name.startswith(prefix) or p.device.type != "meta"):
                continue
            dk = key_map.get(name)
            if dk is None or dk not in index:
                raise KeyError(
                    f"no checkpoint source for parameter {name!r} (diffusers key {dk!r})"
                )
            path, fk = index[dk]
            ts = handle(path).get_slice(fk)
            rng = _slice_range(p)
            if rng is None:
                t = ts[:]
            elif rng[0] == 0:
                t = ts[rng[1] : rng[2]]
            elif rng[0] == 1:
                t = ts[:, rng[1] : rng[2]]
            else:
                raise ValueError(f"unsupported shard dim {rng[0]} for {name}")
            want = tuple(getattr(p, "_local_tensor", p).shape)
            if tuple(t.shape) != want:
                raise ValueError(
                    f"{name}: checkpoint tensor {tuple(ts.get_shape())} gives a {tuple(t.shape)} slice, the model "
                    f"expects {want} — checkpoint_dir does not match model config"
                )
            if rng is not None:
                stats["sharded"] += 1
            target_dtype = torch.float32 if name.startswith("time_embedder.") else dtype
            t = t.to(target_dtype).contiguous().to(device)
            _set_param(model, name, t, p)
            stats["loaded"] += 1
    finally:
        handles.clear()
    return stats


if __name__ == "__main__":
    # Smoke (needs the checkpoint): 2-layer CPU bf16 load equals direct safe_open reads.
    ckpt = os.environ.get("PWM_CKPT", os.path.expanduser("~/models/Cosmos3-Nano"))
    if not Path(ckpt, _INDEX).exists() and not Path(ckpt, _INDEX_TRAINING).exists():
        print("load smoke SKIPPED (no checkpoint at", ckpt, ")")
        raise SystemExit(0)
    from safetensors import safe_open

    from pwm.configs.config import ModelConfig
    from pwm.model.mot import NanoMoT

    with torch.device("meta"):
        m = NanoMoT(ModelConfig(layers=2))
    st = load_checkpoint(m, ckpt, dtype=torch.bfloat16)
    assert st["loaded"] == 10 + 22 * 2 and st["sharded"] == 0, st
    assert (
        m.time_embedder[0].weight.dtype == torch.float32 and m.embed.weight.dtype == torch.bfloat16
    )
    index = read_index(ckpt)
    for pk, dk in (
        ("blocks.1.gen.mlp.down.weight", "layers.1.mlp_moe_gen.down_proj.weight"),
        ("vae2llm.bias", "proj_in.bias"),
    ):
        path, fk = index[dk]
        with safe_open(path, framework="pt", device="cpu") as f:
            ref = f.get_tensor(fk)
        got = dict(m.named_parameters())[pk]
        assert torch.equal(got.float(), ref.to(torch.bfloat16).float()), pk
    assert all(p.device.type == "cpu" and not p.is_meta for p in m.parameters())
    n_params = sum(p.numel() for p in m.parameters())
    print(f"load smoke OK ({n_params / 1e9:.2f} B params in 2 layers)")
