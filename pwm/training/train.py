"""``fit`` — the training loop: full-parameter AdamW, DP×TP via ``pwm.parallel``.

Per optimizer step, on every rank: for each micro-batch draw one sigma and one eps from the rank's
generator, pack → forward → ``flow_loss`` (fp32) → backward; then SUM the TP-partial grads (q/k-norm
gains), average the TP-replicated grads, clip from local shards, and step only if every rank agrees
loss and grad norm are finite (all-reduce MIN) — all ranks step or all skip, never a desync.
Params are fp32 shards under the FSDP2 mixed-precision policy (bf16 all-gather, fp32 reduce, fp32
Adam moments). On Neuron the optimizer is one of two AdamW pacings (``training.optimizer_mode``):
``chunk_sync`` (single-tensor, one device sync per group of ``optimizer_sync_every`` params),
``foreach`` (multi-tensor kernels, one sync per step) or ``flat`` (one padded flat fp32 buffer per group; opt-in).

Checkpoints: ``<ckpt_dir>/step_{N:08d}/rank{R:04d}.pt`` (local shards, optimizer, scheduler, sampler
cursor, generator state, config) written atomically; rank 0 adds ``COMPLETE`` after a barrier.
``latest_step`` = highest step with ``COMPLETE``; a rerun resumes from it bit-exactly.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import torch
from torch import nn
from torch.distributed.tensor import DTensor

from pwm.configs.config import Config
from pwm.data.dataset import ClipDataset, ResumableSampler
from pwm.data.pack import pack
from pwm.model.diffusion import flow_loss, sample_sigma
from pwm.model.patchify import unpatchify
from pwm.parallel.mesh import is_dist_initialized

__all__ = [
    "TrainState",
    "build_optimizer",
    "training_step",
    "save_checkpoint",
    "load_checkpoint_dir",
    "latest_step",
    "fit",
]


@dataclass
class TrainState:
    step: int = 0
    skipped: int = 0
    step_times: list = field(default_factory=list)  # wall seconds per optimizer step (bench)


def _dist():
    """``torch.distributed`` when a process group is up, else ``None`` (single-process runs skip collectives)."""
    import torch.distributed as dist  # noqa: PLC0415

    return dist if is_dist_initialized() else None


def _log(msg: str, rank: int) -> None:
    if rank == 0:
        print(f"[{time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())}Z] {msg}", flush=True)

_MEM_LOG = os.environ.get("PWM_MEM_LOG", "") not in ("", "0")  # PWM_MEM_LOG=1: per-phase HBM log (see _mem)


def _check_no_fallback_ops(device, rank: int) -> None:
    """Once, after the first step on Neuron: ``torch_neuronx.get_fallback_ops()`` must be empty. A non-empty
    list means an op silently ran on host, the step is not accelerated and stays that way; every rank raises."""
    if str(device) != "neuron":
        return
    import torch_neuronx  # noqa: PLC0415

    get = getattr(torch_neuronx, "get_fallback_ops", None)
    if get is None:
        _log("fallback-op check unavailable in this torch_neuronx", rank)
        return
    ops = sorted(str(o) for o in get())
    _log(f"fallback ops after first step: {ops or 'none'}", rank)
    if ops:
        raise RuntimeError(f"{len(ops)} op(s) fell back to host on Neuron: {ops}")


def _clear_op_tracking(device) -> None:
    """Reset torch_neuronx's op tracking so :func:`_check_no_fallback_ops` sees only training-step ops."""
    if str(device) != "neuron":
        return
    import torch_neuronx  # noqa: PLC0415

    clear = getattr(torch_neuronx, "clear_op_tracking", None)
    if clear is not None:
        clear()


def _mem(tag: str, device, rank: int, dist) -> None:
    """Opt-in (``PWM_MEM_LOG=1``, a diagnostic env var rather than a config key) device-memory line per phase:
    rank-0 allocated / peak / reserved and the max peak over ranks. Adds a sync per call — leave off for
    timing runs. No-op off ``neuron``."""
    if not _MEM_LOG or str(device) != "neuron":
        return
    tn = torch.neuron  # type: ignore[attr-defined]
    alloc, peak, resv = tn.memory_allocated(), tn.max_memory_allocated(), tn.memory_reserved()
    mx = torch.tensor(float(peak), device=device)
    if dist is not None:
        dist.all_reduce(mx, op=dist.ReduceOp.MAX)
    _log(
        f"mem[{tag}] alloc {alloc / 2**30:.2f} GiB peak {peak / 2**30:.2f} GiB reserved {resv / 2**30:.2f} GiB"
        f" | max-rank peak {mx.item() / 2**30:.2f} GiB",
        rank,
    )


