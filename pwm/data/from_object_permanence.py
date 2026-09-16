"""Rendered ``object_permanence`` samples → the JSONL manifest ``pwm.cli encode`` reads.

Every sample directory ``<root>/<task>_task/<task>_NNNN/`` holds ``input_video.mp4`` (60 frames, 24 fps),
``target_video.mp4`` (the 60 frames that follow) and ``prompt.txt``. One row per sample:

    {"id": "<task>_NNNN", "videos": [input, target], "caption": <prompt.txt>, "fps": 24.0,
     "skip_frames": 3, "cond_latent_frames": 15}

``skip_frames`` 3 + ``latent_t`` 30 (117 px frames) = the last 57 input frames as the clean prefix and all 60
target frames as the prediction span (paper Section 4.1; ``configs/wrop.yaml``). Rows go to stdout.

    python -m pwm.data.from_object_permanence /data/renders > rows.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

__all__ = ["rows"]


def rows(root: str | Path):
    root = Path(root)
    for sdir in sorted(p for p in root.glob("*_task/*") if p.is_dir()):
        inp, tgt, prompt = sdir / "input_video.mp4", sdir / "target_video.mp4", sdir / "prompt.txt"
        if not (inp.exists() and tgt.exists() and prompt.exists()):
            print(f"skip {sdir}: incomplete sample", file=sys.stderr)
            continue
        yield {
            "id": sdir.name,
            "videos": [str(inp), str(tgt)],
            "caption": prompt.read_text(encoding="utf-8").strip(),
            "fps": 24.0,
            "skip_frames": 3,
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
