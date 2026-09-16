# -*- coding: utf-8 -*-
"""
Audit WROP V2V output.

Validates the five-file output format produced by core/generate.py, laid out as
output/{domain}_task/{domain}_{NNNN}/, in the order the checks run:
  - no ERROR.txt: a recorded generation failure fails the sample outright
  - required V2V files present and non-empty
    (input_video.mp4, target_video.mp4, prompt.txt, trajectory.npz, metadata.json)
  - media integrity: ffprobe-decodable mp4s with matching dimensions
  - metadata.json is exactly parameters / provenance / video_split, and
    provenance is populated: generator_version, blender_version, render_engine
  - no preview samples unless --allow-preview; preview_sampling recorded
  - prompt text not whitespace-only
  - trajectory.npz deep checks: required arrays (xpos, xquat, qpos, qvel,
    body_names/roles/shapes/colors, is_target, fps, frame range), shapes,
    finite values, at least one target body
  - split identity: each clip is as long as the split it declares, the two
    source windows meet with no gap or overlap, both lie inside the trajectory's
    frame range, and an event-aligned input stops before the event frame
  - coverage: task dirs with zero samples always fail; --expect-tasks and
    --per gate dataset completeness

Also validates the repo's own task manifests with --manifests (ignores --out):
task.json schema, id agreeing with the directory's G-number, member/script
agreement, dangling or orphaned scripts, globally unique member indices,
8-digit script prefixes, event/split frame declarations, and the headless
render engine literal every scene script must carry.

Usage:
    object-permanence audit --out ./out                  # audit generated output
    object-permanence audit --out ./out --task G18       # by G-id
    object-permanence audit --out ./out --task turntable_behind_screen  # by domain
    object-permanence audit --out ./out --expect-tasks all --per 20     # coverage gate
    object-permanence audit --manifests                  # audit tasks/ manifests
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

from object_permanence.generator.core.diversity import (
    UNIVERSAL_VIEWPOINT_SPEC,
    sample_factorial_diversity,
    validate_diversity_spec,
)

REQUIRED_FILES = [
    "input_video.mp4",
    "target_video.mp4",
    "trajectory.npz",
    "metadata.json",
    "prompt.txt",
]

VIDEO_FILES = ["input_video.mp4", "target_video.mp4"]

# render.py's headless rewrite replaces this exact literal with '["CYCLES"]'
# on GL-less boxes; a scene script missing it silently sticks on EEVEE and
# segfaults headless. Every pb_task_*.py must contain it verbatim.
ENGINE_LITERAL = '["BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"]'

# Every scene animates exactly 120 frames at 24 fps so the 60/60 clip contract
# (core/generate.py CLIP_FRAMES) covers the whole event. A script with a longer
# range renders fine but gets trimmed at both ends without anything noticing;
# this is the check.
SCENE_FRAME_END = 120
FRAME_END_RE = re.compile(r"^FRAME_END\s*=\s*(\d+)\s*$", re.M)

MANIFEST_KEYS = {"id", "title", "name", "members", "member_scripts", "description"}

# Keys a task.json may carry but is not required to. video_split declares the
# event-aligned cut consumed by core/generate.py; preview_event_frame aligns a
# sparse QA preview without changing the dataset split policy.
OPTIONAL_MANIFEST_KEYS = {"video_split", "preview_event_frame", "diversity"}


# ---------------------------------------------------------------------------
# media helpers
# ---------------------------------------------------------------------------

def ffprobe_available():
    return shutil.which("ffprobe") is not None


def _ffprobe_json(path, count_frames=False):
    cmd = ["ffprobe", "-v", "error"]
    if count_frames:
        cmd.append("-count_frames")
    entries = "stream=nb_read_frames,width,height" if count_frames else "stream=nb_frames,width,height"
    cmd += ["-select_streams", "v:0", "-show_entries", entries, "-of", "json", str(path)]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(detail[-1] if detail else f"ffprobe exit {proc.returncode}")
    return json.loads(proc.stdout.decode("utf-8", "replace"))


def probe_video(path):
    """Return (info, errors). info = {'frames': int|None, 'width': int|None,
    'height': int|None}; errors is a list of per-file problem strings."""
    name = Path(path).name
    errors = []
    info = {"frames": None, "width": None, "height": None}
    try:
        d = _ffprobe_json(path)
    except Exception as e:
        errors.append(f"{name} not decodable by ffprobe: {e}")
        return info, errors
    streams = d.get("streams") or []
    if not streams:
        errors.append(f"{name} has no video stream")
        return info, errors
    st = streams[0]
    for dim in ("width", "height"):
        try:
            v = int(st.get(dim))
            info[dim] = v if v > 0 else None
        except (TypeError, ValueError):
            pass
    if info["width"] is None or info["height"] is None:
        errors.append(f"{name} missing width/height in ffprobe output")

    frames = st.get("nb_frames")
    try:
        frames = int(frames)
    except (TypeError, ValueError):
        frames = None
    if frames is None:
        # container did not record nb_frames — decode and count
        try:
            d2 = _ffprobe_json(path, count_frames=True)
            st2 = (d2.get("streams") or [{}])[0]
            frames = int(st2.get("nb_read_frames"))
        except Exception as e:
            errors.append(f"{name} frame count unavailable (nb_frames missing, -count_frames failed: {e})")
            frames = None
    if frames is not None:
        if frames <= 0:
            errors.append(f"{name} has zero frames")
            info["frames"] = None
        else:
            info["frames"] = frames
    return info, errors


def audit_media(sample_dir):
    """Check mp4s are decodable, have sane frame counts and matching dimensions.
    Returns (errors, probes); the split identity vs the trajectory frame range is
    checked in audit_sample once metadata is parsed."""
    errors = []
    probes = {}
    for name in VIDEO_FILES:
        p = sample_dir / name
        if not p.exists() or p.stat().st_size <= 0:
            continue  # missing/empty already reported by the file check
        info, errs = probe_video(p)
        probes[name] = info
        errors.extend(errs)

    iv, tv = probes.get("input_video.mp4") or {}, probes.get("target_video.mp4") or {}
    if all(v is not None for v in (iv.get("width"), iv.get("height"), tv.get("width"), tv.get("height"))):
        if (iv["width"], iv["height"]) != (tv["width"], tv["height"]):
            errors.append(
                f"video dimensions mismatch: input_video {iv['width']}x{iv['height']} "
                f"!= target_video {tv['width']}x{tv['height']}"
            )
    return errors, probes


# ---------------------------------------------------------------------------
# per-sample audit
# ---------------------------------------------------------------------------

_SPLIT_WINDOW_FIELDS = (
    "input_start_index", "input_end_index",
    "target_start_index", "target_end_index",
    "input_source_frames", "target_source_frames",
    "input_pad_start_frames", "target_pad_end_frames",
    "clip_frames",
)


def check_split_identity(input_frames, target_frames, ssg_frame_count,
                         video_split) -> list:
    """Verify the two clips are the cut their own metadata declares.

    Every split method cuts source windows on either side of one seam. Each
    encoded clip is fixed at ``clip_frames`` frames; if a source window is
    shorter, the generator clones only its outer edge (the beginning of input or
    the end of target), never a frame across the semantic seam.

    The invariant here holds for all of them without asking which one ran:

    * each measured clip is exactly ``clip_frames`` long
    * each declared source count matches the width of its declared window
    * each source window plus its declared edge padding is ``clip_frames`` long
    * the windows meet, so no frame is dropped or shown twice at the seam
    * both windows lie inside the simulation

    Only the first of those compares *measured* video against *declared*
    metadata; it is the one that catches a truncated or mis-encoded clip. The
    rest are consistency checks on the declaration itself.

    This audits the schema this version of the generator emits. Data rendered by
    an older generator should be audited with the matching older version.
    """
    errors = []
    if input_frames is None or target_frames is None or ssg_frame_count is None:
        return errors
    vs = video_split if isinstance(video_split, dict) else {}

    missing = [f for f in _SPLIT_WINDOW_FIELDS if not isinstance(vs.get(f), int)]
    if missing:
        errors.append("video_split is missing " + ", ".join(missing))
        return errors

    in_start, in_end = vs["input_start_index"], vs["input_end_index"]
    tgt_start, tgt_end = vs["target_start_index"], vs["target_end_index"]
    in_source, tgt_source = vs["input_source_frames"], vs["target_source_frames"]
    in_pad, tgt_pad = vs["input_pad_start_frames"], vs["target_pad_end_frames"]
    clip = vs["clip_frames"]

    for label, frames, lo, hi, source, pad in (
        ("input_video", input_frames, in_start, in_end, in_source, in_pad),
        ("target_video", target_frames, tgt_start, tgt_end, tgt_source, tgt_pad),
    ):
        if source != hi - lo:
            errors.append(
                f"{label} source count ({source}) != its declared window "
                f"[{lo}, {hi}) = {hi - lo} frames"
            )
        if pad < 0 or source + pad != clip:
            errors.append(
                f"{label} declared window ({source}) + edge padding ({pad}) "
                f"!= video_split.clip_frames ({clip})"
            )
        if frames != clip:
            errors.append(
                f"{label} has {frames} frames but its declared window after padding "
                f"is video_split.clip_frames ({clip})"
            )

    boundary_method = vs.get("boundary_method")
    expected_input_end = tgt_start + 1 if boundary_method == "overlap_event" else tgt_start
    if in_end != expected_input_end:
        errors.append(
            f"invalid seam for {boundary_method}: input ends at {in_end}, "
            f"target starts at {tgt_start}"
        )
    if in_start < 0 or tgt_end > ssg_frame_count:
        errors.append(
            f"split window [{in_start}, {tgt_end}) falls outside the simulation "
            f"(0, {ssg_frame_count})"
        )

    # An event-aligned cut promises a precise seam. For the usual before-event
    # policy, input stops before the first target frame. An overlap-event seam
    # repeats the exact contact frame at both sides of the boundary.
    first_target = vs.get("first_target_frame")
    last_input = vs.get("last_input_frame")
    if (boundary_method != "overlap_event" and isinstance(first_target, int)
            and isinstance(last_input, int) and last_input >= first_target):
        errors.append(
            f"input runs into the event: last_input_frame ({last_input}) >= "
            f"first_target_frame ({first_target})"
        )
    if boundary_method == "overlap_event":
        event_frame = vs.get("event_frame")
        first_rendered = vs.get("first_target_rendered_frame")
        if last_input != event_frame or first_rendered != event_frame or first_target != event_frame:
            errors.append(
                "overlap-event seam must use the same event frame as Input's final "
                "frame and Target's first frame"
            )
        if vs.get("seam_overlap_frames") != 1:
            errors.append("overlap-event seam must declare seam_overlap_frames=1")
    return errors


def audit_sample(sample_dir: Path, check_media=True, allow_preview=False) -> list:
    errors = []

    # a recorded generation failure, even when all required files exist
    if (sample_dir / "ERROR.txt").exists():
        errors.append("ERROR.txt present — sample recorded a generation failure")

    for name in REQUIRED_FILES:
        p = sample_dir / name
        if not p.exists():
            errors.append(f"missing {name}")
        elif p.is_file() and p.stat().st_size <= 0:
            errors.append(f"empty {name}")

    probes = {}
    if check_media:
        media_errors, probes = audit_media(sample_dir)
        errors.extend(media_errors)

    meta_path = sample_dir / "metadata.json"
    ssg_frame_count = None
    meta_ok = False
    if not meta_path.exists():
        d = {}
    else:
        try:
            d = json.loads(meta_path.read_text(encoding="utf-8"))
            meta_ok = True
        except Exception as e:
            errors.append(f"metadata invalid json: {e}")
            d = {}

    if meta_ok:
        # Provenance must be populated, not merely present: a corrupted SR_INFO
        # line makes generate.py stamp nulls (its parse failure is deliberately
        # non-fatal), and a whole batch rendered that way can never afterwards be
        # told apart by Blender version or render engine. Gate it here so such a
        # batch cannot pass a shard audit.
        prov = d.get("provenance") or {}
        for key in ("generator_version", "blender_version", "render_engine"):
            val = prov.get(key)
            if not isinstance(val, str) or not val.strip():
                errors.append(f"provenance.{key} missing or empty (got {val!r})")

        # metadata.json carries exactly three blocks (generate.py build_metadata);
        # anything else is a schema drift that would silently bloat 1.5M samples.
        extra = set(d) - {"parameters", "provenance", "video_split"}
        if extra:
            errors.append(f"metadata.json unexpected top-level keys: {', '.join(sorted(extra))}")
        for key in ("parameters", "provenance", "video_split"):
            if not isinstance(d.get(key), dict):
                errors.append(f"metadata.json {key} missing or not an object")

        if d.get("parameters", {}).get("preview") and not allow_preview:
            errors.append(
                "parameters.preview is true — QA preview samples must not "
                "enter production datasets (pass --allow-preview to accept)"
            )

        if d.get("parameters", {}).get("preview"):
            sampling = d.get("parameters", {}).get("preview_sampling")
            if not isinstance(sampling, dict):
                errors.append("parameters.preview_sampling is missing for a preview sample")
            else:
                for key in ("requested_frame_step", "effective_frame_step"):
                    value = sampling.get(key)
                    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                        errors.append(f"parameters.preview_sampling.{key} must be a positive integer")
                for key in ("source_fps", "output_fps"):
                    value = sampling.get(key)
                    if (not isinstance(value, (int, float)) or isinstance(value, bool)
                            or not math.isfinite(float(value)) or value <= 0):
                        errors.append(f"parameters.preview_sampling.{key} must be positive and finite")
                requested = sampling.get("requested_frame_step")
                effective = sampling.get("effective_frame_step")
                reason = sampling.get("override_reason")
                if requested != effective and not isinstance(reason, str):
                    errors.append(
                        "parameters.preview_sampling.override_reason is required when the frame step changes"
                    )
                if requested == effective and reason is not None:
                    errors.append(
                        "parameters.preview_sampling.override_reason must be null when the frame step is unchanged"
                    )


    prompt_path = sample_dir / "prompt.txt"
    if prompt_path.exists() and prompt_path.stat().st_size > 0:
        text = prompt_path.read_text(encoding="utf-8").strip()
        if not text:
            errors.append("prompt.txt is whitespace-only")

    traj_path = sample_dir / "trajectory.npz"
    if traj_path.exists() and traj_path.stat().st_size > 0:
        try:
            import numpy as np
            z = np.load(traj_path, allow_pickle=False)
            for key in ("xpos", "xquat", "qpos", "qvel", "body_names", "body_roles",
                        "body_shapes", "body_colors", "is_target", "fps",
                        "frame_start", "frame_end"):
                if key not in z:
                    errors.append(f"trajectory.npz missing array {key}")
            if "xpos" in z and (z["xpos"].ndim != 3 or z["xpos"].shape[0] == 0):
                errors.append(f"trajectory.npz xpos has bad shape {z['xpos'].shape}")
            elif "xpos" in z:
                # deep shape / finiteness / frame-alignment checks
                T, N = z["xpos"].shape[0], z["xpos"].shape[1]
                ssg_frame_count = T
                if tuple(z["xpos"].shape) != (T, N, 3):
                    errors.append(f"trajectory.npz xpos shape {tuple(z['xpos'].shape)} != ({T}, {N}, 3)")
                if "xquat" in z and tuple(z["xquat"].shape) != (T, N, 4):
                    errors.append(f"trajectory.npz xquat shape {tuple(z['xquat'].shape)} != ({T}, {N}, 4)")
                for key in ("body_names", "body_roles", "body_shapes", "body_colors", "is_target"):
                    if key in z and len(z[key]) != N:
                        errors.append(f"trajectory.npz {key} length {len(z[key])} != body count {N}")
                if "is_target" in z and not bool(z["is_target"].any()):
                    errors.append("trajectory.npz is_target marks no body as target")
                if "frame_start" in z and "frame_end" in z and int(z["frame_end"]) - int(z["frame_start"]) + 1 != T:
                    errors.append(
                        f"trajectory.npz frame range {int(z['frame_start'])}..{int(z['frame_end'])} "
                        f"does not span {T} frames"
                    )
                if "qpos" in z and tuple(z["qpos"].shape) != (T, N * 7):
                    errors.append(
                        f"trajectory.npz qpos shape {tuple(z['qpos'].shape)} "
                        f"!= expected ({T}, {N * 7})"
                    )
                if "qvel" in z and tuple(z["qvel"].shape) != (T, N * 6):
                    errors.append(
                        f"trajectory.npz qvel shape {tuple(z['qvel'].shape)} "
                        f"!= expected ({T}, {N * 6})"
                    )
                for key in ("xpos", "xquat", "qpos", "qvel"):
                    if key in z and not np.isfinite(z[key]).all():
                        errors.append(f"trajectory.npz {key} contains non-finite values")
        except Exception as e:
            errors.append(f"trajectory.npz unreadable: {e}")

    # The trajectory covers the FULL source frame range even in preview mode
    # (render.py record_scene_state_graph), so it is the frame count the split
    # indices are checked against.
    if meta_ok:
        errors.extend(check_split_identity(
            input_frames=probes.get("input_video.mp4", {}).get("frames"),
            target_frames=probes.get("target_video.mp4", {}).get("frames"),
            ssg_frame_count=ssg_frame_count,
            video_split=d.get("video_split"),
        ))

    return errors


# ---------------------------------------------------------------------------
# manifest loading (shared by --task resolution, coverage gate, --manifests)
# ---------------------------------------------------------------------------

def _tasks_dir():
    return Path(__file__).resolve().parent.parent / "tasks"


def _load_manifests():
    """Return list of (task_dir_path, manifest_dict_or_None, parse_error_or_None)
    for every G-prefixed subdir of the repo tasks/ tree."""
    out = []
    tasks_dir = _tasks_dir()
    if not tasks_dir.is_dir():
        return out
    for td in sorted(p for p in tasks_dir.iterdir() if p.is_dir() and re.match(r"G\d+", p.name)):
        tj = td / "task.json"
        if not tj.exists():
            out.append((td, None, "missing task.json"))
            continue
        try:
            out.append((td, json.loads(tj.read_text(encoding="utf-8")), None))
        except Exception as e:
            out.append((td, None, f"task.json invalid json: {e}"))
    return out


def _manifest_domains():
    """Map manifest id -> name for every parseable task.json."""
    return {d["id"]: d["name"] for _, d, err in _load_manifests()
            if err is None and isinstance(d, dict) and d.get("id") and d.get("name")}


def _resolve_domain(task_arg):
    """Map a --task value to the output domain. Accepts a G-id (G18), a domain
    name (turntable_behind_screen), or a {name}_task dir name. Unknown G-ids
    are a hard error instead of silently degrading."""
    if re.fullmatch(r"G\d+", task_arg or ""):
        domains = _manifest_domains()
        if task_arg not in domains:
            raise SystemExit(f"unknown task {task_arg} (no task.json matches)")
        return domains[task_arg]
    if task_arg and task_arg.endswith("_task"):
        return task_arg[: -len("_task")]
    return task_arg


def _match_task_dirs(out_root, domain):
    """Match task dirs as domain + '_task' (or the bare domain, or domain + '_'
    + digits for flat layouts) via fullmatch — never a bare startswith, which
    over-matches e.g. --task car onto car_on_bridge."""
    pat = re.compile(re.escape(domain) + r"(?:_task|_\d+)?$")
    return sorted(p for p in out_root.iterdir() if p.is_dir() and pat.fullmatch(p.name))


# ---------------------------------------------------------------------------
# --manifests self-check mode
# ---------------------------------------------------------------------------

def audit_manifests(require_task_specific=False, require_balanced_factorial=False):
    """Validate the repo's own tasks/ tree. Returns dict of task_dir_name -> errors."""
    manifests = _load_manifests()
    all_errors = {}
    index_owners = {}  # member index -> [task dir names]

    for td, d, parse_err in manifests:
        errors = []
        if parse_err is not None:
            all_errors[td.name] = [parse_err]
            continue

        keys = set(d.keys())
        missing = MANIFEST_KEYS - keys
        extra = keys - MANIFEST_KEYS - OPTIONAL_MANIFEST_KEYS
        if missing:
            errors.append(f"task.json missing keys: {', '.join(sorted(missing))}")
        if extra:
            errors.append(f"task.json unexpected keys: {', '.join(sorted(extra))}")

        # video_split content check. The key-name whitelist alone would let a
        # typo'd method or an out-of-range frame through pre-flight, leaving
        # compute_split to raise mid-render -- fail here, before GPU hours burn.
        vs = d.get("video_split")
        if vs is not None:
            if not isinstance(vs, dict):
                errors.append("video_split must be an object")
            else:
                vs_extra = set(vs.keys()) - {"method", "event", "event_frame", "first_target_frame"}
                if vs_extra:
                    errors.append(f"video_split unexpected keys: {', '.join(sorted(vs_extra))}")
                method = vs.get("method")
                if method not in {"before_event", "overlap_event"}:
                    errors.append(
                        "video_split.method must be 'before_event' or 'overlap_event' "
                        f"(got {method!r})"
                    )
                ftf = vs.get("first_target_frame")
                if not isinstance(ftf, int) or isinstance(ftf, bool) or not (2 <= ftf <= 120):
                    errors.append(f"video_split.first_target_frame must be an int in 2..120 (got {ftf!r})")
                event_frame = vs.get("event_frame")
                if method == "overlap_event":
                    if not isinstance(event_frame, int) or isinstance(event_frame, bool):
                        errors.append(f"{method} video_split.event_frame must be an integer")
                    elif ftf != event_frame:
                        errors.append(
                            "overlap_event video_split.first_target_frame must equal event_frame"
                        )
                elif event_frame is not None:
                    errors.append("before_event video_split must not declare event_frame")
                ev = vs.get("event")
                if not isinstance(ev, str) or not ev.strip():
                    errors.append("video_split.event must be a non-empty string")

        pef = d.get("preview_event_frame")
        if pef is not None and (
            not isinstance(pef, int) or isinstance(pef, bool) or pef < 1
        ):
            errors.append(
                f"preview_event_frame must be a positive integer (got {pef!r})"
            )

        diversity = d.get("diversity")
        errors.extend(validate_diversity_spec(diversity))
        if require_task_specific and not diversity:
            errors.append("task-specific diversity is required but not declared")
        if require_balanced_factorial and diversity:
            try:
                design = sample_factorial_diversity(
                    diversity, 0, member_slot=0, member_count=len(d.get("members") or [])
                )["factorial"]
                if design["cycle_length"] > 1000:
                    errors.append(
                        f"factorial cycle {design['cycle_length']} exceeds the "
                        "planned 1000 samples per generator"
                    )
            except Exception as exc:
                errors.append(f"balanced factorial design invalid: {exc}")

        m = re.match(r"(G\d+)(?:_|$)", td.name)
        dir_gid = m.group(1) if m else None
        if dir_gid is not None and d.get("id") != dir_gid:
            errors.append(f"id {d.get('id')!r} does not match directory G-number {dir_gid}")

        members = d.get("members") if isinstance(d.get("members"), list) else []
        scripts = d.get("member_scripts") if isinstance(d.get("member_scripts"), list) else []
        if len(members) != len(scripts):
            errors.append(
                f"members ({len(members)}) and member_scripts ({len(scripts)}) lengths disagree"
            )

        referenced = set()
        for i, fname in enumerate(scripts):
            if not isinstance(fname, str):
                errors.append(f"member_scripts[{i}] is not a string: {fname!r}")
                continue
            referenced.add(fname)
            sp = td / fname
            if not sp.exists():
                errors.append(f"member_scripts[{i}] {fname} does not exist on disk")
            else:
                try:
                    text = sp.read_text(encoding="utf-8")
                except Exception as e:
                    text = ""
                    errors.append(f"{fname} unreadable: {e}")
                if text and ENGINE_LITERAL not in text:
                    errors.append(
                        f"{fname} missing engine literal {ENGINE_LITERAL} "
                        "(render.py headless rewrite depends on it)"
                    )
                if text:
                    m = FRAME_END_RE.search(text)
                    if not m:
                        errors.append(f"{fname} does not declare FRAME_END")
                    elif int(m.group(1)) != SCENE_FRAME_END:
                        errors.append(
                            f"{fname} declares FRAME_END = {m.group(1)}; every scene must be "
                            f"{SCENE_FRAME_END} frames so the 60/60 clips cover the whole event"
                        )
                params = (diversity or {}).get("parameters", {})
                consumed = []
                for pname, rule in params.items():
                    binding = rule.get("binding")
                    if binding:
                        constant = binding.get("constant") or binding.get("by_script", {}).get(fname)
                        if constant is None:
                            errors.append(f"{fname}: diversity parameter {pname!r} has no source binding")
                            continue
                        scope = binding.get("scope") or binding.get("scope_by_script", {}).get(fname)
                        binding_text = text
                        if scope:
                            function = re.search(
                                rf"(?m)^def[ \t]+{re.escape(scope)}[ \t]*\([^\n]*\)[^:\n]*:[ \t]*(?:#.*)?$",
                                text,
                            )
                            if function is None:
                                errors.append(
                                    f"{fname}: binding {pname!r} cannot find function scope {scope!r}"
                                )
                                continue
                            start = function.end()
                            following = re.search(r"(?m)^(?:async[ \t]+)?def[ \t]+", text[start:])
                            end = start + following.start() if following else len(text)
                            binding_text = text[start:end]
                        count = len(re.findall(
                            rf"(?m)^[ \t]*{re.escape(constant)}[ \t]*=[ \t]*[^\n#]+?(?:[ \t]*#.*)?$",
                            binding_text,
                        ))
                        if count != 1:
                            errors.append(
                                f"{fname}: binding {pname!r} expected one "
                                f"assignment for {constant}, found {count}"
                            )
                        else:
                            consumed.append(pname)
                    elif re.search(rf'DIVERSITY\.get\(["\']{re.escape(pname)}["\']', text):
                        consumed.append(pname)
                if require_task_specific and params and not consumed:
                    errors.append(f"{fname}: no declared task-specific diversity parameter is consumed")
            pm = re.match(r"pb_task_(\d{8})_", fname)
            if pm is None:
                errors.append(f"member_scripts[{i}] {fname} has no 8-digit pb_task_ prefix")
            elif i < len(members):
                if int(pm.group(1)) != members[i]:
                    errors.append(
                        f"member_scripts[{i}] {fname} prefix {int(pm.group(1))} "
                        f"!= member index {members[i]}"
                    )

        for fname in sorted(p.name for p in td.glob("pb_task_*.py")):
            if fname not in referenced:
                errors.append(f"on-disk script {fname} not referenced by member_scripts")

        for i, idx in enumerate(members):
            if isinstance(idx, int):
                index_owners.setdefault(idx, []).append(td.name)
            else:
                errors.append(f"members[{i}] is not an integer: {idx!r}")

        if errors:
            all_errors[td.name] = errors

    for idx, owners in sorted(index_owners.items()):
        if len(owners) > 1:
            for owner in owners:
                all_errors.setdefault(owner, []).append(
                    f"member index {idx} not globally unique (also in "
                    f"{', '.join(o for o in owners if o != owner)})"
                )

    return manifests, all_errors


