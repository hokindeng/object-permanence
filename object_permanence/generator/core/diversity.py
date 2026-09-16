"""Deterministic, manifest-owned sampling for task-level data diversity."""

from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path


SCHEMA_VERSION = 1
SUPPORTED_TYPES = {"choice", "uniform", "integer"}
SUPPORTED_BINDING_OPERATIONS = {"replace", "multiply", "add"}

# Canonical bounds for automatically planned visible task diversity. Because
# the balanced design samples the 25th and 75th percentiles, these yield actual
# low/high multipliers of 0.82/1.18 for primary or dynamics factors and
# 0.84/1.16 for secondary geometry factors.
VISIBLE_PRIMARY_BOUNDS = (0.64, 1.36)
VISIBLE_SECONDARY_GEOMETRY_BOUNDS = (0.68, 1.32)
VISIBLE_SECONDARY_DYNAMICS_BOUNDS = VISIBLE_PRIMARY_BOUNDS

# Dataset-facing factors.  Eight clearly separated target colours and three
# substantially separated camera orbits are crossed with task factors
# and member-script/object variant.  Keeping these radices modest means the
# planned 1,000 samples per generator cover every design cell at least once.
FACTORIAL_COLORS = (
    "orange", "red", "pink", "purple", "blue", "cyan", "green", "yellow",
)
FACTORIAL_VIEWPOINTS = (
    {"name": "left", "camera_azimuth_deg": -16.0, "camera_elevation_deg": -3.0,
     "camera_distance_scale": 1.18},
    {"name": "center", "camera_azimuth_deg": 0.0, "camera_elevation_deg": 7.0,
     "camera_distance_scale": 1.06},
    {"name": "right", "camera_azimuth_deg": 16.0, "camera_elevation_deg": -3.0,
     "camera_distance_scale": 1.18},
)
MAX_FULL_FACTORIAL_TASK_AXES = 5
FRACTIONAL_FACTORIAL_RUNS = 32
# Non-zero, pairwise-distinct linear forms over five binary base columns.
# Any two columns therefore contain 00/01/10/11 equally often over 32 runs.
FRACTIONAL_FACTOR_MASKS = (1, 2, 4, 8, 16, 3, 5, 9, 17, 6, 10, 18, 12, 20, 24)
# Coprime strides chosen against the production budget (1,000 samples per
# generator).  They permute the complete Cartesian cells while keeping every
# factor's marginal counts nearly equal even when 1,000 is not a multiple of
# the cycle length.  Keys are (task-axis count, member/object-variant count).
BALANCED_FACTORIAL_STRIDES = {
    (1, 1): 11, (1, 2): 5, (1, 3): 17, (1, 4): 5,
    (2, 1): 7, (2, 2): 5, (2, 3): 79, (2, 5): 41, (2, 6): 11, (2, 7): 29,
    (3, 1): 59, (4, 1): 67, (5, 1): 89, (6, 1): 89, (7, 1): 89, (8, 1): 163,
}

# Safe observation-level diversity shared by every generator. These parameters
# move only the active camera around its existing optical-axis focus; they never
# alter scene geometry, animation, physics, or the input/target boundary.
UNIVERSAL_VIEWPOINT_SPEC = {
    "schema_version": SCHEMA_VERSION,
    "parameters": {
        "camera_azimuth_deg": {
            "type": "uniform", "min": -16.0, "max": 16.0, "precision": 3,
        },
        "camera_elevation_deg": {
            "type": "uniform", "min": -5.0, "max": 8.0, "precision": 3,
        },
        "camera_distance_scale": {
            "type": "uniform", "min": 1.04, "max": 1.20, "precision": 4,
        },
    },
}


def _parameter_seed(seed: int, name: str) -> int:
    raw = f"object-permanence-diversity-v{SCHEMA_VERSION}:{seed}:{name}".encode()
    return int(hashlib.sha256(raw).hexdigest()[:16], 16)


