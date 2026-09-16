"""Plan or apply conservative source-bound task diversity across all tasks.

The planner only considers uniquely assigned numeric constants with names that
identify scene geometry or dynamics.  Camera, lighting, render, timing, and
ground-plane constants are deliberately excluded.  The generated manifest
bindings remain explicit and are subsequently checked by ``audit --manifests``
and by Blender smoke renders; this script is not a substitute for those gates.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from object_permanence.generator.core.diversity import (
    VISIBLE_PRIMARY_BOUNDS,
    VISIBLE_SECONDARY_DYNAMICS_BOUNDS,
    VISIBLE_SECONDARY_GEOMETRY_BOUNDS,
)


TASKS = Path(__file__).resolve().parents[1] / "tasks"

OBJECT_WORDS = (
    "BALL", "SPHERE", "CUBE", "BLOCK", "CAR", "BOX", "CUP", "DOOR",
    "PANEL", "SCREEN", "COVER", "WALL", "HOLE", "TUNNEL", "RAMP",
    "TRACK", "DISC", "CYLINDER", "OCCLUD", "PLATFORM", "GATE", "FLAP",
    "LID", "DRAWER", "CABINET", "PENDULUM", "RING", "OBJECT", "PADDLE",
    "RAIL", "BARRIER", "CHUTE", "FUNNEL", "ROD", "ARM", "BEAM", "TEE",
    "CONTAINER", "ROLLER", "TRAP", "BRIDGE", "SLOT", "PEG", "DRUM",
    "DOME", "SLEEVE", "CURTAIN", "SHUTTER", "BLIND", "SHELF", "SUPPORT",
)
DIMENSION_WORDS = (
    "RADIUS", "WIDTH", "HEIGHT", "LENGTH", "DEPTH", "THICK", "SIZE",
    "DIAMETER", "CLEARANCE", "SPACING", "GAP", "OFFSET", "DISTANCE",
)
DYNAMIC_WORDS = (
    "SPEED", "VELOCITY", "RESTITUTION", "FRICTION", "IMPULSE", "FORCE",
    "GRAVITY", "OMEGA", "ANGULAR", "MASS", "SHIFT", "TRAVEL",
)
EXCLUDE_WORDS = (
    "CAM", "LIGHT", "SUN", "LAMP", "FPS", "FRAME", "RESOLUTION",
    "SAMPLE", "SEED", "GROUND", "FLOOR", "TABLE", "BASE", "WORLD", "SHADOW", "BEVEL",
    "FONT", "TEXT", "LABEL", "MARKER", "EPS", "TOLERANCE", "DURATION",
    "START_FRAME", "END_FRAME", "REVEAL_FRAME", "CONTACT_FRAME",
)


def numeric_assignments(source: str) -> list[tuple[str | None, str, float]]:
    """Return literal numeric assignments unique within their function scope."""
    found: list[tuple[str | None, str, float]] = []

    class Visitor(ast.NodeVisitor):
        scope: str | None = None

        def visit_FunctionDef(self, node):
            previous, self.scope = self.scope, node.name
            self.generic_visit(node)
            self.scope = previous

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Assign(self, node):
            self._record(node.targets, node.value)
            self.generic_visit(node)

        def visit_AnnAssign(self, node):
            self._record([node.target], node.value)
            self.generic_visit(node)

        def _record(self, targets, value):
            number = None
            if isinstance(value, ast.Constant) and isinstance(value.value, (int, float)):
                number = float(value.value)
            elif (
                isinstance(value, ast.UnaryOp)
                and isinstance(value.op, (ast.USub, ast.UAdd))
                and isinstance(value.operand, ast.Constant)
                and isinstance(value.operand.value, (int, float))
            ):
                number = float(value.operand.value) * (-1 if isinstance(value.op, ast.USub) else 1)
            if number is None or number == 0:
                return
            for target in targets:
                if isinstance(target, ast.Name):
                    found.append((self.scope, target.id, number))

    Visitor().visit(ast.parse(source))
    counts = Counter((scope, name) for scope, name, _ in found)
    return [item for item in found if counts[item[:2]] == 1]


def score(name: str, kind: str) -> int:
    upper = name.upper()
    if any(word in upper for word in EXCLUDE_WORDS):
        return -10_000
    object_score = 8 if any(word in upper for word in OBJECT_WORDS) else 0
    abbreviated_dimension = bool(
        re.search(r"(?:^|_)(?:R|W|H|D|T|L|X|Y|Z)(?:$|\d|_)", upper)
        or re.search(r"_(?:X|Y|Z)$", upper)
    )
    dimension_score = 10 if any(word in upper for word in DIMENSION_WORDS) or abbreviated_dimension else 0
    dynamic_score = 12 if any(word in upper for word in DYNAMIC_WORDS) else 0
    constant_style = 2 if re.fullmatch(r"[A-Z][A-Z0-9_]*", name) else 0
    if kind == "geometry":
        return object_score + dimension_score + constant_style - dynamic_score
    return object_score // 2 + dynamic_score + constant_style


def choose(source: str, task_name: str) -> tuple[tuple[str, str | None], tuple[str, str | None] | None]:
    candidates = numeric_assignments(source)
    kind_match = re.search(r'"(?:kind|scene_kind)"\s*:\s*"([^"]+)"', source[:4000])
    preferred_scope = f"build_{kind_match.group(1)}" if kind_match else None
    if kind_match:
        dispatch = re.search(
            rf'if[ \t]+kind[ \t]*==[ \t]*["\']{re.escape(kind_match.group(1))}["\'][ \t]*:'
            rf'[\s\S]{{0,160}}?return[ \t]+([A-Za-z_][A-Za-z0-9_]*)[ \t]*\(',
            source,
        )
        if dispatch:
            preferred_scope = dispatch.group(1)
    task_tokens = {t for t in task_name.lower().split("_") if len(t) >= 4}

    if preferred_scope:
        candidates = [item for item in candidates if item[0] in (None, preferred_scope)]

    def rank(item, which):
        scope, name, _ = item
        scope_words = set((scope or "").lower().split("_"))
        name_words = set(name.lower().split("_"))
        overlap = len(task_tokens & scope_words)
        name_overlap = len(task_tokens & name_words)
        scope_bonus = (
            80 if scope == preferred_scope
            else (5 + 8 * overlap if scope and scope.startswith(("build", "animate")) else 0)
        )
        return (-(score(name, which) + scope_bonus + 6 * name_overlap), scope or "", name)

    geometry = sorted(candidates, key=lambda item: rank(item, "geometry"))
    geometry = [item for item in geometry if score(item[1], "geometry") >= 10]
    dynamics = sorted(candidates, key=lambda item: rank(item, "dynamics"))
    dynamics = [item for item in dynamics if score(item[1], "dynamics") >= 12]
    if not geometry and not dynamics:
        raise ValueError("no safe task geometry or dynamics constant")
    primary_item = geometry[0] if geometry else dynamics[0]
    primary = (primary_item[1], primary_item[0])
    compatible = [item for item in dynamics if item[0] in (None, primary_item[0])]
    secondary_item = next((item for item in compatible if item[:2] != primary_item[:2]), None)
    secondary = (secondary_item[1], secondary_item[0]) if secondary_item else None
    if secondary is None:
        compatible = [item for item in geometry if item[0] in (None, primary_item[0])]
        secondary_item = next((item for item in compatible if item[:2] != primary_item[:2]), None)
        secondary = (secondary_item[1], secondary_item[0]) if secondary_item else None
    return primary, secondary


def make_binding(mapping: dict[str, tuple[str, str | None]]) -> dict:
    constants = {script: pair[0] for script, pair in mapping.items()}
    scopes = {script: pair[1] for script, pair in mapping.items() if pair[1] is not None}
    values = set(constants.values())
    target = {"constant": next(iter(values))} if len(values) == 1 else {"by_script": constants}
    if scopes:
        scope_values = set(scopes.values())
        target.update(
            {"scope": next(iter(scope_values))}
            if len(scopes) == len(mapping) and len(scope_values) == 1
            else {"scope_by_script": scopes}
        )
    return {"operation": "multiply", **target}


def plan_task(task_dir: Path) -> dict:
    manifest_path = task_dir / "task.json"
    manifest = json.loads(manifest_path.read_text())
    scripts = [task_dir / name for name in manifest["member_scripts"]]
    choices = {script.name: choose(script.read_text(), manifest["name"]) for script in scripts}
    primary = {name: pair[0] for name, pair in choices.items()}
    secondary = {name: pair[1] for name, pair in choices.items() if pair[1] is not None}
    parameters = {
        "primary_geometry_scale": {
            "type": "uniform", "min": VISIBLE_PRIMARY_BOUNDS[0],
            "max": VISIBLE_PRIMARY_BOUNDS[1], "precision": 4,
            "binding": make_binding(primary),
        }
    }
    if len(secondary) == len(scripts):
        secondary_is_dynamic = all(
            any(word in constant[0].upper() for word in DYNAMIC_WORDS)
            for constant in secondary.values()
        )
        parameter_name = "secondary_dynamics_scale" if secondary_is_dynamic else "secondary_geometry_scale"
        parameters[parameter_name] = {
            "type": "uniform",
            "min": (VISIBLE_SECONDARY_DYNAMICS_BOUNDS if secondary_is_dynamic
                    else VISIBLE_SECONDARY_GEOMETRY_BOUNDS)[0],
            "max": (VISIBLE_SECONDARY_DYNAMICS_BOUNDS if secondary_is_dynamic
                    else VISIBLE_SECONDARY_GEOMETRY_BOUNDS)[1],
            "precision": 4,
            "binding": make_binding(secondary),
        }
    return {
        "manifest": manifest,
        "manifest_path": manifest_path,
        "choices": choices,
        "diversity": {"schema_version": 1, "parameters": parameters},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--replace-existing", action="store_true")
    args = parser.parse_args()
    failed = []
    planned = []
    for task_dir in sorted(TASKS.glob("G[0-9]*_*")):
        manifest_path = task_dir / "task.json"
        manifest = json.loads(manifest_path.read_text())
        if "diversity" in manifest and not args.replace_existing:
            continue
        try:
            item = plan_task(task_dir)
        except Exception as exc:
            failed.append((task_dir.name, str(exc)))
            continue
        planned.append(item)
        choices = ", ".join(
            f"{script}: {pair[0][0]}@{pair[0][1] or 'module'} / "
            f"{(pair[1][0] + '@' + (pair[1][1] or 'module')) if pair[1] else '-'}"
            for script, pair in item["choices"].items()
        )
        print(f"{task_dir.name}: {choices}")
        if args.write:
            item["manifest"]["diversity"] = item["diversity"]
            item["manifest_path"].write_text(
                json.dumps(item["manifest"], indent=2, ensure_ascii=False) + "\n"
            )
    print(f"planned={len(planned)} failed={len(failed)}")
    for name, reason in failed:
        print(f"FAILED {name}: {reason}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