# ------------------------------------------------------------------------------------ optimizer
class _OneSyncAdamW(torch.optim.AdamW):
    """AdamW with ``foreach=True`` (multi-tensor ``_foreach_*`` kernels: ~10 launches per parameter group instead
    of ~10 per parameter) and ONE device sync after the whole step. Parameter groups are ``_ChunkSyncAdamW``'s
    chunks, each split into a DTensor part and a plain part (``foreach`` cannot mix the two) — so the optimizer
    checkpoint is layout-compatible with ``chunk_sync`` only when every parameter is a DTensor (fsdp > 1);
    under tp-only the plain replicated params make extra groups and the two modes' checkpoints do not
    interchange. One-core micro-benchmark on a 662-tensor / 380M-param rank: 126 ms vs 1,324 ms for the
    chunk-synced single-tensor loop; CPU bitwise-equal to the single-tensor path; no ``Tensor not bound``
    in 64-rank runs. Selected by ``training.optimizer_mode: foreach``."""

    @torch.no_grad()
    def step(self, closure=None):  # noqa: D102
        super().step(closure)
        torch.neuron.synchronize()  # type: ignore[attr-defined]
        return None


class _ChunkSyncAdamW(torch.optim.AdamW):
    """AdamW that steps its parameter groups one at a time with a device sync in between.

    On the Neuron async runtime a plain ``step()`` over 814 parameters (3 lazily allocated temporaries
    each) outruns the queue: ``aten::addcmul_ … Tensor not bound: lazy alloc kAlloc may not have
    executed``. ``NEURON_LAUNCH_BLOCKING=1`` passes and a single sync before ``step()`` does not help,
    so the pacing has to be inside the loop. Groups are chunks of ``training.optimizer_sync_every``
    parameters (default 32); the per-parameter update is unchanged.
    """

    @torch.no_grad()
    def step(self, closure=None):  # noqa: D102
        groups = self.param_groups
        try:
            for g in groups:
                self.param_groups = [g]
                super().step(closure)
                torch.neuron.synchronize()  # type: ignore[attr-defined]
        finally:
            self.param_groups = groups
        return None


