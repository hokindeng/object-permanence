"""Choose five visibly different, factorially informative samples per generator.

Consecutive sample IDs are a poor visual-review set: depending on the mixed-
radix stride, one or more task factors can remain fixed.  This planner searches
one complete design cycle and greedily covers both levels of every task factor,
all three camera cells, five colours, and as many member scripts as the five-
sample budget permits.  The result is deterministic and stores real dataset
sample indices; it does not invent a review-only randomization path.
"""

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


def _record(spec: dict, index: int, member_count: int) -> dict:
    member = index % member_count
    design = sample_factorial_diversity(spec, index, member, member_count)
    factors = design["factorial"]["factors"]
    return {
        "index": index,
        "member": member,
        "color": factors["object_color"]["level"],
        "view": factors["camera_angle"]["level"],
        "task": tuple(
            (name, factors[name]["level"])
            for name in sorted(spec["parameters"])
        ),
    }


def plan_indices(spec: dict, member_count: int, count: int = 5) -> list[int]:
    """Return a deterministic, high-coverage set of real sample indices."""
    probe = sample_factorial_diversity(spec, 0, 0, member_count)
    cycle = probe["factorial"]["cycle_length"]
    candidates = [_record(spec, index, member_count) for index in range(cycle)]
    selected = []
    covered_task = set()
    covered_views = set()
    covered_members = set()
    used_colors = set()

    # Starting at the all-low task cell maximizes contrast with subsequent
    # selections and makes the plan stable when new nuisance factors are added.
    def initial_key(item):
        return (
            sum(level for _, level in item["task"]),
            item["member"], item["view"], item["index"],
        )

    first = min(candidates, key=initial_key)
    for _ in range(count):
        if selected:
            available = [item for item in candidates if item["color"] not in used_colors]
            if not available:
                available = candidates

            def gain(item):
                new_task = sum(token not in covered_task for token in item["task"])
                new_view = item["view"] not in covered_views
                new_member = item["member"] not in covered_members
                task_distance = max(
                    (sum(a != b for (_, a), (_, b) in zip(item["task"], old["task"]))
                     for old in selected),
                    default=0,
                )
                return (
                    new_task * 100 + new_view * 30 + new_member * 20 + task_distance * 4,
                    new_task, new_view, new_member, task_distance,
                    -item["index"],
                )

            item = max(available, key=gain)
        else:
            item = first
        selected.append(item)
        candidates.remove(item)
        covered_task.update(item["task"])
        covered_views.add(item["view"])
        covered_members.add(item["member"])
        used_colors.add(item["color"])
    return [item["index"] for item in selected]


def plan_all() -> dict:
    result = {}
    for task_dir in sorted(TASKS.glob("G[0-9]*_*"), key=task_number):
        manifest = json.loads((task_dir / "task.json").read_text())
        indices = plan_indices(manifest["diversity"], len(manifest["member_scripts"]))
        result[manifest["id"]] = {"task": manifest["name"], "indices": indices}
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument("--render-out", type=Path)
    parser.add_argument("--blender")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--preview", type=int, choices=(0, 1), default=1)
    args = parser.parse_args()
    plan = plan_all()
    payload = json.dumps(plan, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload)
    else:
        print(payload, end="")
    if not args.render_out:
        return 0
    if not args.blender:
        parser.error("--blender is required with --render-out")

    cases = [
        (generator_id, sample_index)
        for generator_id, item in plan.items()
        for sample_index in item["indices"]
    ]
    environment = os.environ.copy()
    environment.setdefault("OP_FORCE_EEVEE", "1")
    lock = threading.Lock()
    completed = 0

    def render(case):
        generator_id, sample_index = case
        command = [
            sys.executable, "-m", "object_permanence", "generate",
            "--task", generator_id, "--per", "1", "--start", str(sample_index),
            "--preview", str(args.preview), "--blender", args.blender,
            "--out", str(args.render_out),
        ]
        return case, subprocess.run(command, env=environment, text=True, capture_output=True)

    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(render, case) for case in cases]
        for future in as_completed(futures):
            case, result = future.result()
            with lock:
                completed += 1
                status = "ok" if result.returncode == 0 else "FAIL"
                print(f"[{completed}/{len(cases)}] {status} {case[0]} sample={case[1]}", flush=True)
            if result.returncode:
                failures.append((case, result.stdout, result.stderr))
    for case, stdout, stderr in failures:
        print(f"FAILED {case}\n{stdout}\n{stderr}", file=sys.stderr)
    print(f"cases={len(cases)} failures={len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