def run_manifests_mode(require_task_specific=False, require_balanced_factorial=False):
    manifests, all_errors = audit_manifests(
        require_task_specific=require_task_specific,
        require_balanced_factorial=require_balanced_factorial,
    )
    tasks_dir = _tasks_dir()
    diversity_count = sum(
        1 for _, d, err in manifests
        if err is None and isinstance(d, dict) and d.get("diversity") is not None
    )
    print("=" * 80)
    print("Audit WROP task manifests (tasks/*/task.json self-check)")
    print(f"root={tasks_dir}  tasks={len(manifests)}")
    print(f"universal viewpoint diversity coverage={len(manifests)}/{len(manifests)}")
    print(f"task-specific diversity manifests={diversity_count}/{len(manifests)}")
    print("=" * 80)
    if not manifests:
        raise SystemExit(f"No task directories found in {tasks_dir}")
    if all_errors:
        print(f"\nFAILED — {len(all_errors)}/{len(manifests)} task manifests have errors:\n")
        for name in sorted(all_errors):
            print(f"  [{name}]")
            for e in all_errors[name]:
                print(f"    - {e}")
        raise SystemExit(1)
    print(f"\nOK: {len(manifests)} task manifests pass all checks.")


def _sampled_task_diversity(sample_dir: Path):
    """Return (profile, values) from one generated sample's metadata."""
    try:
        d = json.loads((sample_dir / "metadata.json").read_text(encoding="utf-8"))
    except Exception:
        return None, None
    params = d.get("parameters") if isinstance(d.get("parameters"), dict) else {}
    applied = params.get("applied_transforms") if isinstance(params.get("applied_transforms"), dict) else {}
    task = applied.get("task_diversity") if isinstance(applied.get("task_diversity"), dict) else {}
    values = task.get("values") if isinstance(task.get("values"), dict) else None
    return params.get("diversity_profile"), values