class _FlatAdamW(torch.optim.Optimizer):
    """AdamW whose per-step math runs on flat fp32 buffers instead of a list of per-rank shards.

    Opt-in (`training.optimizer_mode: flat`) —
    on pwm it measured ~2% SLOWER than foreach (the grad/param copies outweigh the launches saved), see README.
    One-core measurements on a sibling model (216M fp32 elements / rank in 1,400 tensors): ``torch.optim.AdamW(foreach=True)``
    339 ms; one ``_foreach_add_`` over the list 16 ms (per-tensor launch cost); the same AdamW on a single flat tensor
    34 ms. Two Neuron facts shape the design:
      * elementwise kernels on a tensor whose numel is NOT a multiple of 128 take a 30-90x slower path
        (32Mi elements: addcdiv_ 1.8 ms; 32Mi+1: 157 ms) -> every flat region is padded to a multiple of 4096;
      * three whole-group temporaries OOM at the 21 GB/core peak -> the group is processed in chunks of
        <= ``PWM_FLAT_CHUNK`` elements (param boundaries), through two persistent chunk buffers (g, w).
    Per chunk: ``_foreach_copy_`` the grads and params into the padded buffers, run torch's single-tensor AdamW op
    sequence (mul_ / lerp_ / mul_+addcmul_ / sqrt / div_ / add_ / addcdiv_ -- same ops, same order, same fp32), and
    ``_foreach_copy_`` the result back into the shards. exp_avg / exp_avg_sq live permanently in flat (padded)
    buffers; ``state[p]`` holds per-param VIEWS into them, so ``state_dict()`` / ``latest.pt`` look exactly like the
    foreach mode's (local shards) and either mode's checkpoint resumes under the other. Groups must not mix DTensor
    and plain tensors (same split as foreach). One device sync after the step. Params whose ``grad`` is None are
    skipped like torch.optim.AdamW does (their m/v and value are left untouched; only the group-shared step counter
    still advances -- the one residual difference to torch's per-param step)."""

    _CHUNK = int(os.environ.get("PWM_FLAT_CHUNK", str(32 * 1024 * 1024)))   # elements per chunk (128 MB fp32)
    _PAD = 4096

    def __init__(self, params, lr: float, betas=(0.9, 0.999), eps: float = 1e-8, weight_decay: float = 0.0):
        super().__init__(params, dict(lr=lr, betas=betas, eps=eps, weight_decay=weight_decay))
        self._flat: dict[int, dict] = {}
        self._dirty = True

    @staticmethod
    def _local(t):
        return t.to_local() if hasattr(t, "to_local") else t

    @classmethod
    def _padded(cls, n: int) -> int:
        return -(-n // cls._PAD) * cls._PAD

    def _ensure_flat(self, gi: int, group: dict) -> dict:
        ps = group["params"]
        F = self._flat.get(gi)
        if F is not None and not self._dirty and F["n_params"] == len(ps):
            return F
        locs = [self._local(p) for p in ps]
        sizes = [t.numel() for t in locs]
        # chunks of <= _CHUNK elements on param boundaries; each chunk's flat region is padded to _PAD
        chunks, i0, acc = [], 0, 0
        for i, sz in enumerate(sizes):
            if acc and acc + sz > self._CHUNK:
                chunks.append((i0, i, acc)); i0, acc = i, 0
            acc += sz
        chunks.append((i0, len(sizes), acc))
        regions, off = [], 0                          # (i0, i1, n, off, n_pad)
        for i0, i1, n in chunks:
            regions.append((i0, i1, n, off, self._padded(n))); off += self._padded(n)
        total = off
        dev = locs[0].device if locs else torch.device("cpu")
        m = torch.zeros(total, dtype=torch.float32, device=dev)
        v = torch.zeros(total, dtype=torch.float32, device=dev)
        step = 0.0
        for i0, i1, n, off, _ in regions:
            o = off
            for p, t, sz in zip(ps[i0:i1], locs[i0:i1], sizes[i0:i1]):
                st = self.state[p]
                if "exp_avg" in st:            # resumed / cross-mode state: seed the flat buffers from it
                    m[o:o + sz].copy_(self._local(st["exp_avg"]).reshape(-1).to(torch.float32))
                    v[o:o + sz].copy_(self._local(st["exp_avg_sq"]).reshape(-1).to(torch.float32))
                    step = float(st["step"]) if "step" in st else step
                st["exp_avg"] = m[o:o + sz].view_as(t)
                st["exp_avg_sq"] = v[o:o + sz].view_as(t)
                o += sz
        step_t = torch.tensor(step, dtype=torch.float32)
        for p in ps:
            self.state[p]["step"] = step_t
        maxpad = max(r[4] for r in regions)
        F = dict(n_params=len(ps), m=m, v=v, sizes=sizes, regions=regions, step=step_t,
                 g=torch.zeros(maxpad, dtype=torch.float32, device=dev),
                 w=torch.zeros(maxpad, dtype=torch.float32, device=dev))
        self._flat[gi] = F
        if all(k in self._flat for k in range(len(self.param_groups)) if self.param_groups[k]["params"]):
            self._dirty = False
        return F

    def load_state_dict(self, state_dict):  # noqa: D102
        super().load_state_dict(state_dict)
        self._dirty = True   # per-param state was replaced by copies -> re-flatten on the next step

    @staticmethod
    def _views(buf, start, tensors):
        out, o = [], start
        for t in tensors:
            out.append(buf[o:o + t.numel()].view_as(t)); o += t.numel()
        return out

    @torch.no_grad()
    def step(self, closure=None):  # noqa: D102
        for gi, group in enumerate(self.param_groups):
            ps = group["params"]
            if not ps:
                continue
            F = self._ensure_flat(gi, group)
            lr, (b1, b2), eps, wd = group["lr"], group["betas"], group["eps"], group["weight_decay"]
            F["step"] += 1
            t = float(F["step"])
            step_size = lr / (1 - b1 ** t)
            bc2_sqrt = math.sqrt(1 - b2 ** t)
            m, v, g, w = F["m"], F["v"], F["g"], F["w"]
            for i0, i1, n, off, n_pad in F["regions"]:
                cl = [self._local(p) for p in ps[i0:i1]]
                grads = [self._local(p.grad) if p.grad is not None else torch.zeros_like(tl)
                         for p, tl in zip(ps[i0:i1], cl)]
                # torch.optim.AdamW SKIPS a param whose grad is None (no decay, no moment update, no step);
                # the flat update runs on the whole region, so for those params snapshot their m/v slices now
                # and restore them -- and leave the param itself untouched -- below.
                none_idx = [j for j, p in enumerate(ps[i0:i1]) if p.grad is None]
                gc, wc, mc, vc = g[:n_pad], w[:n_pad], m[off:off + n_pad], v[off:off + n_pad]
                if none_idx:
                    mv_, vv_ = self._views(mc, 0, cl), self._views(vc, 0, cl)
                    saved = [(mv_[j].clone(), vv_[j].clone()) for j in none_idx]
                torch._foreach_copy_(self._views(gc, 0, cl), grads)
                torch._foreach_copy_(self._views(wc, 0, cl), cl)
                # == torch.optim.adamw._single_tensor_adam (no amsgrad, not capturable, not maximize); the pad
                # tail stays 0 (g=0 -> m,v=0 -> denom=eps -> update 0).
                wc.mul_(1 - lr * wd)
                mc.lerp_(gc, 1 - b1)
                vc.mul_(b2).addcmul_(gc, gc, value=1 - b2)
                torch.sqrt(vc, out=gc)                  # gc is dead from here: reuse it as the denominator
                gc.div_(bc2_sqrt).add_(eps)
                wc.addcdiv_(mc, gc, value=-step_size)
                if none_idx:
                    for j, (sm, sv) in zip(none_idx, saved):
                        mv_[j].copy_(sm); vv_[j].copy_(sv)
                    keep = [j for j in range(len(cl)) if j not in set(none_idx)]
                    wv_ = self._views(wc, 0, cl)
                    if keep:
                        torch._foreach_copy_([cl[j] for j in keep], [wv_[j] for j in keep])
                else:
                    torch._foreach_copy_(cl, self._views(wc, 0, cl))
        if hasattr(torch, "neuron"):
            torch.neuron.synchronize()  # type: ignore[attr-defined]
        return None


def build_optimizer(model: nn.Module, cfg: Config):
    tc = cfg.training
    params = [p for p in model.parameters() if p.requires_grad]
    on_neuron = bool(params) and params[0].device.type == "neuron"
    mode = tc.optimizer_mode
    foreach = False
    if mode == "flat":
        # AdamW on one padded flat fp32 buffer per group. Same
        # DTensor/plain split as foreach (the flat copies must not mix the two); the same class runs on CPU.
        dt = [p for p in params if hasattr(p, "to_local")]
        pl = [p for p in params if not hasattr(p, "to_local")]
        param_arg = [{"params": x} for x in (dt, pl) if x]
        opt = _FlatAdamW(param_arg, lr=tc.lr, betas=tuple(tc.betas), eps=tc.eps, weight_decay=tc.weight_decay)
    elif on_neuron:
        every = max(1, tc.optimizer_sync_every)  # params per chunk between device syncs (see _ChunkSyncAdamW)
        param_arg = [{"params": params[i : i + every]} for i in range(0, len(params), every)]
        if mode == "foreach":
            cls, foreach = _OneSyncAdamW, True
            split = []
            for g in param_arg:
                dt = [p for p in g["params"] if hasattr(p, "to_local")]
                pl = [p for p in g["params"] if not hasattr(p, "to_local")]
                split += [{"params": x} for x in (dt, pl) if x]
            param_arg = split
        elif mode == "chunk_sync":
            cls = _ChunkSyncAdamW
        else:
            raise ValueError(f"optimizer_mode {mode!r}: chunk_sync | foreach | flat")
        opt = cls(param_arg, lr=tc.lr, betas=tuple(tc.betas), eps=tc.eps, weight_decay=tc.weight_decay,
                  foreach=foreach)  # foreach groups never mix DTensor and plain Tensor (split above)
    else:
        opt = torch.optim.AdamW(params, lr=tc.lr, betas=tuple(tc.betas), eps=tc.eps, weight_decay=tc.weight_decay,
                                foreach=False)

    def lr_lambda(step: int) -> float:
        if step < tc.warmup_steps:
            return (step + 1) / max(1, tc.warmup_steps)
        prog = (step - tc.warmup_steps) / max(1, tc.max_steps - tc.warmup_steps)
        return 0.5 * (1.0 + math.cos(math.pi * min(1.0, prog)))

    sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_lambda)
    return opt, sched


