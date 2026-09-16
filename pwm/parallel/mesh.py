"""Process-group lifecycle + the 2-D ``("dp", "tp")`` DeviceMesh.

Backend: **gloo** for CPU runs; **``"neuron"``** on device — the c10d backend ``torch_neuronx``
registers, which binds each torchrun rank to its own core from ``LOCAL_RANK``. Never export
``NEURON_RT_NUM_CORES`` / ``NEURON_RT_VISIBLE_CORES`` around a multi-rank run (ranks fight over cores).

Rank order is row-major ``rank = dp_idx * tp + tp_idx``, so each contiguous block of ``tp`` ranks is one
TP group — ``mesh["tp"]`` feeds ``tp.parallelize``, ``mesh["dp"]`` feeds ``fsdp.apply_fsdp2``.
"""

from __future__ import annotations

import datetime
import logging
import os

import torch.distributed as dist

logger = logging.getLogger("pwm.parallel.mesh")

__all__ = ["PG_TIMEOUT_S", "init_dist", "is_dist_initialized", "world_size", "build_mesh"]

# gloo's stock collective timeout is 30 min — shorter than one full-depth (36L) first-touch NEFF
# compile, and ranks do not share the compile cache. The first rank to finish blocks on a
# collective until the slowest compiles, so the run would die on compile skew. Default 6 h.
PG_TIMEOUT_S = float(os.environ.get("PWM_PG_TIMEOUT_S", 6 * 3600))


def _is_torchrun_launch() -> bool:
    return all(k in os.environ for k in ("RANK", "WORLD_SIZE", "LOCAL_RANK"))


def init_dist(backend: str | None = None) -> bool:
    """Init the default process group from torchrun env vars. Idempotent; False when not torchrun.

    ``backend`` ``None``/``"gloo"`` → gloo. ``"neuron"`` → the ``torch_neuronx`` c10d backend
    (raises if ``torch_neuronx`` is not importable — on-device only).
    """
    if is_dist_initialized():
        return True
    if not _is_torchrun_launch():
        return False
    backend = backend or "gloo"
    if backend == "neuron":
        import torch_neuronx  # noqa: F401, PLC0415 — registers the "neuron" backend

    _set_default_timeout()
    dist.init_process_group(backend=backend, timeout=datetime.timedelta(seconds=PG_TIMEOUT_S))
    logger.info("init_dist: backend=%s world=%s rank=%s pg_timeout=%.0fs", backend,
                os.environ["WORLD_SIZE"], os.environ["RANK"], PG_TIMEOUT_S)  # fmt: skip
    return True


def _set_default_timeout() -> None:
    """``DeviceMesh`` creates the dp/tp sub-groups with ``new_group(timeout=None)``, which reads
    ``distributed_c10d.default_pg_timeout`` (30 min stock) — not the default group's timeout. The block-level
    TP all-reduces and FSDP all-gathers run on those sub-groups, so the compile-skew protection has to be
    set here too."""
    from torch.distributed import distributed_c10d  # noqa: PLC0415

    distributed_c10d.default_pg_timeout = datetime.timedelta(seconds=PG_TIMEOUT_S)


def is_dist_initialized() -> bool:
    return dist.is_available() and dist.is_initialized()


def world_size() -> int:
    return dist.get_world_size() if is_dist_initialized() else 1


# ------------------------------------------------------------------------------------------ mesh
def build_mesh(fsdp: int, tp: int, device_type: str = "cpu"):
    """2-D ``(dp=fsdp, tp)`` DeviceMesh; needs ``world == fsdp * tp`` (degree-1 axes are fine)."""
    from torch.distributed.device_mesh import init_device_mesh  # noqa: PLC0415

    if fsdp * tp != world_size():
        raise ValueError(f"mesh needs world == fsdp*tp: world={world_size()} fsdp={fsdp} tp={tp}")
    _set_default_timeout()  # also when the default group was created elsewhere (tests' spawn_gloo)
    return init_device_mesh(device_type, (fsdp, tp), mesh_dim_names=("dp", "tp"))


if __name__ == "__main__":
    # Hardware-free smoke: single-process gloo world of 1, (1,1) mesh, helpers.
    os.environ.update(MASTER_ADDR="127.0.0.1", MASTER_PORT="29511", RANK="0", WORLD_SIZE="1",
                      LOCAL_RANK="0")  # fmt: skip
    assert _is_torchrun_launch() and init_dist() and init_dist()  # idempotent
    m = build_mesh(1, 1, device_type="cpu")
    assert m.mesh_dim_names == ("dp", "tp") and m["tp"].size() == 1 and m["dp"].size() == 1
    assert m["tp"].get_local_rank() == 0 and isinstance(m["tp"].get_group(), dist.ProcessGroup)
    try:
        build_mesh(2, 1)
        raise AssertionError("world mismatch must raise")
    except ValueError:
        pass
    dist.destroy_process_group()
    assert not is_dist_initialized() and world_size() == 1
    print("mesh smoke OK")