def _factorial_assignment(sample_dir: Path):
    """Return the recorded balanced-factorial block, or None."""
    try:
        d = json.loads((sample_dir / "metadata.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    params = d.get("parameters") if isinstance(d.get("parameters"), dict) else {}
    applied = params.get("applied_transforms") if isinstance(params.get("applied_transforms"), dict) else {}
    task = applied.get("task_diversity") if isinstance(applied.get("task_diversity"), dict) else {}
    factorial = task.get("factorial")
    return factorial if isinstance(factorial, dict) else None


def _factorial_application_errors(sample_dir: Path, factorial):
    """Verify that recorded factor levels reached the rendered scene, not only metadata."""
    try:
        d = json.loads((sample_dir / "metadata.json").read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"cannot verify factorial application: {exc}"]

    errors = []
    params = d.get("parameters") if isinstance(d.get("parameters"), dict) else {}
    applied = params.get("applied_transforms") if isinstance(params.get("applied_transforms"), dict) else {}
    task = applied.get("task_diversity") if isinstance(applied.get("task_diversity"), dict) else {}
    values = task.get("values") if isinstance(task.get("values"), dict) else {}
    factors = factorial.get("factors") if isinstance(factorial.get("factors"), dict) else {}

    object_factor = factors.get("object_variant") or {}
    if object_factor.get("value") != params.get("source_script"):
        errors.append("object-variant factor does not match the rendered source script")

    color_factor = factors.get("object_color") or {}
    expected_color = color_factor.get("value")
    recolor = applied.get("recolor_material") if isinstance(applied.get("recolor_material"), dict) else {}
    groups = recolor.get("groups") if isinstance(recolor.get("groups"), list) else []
    if not isinstance(recolor.get("targets"), int) or recolor.get("targets", 0) < 1 or not groups:
        errors.append("object-colour factor was recorded but no target object was recoloured")
    elif groups[0].get("new") != expected_color:
        errors.append(
            f"primary target colour {groups[0].get('new')!r} != factor {expected_color!r}"
        )
    camera = applied.get("camera_viewpoint") if isinstance(applied.get("camera_viewpoint"), dict) else {}
    for actual_key, value_key in (
        ("azimuth_deg", "camera_azimuth_deg"),
        ("elevation_deg", "camera_elevation_deg"),
        ("distance_scale", "camera_distance_scale"),
    ):
        try:
            if not math.isclose(float(camera[actual_key]), float(values[value_key]), abs_tol=1e-6):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            errors.append(f"applied camera {actual_key} does not match its factorial value")

    source_bindings = applied.get("source_bindings")
    source_bindings = source_bindings if isinstance(source_bindings, dict) else {}
    expected_bindings = task.get("source_bindings")
    expected_bindings = expected_bindings if isinstance(expected_bindings, dict) else {}
    if set(source_bindings) != set(expected_bindings):
        errors.append("applied source-binding set does not match the sampled design")
    for name, binding in source_bindings.items():
        if not isinstance(binding, dict) or binding.get("sampled_value") != values.get(name):
            errors.append(f"source binding {name!r} does not match its factorial value")
    return errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser(parser=None):
    if parser is None:
        parser = argparse.ArgumentParser(description="Audit WROP V2V output")
    parser.add_argument("--out", default=None,
                        help="output directory from generate.py (required unless --manifests)")
    parser.add_argument("--task", default=None,
                        help="audit only one generator, by G-id (e.g. G18) or domain name (e.g. turntable_behind_screen)")
    parser.add_argument("--no-media", action="store_true",
                        help="skip ffprobe media integrity checks (e.g. when ffprobe is unavailable)")
    parser.add_argument("--expect-tasks", default=None, metavar="N|all",
                        help="coverage gate: 'all' requires every tasks/*/task.json domain present; "
                             "an integer requires exactly that many task dirs")
    parser.add_argument("--per", type=int, default=None, metavar="N",
                        help="coverage gate: every task dir must contain exactly N sample dirs")
    parser.add_argument("--allow-preview", action="store_true",
                        help="accept samples generated with --preview")
    parser.add_argument("--require-task-diversity", action="store_true",
                        help="fail samples that did not record a non-empty structural-diversity assignment "
                             "(universal viewpoint and any task-specific parameters)")
    parser.add_argument("--min-unique-diversity", type=int, default=None, metavar="N",
                        help="require at least N distinct recorded structural-diversity assignments per output task")
    parser.add_argument("--manifests", action="store_true",
                        help="ignore --out and validate the repo's own tasks/ manifests instead")
    parser.add_argument("--require-task-specific-diversity", action="store_true",
                        help="require generator-specific parameters and exclude universal camera/surface "
                             "variation from the diversity gate; with --manifests, require every member "
                             "script to consume a declared generator-specific parameter")
    parser.add_argument("--require-balanced-factorial", action="store_true",
                        help="require balanced_factorial_v1 provenance and uniform, non-repeating "
                             "design-cell coverage; with --manifests, require a cycle <= 1000")
    return parser


def main(args=None):
    if args is None:
        args = build_parser().parse_args()

    if args.manifests:
        run_manifests_mode(
            args.require_task_specific_diversity, args.require_balanced_factorial
        )
        return

    if not args.out:
        raise SystemExit("audit: --out is required (unless --manifests is passed)")

    expect_tasks = args.expect_tasks
    if expect_tasks is not None and expect_tasks != "all":
        try:
            expect_tasks = int(expect_tasks)
        except ValueError:
            raise SystemExit(f"audit: --expect-tasks must be an integer or 'all', got {args.expect_tasks!r}")

    check_media = not args.no_media
    if check_media and not ffprobe_available():
        raise SystemExit(
            "audit: ffprobe not found on PATH. ffmpeg is a hard pipeline dependency — "
            "install it (e.g. apt install ffmpeg / brew install ffmpeg) or pass "
            "--no-media to skip media integrity checks."
        )

    out_root = Path(args.out).resolve()
    if not out_root.exists():
        raise SystemExit(f"Output directory not found: {out_root}")

    if args.task:
        domain = _resolve_domain(args.task)
        task_dirs = _match_task_dirs(out_root, domain)
    else:
        task_dirs = sorted([p for p in out_root.iterdir() if p.is_dir()])

    if not task_dirs:
        raise SystemExit(f"No task directories found in {out_root}")

    all_errors = {}

    samples = []
    for td in task_dirs:
        task_samples = sorted(p for p in td.iterdir() if p.is_dir())
        # always on: a task dir with no sample subdirs is an error
        if not task_samples:
            all_errors.setdefault(td.name, []).append("task dir has zero sample subdirs")
        elif args.per is not None and len(task_samples) != args.per:
            all_errors.setdefault(td.name, []).append(
                f"sample count {len(task_samples)} != --per {args.per}"
            )
        samples.extend(task_samples)

    if args.min_unique_diversity is not None and args.min_unique_diversity < 1:
        raise SystemExit("audit: --min-unique-diversity must be >= 1")

    if (args.require_task_diversity or args.require_task_specific_diversity
            or args.min_unique_diversity is not None):
        unique_by_task = {}
        universal_keys = set(UNIVERSAL_VIEWPOINT_SPEC["parameters"])
        for sample in samples:
            profile, values = _sampled_task_diversity(sample)
            if args.require_task_specific_diversity and isinstance(values, dict):
                values = {k: v for k, v in values.items() if k not in universal_keys}
            if profile != "task" or not values:
                all_errors.setdefault(f"{sample.parent.name}/{sample.name}", []).append(
                    "missing non-empty generator-specific diversity assignment"
                    if args.require_task_specific_diversity
                    else "missing non-empty task-level diversity assignment"
                )
                continue
            unique_by_task.setdefault(sample.parent.name, set()).add(
                json.dumps(values, sort_keys=True, separators=(",", ":"))
            )
        if args.min_unique_diversity is not None:
            for task_dir in task_dirs:
                count = len(unique_by_task.get(task_dir.name, set()))
                if count < args.min_unique_diversity:
                    all_errors.setdefault(task_dir.name, []).append(
                        f"unique task-diversity assignments {count} < "
                        f"--min-unique-diversity {args.min_unique_diversity}"
                    )

    if args.require_balanced_factorial:
        cells_by_task = {}
        cycle_by_task = {}
        for sample in samples:
            factorial = _factorial_assignment(sample)
            sample_key = f"{sample.parent.name}/{sample.name}"
            if not factorial or factorial.get("schema") != "balanced_factorial_v1":
                all_errors.setdefault(sample_key, []).append(
                    "missing balanced_factorial_v1 provenance"
                )
                continue
            factors = factorial.get("factors")
            required = {"object_variant", "object_color", "camera_angle"}
            if not isinstance(factors, dict) or not required <= set(factors):
                all_errors.setdefault(sample_key, []).append(
                    "factorial assignment missing object, color, or camera-angle factor"
                )
                continue
            application_errors = _factorial_application_errors(sample, factorial)
            if application_errors:
                all_errors.setdefault(sample_key, []).extend(application_errors)
            try:
                cell = int(factorial["cell_index"])
                cycle = int(factorial["cycle_length"])
            except (KeyError, TypeError, ValueError):
                all_errors.setdefault(sample_key, []).append(
                    "factorial cell_index/cycle_length is invalid"
                )
                continue
            if cycle < 1 or not 0 <= cell < cycle:
                all_errors.setdefault(sample_key, []).append(
                    f"factorial cell {cell} lies outside cycle 0..{cycle - 1}"
                )
                continue
            try:
                sample_index = int(factorial["sample_index"])
                directory_index = int(sample.name.rsplit("_", 1)[1])
                member_factor = factors["object_variant"]
                member_count = int(member_factor["levels"])
                member_level = int(member_factor["level"])
                stride = int(factorial["permutation_stride"])
                outer_cycle = cycle // member_count
                within_cycle = sample_index % cycle
                expected_member = within_cycle % member_count
                outer_ordinal = within_cycle // member_count
                expected_cell = (
                    (stride * outer_ordinal) % outer_cycle
                ) * member_count + expected_member
                if sample_index != directory_index:
                    raise ValueError(
                        f"sample_index {sample_index} != directory index {directory_index}"
                    )
                if member_level != expected_member:
                    raise ValueError(
                        f"object_variant level {member_level} != scheduled {expected_member}"
                    )
                if math.gcd(stride, outer_cycle) != 1:
                    raise ValueError(
                        f"permutation stride {stride} is not coprime with {outer_cycle}"
                    )
                if cell != expected_cell:
                    raise ValueError(f"cell_index {cell} != scheduled {expected_cell}")
                if int(factorial["replicate_index"]) != sample_index // cycle:
                    raise ValueError("replicate_index disagrees with sample_index/cycle_length")
            except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
                all_errors.setdefault(sample_key, []).append(
                    f"factorial schedule provenance is inconsistent: {exc}"
                )
                continue
            previous = cycle_by_task.setdefault(sample.parent.name, cycle)
            if previous != cycle:
                all_errors.setdefault(sample.parent.name, []).append(
                    f"inconsistent factorial cycle lengths {previous} and {cycle}"
                )
            cells_by_task.setdefault(sample.parent.name, []).append(cell)
        for task_dir in task_dirs:
            cells = cells_by_task.get(task_dir.name, [])
            if not cells:
                continue
            cycle = cycle_by_task[task_dir.name]
            counts = {cell: cells.count(cell) for cell in set(cells)}
            if len(cells) <= cycle and len(counts) != len(cells):
                all_errors.setdefault(task_dir.name, []).append(
                    "factorial design repeats a cell before completing its cycle"
                )
            if len(cells) >= cycle:
                if len(counts) != cycle:
                    all_errors.setdefault(task_dir.name, []).append(
                        f"factorial coverage has {len(counts)}/{cycle} design cells"
                    )
                elif max(counts.values()) - min(counts.values()) > 1:
                    all_errors.setdefault(task_dir.name, []).append(
                        "factorial design-cell counts differ by more than one"
                    )

    # coverage gate: 'all' against the tasks/*/task.json domain set, an integer
    # against the number of task dirs found
    if expect_tasks is not None:
        found_domains = set()
        for td in task_dirs:
            found_domains.add(td.name[:-len("_task")] if td.name.endswith("_task") else td.name)
        if expect_tasks == "all":
            manifest_domains = set(_manifest_domains().values())
            missing = sorted(manifest_domains - found_domains)
            if missing:
                all_errors.setdefault("(coverage)", []).append(
                    f"--expect-tasks all: {len(missing)} task domain(s) missing from output: "
                    + ", ".join(missing)
                )
        else:
            if len(task_dirs) != expect_tasks:
                all_errors.setdefault("(coverage)", []).append(
                    f"--expect-tasks {expect_tasks}: found {len(task_dirs)} task dir(s)"
                )

    print("=" * 80)
    print(f"Audit WROP output (v6, v2v)")
    print(f"root={out_root}  tasks={len(task_dirs)}  samples={len(samples)}")
    print("=" * 80)

    n_sample_failed = 0
    for s in samples:
        sample_key = f"{s.parent.name}/{s.name}"
        errs = audit_sample(s, check_media=check_media, allow_preview=args.allow_preview)
        if errs:
            all_errors.setdefault(sample_key, []).extend(errs)
        if sample_key in all_errors:
            n_sample_failed += 1

    if all_errors:
        n_other = len(all_errors) - n_sample_failed
        extra = f" (+{n_other} task/run-level)" if n_other else ""
        print(f"\nFAILED — {n_sample_failed}/{len(samples)} samples have errors{extra}:\n")
        for sample, errs in all_errors.items():
            print(f"  [{sample}]")
            for e in errs:
                print(f"    - {e}")
        raise SystemExit(1)

    print(f"\nOK: {len(samples)} samples pass all checks.")

    import numpy as np
    for s in samples:
        d = json.loads((s / "metadata.json").read_text(encoding="utf-8"))
        z = np.load(s / "trajectory.npz", allow_pickle=False)
        prov = d.get("provenance", {})
        print(
            f"  {s.parent.name}/{s.name}",
            f"seed={d.get('parameters', {}).get('seed')}",
            f"bodies={z['xpos'].shape[1]}",
            f"frames={z['xpos'].shape[0]}",
            f"engine={prov.get('render_engine')}",
            f"blender={prov.get('blender_version')}",
        )


if __name__ == "__main__":
    main()