def materialize_optimizer_state(opt: torch.optim.Optimizer, device) -> int:
    """Create AdamW's per-parameter state up front, exactly as ``Adam._init_group`` would (CPU fp32
    ``step``, ``zeros_like`` moments), then sync the device once.

    On the Neuron async runtime the optimizer's own lazy init races: ``exp_avg = zeros_like(p)``
    immediately followed by ``exp_avg.lerp_(grad)`` can hit ``Tensor not bound: lazy alloc kAlloc may
    not have executed``. Allocating here and syncing once makes the first ``step()`` find bound
    tensors; the state layout is identical, so resume/compare are unaffected. Skips parameters that
    already have state (a resumed run). Returns the number of parameters initialised.
    """
    n = 0
    for group in opt.param_groups:
        assert not group.get("amsgrad") and not group.get("capturable") and not group.get("fused"), (
            "materialize_optimizer_state mirrors the plain AdamW state layout only"
        )
        for p in group["params"]:
            if not p.requires_grad:
                continue
            state = opt.state[p]
            if len(state):
                continue
            state["step"] = torch.tensor(0.0, dtype=torch.float32)
            state["exp_avg"] = torch.zeros_like(p, memory_format=torch.preserve_format)
            state["exp_avg_sq"] = torch.zeros_like(p, memory_format=torch.preserve_format)
            n += 1
    if str(device) == "neuron" and n:
        torch.neuron.synchronize()  # type: ignore[attr-defined]
    return n


