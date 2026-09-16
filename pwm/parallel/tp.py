"""Tensor parallel for ``NanoMoT`` — DTensor Colwise/Rowwise per block, both towers.

Applies to the MoT layout ``blocks.{i}.{und,gen}.{q,k,v,o,mlp.{gate,up,down}}``:

| module (x2 towers)        | style            | weight placement | what moves            |
|---------------------------|------------------|------------------|-----------------------|
| ``q, k, v``               | ColwiseParallel  | ``Shard(0)``     | heads // tp per rank  |
| ``o``                     | RowwiseParallel  | ``Shard(1)``     | all-reduce after      |
| ``mlp.gate, mlp.up``      | ColwiseParallel  | ``Shard(0)``     | ffn // tp per rank    |
| ``mlp.down``              | RowwiseParallel  | ``Shard(1)``     | all-reduce after      |

Everything else (``embed, vae2llm, time_embedder, norm_gen, llm2vae, norm1/norm2, q_norm/k_norm``)
stays a plain replicated parameter. After sharding, ``Tower.heads`` / ``Tower.kv_heads`` are divided
by the TP degree (32→8 / 8→2 at tp4) so ``Tower.qkv``'s ``view`` and the block's GQA
``groups = heads // kv_heads`` (still 4) work on the local head slice. Colwise shards q-heads and
kv-heads in the same contiguous order, so local q head ``j`` still maps to local kv head ``j//4``.

No collective is spelled here. The forward's all-reduces are DTensor redistributions (``Partial →
Replicate`` in Rowwise; the Colwise input's backward), which torch implements with
``torch.distributed._functional_collectives`` — the only spelling that survives a compiled backward on
Neuron. The collectives pwm adds (:func:`reduce_tp_partial_grads`, :func:`sync_tp_replicated_grads`)
are post-backward ``dist.all_reduce`` calls outside any compiled region. The plan's module names
(``COLWISE`` / ``ROWWISE``) live in ``pwm.model.block`` next to the modules they name, so
``pwm.model.consolidate`` can reassemble shards without importing this module.

**Partial vs replicated gradients.** ``q_norm.weight`` / ``k_norm.weight`` are ``[head_dim]`` gains
applied per head: their *storage* is replicated but each rank feeds them only its own heads, so
their gradients are rank-**partial** and must be all-reduce-SUMmed over the TP group before
clipping / the optimizer. Every other replicated parameter sees replicated inputs and replicated
upstream gradients (DTensor reduces the Colwise input grad), so its gradient is already
**identical** on every TP rank and must NOT be summed again.
"""

from __future__ import annotations

import torch
import torch.distributed as dist
from torch import nn

from pwm.model.block import COLWISE, ROWWISE, Tower

__all__ = [
    "COLWISE", "ROWWISE", "parallelize", "tp_sharded_params", "tp_partial_params",
    "tp_replicated_params", "reduce_tp_partial_grads", "reduce_partial_grads_",
    "sync_tp_replicated_grads",
]  # fmt: skip

_PARTIAL = ("q_norm", "k_norm")


def parallelize(model: nn.Module, tp_mesh) -> int:
    """Apply the plan to every ``blocks.{i}`` (both towers), patch head counts, record TP context.

    Weights are sliced locally (``src_data_rank=None``): pwm parameters are either still on
    ``meta`` (streamed per-shard afterwards by ``pwm.model.load``) or identical on every rank by
    construction, so the default rank-0 broadcast would only add traffic. Returns #blocks.
    """
    from torch.distributed.tensor.parallel import (  # noqa: PLC0415
        ColwiseParallel,
        RowwiseParallel,
        parallelize_module,
    )

    world = tp_mesh.size()
    plan = {}
    for tower in ("und", "gen"):
        plan.update({f"{tower}.{n}": ColwiseParallel() for n in COLWISE})
        plan.update({f"{tower}.{n}": RowwiseParallel() for n in ROWWISE})
    for blk in model.blocks:
        for tower in (blk.und, blk.gen):
            if tower.heads % world or tower.kv_heads % world:
                raise ValueError(f"heads={tower.heads} kv_heads={tower.kv_heads} vs tp={world}")
    n = 0
    for blk in model.blocks:
        parallelize_module(blk, tp_mesh, plan, src_data_rank=None)
        for tower in (blk.und, blk.gen):
            tower.heads //= world
            tower.kv_heads //= world
        n += 1
    model._tp_group = tp_mesh.get_group()
    return n


# ------------------------------------------------------------------------- parameter categories
def _towers(model: nn.Module):
    root = getattr(model, "_orig_mod", model)
    return [(name, m) for name, m in root.named_modules() if isinstance(m, Tower)]


def tp_sharded_params(model: nn.Module) -> list[tuple[str, nn.Parameter]]:
    """The 7 linears per tower that the plan shards (DTensors once :func:`parallelize` ran)."""
    return [(f"{name}.{n}.weight", tower.get_submodule(n).weight)
            for name, tower in _towers(model) for n in COLWISE + ROWWISE]  # fmt: skip


def tp_partial_params(model: nn.Module) -> list[tuple[str, nn.Parameter]]:
    """The ``[head_dim]`` q/k-norm gains (4 per layer): replicated storage, partial gradient."""
    return [(f"{name}.{n}.weight", getattr(tower, n).weight)
            for name, tower in _towers(model) for n in _PARTIAL]  # fmt: skip


