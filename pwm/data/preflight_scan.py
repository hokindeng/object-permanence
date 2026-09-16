"""Pre-launch integrity scan of a clips directory.

A single truncated / non-zip ``<id>.pt`` kills all ranks the moment the sampler draws it -- with per-rank
checkpoints every ``save_every`` steps that costs up to ``save_every`` steps plus a restart. Scan first:

    python -m pwm.data.preflight_scan /out/clips [--procs 48]

Exit 0 = every file opens as a zip with a clean CRC table; exit 1 = bad files (listed, and written to
``<clips_dir>/.preflight_bad.txt``). Zip-level only (~fast); it does not deserialize the tensors.
"""

from __future__ import annotations

import argparse
import os
import sys
import zipfile
from multiprocessing import Pool
from pathlib import Path


def _check(path: str) -> tuple[str, str] | None:
    try:
        if os.path.getsize(path) < 1024:
            return (path, "tiny")
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()
            return (path, f"crc:{bad}") if bad is not None else None
    except Exception as e:  # noqa: BLE001
        return (path, f"{type(e).__name__}: {str(e)[:60]}")


def scan(clips_dir: str | Path, procs: int = 32) -> list[tuple[str, str]]:
    files = sorted(str(p) for p in Path(clips_dir).glob("*.pt"))
    if not files:
        raise FileNotFoundError(f"no *.pt under {clips_dir}")
    with Pool(procs) as pool:
        bad = [r for r in pool.imap_unordered(_check, files, chunksize=64) if r]
    return sorted(bad)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("clips_dir")
    ap.add_argument("--procs", type=int, default=32)
    a = ap.parse_args(argv)
    bad = scan(a.clips_dir, a.procs)
    n = len(list(Path(a.clips_dir).glob("*.pt")))
    if bad:
        out = Path(a.clips_dir) / ".preflight_bad.txt"
        out.write_text("\n".join(f"{p}\t{why}" for p, why in bad) + "\n")
        print(f"preflight: {len(bad)} / {n} clips BAD -> {out}", flush=True)
        for p, why in bad[:20]:
            print(f"  {p}: {why}")
        return 1
    print(f"preflight: {n} clips OK", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
