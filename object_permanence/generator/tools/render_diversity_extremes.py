"""Render low/high task-factor witnesses for every generator member script."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from object_permanence.generator.core.diversity import sample_factorial_diversity


TASKS = Path(__file__).resolve().parents[1] / "tasks"


def task_number(path: Path) -> int:
    return int(re.match(r"G(\d+)", path.name).group(1))


def factor_levels(spec: dict, sample_index: int, member_slot: int, member_count: int) -> tuple[int, ...]:
    record = sample_factorial_diversity(spec, sample_index, member_slot, member_count)
    factors = record["factorial"]["factors"]
    return tuple(factors[name]["level"] for name in sorted(spec["parameters"]))


def extreme_indices(spec: dict, member_slot: int, member_count: int) -> tuple[int, int]:
    """Return earliest all-low and maximally-high cells for one member script."""
    candidates = range(member_slot, 1000, member_count)
    low_index = None
    high_index = None
    high_score = -1
    for sample_index in candidates:
        levels = factor_levels(spec, sample_index, member_slot, member_count)
        if low_index is None and not any(levels):
            low_index = sample_index
        score = sum(levels)
        if score > high_score:
            high_score = score
            high_index = sample_index
        if low_index is not None and score == len(levels):
            break
    if low_index is None or high_index is None:
        raise ValueError(f"could not locate extreme cells for member {member_slot}/{member_count}")
    return low_index, high_index


def planned_cases() -> list[tuple[str, int, str, int]]:
    cases = []
    for task_dir in sorted(TASKS.glob("G[0-9]*_*"), key=task_number):
        manifest = json.loads((task_dir / "task.json").read_text())
        spec = manifest["diversity"]
        member_count = len(manifest["member_scripts"])
        for member_slot in range(member_count):
            low, high = extreme_indices(spec, member_slot, member_count)
            cases.append((manifest["id"], low, "low", member_slot))
            if high != low:
                cases.append((manifest["id"], high, "high", member_slot))
    return cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--blender", required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--preview", type=int, choices=(0, 1), default=1)
    args = parser.parse_args()
    cases = planned_cases()
    env = os.environ.copy()
    env.setdefault("OP_FORCE_EEVEE", "1")
    lock = threading.Lock()
    completed = 0

    def run(case):
        generator_id, sample_index, level, member_slot = case
        command = [
            sys.executable, "-m", "object_permanence", "generate",
            "--task", generator_id,
            "--per", "1",
            "--start", str(sample_index),
            "--preview", str(args.preview),
            "--blender", args.blender,
            "--out", args.out,
        ]
        result = subprocess.run(command, env=env, text=True, capture_output=True)
        return case, result

    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(run, case) for case in cases]
        for future in as_completed(futures):
            case, result = future.result()
            with lock:
                completed += 1
                generator_id, sample_index, level, member_slot = case
                status = "ok" if result.returncode == 0 else "FAIL"
                print(
                    f"[{completed}/{len(cases)}] {status} {generator_id} "
                    f"member={member_slot} {level} sample={sample_index}",
                    flush=True,
                )
            if result.returncode:
                failures.append((case, result.stdout, result.stderr))
    for case, stdout, stderr in failures:
        print(f"FAILED {case}\n{stdout}\n{stderr}", file=sys.stderr)
    print(f"cases={len(cases)} failures={len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