# ----------------------------------------------------------------------------------------- step
def training_step(
    model: nn.Module, cfg: Config, clip: dict, gen: torch.Generator, device
) -> tuple[torch.Tensor, float]:
    """One micro-step: draw sigma/eps, pack, forward, loss (fp32). Returns ``(loss, sigma)``. No backward."""
    mc, dc, fc = cfg.model, cfg.data, cfg.diffusion
    x0 = clip["latent"].to(torch.float32)
    sigma = float(sample_sigma(fc.sigma_kind, 1, shift=fc.train_shift, generator=gen)[0])
    eps = torch.randn(x0.shape, generator=gen, dtype=torch.float32)
    pk = pack(
        clip["text_ids"],
        x0,
        sigma,
        cond_frames=int(clip.get("cond_latent_frames", 0)),
        eps=eps,
        is_x0=True,
        fps=float(clip.get("fps", dc.fps)),
        temporal_margin=dc.temporal_margin,
        head_dim=mc.head_dim,
        rope_theta=mc.rope_theta,
        mrope_section=mc.mrope_section,
    )
    out = model(*pk.model_inputs(device))  # [Nv,192]
    pred = unpatchify(out.to(torch.float32), pk.grid)
    loss = flow_loss(pred, pk.target.to(pred.device), pk.noisy_frame_mask.to(pred.device))
    return loss, sigma


# ----------------------------------------------------------------------------------- checkpoint
def _to_saveable(sd: dict) -> dict:
    """DTensors → local shards (``ProcessGroup`` is unpicklable), tensors → CPU."""
    out = {}
    for k, v in sd.items():
        if isinstance(v, dict):
            out[k] = _to_saveable(v)
        elif isinstance(v, DTensor):
            out[k] = v.to_local().detach().cpu()
        elif torch.is_tensor(v):
            out[k] = v.detach().cpu()
        else:
            out[k] = v
    return out


def _load_into(dst: dict, src: dict) -> None:
    """Copy saved tensors into the live state dict (DTensor local shards included), in place."""
    for k, v in src.items():
        if isinstance(v, dict):
            _load_into(dst[k], v)
        elif torch.is_tensor(v):
            tgt = dst[k]
            (tgt.to_local() if isinstance(tgt, DTensor) else tgt).copy_(v.to(tgt.dtype))
        else:
            dst[k] = v


def _relift_optimizer_state(opt) -> None:
    """After ``load_state_dict`` from local shards, wrap state tensors of DTensor params back into DTensors."""
    for group in opt.param_groups:
        for p in group["params"]:
            if not isinstance(p, DTensor) or p not in opt.state:
                continue
            st = opt.state[p]
            for k, v in list(st.items()):
                if torch.is_tensor(v) and v.ndim > 0 and not isinstance(v, DTensor):
                    st[k] = DTensor.from_local(
                        v.to(p.to_local().device), p.device_mesh, p.placements, run_check=False
                    )


def save_checkpoint(
    ckpt_dir: str | Path,
    step: int,
    model,
    opt,
    sched,
    sampler: ResumableSampler,
    gen: torch.Generator,
    state: TrainState,
    cfg: Config,
    rank: int,
) -> Path:
    d = Path(ckpt_dir) / f"step_{step:08d}"
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "step": step,
        "skipped": state.skipped,
        "model": _to_saveable(model.state_dict()),
        "opt": _to_saveable(opt.state_dict()),
        "sched": sched.state_dict(),
        "sampler": sampler.state_dict(),
        "rng": torch.get_rng_state(),
        "gen": gen.get_state(),
        "cfg": cfg.to_dict(),
    }
    tmp = d / f"rank{rank:04d}.pt.tmp"
    torch.save(payload, tmp)
    tmp.replace(d / f"rank{rank:04d}.pt")
    dist = _dist()
    if dist is not None:
        dist.barrier()
    if rank == 0:
        (d / "COMPLETE").write_text(
            json.dumps({"step": step, "world": dist.get_world_size() if dist else 1})
        )
    return d


_STEP_DIR = re.compile(r"step_\d{8}")


