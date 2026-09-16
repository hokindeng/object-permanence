"""Per-rank training shards → one checkpoint in the **diffusers layout** ``pwm.cli infer --ckpt`` can load.

A ``step_N/`` directory holds ``rank{R:04d}.pt`` files whose ``"model"`` entry maps every pwm parameter
name to that rank's LOCAL shard (``training.train._to_saveable``). With the ``(dp, tp)`` mesh (tp inner:
``R = dp * tp + t``) the full tensor is two nested concatenations, decided by name:

* TP-Colwise (``q/k/v, mlp.gate, mlp.up``): tp splits dim 0, FSDP splits each tp chunk on dim 0 again
  → ``cat_t( cat_d( local(d, t) ) )`` along dim 0.
* TP-Rowwise (``o, mlp.down``): tp splits dim 1, FSDP dim 0 → ``cat_t( cat_d( local(d, t), dim 0 ), dim 1 )``.
* everything else (norm gains, embed, vae2llm, time_embedder, norm_gen, llm2vae): replicated over tp,
  FSDP dim 0 → ``cat_d( local(d, 0) )`` (the other tp copies are checked identical).

Output: ``<out>/transformer/diffusion_pytorch_model.safetensors`` (+ ``.index.json``, ``config.json``
copied from the base) with keys renamed back to diffusers names via ``convert.pwm_key_to_diffusers``,
and ``vae/`` + ``text_tokenizer/`` symlinked to the base checkpoint, so ``pwm.model.load`` streams it
exactly like ``nvidia/Cosmos3-Nano``. Masters are fp32; ``dtype`` defaults to bf16 (the base's dtype
and what the forward computes in). CPU only; reads each rank file once.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

import torch

from pwm.model.block import COLWISE, ROWWISE
from pwm.model.convert import pwm_key_to_diffusers

__all__ = ["tp_placement", "assemble", "consolidate_dir"]

_COL = tuple(f".{n}.weight" for n in COLWISE)
_ROW = tuple(f".{n}.weight" for n in ROWWISE)


def tp_placement(name: str) -> int | None:
    """dim the TP plan shards ``name`` on: 0 (Colwise), 1 (Rowwise) or None (replicated)."""
    if re.match(r"blocks\.\d+\.(und|gen)\.", name):
        if name.endswith(_COL):
            return 0
        if name.endswith(_ROW):
            return 1
    return None


def assemble(
    name: str, shards: dict[tuple[int, int], torch.Tensor], dp: int, tp: int
) -> tuple[torch.Tensor, float]:
    """``shards[(d, t)]`` → ``(full tensor, tp_drift)`` per :func:`tp_placement`.

    ``tp_drift`` is the worst ``|tp_t - tp_0| / max|tp_0|`` over the TP copies of a replicated
    parameter (0.0 for sharded ones): the copies drift slightly on Neuron (per-rank bf16
    all-reduce order → slightly different Adam steps). tp=0 is taken; a gross mismatch (> 1e-2)
    means a wrong reassembly rather than drift and raises.
    """
    pl = tp_placement(name)
    if pl is None:
        full = torch.cat([shards[(d, 0)] for d in range(dp)], dim=0)
        scale = float(full.abs().max()) + 1e-12
        drift = 0.0
        for t in range(1, tp):
            other = torch.cat([shards[(d, t)] for d in range(dp)], dim=0)
            rel = float((other.float() - full.float()).abs().max()) / scale
            drift = max(drift, rel)
            if rel > 1e-2:
                raise ValueError(f"{name}: tp copy {t} deviates {rel:.3e} from tp 0 — not a drift, a layout bug")
        return full, drift
    chunks = [torch.cat([shards[(d, t)] for d in range(dp)], dim=0) for t in range(tp)]
    return torch.cat(chunks, dim=pl), 0.0


def consolidate_dir(
    step_dir: str | os.PathLike,
    out_dir: str | os.PathLike,
    *,
    tp: int,
    fsdp: int,
    layers: int,
    base_ckpt: str | os.PathLike,
    dtype: torch.dtype = torch.bfloat16,
) -> dict[str, int]:
    from safetensors import safe_open  # noqa: PLC0415
    from safetensors.torch import save_file  # noqa: PLC0415

    from pwm.model.load import read_index  # noqa: PLC0415

    step_dir, out_dir, base = Path(step_dir), Path(out_dir), Path(base_ckpt)
    files = sorted(step_dir.glob("rank*.pt"))
    if not (step_dir / "COMPLETE").exists():
        raise ValueError(f"{step_dir}: no COMPLETE marker — refusing a partial checkpoint")
    complete = json.loads((step_dir / "COMPLETE").read_text() or "{}")
    if len(files) != tp * fsdp or complete.get("world", tp * fsdp) != tp * fsdp:
        raise ValueError(
            f"{step_dir}: {len(files)} rank files, COMPLETE says world {complete.get('world')}, "
            f"asked tp*fsdp = {tp * fsdp}"
        )
    shards: dict[str, dict[tuple[int, int], torch.Tensor]] = {}
    for f in files:
        r = int(f.stem[4:])
        d, t = divmod(r, tp)
        payload = torch.load(f, map_location="cpu", weights_only=False)
        saved = payload.get("cfg") or {}
        sp, sm = saved.get("parallel") or {}, saved.get("model") or {}
        if (sp.get("tp", tp), sp.get("fsdp", fsdp)) != (tp, fsdp):
            raise ValueError(
                f"{f.name}: shards were trained with tp={sp.get('tp')} fsdp={sp.get('fsdp')}, "
                f"asked tp={tp} fsdp={fsdp} — pass the training YAML"
            )
        if sm.get("layers", layers) != layers:
            raise ValueError(f"{f.name}: shards hold {sm.get('layers')} layers, config says {layers}")
        for k, v in payload["model"].items():
            shards.setdefault(k, {})[(d, t)] = v
        del payload
    key_map = pwm_key_to_diffusers(layers)
    base_index = read_index(base)
    out_t = out_dir / "transformer"
    out_t.mkdir(parents=True, exist_ok=True)
    tensors, stats = {}, {"params": 0, "sharded": 0, "replicated": 0}
    drift: dict[str, float] = {}
    for name in sorted(shards):
        full, d = assemble(name, shards[name], fsdp, tp)
        if d > 0:
            drift[name] = d
        dk = key_map.get(name)
        if dk is None:
            raise KeyError(f"no diffusers key for pwm parameter {name!r}")
        if dk not in base_index:
            raise KeyError(f"{dk!r} (from {name}) is not in the base checkpoint {base}")
        base_path, base_key = base_index[dk]
        with safe_open(base_path, framework="pt", device="cpu") as fh:
            base_shape = tuple(fh.get_slice(base_key).get_shape())
        if tuple(full.shape) != base_shape:
            raise ValueError(
                f"{name}: assembled {tuple(full.shape)} but the base checkpoint has {base_shape} — "
                f"wrong tp/fsdp split for these shards"
            )
        tensors[dk] = full.to(dtype).contiguous()
        stats["params"] += 1
        stats["sharded" if tp_placement(name) is not None else "replicated"] += 1
    fname = "diffusion_pytorch_model.safetensors"
    save_file(tensors, str(out_t / fname), metadata={"format": "pt", "source": str(step_dir)})
    (out_t / f"{fname}.index.json").write_text(
        json.dumps({"metadata": {"total_size": sum(v.numel() * v.element_size() for v in tensors.values())},
                    "weight_map": {k: fname for k in tensors}}, indent=1)
    )
    shutil.copy(base / "transformer" / "config.json", out_t / "config.json")
    for sub in ("vae", "text_tokenizer"):
        link = out_dir / sub
        if not link.exists():
            os.symlink(os.path.abspath(base / sub), link)
    if drift:
        worst = max(drift.items(), key=lambda kv: kv[1])
        stats["tp_drift_worst"] = f"{worst[1]:.2e}@{worst[0]}"
        stats["tp_drift_n"] = len(drift)
    return stats
