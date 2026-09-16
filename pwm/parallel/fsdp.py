"""FSDP2 (``fully_shard``) over the ``dp`` mesh axis + per-block compile.

``apply_fsdp2`` after ``tp.parallelize`` turns each TP DTensor into a 2-D ``(dp, tp)`` DTensor
(``_StridedShard`` on dp). ``compile_blocks`` installs the ``DeviceMesh``/``ProcessGroup``
``__deepcopy__`` no-op that Dynamo's DTENSOR_SPEC_MATCH guard needs on Neuron.

Two pwm-specific points:

* **fp32 island.** ``NanoMoT.time_embedder`` must compute in fp32 (upstream wraps it in an fp32
  autocast). Under ``fsdp2_mp_policy()`` (bf16 all-gather) it gets its **own** ``fully_shard`` unit
  with ``MixedPrecisionPolicy(param_dtype=fp32, reduce_dtype=fp32)``, so its all-gathered working
  copy stays fp32 while every other unit gathers bf16. FSDP2 excludes a nested unit's params from
  the root unit, so the root policy never touches them.
* **No input casting.** ``fsdp2_mp_policy()`` sets ``cast_forward_inputs=False``: FSDP2's default
  would cast every floating-point forward input of the root to bf16 — including ``t_freq``, the
  fp32 sinusoid feeding the island. pwm casts at its own boundaries (``patches/cos/sin/noisy_mask
  .to(dt)``, ``dt = embed.weight.dtype`` = the bf16 all-gathered param inside the forward).
"""

from __future__ import annotations

import os
from typing import Any, Callable

import torch

__all__ = ["configure_fsdp_prefetch", "apply_fsdp2", "compile_blocks", "fsdp2_mp_policy", "FP32_ISLAND",
           "BLOCKS_ATTR", "rowcat_reduce_scatter_copy_in", "install_fast_reduce_scatter_copy_in"]  # fmt: skip

FP32_ISLAND = "time_embedder"
BLOCKS_ATTR = "blocks"  # NanoMoT's ModuleList of MoTBlocks — the FSDP2 / compile units


def rowcat_reduce_scatter_copy_in(
    unsharded_grads: list[torch.Tensor], reduce_scatter_input: torch.Tensor, world_size: int
) -> None:
    """chunk_cat layout from contiguous ops only: cast (+ zero-pad dim 0 to a multiple of
    ``world_size``, exactly as ``_chunk_cat`` does) each gradient once, then build each destination
    row ``out[j]`` (contiguous) with ONE ``torch.cat`` of the row-chunks ``g.view(W, -1)[j]``.
    22 casts + W cats per unit instead of per-chunk copies. Bit-identical to ``torch._chunk_cat``
    (padded shapes included)."""
    out = reduce_scatter_input.view(world_size, -1)
    rows = []
    for g in unsharded_grads:
        g = g.to(out.dtype)
        pad = (-g.size(0)) % world_size
        if pad:
            g = torch.cat([g, g.new_zeros((pad,) + tuple(g.shape[1:]))], dim=0)
        rows.append(g.reshape(world_size, -1))
    for j in range(world_size):
        torch.cat([r[j] for r in rows], dim=0, out=out[j])


def install_fast_reduce_scatter_copy_in() -> str:
    """Route FSDP2's reduce-scatter copy-in through :func:`rowcat_reduce_scatter_copy_in` (default;
    bit-identical to ``torch._chunk_cat`` and ~14× faster on Neuron, where the per-chunk copies were
    half the step). ``PWM_FSDP_COPYIN=chunk_cat`` leaves torch's own in place — the escape hatch if a
    torch bump changes the private ``_fsdp_collectives`` signature. Returns the variant in effect."""
    which = os.environ.get("PWM_FSDP_COPYIN", "rowcat")
    if which == "chunk_cat":
        return which
    if which != "rowcat":
        raise ValueError(f"PWM_FSDP_COPYIN={which!r}: expected 'rowcat' or 'chunk_cat'")
    from torch.distributed.fsdp._fully_shard import _fsdp_collectives as C  # noqa: PLC0415

    C.foreach_reduce_scatter_copy_in = rowcat_reduce_scatter_copy_in
    return which