def check_ckpt_disk(model: nn.Module, ckpt_dir: str | Path, step: int, max_steps: int, save_every: int, world: int) -> int:
    """Checkpoints are never deleted, so the run needs room for every save it will make: per rank the local
    parameter shard plus two fp32 AdamW moments, times ``world`` (one disk), times the saves left. Raises before
    the first step when the free space is short. Returns the bytes needed."""
    saves = max_steps // save_every - step // save_every + (1 if max_steps % save_every else 0)
    per_rank = sum(
        getattr(p, "_local_tensor", p).numel() * (p.element_size() + 8) for p in model.parameters() if p.requires_grad
    )
    need = per_rank * world * max(saves, 0)
    root = Path(ckpt_dir)
    root.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(root).free
    if need > free:
        raise RuntimeError(
            f"{root}: {saves} checkpoint(s) x {per_rank * world / 2**30:.1f} GiB = {need / 2**30:.0f} GiB needed, "
            f"{free / 2**30:.0f} GiB free — checkpoints are never deleted; free the disk, raise save_every, or lower "
            f"max_steps"
        )
    return need


def latest_step(ckpt_dir: str | Path) -> int | None:
    """Newest ``step_N`` with a ``COMPLETE`` marker. Anything else in ``ckpt_dir`` besides ``metrics.jsonl`` is an
    error: the directory belongs to one run."""
    root = Path(ckpt_dir)
    if not root.exists():
        return None
    steps = []
    for p in root.iterdir():
        if p.name == "metrics.jsonl" or p.name.startswith("."):
            continue
        if not (p.is_dir() and _STEP_DIR.fullmatch(p.name)):
            raise ValueError(f"{root}: unexpected entry {p.name!r} in training.ckpt_dir (expected step_NNNNNNNN/)")
        if (p / "COMPLETE").exists():
            steps.append(int(p.name[5:]))
    return max(steps) if steps else None


# Keys a resumed run may change without touching the trained state: where things are written, how often
# they are logged, and performance knobs. Everything else in cfg must equal what the checkpoint was saved with.
_RESUME_FREE = {
    "device", "checkpoint_dir", "data.clips_dir", "training.ckpt_dir", "training.save_every", "training.log_every",
    "parallel.compile", "parallel.reshard_after_forward", "parallel.reshard_after_forward_blocks",
    "parallel.fsdp_forward_prefetch", "parallel.fsdp_backward_prefetch", "training.skip_step_abort_after",
}


def _flat(d: dict, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flat(v, key + "."))
        else:
            out[key] = list(v) if isinstance(v, (list, tuple)) else v
    return out


def check_resume_cfg(saved: dict | None, current: dict, step_dir: Path) -> None:
    """Raise unless every non-free key of the current config equals the checkpoint's. A YAML change that the
    resumed optimizer/scheduler would silently ignore (lr, betas, warmup, max_steps ...) or that changes the
    math (model, data geometry, diffusion, tp/fsdp, mixed precision) is an error, not a surprise."""
    if not saved:
        raise ValueError(f"{step_dir}: checkpoint carries no cfg — cannot verify it matches this run")
    a, b = _flat(saved), _flat(current)
    diff = [k for k in b if k.split(".")[0] != "inference" and k not in _RESUME_FREE and a.get(k, "<missing>") != b[k]]
    if diff:
        lines = "\n  ".join(f"{k}: checkpoint {a.get(k, '<missing>')!r} != config {b[k]!r}" for k in diff)
        raise ValueError(
            f"{step_dir}: resume config differs from the checkpoint's in {len(diff)} key(s) — start a new "
            f"training.ckpt_dir for a new recipe, or restore the values:\n  {lines}"
        )


def load_checkpoint_dir(
    ckpt_dir: str | Path,
    step: int,
    model,
    opt,
    sched,
    sampler: ResumableSampler,
    gen: torch.Generator,
    rank: int,
    world: int,
    cfg: Config | None = None,
) -> TrainState:
    d = Path(ckpt_dir) / f"step_{step:08d}"
    if not (d / "COMPLETE").exists():
        raise FileNotFoundError(
            f"{d} has no COMPLETE marker — refusing to resume from a partial checkpoint"
        )
    present = sorted(d.glob("rank*.pt"))
    if len(present) != world:
        raise FileNotFoundError(f"{d}: {len(present)} rank files for world {world}")
    p = torch.load(d / f"rank{rank:04d}.pt", map_location="cpu", weights_only=False)
    if cfg is not None:
        check_resume_cfg(p.get("cfg"), cfg.to_dict(), d)
    live = model.state_dict()
    _load_into(live, p["model"])
    opt.load_state_dict(p["opt"])
    _relift_optimizer_state(opt)
    sched.load_state_dict(p["sched"])
    sampler.load_state_dict(p["sampler"])
    torch.set_rng_state(p["rng"])
    gen.set_state(p["gen"])
    return TrainState(step=int(p["step"]), skipped=int(p["skipped"]))


