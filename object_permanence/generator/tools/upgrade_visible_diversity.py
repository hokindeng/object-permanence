"""Upgrade legacy task-factor ranges from bookkeeping noise to visible variation.

This migration intentionally touches only a parameter whose name and source
binding exactly match the recipe currently emitted by
``plan_task_diversity.py``. A coincidentally equal numeric range is not enough:
authored generator parameters must remain untouched. The resulting low/high
factorial cells change primary geometry or dynamics by 18 percent and secondary
geometry by 16 percent. These bands are intentionally obvious in a five-sample
review and must be followed by rendered semantic and collision QA.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from object_permanence.generator.core.diversity import (
    VISIBLE_PRIMARY_BOUNDS,
    VISIBLE_SECONDARY_DYNAMICS_BOUNDS,
    VISIBLE_SECONDARY_GEOMETRY_BOUNDS,
)
from object_permanence.generator.tools.plan_task_diversity import plan_task


TASKS = Path(__file__).resolve().parents[1] / "tasks"
SKIP_GENERATORS = {"G94", "G100", "G122"}

# _factor_value() selects the 25th and 75th percentiles. Therefore 0.64..1.36
# yields actual multipliers 0.82 and 1.18, rather than exercising the extrema.
UPGRADES = {
    (0.96, 1.04): VISIBLE_PRIMARY_BOUNDS,
    (0.97, 1.03): VISIBLE_SECONDARY_GEOMETRY_BOUNDS,
    (0.76, 1.24): VISIBLE_PRIMARY_BOUNDS,
    (0.80, 1.20): VISIBLE_SECONDARY_GEOMETRY_BOUNDS,
}


def upgraded_bounds(name: str, rule: dict) -> tuple[float, float] | None:
    if rule.get("type") != "uniform":
        return None
    current = (round(float(rule.get("min", 0)), 4), round(float(rule.get("max", 0)), 4))
    if name == "secondary_dynamics_scale" and current in {
        (0.97, 1.03), (0.80, 1.20), (0.76, 1.24)
    }:
        return VISIBLE_SECONDARY_DYNAMICS_BOUNDS
    return UPGRADES.get(current)


def upgrade_manifest(path: Path, write: bool = False) -> list[tuple[str, tuple, tuple]]:
    manifest = json.loads(path.read_text())
    if manifest.get("id") in SKIP_GENERATORS:
        return []
    try:
        planned_parameters = plan_task(path.parent)["diversity"]["parameters"]
    except Exception:
        # A migration must fail closed: when planner provenance cannot be
        # reconstructed, changing an authored range would be irreversible.
        return []
    changes = []
    for name, rule in manifest.get("diversity", {}).get("parameters", {}).items():
        planned_rule = planned_parameters.get(name)
        if not isinstance(planned_rule, dict) or rule.get("binding") != planned_rule.get("binding"):
            continue
        bounds = upgraded_bounds(name, rule)
        if bounds is None:
            continue
        old = (rule["min"], rule["max"])
        rule["min"], rule["max"] = bounds
        changes.append((name, old, bounds))
    if write and changes:
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return changes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    changed_manifests = 0
    changed_parameters = 0
    for path in sorted(TASKS.glob("G[0-9]*_*/task.json")):
        changes = upgrade_manifest(path, write=args.write)
        if not changes:
            continue
        changed_manifests += 1
        changed_parameters += len(changes)
        summary = ", ".join(
            f"{name} {old[0]}..{old[1]} -> {new[0]}..{new[1]}"
            for name, old, new in changes
        )
        print(f"{path.parent.name}: {summary}")
    print(f"changed_manifests={changed_manifests} changed_parameters={changed_parameters}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
