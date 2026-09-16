"""Rendered ``object_permanence`` samples → the JSONL manifest ``pwm.cli encode`` reads.

Every sample directory ``<root>/<task>_task/<task>_NNNN/`` holds ``input_video.mp4`` (60 frames at 24 fps;
a few tasks 90), ``target_video.mp4`` (the frames that follow) and ``prompt.txt``. One row per sample:

    {"id": "<task>_NNNN", "videos": [input, target], "caption": <prompt.txt>, "fps": 24.0,
     "skip_frames": <input frames - 57>, "cond_latent_frames": 15}

``skip_frames`` drops the head of the input so that the **last 57 input frames** are the clean prefix and the
first 60 target frames are the prediction span (117 px frames = ``latent_t`` 30; paper Section 4.1;
``configs/wrop.yaml``). The input's frame count comes from the same imageio/FFMPEG reader ``pwm.data.encode``
decodes with (the container ships no ffmpeg binary of its own). Rows go to stdout.

    python -m pwm.data.from_object_permanence /data/renders > rows.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

__all__ = ["rows", "frame_count"]

COND_FRAMES = 57


def frame_count(video: Path) -> int:
    """Number of frames in ``video`` (imageio/FFMPEG, the reader ``encode.read_frames`` uses)."""
    import imageio.v2 as imageio  # noqa: PLC0415

    with imageio.get_reader(str(video), format="FFMPEG") as r:
        return int(r.count_frames())


def rows(root: str | Path):
    root = Path(root)
    for sdir in sorted(p for p in root.glob("*_task/*") if p.is_dir()):
        inp, tgt, prompt = sdir / "input_video.mp4", sdir / "target_video.mp4", sdir / "prompt.txt"
        if not (inp.exists() and tgt.exists() and prompt.exists()):
            print(f"skip {sdir}: incomplete sample", file=sys.stderr)
            continue
        n_in = frame_count(inp)
        if n_in < COND_FRAMES:
            print(f"skip {sdir}: input has {n_in} frames < {COND_FRAMES}", file=sys.stderr)
            continue
        yield {
            "id": sdir.name,
            "videos": [str(inp.resolve()), str(tgt.resolve())],
            "caption": prompt.read_text(encoding="utf-8").strip(),
            "fps": 24.0,
            "skip_frames": n_in - COND_FRAMES,
            "cond_latent_frames": 15,
        }


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("root", help="dataset root (contains <task>_task/ directories)")
    args = ap.parse_args(argv)
    n = 0
    for r in rows(args.root):
        print(json.dumps(r))
        n += 1
    print(f"{n} rows", file=sys.stderr)


if __name__ == "__main__":
    main()