# ------------------------------------------------------------------------------------------ fit
def fit(
    model: nn.Module,
    cfg: Config,
    *,
    tp_group=None,
    dp_rank: int = 0,
    dp_world: int = 1,
    rank: int = 0,
    device="cpu",
    dataset: ClipDataset | None = None,
    max_steps: int | None = None,
) -> TrainState:
    from pwm.parallel.grad import clip_grad_norm  # noqa: PLC0415
    from pwm.parallel.tp import reduce_tp_partial_grads, sync_tp_replicated_grads  # noqa: PLC0415

    tc = cfg.training
    max_steps = tc.max_steps if max_steps is None else max_steps
    dist = _dist()
    world = dist.get_world_size() if dist else 1
    dataset = dataset or ClipDataset(cfg.data.clips_dir, expect=asdict(cfg.data))
    sampler = ResumableSampler(len(dataset), dp_rank, dp_world, seed=tc.seed)
    gen = torch.Generator().manual_seed(
        tc.seed * 7919 + dp_rank
    )  # dp ranks draw different sigma/eps; tp ranks identical
    opt, sched = build_optimizer(model, cfg)
    state = TrainState()
    if tc.ckpt_dir and (last := latest_step(tc.ckpt_dir)) is not None:
        state = load_checkpoint_dir(tc.ckpt_dir, last, model, opt, sched, sampler, gen, rank, world, cfg=cfg)
        _log(f"resumed from step {state.step} ({tc.ckpt_dir})", rank)
    _abort_after = tc.skip_step_abort_after
    _log(f"skip guard: refuse steps with grad norm > {tc.skip_step_grad_norm} from step 0"
         + (f"; abort after {_abort_after} consecutive refusals" if _abort_after is not None else "; never aborts"), rank)
    if not tc.ckpt_dir:
        _log("WARNING: training.ckpt_dir is empty -- this run writes NO checkpoints", rank)
    consecutive_skips = 0
    if tc.ckpt_dir:
        check_ckpt_disk(model, tc.ckpt_dir, state.step, max_steps, tc.save_every, world)
    materialize_optimizer_state(opt, device)  # no-op after a resume (state already loaded)
    model.train()
    _clear_op_tracking(device)
    fallback_checked = False
    _mem("fit:start", device, rank, dist)
    metrics_path = Path(tc.ckpt_dir) / "metrics.jsonl" if tc.ckpt_dir else None
    t_prev = time.time()
    while state.step < max_steps:
        # Scalars that feed collectives live on `device`: the neuron c10d backend rejects host
        # tensors ("Expected neuron device, got cpu"); gloo/CPU is unchanged (device="cpu").
        step_loss = torch.zeros((), dtype=torch.float32, device=device)
        sigmas = []
        skip = False
        for _ in range(tc.grad_accum):
            clip = dataset[sampler.next_index()]
            loss, sigma = training_step(model, cfg, clip, gen, device)
            _mem("after-forward", device, rank, dist)
            sigmas.append(sigma)
            # Every rank must run the same collectives: agree on finiteness BEFORE backward
            # (a rank that skips backward desyncs FSDP's reduce-scatter and hangs/aborts the job).
            finite = torch.tensor(
                1.0 if bool(torch.isfinite(loss.detach()).item()) else 0.0, device=device
            )
            if dist is not None:
                dist.all_reduce(finite, op=dist.ReduceOp.MIN)
            if finite.item() == 0.0:
                skip = True
                step_loss += float("nan")
                break
            (loss / tc.grad_accum).backward()
            _mem("after-backward", device, rank, dist)
            step_loss += loss.detach().float() / tc.grad_accum
        if skip:
            total_norm = float("nan")
            ok = torch.tensor(0.0, device=device)
        else:
            if tp_group is not None:
                reduce_tp_partial_grads(model, tp_group)
                if cfg.parallel.tp_sync_replicated_grads:
                    sync_tp_replicated_grads(model, tp_group)
            total_norm = clip_grad_norm(list(model.parameters()), tc.max_grad_norm)
            _mem("after-clip", device, rank, dist)
            ok = torch.tensor(
                float(math.isfinite(total_norm) and total_norm <= tc.skip_step_grad_norm),
                device=device,
            )
            if dist is not None:
                dist.all_reduce(ok, op=dist.ReduceOp.MIN)
        if ok.item() > 0:
            opt.step()
            sched.step()
            _mem("after-opt", device, rank, dist)
            consecutive_skips = 0
        else:
            state.skipped += 1
            consecutive_skips += 1
            _log(
                f"step {state.step + 1}: SKIPPED (loss={step_loss.item():.4g} gnorm={total_norm:.4g}; "
                f"{state.skipped} total, {consecutive_skips} consecutive)",
                rank,
            )
            if _abort_after is not None and consecutive_skips >= _abort_after:
                # A sustained storm = a diverged model; checkpoint and stop.
                state.step += 1
                if tc.ckpt_dir:
                    save_checkpoint(tc.ckpt_dir, state.step, model, opt, sched, sampler, gen, state, cfg, rank)
                raise RuntimeError(
                    f"fit: {consecutive_skips} consecutive skipped steps (grad norm > {tc.skip_step_grad_norm} or "
                    f"non-finite) at step {state.step} -- the run has diverged; aborting"
                    + (" (checkpoint written)" if tc.ckpt_dir else "")
                    + ". Set training.skip_step_abort_after to null to disable this guard.")
        opt.zero_grad(set_to_none=True)
        state.step += 1
        if not fallback_checked:
            _check_no_fallback_ops(device, rank)
            fallback_checked = True
        if dist is not None:  # global mean loss for the log line (SUM/world: gloo has no AVG)
            dist.all_reduce(step_loss, op=dist.ReduceOp.SUM)
            step_loss /= world
        now = time.time()
        state.step_times.append(now - t_prev)
        if state.step % tc.log_every == 0:
            rec = {
                "step": state.step,
                "loss": round(step_loss.item(), 6),
                "gnorm": round(float(total_norm), 6),
                "lr": sched.get_last_lr()[0],
                "sigma": [round(s, 4) for s in sigmas],
                "step_time": round(now - t_prev, 3),
                "skipped": state.skipped,
                "gnorm_spread": round(float(getattr(clip_grad_norm, "last_spread", 0.0)), 8),
            }
            _log(
                f"fit: step {state.step}/{max_steps} loss {rec['loss']:.5f} gnorm {rec['gnorm']:.4f} lr {rec['lr']:.2e} {rec['step_time']:.2f}s",
                rank,
            )
            if metrics_path is not None and rank == 0:
                metrics_path.parent.mkdir(parents=True, exist_ok=True)
                with metrics_path.open("a") as f:
                    f.write(json.dumps(rec) + "\n")
        t_prev = now
        if tc.ckpt_dir and (state.step % tc.save_every == 0 or state.step == max_steps):
            save_checkpoint(
                tc.ckpt_dir, state.step, model, opt, sched, sampler, gen, state, cfg, rank
            )
            _log(f"saved checkpoint step {state.step}", rank)
    return state