def validate_diversity_spec(spec) -> list[str]:
    """Return schema errors for one manifest's optional ``diversity`` block."""
    if spec is None:
        return []
    if not isinstance(spec, dict):
        return ["diversity must be an object"]
    errors = []
    extra = set(spec) - {"schema_version", "parameters"}
    if extra:
        errors.append(f"diversity unexpected keys: {', '.join(sorted(extra))}")
    if spec.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"diversity.schema_version must be {SCHEMA_VERSION} "
            f"(got {spec.get('schema_version')!r})"
        )
    params = spec.get("parameters")
    if not isinstance(params, dict) or not params:
        errors.append("diversity.parameters must be a non-empty object")
        return errors
    for name, rule in sorted(params.items()):
        prefix = f"diversity.parameters.{name}"
        if not isinstance(name, str) or not name:
            errors.append("diversity parameter names must be non-empty strings")
            continue
        if not isinstance(rule, dict):
            errors.append(f"{prefix} must be an object")
            continue
        kind = rule.get("type")
        if kind not in SUPPORTED_TYPES:
            errors.append(f"{prefix}.type must be one of {sorted(SUPPORTED_TYPES)}")
            continue
        allowed = {"type", "values", "binding"} if kind == "choice" else {
            "type", "min", "max", "precision", "binding"
        }
        unexpected = set(rule) - allowed
        if unexpected:
            errors.append(f"{prefix} unexpected keys: {', '.join(sorted(unexpected))}")
        if kind == "choice":
            values = rule.get("values")
            if not isinstance(values, list) or len(values) < 2:
                errors.append(f"{prefix}.values must contain at least two choices")
        else:
            lo, hi = rule.get("min"), rule.get("max")
            numeric = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
            if not numeric(lo) or not numeric(hi) or lo >= hi:
                errors.append(f"{prefix} requires numeric min < max")
            if kind == "integer" and (not isinstance(lo, int) or not isinstance(hi, int)):
                errors.append(f"{prefix} integer bounds must be integers")
            precision = rule.get("precision", 4)
            if not isinstance(precision, int) or isinstance(precision, bool) or not 0 <= precision <= 8:
                errors.append(f"{prefix}.precision must be an integer in 0..8")
        binding = rule.get("binding")
        if binding is not None:
            if not isinstance(binding, dict):
                errors.append(f"{prefix}.binding must be an object")
                continue
            unexpected_binding = set(binding) - {
                "operation", "constant", "by_script", "scope", "scope_by_script"
            }
            if unexpected_binding:
                errors.append(
                    f"{prefix}.binding unexpected keys: "
                    + ", ".join(sorted(unexpected_binding))
                )
            operation = binding.get("operation", "replace")
            if operation not in SUPPORTED_BINDING_OPERATIONS:
                errors.append(
                    f"{prefix}.binding.operation must be one of "
                    f"{sorted(SUPPORTED_BINDING_OPERATIONS)}"
                )
            has_constant = isinstance(binding.get("constant"), str) and bool(binding["constant"])
            by_script = binding.get("by_script")
            has_by_script = (
                isinstance(by_script, dict)
                and bool(by_script)
                and all(isinstance(k, str) and k and isinstance(v, str) and v
                        for k, v in by_script.items())
            )
            if has_constant == has_by_script:
                errors.append(
                    f"{prefix}.binding requires exactly one of non-empty constant or by_script"
                )
            scope = binding.get("scope")
            scope_by_script = binding.get("scope_by_script")
            if scope is not None and (not isinstance(scope, str) or not scope):
                errors.append(f"{prefix}.binding.scope must be a non-empty function name")
            if scope_by_script is not None and (
                not isinstance(scope_by_script, dict)
                or not all(isinstance(k, str) and k and isinstance(v, str) and v
                           for k, v in scope_by_script.items())
            ):
                errors.append(f"{prefix}.binding.scope_by_script must map scripts to functions")
            if scope is not None and scope_by_script is not None:
                errors.append(f"{prefix}.binding cannot use both scope and scope_by_script")
    return errors


def sample_diversity(spec, seed: int) -> dict:
    """Sample every parameter independently so adding a knob does not shift old knobs."""
    errors = validate_diversity_spec(spec)
    if errors:
        raise ValueError("; ".join(errors))
    if spec is None:
        return {}
    values = {}
    for name, rule in sorted(spec["parameters"].items()):
        rng = random.Random(_parameter_seed(seed, name))
        kind = rule["type"]
        if kind == "choice":
            values[name] = rng.choice(rule["values"])
        elif kind == "integer":
            values[name] = rng.randint(rule["min"], rule["max"])
        else:
            values[name] = round(
                rng.uniform(float(rule["min"]), float(rule["max"])),
                rule.get("precision", 4),
            )
    return values


def _factor_value(rule: dict, level: int, levels: int = 2):
    """Map one balanced discrete level into a safe point inside an authored range."""
    kind = rule["type"]
    if kind == "choice":
        values = rule["values"]
        return values[level % len(values)]
    # Interior quantiles avoid repeatedly exercising only the exact extrema,
    # while retaining an unambiguous low/high size or dynamics factor.
    quantile = (level + 0.5) / levels
    lo, hi = rule["min"], rule["max"]
    value = float(lo) + (float(hi) - float(lo)) * quantile
    if kind == "integer":
        return max(int(lo), min(int(hi), int(round(value))))
    return round(value, rule.get("precision", 4))