def apply_fsdp2(model: torch.nn.Module, dp_mesh, *,
                mp_policy: Any | None = None,
                reshard_after_forward: bool | int = True,
                reshard_after_forward_blocks: int | None = None,
                materialize: Callable[[str], Any] | None = None) -> int:  # fmt: skip
    """Shard ``model`` over ``dp_mesh``: blocks, the fp32 island, then the root. Returns #blocks.

    ``mp_policy`` (see :func:`fsdp2_mp_policy`) keeps fp32 sharded masters (the model must NOT be
    pre-cast to bf16), all-gathers bf16 working copies, reduce-scatters grads in fp32 → fp32 AdamW
    moments. ``None`` shards whatever dtype the params already have. ``reshard_after_forward`` is
    forwarded to every ``fully_shard`` (``False`` = keep gathered params resident: fewer all-gathers
    for ~0.8 GB/rank more memory, losses bit-identical). Only shards — the caller then does
    ``model.to(device)`` and optionally :func:`compile_blocks`.

    ``materialize(prefix)`` (optional) is called right before each ``fully_shard`` with the
    parameter-name prefix of the unit about to be wrapped (``"blocks.3."``, ``"time_embedder."``,
    then ``""`` for everything left before the root wrap), so a meta model is loaded one unit at a
    time and the device holds at most one unsharded unit (loading everything first fragments the
    pool and the backward OOMs).
    """
    from torch.distributed.fsdp import MixedPrecisionPolicy, fully_shard  # noqa: PLC0415

    install_fast_reduce_scatter_copy_in()
    kw: dict[str, Any] = {"mp_policy": mp_policy} if mp_policy is not None else {}
    if reshard_after_forward is not True:  # keep the default path byte-identical to FSDP2's own
        kw["reshard_after_forward"] = reshard_after_forward
    # `reshard_after_forward_blocks=N` applies the non-default
    # policy to the FIRST N blocks only; the rest, the island and the root keep FSDP2's default (True), so the
    # HBM/time trade can be dialled instead of all-or-nothing (all 36 blocks resident OOMs at the first clip:
    # allocated peak 14.6 GiB but the NRT pool had 20.5 GiB reserved; 24 resident = 13.1 GiB peak, -8.6% step time).
    kw_default = {k: v for k, v in kw.items() if k != "reshard_after_forward"}
    n = 0
    for blk in getattr(model, BLOCKS_ATTR):
        if materialize is not None:
            materialize(f"{BLOCKS_ATTR}.{n}.")
        use = kw if (reshard_after_forward_blocks is None or n < reshard_after_forward_blocks) else kw_default
        fully_shard(blk, mesh=dp_mesh, **use)
        n += 1
    if reshard_after_forward_blocks is not None:
        kw = kw_default          # island + root: FSDP2 default
    island = getattr(model, FP32_ISLAND, None)
    if island is not None:
        if materialize is not None:
            materialize(f"{FP32_ISLAND}.")
        ikw = dict(kw)
        if mp_policy is not None:
            ikw["mp_policy"] = MixedPrecisionPolicy(param_dtype=torch.float32,
                                                    reduce_dtype=torch.float32,
                                                    cast_forward_inputs=False)  # fmt: skip
        fully_shard(island, mesh=dp_mesh, **ikw)
    if materialize is not None:
        materialize("")
    fully_shard(model, mesh=dp_mesh, **kw)
    # Never cast the sharded params afterwards (``to_dtype`` before wrapping only): casting the fp32
    # masters to bf16 AFTER wrapping would turn them into pure-bf16 state and undo the policy.
    return n


def configure_fsdp_prefetch(model: torch.nn.Module, *, forward_prefetch: int = 0,
                            backward_prefetch: int = 0) -> dict[str, int]:  # fmt: skip
    """FSDP2 explicit prefetch on the block units (call after :func:`apply_fsdp2`): block ``i`` issues the
    all-gathers of blocks ``i+1..i+N`` with its own in forward, and of the N previous blocks in backward order.
    2/2 measured -0.3 s of an 11.2 s step at 64 ranks (2026-09-06). Returns what was set."""
    blocks = list(getattr(model, BLOCKS_ATTR, []))
    done = {"forward_prefetch": 0, "backward_prefetch": 0}
    if forward_prefetch > 0:
        for i, b in enumerate(blocks):
            nxt = blocks[i + 1 : i + 1 + forward_prefetch]
            if nxt:
                b.set_modules_to_forward_prefetch(nxt)
                done["forward_prefetch"] += 1
    if backward_prefetch > 0:
        for i, b in enumerate(blocks):
            prv = list(reversed(blocks[max(0, i - backward_prefetch) : i]))
            if prv:
                b.set_modules_to_backward_prefetch(prv)
                done["backward_prefetch"] += 1
    return done


def fsdp2_mp_policy(param_dtype: torch.dtype = torch.bfloat16,
                    reduce_dtype: torch.dtype = torch.float32) -> Any:  # fmt: skip
    """FSDP2 ``MixedPrecisionPolicy`` — NOT FSDP1's ``MixedPrecision`` (``fully_shard`` ignores it).

    fp32 sharded masters / bf16 all-gather / fp32 grad reduce; ``cast_forward_inputs=False`` (see
    module docstring — the fp32 island's ``t_freq`` must not be bf16-rounded by FSDP2).
    """
    from torch.distributed.fsdp import MixedPrecisionPolicy  # noqa: PLC0415

    return MixedPrecisionPolicy(param_dtype=param_dtype, reduce_dtype=reduce_dtype,
                                cast_forward_inputs=False)  # fmt: skip


