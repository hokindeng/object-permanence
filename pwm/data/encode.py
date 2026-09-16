"""Offline encode: ``(video, caption)`` rows → one static-shape clip ``.pt`` each (the ``ClipDataset`` format).

Per row: read the first ``4*(T-1)+1`` frames (Wan VAE causal ``4n+1`` rule; a shorter source is padded by
repeating its last frame), resize + center-crop to ``height×width`` (bilinear, antialiased), scale to ``[-1, 1]``,
encode with the Wan2.2 VAE (deterministic mean), normalise ``(z - mean) / std``; tokenise the caption to exactly
``text_len`` templated tokens (``pack.fit_text_ids``). Existing outputs are skipped (resumable); ``clips.jsonl``
is written last as the completeness marker. Runs on CPU.

Manifest row (JSONL): ``{"id": str, "video": path | "videos": [paths], "caption": str, "fps"?: float,
"native_fps"?: float (nearest-frame resample native_fps → fps), "skip_frames"?: int (leading frames dropped
before the ``4n+1`` cut), "cond_latent_frames"?: int}``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from pwm.inference.decode import latent_stats, load_vae

__all__ = ["main"]


def probe_fps(path: str) -> float:
    """Container frame rate via imageio/FFMPEG metadata."""
    import imageio.v2 as imageio  # noqa: PLC0415

    with imageio.get_reader(path, format="FFMPEG") as r:
        fps = r.get_meta_data().get("fps")
    if not fps:
        raise ValueError(f"{path}: container reports no fps; set native_fps in the manifest row")
    return float(fps)


def read_frames(path: str, max_frames: int | None = None) -> np.ndarray:
    """mp4 → ``[T, H, W, 3]`` uint8 via imageio/FFMPEG (no torchvision)."""
    import imageio.v2 as imageio  # noqa: PLC0415

    frames = []
    with imageio.get_reader(path, format="FFMPEG") as r:
        for f in r:
            frames.append(np.asarray(f)[..., :3])
            if max_frames is not None and len(frames) >= max_frames:
                break
    assert frames, f"no frames decoded from {path}"
    return np.stack(frames)


def resize_center_crop(frames: torch.Tensor, th: int, tw: int) -> torch.Tensor:
    """``[T,3,H,W]`` float → ``[T,3,th,tw]``: scale = max(tw/W, th/H), resize, center crop."""
    _, _, oh, ow = frames.shape
    scale = max(tw / ow, th / oh)
    rh, rw = int(round(oh * scale)), int(round(ow * scale))
    frames = F.interpolate(
        frames, size=(rh, rw), mode="bilinear", align_corners=False, antialias=True
    )
    top, left = (rh - th) // 2, (rw - tw) // 2
    return frames[:, :, top : top + th, left : left + tw]


def frames_to_video_tensor(
    frames_u8: np.ndarray, latent_t: int, height: int, width: int
) -> tuple[torch.Tensor, int]:
    """``[T,H,W,3]`` uint8 → ``[1,3,4(T-1)+1,height,width]`` in ``[-1,1]``, plus #frames used. A source shorter
    than the geometry is an error (a freeze-frame tail is not a video); trim ``--latent-t`` or drop the row."""
    out_px = 4 * (latent_t - 1) + 1
    if len(frames_u8) < out_px:
        raise ValueError(f"{len(frames_u8)} frames < {out_px} needed for latent_t={latent_t}")
    v = torch.from_numpy(frames_u8[:out_px]).float().permute(0, 3, 1, 2)
    v = resize_center_crop(v, height, width) / 127.5 - 1.0
    return v.permute(1, 0, 2, 3).unsqueeze(0).contiguous(), out_px


@torch.no_grad()
def encode_normalized(video: torch.Tensor, vae) -> torch.Tensor:
    """``[1,3,T_px,H,W]`` in ``[-1,1]`` → normalised latent ``[1,48,T,H/16,W/16]`` fp32."""
    t_px = video.shape[2]
    assert t_px == 1 or (t_px - 1) % 4 == 0, f"T_px={t_px} must be 4n+1"
    z = vae.encode(video, return_dict=False)[0].mode()
    mean, std = latent_stats(vae)
    return (z.to(torch.float32) - mean) / std


def encode_row(
    row: dict,
    vae,
    tok,
    *,
    latent_t: int,
    height: int,
    width: int,
    text_len: int,
    default_fps: float,
) -> dict:
    from pwm.data.pack import fit_text_ids  # noqa: PLC0415

    skip = int(row.get("skip_frames", 0))
    need = 4 * (latent_t - 1) + 1 + skip
    srcs = row.get("videos") or [row["video"]]
    native_fps, target_fps = row.get("native_fps"), float(row.get("fps", default_fps))
    if native_fps is None:
        # No declared source rate: the container's must equal the target, or the clip's time axis (RoPE t from
        # `fps`) would be wrong by the ratio. Declare native_fps to resample instead.
        probed = [probe_fps(v) for v in srcs]
        off = [f for f in probed if abs(f - target_fps) > 1e-3]
        if off:
            raise ValueError(
                f"{row['id']}: source fps {probed} != target {target_fps}; set native_fps in the manifest row to resample"
            )
    if native_fps and abs(float(native_fps) - target_fps) > 1e-6:
        # temporal resample (nearest source frame at each target time), so e.g. a 30 fps 5 s clip becomes
        # 120 frames at 24 fps and fits the t30 geometry whole; read everything first, then pick
        frames = np.concatenate([read_frames(v) for v in srcs])
        idx = np.round(np.arange(len(frames) * target_fps / float(native_fps)) * float(native_fps) / target_fps).astype(int)
        frames = frames[np.clip(idx, 0, len(frames) - 1)][:need]
    elif len(srcs) > 1:
        # segments concatenated in pixel space (v2v: conditioning clip followed by its continuation;
        # with cond_latent_frames set, the loss covers only the continuation)
        frames = np.concatenate([read_frames(v) for v in srcs])[:need]
    else:
        frames = read_frames(srcs[0], max_frames=need)
    video, n_real = frames_to_video_tensor(frames[skip:], latent_t, height, width)
    latent = encode_normalized(video, vae)
    assert torch.isfinite(latent).all(), f"non-finite latent for {row['id']}"
    return {
        "latent": latent.cpu(),
        "text_ids": fit_text_ids(tok, row["caption"], text_len),
        "cond_latent_frames": int(row.get("cond_latent_frames", 0)),
        "caption": row["caption"],
        "src": " || ".join(srcs),
        "fps": target_fps,
        "real_px_frames": n_real,
    }


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="encode (video, caption) rows into static-shape clips")
    ap.add_argument(
        "--manifest",
        required=True,
        help="JSONL rows: id, video|videos, caption[, fps, native_fps, skip_frames, cond_latent_frames]",
    )
    ap.add_argument("--out", required=True, help="output directory for <id>.pt + clips.jsonl")
    ap.add_argument(
        "--ckpt", required=True, help="Cosmos3-Nano dir (uses vae/ and text_tokenizer/)"
    )
    ap.add_argument("--latent-t", type=int, default=30)
    ap.add_argument("--height", type=int, default=288)
    ap.add_argument("--width", type=int, default=512)
    ap.add_argument("--text-len", type=int, default=128)
    ap.add_argument("--fps", type=float, default=24.0)
    ap.add_argument("--threads", type=int, default=0)
    args = ap.parse_args(argv)
    if args.threads:
        torch.set_num_threads(args.threads)
    assert args.height % 32 == 0 and args.width % 32 == 0, (
        "height/width must be multiples of 32 (VAE 16 × patch 2)"
    )
    from pwm.data.pack import load_tokenizer  # noqa: PLC0415

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = [
        json.loads(line) for line in Path(args.manifest).read_text().splitlines() if line.strip()
    ]
    vae = load_vae(str(Path(args.ckpt) / "vae"))
    tok = load_tokenizer(str(Path(args.ckpt) / "text_tokenizer"))
    done = []
    for i, row in enumerate(rows):
        dst = out / f"{row['id']}.pt"
        if dst.exists():
            done.append({"clip": dst.name, "id": row["id"]})
            continue
        clip = encode_row(
            row,
            vae,
            tok,
            latent_t=args.latent_t,
            height=args.height,
            width=args.width,
            text_len=args.text_len,
            default_fps=args.fps,
        )
        tmp = dst.with_suffix(".pt.tmp")
        torch.save(clip, tmp)
        tmp.replace(dst)
        done.append({"clip": dst.name, "id": row["id"]})
        print(
            f"[{i + 1}/{len(rows)}] {dst.name} latent {tuple(clip['latent'].shape)} text_len {clip['text_ids'].shape[0]}",
            flush=True,
        )
    (out / "clips.jsonl").write_text("".join(json.dumps(d) + "\n" for d in done))
    print(f"wrote {len(done)} clips + clips.jsonl to {out}")


if __name__ == "__main__":
    # Hardware-free smoke of the pixel pipeline (no VAE): padding, crop geometry, value range.
    frames = (np.random.rand(15, 100, 180, 3) * 255).astype(np.uint8)
    v, n = frames_to_video_tensor(frames, latent_t=4, height=64, width=96)
    assert v.shape == (1, 3, 13, 64, 96) and n == 13 and v.min() >= -1 and v.max() <= 1
    try:
        frames_to_video_tensor(frames[:9], latent_t=4, height=64, width=96)
        raise AssertionError("short source must raise")
    except ValueError:
        pass
    print("encode smoke OK")