def _task_factor_design(spec: dict | None, row: int) -> tuple[dict, dict]:
    """Return task values and factor provenance for one factorial design row.

    Up to five task axes use the complete two-level factorial.  Higher-
    dimensional authored tasks use a 32-run resolution-style fractional
    factorial: all levels and every pair of levels remain exactly balanced,
    without exploding beyond the 1,000-sample per-generator budget.
    """
    params = (spec or {}).get("parameters", {})
    names = sorted(params)
    if len(names) <= MAX_FULL_FACTORIAL_TASK_AXES:
        runs = 1 << len(names)
        masks = tuple(1 << i for i in range(len(names)))
        design_type = "full_factorial"
    else:
        if len(names) > len(FRACTIONAL_FACTOR_MASKS):
            raise ValueError(
                f"too many task diversity axes for the balanced design: {len(names)}"
            )
        runs = FRACTIONAL_FACTORIAL_RUNS
        masks = FRACTIONAL_FACTOR_MASKS[:len(names)]
        design_type = "fractional_factorial_strength_2"
    row %= runs
    values = {}
    factors = {}
    for name, mask in zip(names, masks):
        level = bin(row & mask).count("1") % 2
        rule = params[name]
        value = _factor_value(rule, level)
        values[name] = value
        factors[name] = {"level": level, "levels": 2, "value": value}
    return values, {
        "type": design_type,
        "row": row,
        "runs": runs,
        "factors": factors,
    }


def sample_factorial_diversity(
    spec: dict | None,
    sample_index: int,
    member_slot: int = 0,
    member_count: int = 1,
) -> dict:
    """Cross object/member, colour, viewpoint, and task factors uniformly.

    The mixed-radix schedule enumerates every design cell exactly once per
    cycle.  Consequently a 1,000-sample generator gives each complete cell
    either one or two samples because every current cycle is <= 1,000.
    """
    errors = validate_diversity_spec(spec)
    if errors:
        raise ValueError("; ".join(errors))
    if sample_index < 0:
        raise ValueError("sample_index must be non-negative")
    if member_count < 1 or not 0 <= member_slot < member_count:
        raise ValueError("member_slot must be in 0..member_count-1")

    params = (spec or {}).get("parameters", {})
    task_runs = (
        1 << len(params)
        if len(params) <= MAX_FULL_FACTORIAL_TASK_AXES
        else FRACTIONAL_FACTORIAL_RUNS
    )
    outer_cycle = len(FACTORIAL_COLORS) * len(FACTORIAL_VIEWPOINTS) * task_runs
    cycle_length = member_count * outer_cycle
    within_cycle = sample_index % cycle_length
    expected_member = within_cycle % member_count
    if member_slot != expected_member:
        raise ValueError(
            f"member slot {member_slot} disagrees with factorial schedule "
            f"({expected_member}) for sample {sample_index}"
        )
    outer_ordinal = within_cycle // member_count
    stride_key = (len(params), member_count)
    if stride_key not in BALANCED_FACTORIAL_STRIDES:
        raise ValueError(
            f"no validated 1000-sample factorial stride for task/member axes {stride_key}"
        )
    stride = BALANCED_FACTORIAL_STRIDES[stride_key]
    outer_cell = (stride * outer_ordinal) % outer_cycle
    cursor = outer_cell
    color_level = cursor % len(FACTORIAL_COLORS)
    cursor //= len(FACTORIAL_COLORS)
    viewpoint_level = cursor % len(FACTORIAL_VIEWPOINTS)
    cursor //= len(FACTORIAL_VIEWPOINTS)
    task_values, task_design = _task_factor_design(spec, cursor)
    viewpoint = FACTORIAL_VIEWPOINTS[viewpoint_level]
    values = {
        "camera_azimuth_deg": viewpoint["camera_azimuth_deg"],
        "camera_elevation_deg": viewpoint["camera_elevation_deg"],
        "camera_distance_scale": viewpoint["camera_distance_scale"],
        **task_values,
    }
    return {
        "values": values,
        "factorial": {
            "schema": "balanced_factorial_v1",
            "sample_index": sample_index,
            "cycle_length": cycle_length,
            "cell_index": outer_cell * member_count + member_slot,
            "replicate_index": sample_index // cycle_length,
            "permutation_stride": stride,
            "factors": {
                "object_variant": {
                    "level": member_slot,
                    "levels": member_count,
                },
                "object_color": {
                    "level": color_level,
                    "levels": len(FACTORIAL_COLORS),
                    "value": FACTORIAL_COLORS[color_level],
                },
                "camera_angle": {
                    "level": viewpoint_level,
                    "levels": len(FACTORIAL_VIEWPOINTS),
                    "value": viewpoint["name"],
                },
                **task_design["factors"],
            },
            "task_design": {
                key: value for key, value in task_design.items() if key != "factors"
            },
        },
    }


