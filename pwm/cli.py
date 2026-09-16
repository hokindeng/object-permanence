"""pwm CLI — ``train | infer | bench | encode | consolidate``.

    python -m pwm.cli train  cfg.yaml [--max-steps N] [--compile/--no-compile] [--no-relaunch]
    python -m pwm.cli infer  cfg.yaml --prompt "..." --out out.mp4 [--v2v clip.pt] [--steps 35 --guidance 6 --seed 1234]
    python -m pwm.cli bench  cfg.yaml [--warmup 3 --steps 20] [--infer-steps 5] [--no-train]
    python -m pwm.cli encode --manifest rows.jsonl --out clips/ --ckpt ~/weights/Cosmos3-Nano [...]
    python -m pwm.cli consolidate cfg.yaml --step N --out /path/to/ckpt_dir [--dtype bf16]

Parallel degrees live only in the YAML ``parallel:`` block. When ``tp*fsdp > 1`` and the process is
not already under torchrun it re-execs itself as ``torchrun --nproc_per_node=<world> -m pwm.cli
<same argv>`` before importing torch (the Neuron runtime is not fork-safe); ``--no-relaunch`` skips that.
``infer`` relaunches with ``tp`` ranks only (``dp = 1``).

Fail fast: the config is validated at load (``Config.validate``); ``train`` and ``infer`` refuse to run without
``checkpoint_dir`` (only ``bench`` builds a random-init model, and says so); ``train`` refuses
``fsdp: 1`` with a bf16 model (no fp32 master copy — every small update would round away); a torchrun world that
does not equal ``tp × fsdp`` (``tp`` for infer) is an error, not a silent override of the YAML degrees.

``build_model``: meta ``NanoMoT`` → TP plan → checkpoint streamed one FSDP2 unit at a time (fp32 shards /
bf16 all-gather / fp32 reduce) → optional per-block ``torch.compile(backend="neuron", dynamic=False)``.
Without FSDP (``dp = 1``) the model is loaded in ``model.dtype`` (bf16) — a 36-layer ``infer`` on 4 cores.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import time
from pathlib import Path

__all__ = ["main", "build_model"]


# ------------------------------------------------------------------------------- torchrun glue
def _free_port() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return str(s.getsockname()[1])


def _entry() -> list[str]:
    """How to re-invoke the current program: ``-m <module>`` when run with ``python -m``, else its path."""
    import __main__  # noqa: PLC0415

    spec = getattr(__main__, "__spec__", None)
    if spec is not None and getattr(spec, "name", None):
        return ["-m", spec.name]
    return [sys.argv[0]]


def _under_torchrun() -> bool:
    return all(k in os.environ for k in ("RANK", "WORLD_SIZE", "LOCAL_RANK"))


def _maybe_relaunch(cfg, args) -> None:
    if _under_torchrun():
        return
    dp = cfg.parallel.fsdp if args.command in ("train", "bench") else 1
    world = cfg.parallel.tp * dp
    if world <= 1:
        return
    if args.no_relaunch:
        raise SystemExit(
            f"pwm: tp={cfg.parallel.tp} x dp={dp} needs {world} torchrun ranks but --no-relaunch was given "
            f"and this is not a torchrun process (RANK/WORLD_SIZE/LOCAL_RANK unset)"
        )
    cmd = [
        sys.executable,
        "-m",
        "torch.distributed.run",
        f"--nproc_per_node={world}",
        "--master_port",
        _free_port(),
        *_entry(),
        *sys.argv[1:],
    ]
    print(
        f"pwm: parallel world = {world} (tp={cfg.parallel.tp} fsdp={dp}) — relaunching under torchrun\n"
        f"  $ {' '.join(cmd)}",
        flush=True,
    )
    os.execv(sys.executable, cmd)  # never returns (same interpreter -> its torch.distributed.run)


# ------------------------------------------------------------------------------------- build
def build_model(
    cfg,
    *,
    device: str,
    do_compile: bool | None = None,
    interleave_load: bool = True,
    allow_random_init: bool = False,
    dp: int | None = None,
):
    """Returns ``(model, ctx)`` with ``ctx = {rank, world, mesh, tp_group, dp_rank, dp_world}``.

    ``dp`` is the FSDP degree this command expects (``parallel.fsdp`` by default; ``infer`` passes 1) and the
    torchrun world must equal ``tp × dp`` exactly. Without ``checkpoint_dir`` the model is a seeded random init
    — only with ``allow_random_init`` (``bench``), announced on rank 0; ``train``/``infer`` raise.
    """
    import torch  # noqa: PLC0415

    from pwm.model.load import load_checkpoint  # noqa: PLC0415
    from pwm.model.mot import _DTYPES, NanoMoT  # noqa: PLC0415

    cfg.validate()
    rank, world = int(os.environ.get("RANK", 0)), int(os.environ.get("WORLD_SIZE", 1))
    tp = cfg.parallel.tp
    dp_expected = cfg.parallel.fsdp if dp is None else dp
    if world != tp * dp_expected:
        raise ValueError(
            f"WORLD_SIZE {world} != tp {tp} x dp {dp_expected}: "
            + ("run under torchrun (drop --no-relaunch)" if world == 1 else "torchrun --nproc_per_node must equal the YAML degrees")
        )
    if not cfg.checkpoint_dir and not allow_random_init:
        raise ValueError("checkpoint_dir is empty: refusing to build a random-init model for train/infer "
                         "(set checkpoint_dir in the YAML or pass --ckpt)")
    ctx = {
        "rank": rank,
        "world": world,
        "mesh": None,
        "tp_group": None,
        "dp_rank": 0,
        "dp_world": 1,
    }
    if device == "neuron":
        import torch_neuronx  # noqa: F401, PLC0415
    mesh = None
    if world > 1:
        from pwm.parallel.mesh import build_mesh, init_dist  # noqa: PLC0415

        init_dist("neuron" if device == "neuron" else "gloo")
        mesh = build_mesh(dp_expected, tp, device)
        ctx.update(mesh=mesh, dp_rank=mesh["dp"].get_local_rank(), dp_world=dp_expected)
        if tp > 1:
            ctx["tp_group"] = mesh["tp"].get_group()
    mc = cfg.model
    use_fsdp = mesh is not None and mesh["dp"].size() > 1
    use_mp = use_fsdp and cfg.parallel.fsdp_mixed_precision
    load_dtype = torch.float32 if use_mp else _DTYPES[mc.dtype]
    if cfg.checkpoint_dir:
        with torch.device("meta"):
            model = NanoMoT(mc)
    else:  # no weights: seeded random init (bench) — identical on every rank
        if rank == 0:
            print(f"build_model: NO WEIGHTS — seeded random init ({mc.layers} layers, seed {cfg.training.seed}); "
                  "bench/test only", flush=True)
        torch.manual_seed(cfg.training.seed)
        model = NanoMoT(mc).to_dtype(load_dtype).to(device)
    if tp > 1:
        from pwm.parallel.tp import parallelize  # noqa: PLC0415

        parallelize(model, mesh["tp"])
    # With FSDP the checkpoint is streamed one unit at a time from inside apply_fsdp2 (load a
    # block's TP shard -> fully_shard it -> next), so the device never holds the whole unsharded
    # model. `interleave_load=False` keeps the load-everything-first order; both orders give identical shards.
    interleave = use_fsdp and bool(cfg.checkpoint_dir) and interleave_load
    if cfg.checkpoint_dir and not interleave:
        load_checkpoint(model, cfg.weights_dir or cfg.checkpoint_dir, dtype=load_dtype, device=device)
    if use_fsdp:  # TP already applied above (before the load)
        from pwm.parallel.fsdp import apply_fsdp2, fsdp2_mp_policy  # noqa: PLC0415

        apply_fsdp2(
            model,
            mesh["dp"],
            mp_policy=fsdp2_mp_policy() if use_mp else None,
            reshard_after_forward=cfg.parallel.reshard_after_forward,
            reshard_after_forward_blocks=cfg.parallel.reshard_after_forward_blocks,
            materialize=(
                (lambda pre: load_checkpoint(model, cfg.weights_dir or cfg.checkpoint_dir, dtype=load_dtype, device=device, prefix=pre))
                if interleave else None
            ),
        )
        pc = cfg.parallel
        if pc.fsdp_forward_prefetch or pc.fsdp_backward_prefetch:
            from pwm.parallel.fsdp import configure_fsdp_prefetch  # noqa: PLC0415

            done = configure_fsdp_prefetch(model, forward_prefetch=pc.fsdp_forward_prefetch,
                                           backward_prefetch=pc.fsdp_backward_prefetch)  # fmt: skip
            if rank == 0:
                print(f"fsdp prefetch: {done}", flush=True)
    if cfg.checkpoint_dir:
        left = [n for n, p in model.named_parameters() if p.device.type == "meta"]
        assert not left, f"parameters still on meta after load: {left[:5]}"
    if cfg.parallel.compile if do_compile is None else do_compile:
        from pwm.parallel.fsdp import compile_blocks  # noqa: PLC0415

        compile_blocks(model, backend="neuron" if device == "neuron" else "inductor")
    return model, ctx


def _synthetic_clip(cfg, gen):
    import torch  # noqa: PLC0415

    from pwm.model.patchify import LATENT_CHANNELS  # noqa: PLC0415

    d = cfg.data
    latent = torch.randn(1, LATENT_CHANNELS, d.latent_t, d.height // 16, d.width // 16, generator=gen)
    ids = torch.randint(0, cfg.model.vocab_size, (d.text_len,), generator=gen)
    return {
        "latent": latent,
        "text_ids": ids,
        "cond_latent_frames": d.cond_latent_frames,
        "fps": d.fps,
    }


# ---------------------------------------------------------------------------------- commands
def cmd_train(cfg, args) -> None:
    from pwm.training.train import fit  # noqa: PLC0415

    if cfg.parallel.fsdp == 1 and cfg.model.dtype != "float32":
        raise ValueError(
            "train with parallel.fsdp = 1 keeps the parameters and the AdamW state in model.dtype "
            f"({cfg.model.dtype}) — no fp32 master copy, small updates round away. "
            "Use parallel.fsdp > 1 (fp32 shards, bf16 all-gather) or model.dtype: float32."
        )
    model, ctx = build_model(cfg, device=cfg.device, do_compile=args.compile)
    fit(
        model,
        cfg,
        tp_group=ctx["tp_group"],
        dp_rank=ctx["dp_rank"],
        dp_world=ctx["dp_world"],
        rank=ctx["rank"],
        device=cfg.device,
        max_steps=args.max_steps,
    )


def cmd_bench(cfg, args) -> None:
    """Synthetic-data throughput: warmup + timed optimizer steps at the config geometry, plus inference forwards."""
    import statistics  # noqa: PLC0415

    import torch  # noqa: PLC0415

    from pwm.data.dataset import ClipDataset  # noqa: PLC0415
    from pwm.training.train import fit  # noqa: PLC0415

    model, ctx = build_model(cfg, device=cfg.device, do_compile=args.compile, allow_random_init=True)
    gen = torch.Generator().manual_seed(cfg.training.seed)
    # ResumableSampler hands rank r position cursor+r, so the pool must hold >= dp_world clips.
    clips = [_synthetic_clip(cfg, gen) for _ in range(max(4, ctx["dp_world"]))]
    if args.no_train:  # time inference forwards only
        args.warmup, args.steps = 0, 0

    class _Synthetic(ClipDataset):  # in-memory stand-in with the same interface
        def __init__(self):
            self.files = [Path(f"synthetic{i}.pt") for i in range(len(clips))]

        def __getitem__(self, i):
            return dict(clips[i])

    cfg.training.ckpt_dir = ""
    cfg.training.log_every = 1
    tok_per_step = (
        (cfg.data.text_len + cfg.data.latent_t * (cfg.data.height // 32) * (cfg.data.width // 32))
        * cfg.training.grad_accum
        * ctx["dp_world"]
    )
    st = None
    if args.warmup or args.steps:
        # One fit call for warmup+steps; fit records wall time per optimizer step in state.step_times.
        # (One fit call per timed step would restart TrainState and the optimizer each time.)
        t0 = time.time()
        st = fit(
            model,
            cfg,
            tp_group=ctx["tp_group"],
            dp_rank=ctx["dp_rank"],
            dp_world=ctx["dp_world"],
            rank=ctx["rank"],
            device=cfg.device,
            dataset=_Synthetic(),
            max_steps=args.warmup + args.steps,
        )
        assert st.step == args.warmup + args.steps and len(st.step_times) == st.step, (st.step, len(st.step_times))
        t_warm = sum(st.step_times[: args.warmup])
        times = st.step_times[args.warmup :]
        t_total = time.time() - t0
        if ctx["rank"] == 0 and times:
            med = statistics.median(times)
            print(
                f"bench: warmup {args.warmup} steps {t_warm:.1f}s | timed {args.steps} steps: median {med:.3f} s/step, "
                f"min {min(times):.3f}, max {max(times):.3f} | {tok_per_step / med:.0f} tok/s global | skipped {st.skipped}"
                f" | fit total {t_total:.1f}s",
                flush=True,
            )
    if args.infer_steps:
        from pwm.data.pack import pack  # noqa: PLC0415

        model.eval()
        clip = clips[0]
        pk = pack(
            clip["text_ids"],
            clip["latent"],
            0.5,
            cond_frames=clip["cond_latent_frames"],
            fps=cfg.data.fps,
            temporal_margin=cfg.data.temporal_margin,
            head_dim=cfg.model.head_dim,
            rope_theta=cfg.model.rope_theta,
            mrope_section=cfg.model.mrope_section,
        )
        inputs = pk.model_inputs(cfg.device)
        with torch.no_grad():
            model(*inputs)  # warm
            ft = []
            for _ in range(args.infer_steps):
                t = time.time()
                out = model(*inputs)
                _ = out.float().cpu()
                ft.append(time.time() - t)
        if ctx["rank"] == 0:
            print(
                f"bench: inference forward median {statistics.median(ft):.3f} s (×2 per CFG step)",
                flush=True,
            )


def cmd_infer(cfg, args) -> None:
    import torch  # noqa: PLC0415

    from pwm.data.pack import load_tokenizer, pad_text_ids, text_ids_for  # noqa: PLC0415
    from pwm.inference.decode import (  # noqa: PLC0415
        decode_latent,
        load_vae,
        to_uint8_frames,
        write_mp4,
    )
    from pwm.inference.sample import Prompt, SampleConfig, initial_latent, unipc_sample  # noqa: PLC0415
    from pwm.model.patchify import LATENT_CHANNELS  # noqa: PLC0415

    model, ctx = build_model(cfg, device=cfg.device, do_compile=args.compile, dp=1)
    model.eval()
    tok = load_tokenizer(str(Path(cfg.checkpoint_dir) / "text_tokenizer"))
    neg = args.negative_prompt if args.negative_prompt is not None else cfg.inference.negative_prompt
    d = cfg.data
    # Both prompts are padded to the trained text_len (one compiled shape, training positions); the pads are
    # hidden from the vision rows via text_valid. Too long is an error (pad_text_ids).
    if tok.pad_token_id is None:
        raise ValueError("tokenizer has no pad token; cannot pad prompts to data.text_len")
    cond_ids, uncond_ids = (
        Prompt(*pad_text_ids(text_ids_for(tok, p), d.text_len, tok.pad_token_id)) for p in (args.prompt, neg)
    )
    x0_clean, cond_frames = None, 0
    if args.v2v:
        blob = torch.load(args.v2v, map_location="cpu", weights_only=False)
        x0_clean, cond_frames = (
            blob["latent"].float(),
            int(blob.get("cond_latent_frames", d.cond_latent_frames)),
        )
    shape = (
        tuple(x0_clean.shape)
        if x0_clean is not None
        else (1, LATENT_CHANNELS, d.latent_t, d.height // 16, d.width // 16)
    )
    pick = lambda flag, key: key if flag is None else flag  # noqa: E731 — 0 is a value, not "unset"
    sc = SampleConfig(
        steps=pick(args.steps, cfg.inference.steps),
        guidance=pick(args.guidance, cfg.inference.guidance),
        shift=pick(args.shift, cfg.inference.shift),
        seed=pick(args.seed, cfg.inference.seed),
        cond_frames=cond_frames,
        fps=d.fps,
        temporal_margin=d.temporal_margin,
    )
    lat0 = initial_latent(shape, sc.seed, x0_clean, cond_frames)
    t0 = time.time()
    latent = unipc_sample(
        model, cond_ids, uncond_ids, lat0, sc, device=cfg.device, x0_clean=x0_clean
    )
    if ctx["rank"] != 0:
        return
    print(
        f"sampled {tuple(latent.shape)} in {time.time() - t0:.1f}s ({sc.steps} UniPC steps): std {latent.std():.3f}",
        flush=True,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {"latent": latent, "prompt": args.prompt, "text_valid": cond_ids.valid, "cfg": cfg.to_dict()},
        out.with_suffix(".pt"),
    )
    if out.suffix == ".mp4":
        vae = load_vae(str(Path(cfg.checkpoint_dir) / "vae"))
        frames = to_uint8_frames(decode_latent(latent, vae))
        write_mp4(frames, str(out), d.fps)
        print(
            f"wrote {out} ({frames.shape[0]} frames {frames.shape[2]}x{frames.shape[1]})",
            flush=True,
        )


def cmd_consolidate(cfg, args) -> None:
    """Per-rank shards of ``step_N`` → one diffusers-layout checkpoint dir ``--out`` that ``infer --ckpt``
    loads unchanged (``pwm.model.consolidate``). CPU, single process (``--no-relaunch`` implied)."""
    import torch  # noqa: PLC0415

    from pwm.model.consolidate import consolidate_dir  # noqa: PLC0415

    d = Path(cfg.training.ckpt_dir) / f"step_{args.step:08d}"
    st = consolidate_dir(
        d, args.out, tp=cfg.parallel.tp, fsdp=cfg.parallel.fsdp, layers=cfg.model.layers,
        base_ckpt=cfg.checkpoint_dir, dtype={"bf16": torch.bfloat16, "fp32": torch.float32}[args.dtype],
    )
    print(f"consolidated {d} -> {args.out} ({st})")


# --------------------------------------------------------------------------------------- main
def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="pwm", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("config", help="YAML (partial override of pwm/configs/config.py defaults)")
        p.add_argument("--ckpt", default=None, help="override checkpoint_dir")
        p.add_argument("--weights", default=None, help="override weights_dir (transformer weights, e.g. a PWM-WROP download)")
        p.add_argument("--device", default=None, help="override device (cpu|neuron)")
        p.add_argument("--compile", dest="compile", action="store_true", default=None)
        p.add_argument("--no-compile", dest="compile", action="store_false")
        p.add_argument("--no-relaunch", action="store_true")

    p = sub.add_parser("train")
    common(p)
    p.add_argument("--max-steps", type=int, default=None)
    p = sub.add_parser("bench")
    common(p)
    p.add_argument("--warmup", type=int, default=3)
    p.add_argument("--steps", type=int, default=20)
    p.add_argument("--infer-steps", type=int, default=0)
    p.add_argument("--no-train", action="store_true", help="skip fit; only time inference forwards")
    p = sub.add_parser("infer")
    common(p)
    p.add_argument("--prompt", required=True)
    p.add_argument("--negative-prompt", default=None)
    p.add_argument("--out", default="out/sample.mp4")
    p.add_argument(
        "--v2v", default=None, help="clip .pt with 'latent' + 'cond_latent_frames' (clean prefix)"
    )
    p.add_argument("--steps", type=int, default=None)
    p.add_argument("--guidance", type=float, default=None)
    p.add_argument("--shift", type=float, default=None)
    p.add_argument("--seed", type=int, default=None)
    p = sub.add_parser("consolidate")  # CPU, single process: no device/compile/relaunch flags
    p.add_argument("config", help="the YAML the shards were trained with")
    p.add_argument("--ckpt", default=None, help="override checkpoint_dir (the base the shards were trained from)")
    p.add_argument("--step", type=int, required=True)
    p.add_argument("--out", required=True, help="output checkpoint DIR (diffusers layout)")
    p.add_argument("--dtype", default="bf16", choices=["bf16", "fp32"])
    sub.add_parser("encode", add_help=False)  # only so `--help` lists it: main() dispatches encode before parsing
    return ap


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("encode", "consolidate"):
        # CPU-only commands: under the container python a bare `import torch` autoloads torch_neuronx,
        # which dies without a device. Set before the first torch import; an explicit value wins.
        os.environ.setdefault("TORCH_DEVICE_BACKEND_AUTOLOAD", "0")
    if argv and argv[0] == "encode":
        from pwm.data.encode import main as encode_main  # noqa: PLC0415

        encode_main(argv[1:])
        return
    args = _parser().parse_args(argv)
    from pwm.configs.config import Config  # noqa: PLC0415 (torch-free)

    cfg = Config.from_yaml(args.config)
    if args.ckpt:
        cfg.checkpoint_dir = args.ckpt
    if getattr(args, "weights", None):
        cfg.weights_dir = args.weights
    if args.command in ("train", "bench", "infer"):
        if args.device:
            cfg.device = args.device
        cfg.validate()  # once, before the relaunch fans out to tp*fsdp ranks
        if args.command != "bench" and not cfg.checkpoint_dir:
            raise SystemExit(f"pwm {args.command}: checkpoint_dir is empty (YAML key or --ckpt) — no weights, no run")
        _maybe_relaunch(cfg, args)
    {"train": cmd_train, "bench": cmd_bench, "infer": cmd_infer, "consolidate": cmd_consolidate}[
        args.command
    ](cfg, args)


if __name__ == "__main__":
    main()