if __name__ == "__main__":
    # Hardware-free smoke: tiny model, single process, 3 steps, checkpoint → resume → identical step-4 loss.
    import tempfile

    from pwm.configs.config import ModelConfig
    from pwm.model.mot import NanoMoT
    from pwm.model.patchify import LATENT_CHANNELS

    mc = ModelConfig(
        layers=1,
        dim=64,
        heads=4,
        kv_heads=2,
        head_dim=16,
        ffn_dim=96,
        vocab_size=64,
        mrope_section=(4, 2, 2),
        gradient_checkpointing=False,
    )
    with tempfile.TemporaryDirectory() as td:
        for i in range(4):
            torch.save(
                {
                    "latent": torch.randn(1, LATENT_CHANNELS, 2, 4, 6),
                    "text_ids": torch.randint(0, 64, (5,)),
                    "cond_latent_frames": 0,
                },
                Path(td) / f"c{i}.pt",
            )
        cfg = Config(model=mc)
        cfg.data.latent_t, cfg.data.height, cfg.data.width, cfg.data.text_len = 2, 64, 96, 5
        (
            cfg.training.max_steps,
            cfg.training.save_every,
            cfg.training.ckpt_dir,
            cfg.training.warmup_steps,
        ) = 4, 3, str(Path(td) / "ckpt"), 1
        cfg.training.lr = 1e-3
        torch.manual_seed(0)
        m = NanoMoT(mc)
        st = fit(m, cfg, dataset=ClipDataset(td), max_steps=3)
        assert st.step == 3 and latest_step(cfg.training.ckpt_dir) == 3
        import shutil

        shutil.copytree(cfg.training.ckpt_dir, Path(td) / "ckpt_b")  # snapshot holding only step 3
        w3 = {k: v.clone() for k, v in m.state_dict().items()}
        fit(
            m, cfg, dataset=ClipDataset(td), max_steps=4
        )  # control: resume 3 -> 4 in the same process
        w4 = {k: v.clone() for k, v in m.state_dict().items()}
        torch.manual_seed(0)
        m2 = NanoMoT(mc)
        cfg.training.ckpt_dir = str(Path(td) / "ckpt_b")
        st2 = fit(m2, cfg, dataset=ClipDataset(td), max_steps=4)  # fresh model: resume 3 -> 4
        assert st2.step == 4 and latest_step(cfg.training.ckpt_dir) == 4
        assert all(torch.equal(w4[k], v) for k, v in m2.state_dict().items()), (
            "resume is not bit-exact"
        )
        assert not all(torch.equal(w3[k], v) for k, v in m2.state_dict().items())
    print("train smoke OK")