def tp_replicated_params(model: nn.Module) -> list[tuple[str, nn.Parameter]]:
    """Every other parameter — replicated over TP with gradients identical on every TP rank."""
    skip = {id(p) for _, p in tp_sharded_params(model) + tp_partial_params(model)}
    root = getattr(model, "_orig_mod", model)
    return [(n, p) for n, p in root.named_parameters() if id(p) not in skip]


# ------------------------------------------------------------------------------ gradient rules
def _local(t: torch.Tensor) -> torch.Tensor:
    from torch.distributed.tensor import DTensor  # noqa: PLC0415

    return t.to_local() if isinstance(t, DTensor) else t


def reduce_partial_grads_(params, group) -> int:
    """all-reduce(SUM) the grads of ``params`` over ``group`` in ONE flat collective, in place.

    Works on plain grads and on FSDP2 dp-sharded DTensor grads alike (the local shard is what
    each TP rank holds; TP ranks in one TP group share the same dp position, hence the same
    slice). Returns the number of grads reduced. Call after ``backward``, outside compiled code.
    """
    locals_ = [_local(p.grad) for p in params if p.grad is not None]
    if not locals_ or group is None or dist.get_world_size(group) == 1:
        return len(locals_)
    flat = torch.cat([t.reshape(-1) for t in locals_])
    dist.all_reduce(flat, op=dist.ReduceOp.SUM, group=group)
    off = 0
    for t in locals_:
        t.copy_(flat[off : off + t.numel()].view_as(t))
        off += t.numel()
    return len(locals_)


def reduce_tp_partial_grads(model: nn.Module, tp_group=None) -> int:
    """Sum the q/k-norm gain gradients over the TP group (see module docstring). No-op at tp=1."""
    group = tp_group if tp_group is not None else getattr(model, "_tp_group", None)
    return reduce_partial_grads_([p for _, p in tp_partial_params(model)], group)


def sync_tp_replicated_grads(model: nn.Module, tp_group=None) -> int:
    """Average the gradients of the TP-*replicated* parameters over the TP group, in one flat collective.

    The assumption that these gradients are identical on every TP rank holds bit-for-bit on gloo
    but not on Neuron: the activation gradients feeding them are all-reduced in bf16 and the
    per-rank reduction order differs by a few ulps, so each TP rank takes a slightly different AdamW
    step and the copies random-walk apart (~6e-5 relative after 100 steps; the q/k-norm gains, which
    are SUMmed explicitly, stay at 1e-7). Averaging pins the copies to one model. ~160 MB per rank per
    step (dp-sharded local grads), on-chip. No-op at tp=1 and on identical grads.
    """
    group = tp_group if tp_group is not None else getattr(model, "_tp_group", None)
    params = [p for _, p in tp_replicated_params(model)]
    n = reduce_partial_grads_(params, group)
    if group is not None and dist.get_world_size(group) > 1:
        inv = 1.0 / dist.get_world_size(group)
        for p in params:
            if p.grad is not None:
                _local(p.grad).mul_(inv)
    return n


if __name__ == "__main__":
    # Hardware-free smoke: world-1 gloo, tp mesh of size 1 — the plan applies (params become
    # DTensors), forward matches the plain model, categories partition the parameter set.
    import os

    from torch.distributed.tensor import DTensor

    from pwm.configs.config import ModelConfig
    from pwm.model.diffusion import TIME_FREQ_DIM
    from pwm.model.mot import NanoMoT
    from pwm.model.patchify import PATCH_DIM
    from pwm.parallel.mesh import build_mesh

    os.environ.update(MASTER_ADDR="127.0.0.1", MASTER_PORT="29512", RANK="0", WORLD_SIZE="1",
                      LOCAL_RANK="0")  # fmt: skip
    dist.init_process_group("gloo")
    try:
        cfg = ModelConfig(layers=2, dim=64, heads=8, kv_heads=2, head_dim=8, ffn_dim=96,
                          vocab_size=64, mrope_section=(2, 1, 1))  # fmt: skip
        torch.manual_seed(0)
        plain = NanoMoT(cfg)
        torch.manual_seed(0)
        m = NanoMoT(cfg)
        assert parallelize(m, build_mesh(1, 1, device_type="cpu")["tp"]) == 2
        assert dist.get_world_size(m._tp_group) == 1 and m.blocks[0].und.heads == 8
        sh, pa, re = tp_sharded_params(m), tp_partial_params(m), tp_replicated_params(m)
        assert (len(sh), len(pa), len(re)) == (28, 8, 18) and 54 == len(list(m.parameters()))
        assert all(isinstance(p, DTensor) for _, p in sh)
        assert not any(isinstance(p, DTensor) for _, p in pa + re)
        Lt, Nv = 5, 12
        x = (torch.arange(Lt), torch.randn(Nv, PATCH_DIM), torch.randn(1, TIME_FREQ_DIM), torch.ones(Nv, 1),
             torch.randn(Lt + Nv, 8), torch.randn(Lt + Nv, 8))  # fmt: skip
        out, ref = m(*x), plain(*x)
        assert torch.allclose(out, ref, atol=1e-5), (out - ref).abs().max()
        out.pow(2).sum().backward()
        assert reduce_tp_partial_grads(m) == 8 and sync_tp_replicated_grads(m) == 18
    finally:
        dist.destroy_process_group()
    print("tp smoke OK")