def load_script_diversity(
    script: str,
    seed: int,
    profile: str,
    sample_index: int | None = None,
    member_slot: int = 0,
    member_count: int = 1,
) -> dict:
    """Sample universal viewpoint knobs plus the script's adjacent task.json."""
    result = {
        "schema_version": SCHEMA_VERSION,
        "profile": profile,
        "values": {},
        "universal_viewpoint": False,
        "source_bindings": {},
        "factorial": None,
    }
    if profile == "surface":
        return result
    # Backward-compatible direct callers historically supplied only ``seed``.
    # The production driver always passes the stable dataset sample index.
    if sample_index is None:
        sample_index = seed
    task_path = Path(script).resolve().parent / "task.json"
    with task_path.open(encoding="utf-8") as f:
        manifest = json.load(f)
    sampled = sample_factorial_diversity(
        manifest.get("diversity"), sample_index, member_slot, member_count
    )
    sampled["factorial"]["factors"]["object_variant"]["value"] = Path(script).name
    result["values"].update(sampled["values"])
    result["universal_viewpoint"] = True
    result["factorial"] = sampled["factorial"]
    for name, rule in (manifest.get("diversity") or {}).get("parameters", {}).items():
        binding = rule.get("binding")
        if not binding:
            continue
        constant = binding.get("constant")
        if constant is None:
            constant = binding["by_script"].get(Path(script).name)
            if constant is None:
                raise ValueError(
                    f"diversity parameter {name!r} has no binding for {Path(script).name}"
                )
        scope = binding.get("scope")
        if scope is None:
            scope = (binding.get("scope_by_script") or {}).get(Path(script).name)
        result["source_bindings"][name] = {
            "constant": constant,
            "operation": binding.get("operation", "replace"),
            "scope": scope,
        }
    return result


def apply_source_bindings(src: str, diversity: dict) -> tuple[str, dict]:
    """Rewrite a uniquely assigned source constant before a script is executed.

    Wrapping the original expression rather than mutating the namespace after
    ``exec`` ensures all subsequently derived geometry/contact constants are
    recalculated from the sampled value.
    """
    applied = {}
    for name, binding in sorted((diversity.get("source_bindings") or {}).items()):
        constant = binding["constant"]
        operation = binding["operation"]
        scope = binding.get("scope")
        search_start, search_end = 0, len(src)
        if scope:
            function = re.search(
                rf"(?m)^def[ \t]+{re.escape(scope)}[ \t]*\([^\n]*\)[^:\n]*:[ \t]*(?:#.*)?$",
                src,
            )
            if function is None:
                raise ValueError(f"source binding {name!r} cannot find function scope {scope!r}")
            search_start = function.end()
            following = re.search(r"(?m)^(?:async[ \t]+)?def[ \t]+", src[search_start:])
            search_end = search_start + following.start() if following else len(src)
        pattern = re.compile(
            rf"(?m)^(?P<indent>[ \t]*){re.escape(constant)}[ \t]*=[ \t]*"
            rf"(?P<rhs>[^\n#]+?)(?P<comment>[ \t]*#.*)?$"
        )
        matches = list(pattern.finditer(src, search_start, search_end))
        if len(matches) != 1:
            raise ValueError(
                f"source binding {name!r} expected exactly one assignment "
                f"for {constant}, found {len(matches)}"
            )
        rhs = matches[0].group("rhs").rstrip()
        comment = matches[0].group("comment") or ""
        indent = matches[0].group("indent")
        if operation == "replace":
            replacement = f'{indent}{constant} = DIVERSITY.get("{name}", {rhs}){comment}'
        elif operation == "multiply":
            replacement = f'{indent}{constant} = ({rhs}) * DIVERSITY.get("{name}", 1.0){comment}'
        else:
            replacement = f'{indent}{constant} = ({rhs}) + DIVERSITY.get("{name}", 0.0){comment}'
        match = matches[0]
        src = src[:match.start()] + replacement + src[match.end():]
        applied[name] = {
            "constant": constant,
            "operation": operation,
            "scope": scope,
            "sampled_value": diversity["values"][name],
        }
    return src, applied
