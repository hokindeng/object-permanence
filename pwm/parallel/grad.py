"""Gradient-norm clipping from LOCAL shards — no gather, one all-reduce per placement signature.

Runs AFTER ``tp.reduce_tp_partial_grads`` (the trainer's order): by then the q/k-norm gains are identical
on every TP rank and count once per TP group like any other replicated parameter.

Sum-of-squares rule per gradient:
* DTensor: local shard is disjoint along every ``Shard``/``_StridedShard`` dim and identical along
  every ``Replicate`` dim → sum local ssq, all-reduce once per distinct ``(mesh, placements)``,
  divide by the replica count (product of mesh dims carrying ``Replicate``).
* plain tensor: identical on every rank (TP-replicated, or no parallelism) → add once, no reduce.

Every rank therefore computes the SAME ``total_norm`` — the invariant that keeps TP-replicated
parameters coherent (a rank-dependent ``coef`` drifts them apart).
"""

from __future__ import annotations

import torch
import torch.distributed as dist
from torch.distributed.tensor import DTensor

__all__ = ["clip_grad_norm"]


def _mesh_group(mesh):
    """Process group spanning every rank of ``mesh`` (what ``full_tensor()`` would gather over)."""
    if mesh.ndim == 1:
        return mesh.get_group()
    if mesh.size() == dist.get_world_size():
        return None  # WORLD
    return mesh._flatten().get_group()


def clip_grad_norm(parameters, max_norm: float) -> float:
    """Clip in place; return the pre-clip global L2 norm (identical on every rank).

    Defers to torch's ``clip_grad_norm_`` when no gradient is a DTensor, so the non-parallel
    path is byte-for-byte the stock clip.
    """
    parameters = [p for p in parameters if p.grad is not None]
    if not parameters:
        return 0.0
    grads = [p.grad for p in parameters]
    if not any(isinstance(g, DTensor) for g in grads):
        return float(torch.nn.utils.clip_grad_norm_(parameters, max_norm))

    def ssq_of(ts):
        # ONE multi-tensor norm kernel per list instead of a pow/sum
        # pair per tensor (hundreds of launches per step on Neuron). Same math: sum of squared L2 norms == sum of
        # squares. Grads are fp32 here (fsdp-mp reduces in fp32), so the norms are fp32 too.
        ts = [t.detach() for t in ts]
        if not ts:
            return torch.zeros((), dtype=torch.float32)
        norms = torch._foreach_norm(ts)
        return torch.stack([n.float() for n in norms]).pow(2).sum()

    by_sig: dict = {}
    plain = []
    for g in grads:
        if isinstance(g, DTensor):
            by_sig.setdefault((g.device_mesh, tuple(g.placements)), []).append(g.to_local())
        else:
            plain.append(g)
    dev = (grads[0].to_local() if isinstance(grads[0], DTensor) else grads[0]).device
    ssq = torch.zeros((), device=dev, dtype=torch.float32)
    for (mesh, placements), locals_ in by_sig.items():
        part = ssq_of(locals_)
        if dist.is_initialized():
            dist.all_reduce(part, op=dist.ReduceOp.SUM, group=_mesh_group(mesh))
        replicas = 1
        for dim, pl in enumerate(placements):
            if pl.is_replicate():
                replicas *= mesh.size(dim)
        ssq = ssq + (part / replicas if replicas > 1 else part)
    if plain:
        ssq = ssq + ssq_of(plain)
    # Agree on the SCALAR world-wide. Under tp>1 x dp>1 the
    # TP-replicated params are 1-D dp DTensors after FSDP2, so their ssq above was reduced over THIS tp position's dp
    # group only; `sync_tp_replicated_grads` makes the tp positions' copies equal up to fp32 rounding, but nothing here
    # enforced it. One 4-byte MAX all-reduce makes total_norm / coef identical on every rank regardless; the MIN
    # alongside exposes the residual spread (`clip_grad_norm.last_spread`, logged as `gnorm_spread`) as a tripwire.
    if dist.is_initialized() and dist.get_world_size() > 1:
        mn = ssq.clone()
        dist.all_reduce(ssq, op=dist.ReduceOp.MAX)
        dist.all_reduce(mn, op=dist.ReduceOp.MIN)
        clip_grad_norm.last_spread = float(ssq.sqrt() - mn.sqrt())
    else:
        clip_grad_norm.last_spread = 0.0
    total_norm = ssq.sqrt()
    coef = float((max_norm / (total_norm + 1e-6)).clamp(max=1.0))
    if coef < 1.0:
        # multi-tensor scale on the LOCAL tensors (a DTensor's to_local() shares storage)
        locals_ = [(g.to_local() if isinstance(g, DTensor) else g).detach() for g in grads]
        torch._foreach_mul_(locals_, coef)
    return float(total_norm)


clip_grad_norm.last_spread = 0.0   # max-min of the per-rank pre-clip norm at the last call (set under dist)


if __name__ == "__main__":
    # Hardware-free smoke: plain path == torch's clip (+ scaling); DTensor path on a world-1 mesh
    # (Shard + Replicate placements mixed with a plain grad) == fp64 truth.
    import os

    from torch.distributed.device_mesh import init_device_mesh
    from torch.distributed.tensor import Replicate, Shard, distribute_tensor

    def truth_of(ps):
        gs = [(p.grad.full_tensor() if isinstance(p.grad, DTensor) else p.grad) for p in ps]
        return float(torch.stack([g.double().pow(2).sum() for g in gs]).sum().sqrt())

    torch.manual_seed(0)
    ps = [torch.nn.Parameter(torch.randn(4, 3)), torch.nn.Parameter(torch.randn(5))]
    for p in ps:
        p.grad = torch.randn_like(p)
    t = truth_of(ps)
    assert abs(clip_grad_norm(ps, 1e30) - t) < 1e-5 and abs(clip_grad_norm(ps, t / 10) - t) < 1e-5
    assert abs(truth_of(ps) - t / 10) / (t / 10) < 1e-3
    os.environ.update(MASTER_ADDR="127.0.0.1", MASTER_PORT="29514", RANK="0", WORLD_SIZE="1",
                      LOCAL_RANK="0")  # fmt: skip
    dist.init_process_group("gloo")
    try:
        mesh = init_device_mesh("cpu", (1,))
        dps = [torch.nn.Parameter(distribute_tensor(torch.randn(4, 3), mesh, [Shard(0)])),
               torch.nn.Parameter(distribute_tensor(torch.randn(5), mesh, [Replicate()])),
               ps[0]]  # fmt: skip
        for p in dps[:2]:
            p.grad = distribute_tensor(torch.randn(p.shape), mesh, p.placements)
        t = truth_of(dps)
        assert abs(clip_grad_norm(dps, 1e30) - t) / t < 1e-5
    finally:
        dist.destroy_process_group()
    print("grad smoke OK")