def _patch_dtensor_deepcopy_for_neuron() -> None:
    """Dynamo's DTENSOR_SPEC_MATCH guard deep-copies DTensor params → recurses into ``DeviceMesh`` →
    ``ProcessGroupNeuron`` (pybind, unpicklable) → ``TypeError``. A mesh / group is a per-rank
    singleton, so a no-op ``__deepcopy__`` is semantically correct. Idempotent."""
    from torch.distributed.device_mesh import DeviceMesh  # noqa: PLC0415
    from torch.distributed.distributed_c10d import ProcessGroup  # noqa: PLC0415

    if getattr(DeviceMesh, "_neuron_deepcopy_patched", False):
        return
    DeviceMesh.__deepcopy__ = lambda self, memo=None: self
    ProcessGroup.__deepcopy__ = lambda self, memo=None: self
    DeviceMesh._neuron_deepcopy_patched = True


def compile_blocks(model: torch.nn.Module, backend: str = "neuron") -> int:
    """Per-block ``torch.compile(backend, dynamic=False)`` — call AFTER ``.to(device)``.

    Whole-forward compile graph-breaks and NaNs under FSDP2 on Neuron; compile each
    ``fully_shard``'d block in place and keep the top-level forward eager. Shapes are static:
    ``data.text_len / latent_t / height / width`` fix the graph, any change recompiles. After the first
    compiled step ``torch_neuronx.get_fallback_ops()`` must be empty — a non-empty list means an op
    silently ran on host.
    """
    _patch_dtensor_deepcopy_for_neuron()
    n = 0
    for blk in getattr(model, BLOCKS_ATTR):
        blk.compile(backend=backend, dynamic=False)
        n += 1
    return n


if __name__ == "__main__":
    # Hardware-free smoke: world-1 gloo, dp mesh of size 1 with the mp policy — fp32 masters,
    # bf16 output, and the time_embedder computing in fp32 during the forward.
    import os

    import torch.distributed as dist
    from torch.distributed.tensor import DTensor

    from pwm.configs.config import ModelConfig
    from pwm.model.diffusion import TIME_FREQ_DIM
    from pwm.model.mot import NanoMoT
    from pwm.model.patchify import PATCH_DIM
    from pwm.parallel.mesh import build_mesh

    os.environ.update(MASTER_ADDR="127.0.0.1", MASTER_PORT="29513", RANK="0", WORLD_SIZE="1",
                      LOCAL_RANK="0")  # fmt: skip
    dist.init_process_group("gloo")
    try:
        cfg = ModelConfig(layers=2, dim=64, heads=8, kv_heads=2, head_dim=8, ffn_dim=96,
                          vocab_size=64, mrope_section=(2, 1, 1))  # fmt: skip
        m = NanoMoT(cfg)
        mesh = build_mesh(1, 1, device_type="cpu")
        assert apply_fsdp2(m, mesh["dp"], mp_policy=fsdp2_mp_policy()) == 2
        assert isinstance(m.time_embedder[0].weight, DTensor)
        assert m.embed.weight.dtype == torch.float32
        seen = {}
        m.time_embedder[0].register_forward_hook(
            lambda mod, i, o: seen.update(x=i[0].dtype, w=mod.weight.dtype))  # fmt: skip
        # Pre-hook: FSDP2's own (prepended) pre-forward has all-gathered bf16 by then; its
        # post-forward would already have resharded back to the fp32 master.
        m.blocks[0].register_forward_pre_hook(
            lambda mod, i: seen.update(blk_w=mod.und.q.weight.dtype))  # fmt: skip
        Lt, Nv = 5, 12
        x = (torch.arange(Lt), torch.randn(Nv, PATCH_DIM), torch.randn(1, TIME_FREQ_DIM), torch.ones(Nv, 1),
             torch.randn(Lt + Nv, 8), torch.randn(Lt + Nv, 8))  # fmt: skip
        out = m(*x)
        assert out.dtype == torch.bfloat16, out.dtype
        assert seen == {"x": torch.float32, "w": torch.float32, "blk_w": torch.bfloat16}, seen
        out.float().pow(2).sum().backward()
        assert m.embed.weight.grad.dtype == m.time_embedder[0].weight.grad.dtype == torch.float32
        m2 = NanoMoT(cfg)
        apply_fsdp2(m2, mesh["dp"])  # no policy: everything stays fp32
        assert m2(*x).dtype == torch.float32
        assert compile_blocks(m2, backend="eager") == 2
        assert torch.distributed.device_mesh.DeviceMesh._neuron_deepcopy_patched
    finally:
        dist.destroy_process_group()
    print("fsdp smoke OK")
