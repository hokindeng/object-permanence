#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Video Reasoning - Object Permanence — dataset generator (driver).

Reads the per-task manifests in ../tasks/<id>_<name>/task.json, and for each
selected task renders --per samples via core/render.py (run inside Blender),
stitching each into a V2V sample (5 files):
    input_video.mp4 · target_video.mp4 · prompt.txt · trajectory.npz · metadata.json

Each task draws from its `member_scripts` (scene scripts co-located in each
task directory) — members are cycled across samples for discrete variety (object
type / count / order / mechanism), and render.py layers the per-seed safe
transforms (colour / material / apparatus colour / lighting).

Usage (Blender 4.4.x + ffmpeg on the PATH; OP_FORCE_EEVEE=1 on headless machines):
    object-permanence generate --out ./out --per 20 --parallel 3          # all 150 tasks
    object-permanence generate --gens G01-G11 --per 20                    # a shard
    object-permanence generate --task G18 --per 20 --preview 1            # one task, fast preview
"""

import argparse, glob, hashlib, json, os, re, shutil, signal, subprocess, sys, time
import concurrent.futures as cf
import math
import numpy as np

_BLENDER_CANDIDATES = [
    "/opt/homebrew/bin/blender",                            # macOS Homebrew (Apple Silicon / Intel)
    "/Applications/Blender.app/Contents/MacOS/blender",    # macOS .app bundle
    "/usr/local/bin/blender",                               # manual install (tarball symlinked here)
    "/usr/bin/blender",                                     # Linux apt -- often 3.x, which CANNOT do headless EEVEE
    "/snap/bin/blender",                                    # Linux snap
]

def _find_blender():
    """Blender binary: OP_BLENDER env var, then known install paths, then $PATH.
    Returns None when nothing is found (main() reports how to fix it)."""
    env = os.environ.get("OP_BLENDER", "").strip()
    if env:
        return env
    for p in _BLENDER_CANDIDATES:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return shutil.which("blender")

HERE = os.path.dirname(os.path.abspath(__file__))
TASKS_DIR = os.path.normpath(os.path.join(HERE, "..", "tasks"))
HARNESS = os.path.join(HERE, "render.py")

MAX_RETRIES = 1
CLIP_FRAMES = 60
# Hard cap on a single Blender render (seconds); 0 disables. Overridden by --render-timeout.
# Generous by design: a legitimate capped-Cycles sample under 4-way CPU contention takes
# ~10 min; only a runaway render should ever hit this.
RENDER_TIMEOUT = 1800
PREVIEW_FRAME_STEP = 6


def _tail_text(s, n=4000):
    """Last n chars of TimeoutExpired output, which may be str, bytes, or None."""
    if s is None:
        return ""
    if isinstance(s, bytes):
        s = s.decode(errors="replace")
    return s[-n:]


def _generator_version():
    try:
        from object_permanence import __version__
        return __version__
    except Exception:
        # ``python object_permanence/generator/core/generate.py`` is the documented
        # invocation, but it does not automatically put the repository root on
        # sys.path. Read the local package marker as a robust direct-script fallback.
        init_path = os.path.normpath(os.path.join(HERE, "..", "..", "__init__.py"))
        try:
            with open(init_path, encoding="utf-8") as f:
                match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', f.read(), re.M)
            return match.group(1) if match else None
        except OSError:
            return None


def deterministic_seed(gid, k, idx):
    # Full 32-bit space, so distinct samples never collide onto one seed: folding
    # the digest into a smaller range yields byte-identical duplicates at 150k samples.
    raw = f"{gid}:{k}:{idx}".encode()
    return int(hashlib.sha256(raw).hexdigest()[:8], 16)


def load_tasks():
    tasks = []
    for tj in glob.glob(os.path.join(TASKS_DIR, "*", "task.json")):
        with open(tj, encoding="utf-8") as f:
            d = json.load(f)
        task_dir = os.path.dirname(tj)
        tasks.append((d["id"], d["name"], d["members"], task_dir))
    tasks.sort(key=lambda t: int(t[0][1:]))
    return tasks


def select(tasks, gen, gens, task):
    if task:
        return [t for t in tasks if t[0] == task]
    if gens:
        m = re.fullmatch(r"G(\d+)-G(\d+)", gens.strip())
        if not m:
            raise SystemExit(f"invalid --gens format: {gens!r} — expected a range like G01-G11 "
                             "(for a single task use --task G07 or --gen G07)")
        lo, hi = int(m.group(1)), int(m.group(2))
        return [t for t in tasks if lo <= int(t[0][1:]) <= hi]
    if gen and gen != "all":
        return [t for t in tasks if t[0] == gen]
    return tasks


def find_script(task_dir, idx):
    g = glob.glob(os.path.join(task_dir, f"pb_task_{idx:08d}_*.py"))
    return g[0] if g else None


def frame_seq(out_dir):
    best = []
    for root, _, files in os.walk(out_dir):
        seq = [os.path.join(root, f) for f in sorted(files)
               if f.lower().endswith(".png") and "frame" in f.lower()
               and re.search(r"\d{3,4}\.png$", f)]
        if len(seq) > len(best):
            best = seq
    return best


def frame_numbers(seq):
    """Return Blender frame numbers for a rendered PNG sequence."""
    out = []
    for path in seq:
        match = re.search(r"(\d{3,4})\.png$", os.path.basename(path), re.IGNORECASE)
        if not match:
            raise ValueError(f"cannot determine Blender frame number from {path!r}")
        out.append(int(match.group(1)))
    return out


def load_video_split(task_dir):
    """Load an optional task-owned semantic input/target boundary."""
    path = os.path.join(task_dir, "task.json")
    with open(path, encoding="utf-8") as f:
        split = json.load(f).get("video_split")
    if split is not None and not isinstance(split, dict):
        raise ValueError(f"{path}: video_split must be an object")
    return split


def load_preview_event_frame(task_dir, task_split=None):
    """Load the frame that sparse preview sampling must include.

    A semantic input/target boundary is preferred when present.  Tasks whose
    key event belongs inside a clip can instead declare ``preview_event_frame``
    without changing their dataset split policy.
    """
    if task_split is not None:
        try:
            if task_split.get("method") == "overlap_event":
                return int(task_split["event_frame"])
            return int(task_split["first_target_frame"])
        except (KeyError, TypeError, ValueError):
            return None
    path = os.path.join(task_dir, "task.json")
    with open(path, encoding="utf-8") as f:
        event_frame = json.load(f).get("preview_event_frame")
    if event_frame is None:
        return None
    try:
        return int(event_frame)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path}: preview_event_frame must be an integer") from exc


# ---------------------------------------------------------------------------
# trajectory + input/target video (V2V / TV2V)
#
# The scene_state_graph.json written by render.py records, per frame, the world
# transform (loc / euler / quat) of every non-background mesh. We surface that as
# a first-class trajectory.npz and use it to choose where to split the simulation
# into input_video / target_video.
#
# NOTE on qpos / qvel: the renderer is Blender, not a reduced-coordinate engine
# like MuJoCo, so there are no true generalized coordinates. We expose each body
# as a FREE body: qpos = [x y z qw qx qy qz] (7 dof), qvel = [vx vy vz wx wy wz]
# (6 dof, finite-differenced). The field *names* match MuJoCo's, and the metadata
# states explicitly that this is a free-body mapping.
# ---------------------------------------------------------------------------

def load_ssg(rd):
    p = os.path.join(rd, "scene_state_graph.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def euler_xyz_to_quat(e):
    """Blender default 'XYZ' euler (radians) -> [w, x, y, z]. Fallback only."""
    cx, cy, cz = math.cos(e[0] / 2), math.cos(e[1] / 2), math.cos(e[2] / 2)
    sx, sy, sz = math.sin(e[0] / 2), math.sin(e[1] / 2), math.sin(e[2] / 2)
    w = cx * cy * cz - sx * sy * sz
    x = sx * cy * cz + cx * sy * sz
    y = cx * sy * cz - sx * cy * sz
    z = cx * cy * sz + sx * sy * cz
    return [w, x, y, z]


def ssg_to_arrays(ssg):
    """Return (names, roles, shapes, colors, is_target_mask, xpos[T,N,3], xquat[T,N,4])."""
    frames = ssg.get("frames") or []
    ometa = ssg.get("objects") or {}
    names = list(ometa.keys())
    T, N = len(frames), len(names)
    xpos = np.zeros((T, N, 3), np.float32)
    xquat = np.zeros((T, N, 4), np.float32)
    xquat[..., 0] = 1.0  # identity default
    for ti, fr in enumerate(frames):
        objs = fr.get("objects", {})
        for ni, nm in enumerate(names):
            st = objs.get(nm)
            if not st:
                continue
            loc = st.get("loc") or [0.0, 0.0, 0.0]
            xpos[ti, ni] = loc[:3]
            q = st.get("quat")
            if q and len(q) == 4:
                xquat[ti, ni] = q
            else:
                xquat[ti, ni] = euler_xyz_to_quat(st.get("rot") or [0.0, 0.0, 0.0])
    is_target = np.array([bool(ometa[n].get("is_target")) for n in names], bool)
    roles = [ometa[n].get("role", "") or "" for n in names]
    shapes = [ometa[n].get("shape", "") or "" for n in names]
    colors = [ometa[n].get("color", "") or "" for n in names]
    return names, roles, shapes, colors, is_target, xpos, xquat


def quat_angular_velocity(q0, q1, dt):
    """Body angular velocity (world) from consecutive [w,x,y,z] quats. Shapes [...,4]."""
    # relative rotation dq = q1 * conj(q0)
    w0, x0, y0, z0 = q0[..., 0], -q0[..., 1], -q0[..., 2], -q0[..., 3]
    w1, x1, y1, z1 = q1[..., 0], q1[..., 1], q1[..., 2], q1[..., 3]
    dw = w1 * w0 - x1 * x0 - y1 * y0 - z1 * z0
    dx = w1 * x0 + x1 * w0 + y1 * z0 - z1 * y0
    dy = w1 * y0 - x1 * z0 + y1 * w0 + z1 * x0
    dz = w1 * z0 + x1 * y0 - y1 * x0 + z1 * w0
    # quaternion double cover: q and -q are the same rotation. Take the short way
    # round (dw >= 0) so a sign flip between frames doesn't read as a ~2pi spin.
    flip = dw < 0
    dw = np.where(flip, -dw, dw)
    dx = np.where(flip, -dx, dx)
    dy = np.where(flip, -dy, dy)
    dz = np.where(flip, -dz, dz)
    dw = np.clip(dw, -1.0, 1.0)
    angle = 2.0 * np.arccos(dw)
    s = np.sqrt(np.maximum(1.0 - dw * dw, 1e-12))
    axis = np.stack([dx, dy, dz], axis=-1) / s[..., None]
    return (axis * (angle / dt)[..., None]).astype(np.float32)


def write_trajectory_npz(sdir, ssg):
    """Write trajectory.npz: xpos / xquat / qpos / qvel (free-body) plus per-body
    names, roles, shapes, colours and the target mask. This file is the only
    per-frame ground truth shipped with a sample."""
    names, roles, shapes, colors, is_target, xpos, xquat = ssg_to_arrays(ssg)
    T, N = xpos.shape[0], xpos.shape[1]
    fps = float(ssg.get("fps") or 24)
    dt = 1.0 / fps if fps else 1.0 / 24
    qpos = np.concatenate([xpos, xquat], axis=2).reshape(T, N * 7).astype(np.float32)
    lin = np.zeros((T, N, 3), np.float32)
    ang = np.zeros((T, N, 3), np.float32)
    if T > 1:
        lin[1:] = (xpos[1:] - xpos[:-1]) / dt
        lin[0] = lin[1]
        ang[1:] = quat_angular_velocity(xquat[:-1], xquat[1:], dt)
        ang[0] = ang[1]
    qvel = np.concatenate([lin, ang], axis=2).reshape(T, N * 6).astype(np.float32)
    np.savez_compressed(
        os.path.join(sdir, "trajectory.npz"),
        xpos=xpos, xquat=xquat, qpos=qpos, qvel=qvel,
        body_names=np.array(names), body_roles=np.array(roles),
        body_shapes=np.array(shapes), body_colors=np.array(colors),
        is_target=is_target, fps=np.float32(fps),
        frame_start=np.int32(ssg.get("frame_start", 1)),
        frame_end=np.int32(ssg.get("frame_end", T)),
    )


def compute_split(ssg, mode, n_seq, rendered_frames=None, task_split=None,
                  clip_frames=CLIP_FRAMES):
    """Return (split_seq_index, info). The boundary divides event context from
    its continuation. Both output clips contain exactly ``clip_frames`` frames.
    The input keeps the frames nearest the event and is left-padded by cloning
    its first available frame when the event occurs too early. The target starts
    at the event and is right-padded by cloning its last available frame when the
    event occurs too late. Padding never crosses the semantic event boundary.

    A task manifest's ``video_split.first_target_frame`` takes precedence. It
    defines a semantic boundary in Blender frame numbers: the input contains
    every selected frame before it and the target starts on it. Most tasks use
    ``method=before_event``, so the event begins the target. Collision tasks
    that need to show contact at both sides of the seam use
    ``method=overlap_event`` with ``event_frame``: the contact frame is the
    final Input frame and is repeated as the first Target frame.

    mode 'half'  -> temporal midpoint (matches a literal 'first/second half').
    mode 'event' -> deepest-occlusion frame: the frame minimising the distance
                    between the target centroid and the nearest apparatus body
                    (a proxy for 'object passes behind the occluder'); falls back
                    to the midpoint when no usable target/apparatus pair exists.
    """
    if n_seq < 2:
        raise ValueError("at least two rendered frames are required for a video split")
    if clip_frames < 1:
        raise ValueError("clip_frames must be positive")

    half = max(1, n_seq // 2)
    info = {"mode": mode, "n_frames": n_seq, "midpoint_index": half}

    def fixed_length_info(input_end, target_start=None):
        if target_start is None:
            target_start = input_end
        input_start = max(0, input_end - clip_frames)
        target_end = min(n_seq, target_start + clip_frames)
        input_source_frames = input_end - input_start
        target_source_frames = target_end - target_start
        return {
            "input_start_index": input_start,
            "input_end_index": input_end,
            "target_start_index": target_start,
            "target_end_index": target_end,
            "input_source_frames": input_source_frames,
            "target_source_frames": target_source_frames,
            "input_pad_start_frames": clip_frames - input_source_frames,
            "target_pad_end_frames": clip_frames - target_source_frames,
            "clip_frames": clip_frames,
            "equal_length": True,
        }
    if task_split:
        boundary_method = task_split.get("method")
        if boundary_method not in {"before_event", "overlap_event"}:
            raise ValueError(
                "video_split.method must be 'before_event' or 'overlap_event'"
            )
        try:
            first_target_frame = int(task_split["first_target_frame"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("video_split.first_target_frame must be an integer") from exc
        event_frame = None
        if boundary_method == "overlap_event":
            try:
                event_frame = int(task_split["event_frame"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"{boundary_method} video splits require an integer event_frame"
                ) from exc
        if boundary_method == "overlap_event" and first_target_frame != event_frame:
            raise ValueError("overlap_event first_target_frame must equal event_frame")

        if rendered_frames is None:
            frame_start = int((ssg or {}).get("frame_start", 1))
            rendered_frames = list(range(frame_start, frame_start + n_seq))
        if len(rendered_frames) != n_seq:
            raise ValueError("rendered frame-number count does not match rendered sequence")

        target_start = sum(frame < first_target_frame for frame in rendered_frames)
        input_end = target_start
        if boundary_method == "overlap_event":
            if target_start >= n_seq or rendered_frames[target_start] != event_frame:
                raise ValueError("overlap_event requires the rendered sequence to contain event_frame")
            input_end = target_start + 1
        if not 1 <= input_end <= n_seq or not 0 <= target_start < n_seq:
            raise ValueError(
                f"semantic split at Blender frame {first_target_frame} leaves an empty input or target"
            )
        info.update({
            "split_index": target_start,
            "method": "manifest_event_boundary",
            "boundary_method": boundary_method,
            "event": task_split.get("event"),
            "policy": (
                "fixed_length_around_event_with_edge_padding; "
                + (
                    "contact_frame_repeated_at_input_target_seam"
                    if boundary_method == "overlap_event"
                    else "input_strictly_before_event"
                )
            ),
            "first_target_frame": first_target_frame,
            "last_input_frame": int(rendered_frames[input_end - 1]),
            "first_target_rendered_frame": int(rendered_frames[target_start]),
        })
        if event_frame is not None:
            info["event_frame"] = event_frame
        if boundary_method == "overlap_event":
            info["seam_overlap_frames"] = 1
        info.update(fixed_length_info(input_end, target_start))
        info["first_input_frame"] = int(rendered_frames[info["input_start_index"]])
        info["last_target_frame"] = int(rendered_frames[info["target_end_index"] - 1])
        return target_start, info
    if mode != "event" or not ssg:
        info.update({"split_index": half, "method": "midpoint"})
        info.update(fixed_length_info(half))
        return half, info
    try:
        names, roles, is_target, xpos, xquat = ssg_to_arrays(ssg)
        T = xpos.shape[0]
        tgt = np.where(is_target)[0]
        app = np.where(~is_target)[0]
        if T < 2 or len(tgt) == 0 or len(app) == 0:
            raise ValueError("no target/apparatus pair")
        tc = xpos[:, tgt, :].mean(axis=1)           # [T,3] target centroid
        ac = xpos[:, app, :]                          # [T,A,3]
        d = np.linalg.norm(ac - tc[:, None, :], axis=2).min(axis=1)  # [T] nearest apparatus
        ev_frame = int(np.argmin(d))                  # 0-based ssg frame
        frac = ev_frame / (T - 1) if T > 1 else 0.5
        raw = int(round(frac * n_seq))
        # keep both clips substantial: clamp the cut into the middle [20%, 80%] band
        lo = max(1, int(round(0.2 * n_seq)))
        hi = min(n_seq - 1, int(round(0.8 * n_seq)))
        if hi < lo:
            lo = hi = half
        split = min(max(raw, lo), hi)
        info.update({"split_index": split, "method": "deepest_occlusion",
                     "event_ssg_frame": ev_frame, "event_fraction": round(frac, 4),
                     "raw_index": raw, "clamp_band": [lo, hi],
                     "min_target_apparatus_dist": round(float(d.min()), 4)})
        info.update(fixed_length_info(split))
        return split, info
    except Exception as e:
        info.update({"split_index": half, "method": "midpoint_fallback", "fallback_reason": str(e)})
        info.update(fixed_length_info(half))
        return half, info


def cut_subvideo(full_mp4, dst_mp4, start_frame, end_frame, fps,
                 pad_start_frames=0, pad_end_frames=0):
    """Cut [start_frame, end_frame) and clone edge frames to a fixed length."""
    if end_frame is None:
        filters = [f"trim=start_frame={start_frame}"]
    else:
        filters = [f"trim=start_frame={start_frame}:end_frame={end_frame}"]
    if pad_start_frames or pad_end_frames:
        filters.append(
            "tpad="
            f"start={int(pad_start_frames)}:start_mode=clone:"
            f"stop={int(pad_end_frames)}:stop_mode=clone"
        )
    filters.append("setpts=PTS-STARTPTS")
    vf = ",".join(filters)
    return subprocess.run(
        ["ffmpeg", "-y", "-i", full_mp4, "-vf", vf, "-r", str(fps),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", dst_mp4],
        capture_output=True)


def build_metadata(sdir, script, idx, seed, sr_info, preview, split_info,
                   diversity_profile="task", requested_preview_frame_step=None,
                   effective_preview_frame_step=None, source_fps=None,
                   output_fps=None):
    """Write metadata.json: how this sample was made and where it was cut.

    Three blocks only. ``parameters`` is everything the generator chose for this
    sample (seed, source script, diversity cell, applied knobs, source bindings,
    preview sampling); ``provenance`` is what rendered it; ``video_split`` is the
    frame boundary between input and target. Per-frame state lives in
    trajectory.npz, the prompt in prompt.txt, the task definition in the repo at
    ``provenance.generator_version`` -- none of that is repeated here.
    """
    sr_info = sr_info or {}
    md = {
        "parameters": {
            "source_index": idx, "source_script": os.path.basename(script),
            "seed": seed, "preview": bool(preview),
            "diversity_profile": diversity_profile,
            "applied_transforms": sr_info.get("transforms"),
            "preview_sampling": ({
                "requested_frame_step": int(requested_preview_frame_step),
                "effective_frame_step": int(effective_preview_frame_step),
                "source_fps": float(source_fps),
                "output_fps": float(output_fps),
                "override_reason": (
                    "overlap_event_requires_adjacent_source_frames"
                    if requested_preview_frame_step != effective_preview_frame_step
                    else None
                ),
            } if preview else None),
        },
        "provenance": {
            "generator_version": _generator_version(),
            "blender_version": sr_info.get("blender_version"),
            "render_engine": sr_info.get("render_engine"),
        },
        "video_split": split_info,
    }
    with open(os.path.join(sdir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(md, f, ensure_ascii=False, indent=2)


def _scratch_workdir(out):
    """The render's /tmp/sr_* scratch dir, parsed from render.py's WORKDIR= marker.
    Returns None unless the path matches the sr_ prefix contract — never anything
    else, so cleanup can only ever delete a render scratch dir."""
    m = re.search(r"^WORKDIR=(.+)$", out or "", re.M)
    if not m:
        return None
    wd = m.group(1).strip()
    if os.path.basename(wd).startswith("sr_") and wd.startswith("/tmp/"):
        return wd
    return None


def _reclaim(workdir):
    """Best-effort delete of a validated scratch workdir."""
    if workdir:
        shutil.rmtree(workdir, ignore_errors=True)


def preview_frame_start(event_frame, frame_step=6):
    """Align sparse preview sampling so an explicit semantic event is rendered.

    Blender samples ``frame_start + n * frame_step``.  Starting every preview at
    frame 1 can skip a collision/release boundary entirely, making the preview
    appear physically wrong even when the full-resolution trajectory is correct.
    """
    if event_frame is None:
        return 1
    try:
        event_frame = int(event_frame)
    except (TypeError, ValueError):
        return 1
    if frame_step < 1 or event_frame < 1:
        return 1
    return 1 + ((event_frame - 1) % frame_step)


def output_video_fps(preview, frame_step=6, source_fps=24):
    """Preserve real-time playback for frame-continuous QA previews.

    Sparse previews retain the established 12 fps review format.  When every
    source frame is rendered, however, encoding those frames at 12 fps would
    make a 24 fps scene play at half speed.
    """
    if not preview:
        return source_fps
    if frame_step == 1:
        return source_fps
    return 12


def run_one(job):
    (blender, task_dir, out_root, gid, name, k, idx, member_slot, member_count,
     preview, split_mode, diversity_profile) = job
    script = find_script(task_dir, idx)
    # Output layout: output/{domain}_task/{task_id}/ with task_id = {domain}_{NNNN}
    # (domain == generator name, G-id dropped).
    sdir = os.path.join(out_root, f"{name}_task", f"{name}_{k:04d}")
    os.makedirs(sdir, exist_ok=True)
    # A stale ERROR.txt from a previous failed run must not survive a re-run: later
    # diagnostics append to the file, so drop it up front rather than at OK-return
    # (which would also destroy this run's non-fatal warnings).
    try:
        os.remove(os.path.join(sdir, "ERROR.txt"))
    except OSError:
        pass
    if not script:
        with open(os.path.join(sdir, "ERROR.txt"), "w") as f:
            f.write("no script idx " + str(idx))
        return (gid, k, "NO_SCRIPT")
    seed = deterministic_seed(gid, k, idx)

    task_video_split = load_video_split(task_dir)
    requested_render_frame_step = PREVIEW_FRAME_STEP
    render_frame_step = requested_render_frame_step
    if preview and task_video_split and task_video_split.get("method") == "overlap_event":
        # A sparse stride cannot preserve an exact authored event seam. These
        # tasks therefore always use every source frame in QA previews, even
        # when the global preview stride is six.
        render_frame_step = 1
        if requested_render_frame_step != render_frame_step:
            print(
                f"{gid}/{k:04d}: preview frame step overridden "
                f"{requested_render_frame_step}->1 to preserve the overlap-event seam",
                flush=True,
            )
    preview_event_frame = load_preview_event_frame(task_dir, task_video_split)
    preview_start = preview_frame_start(preview_event_frame, render_frame_step) if preview else 1
    status = None
    err_out = err_err = ""
    out = ""
    for attempt in range(1 + MAX_RETRIES):
        # Own process group (start_new_session) so a timeout can reap Blender's helper
        # processes too, not just the direct child.
        proc = subprocess.Popen([blender, "--background", "--python", HARNESS, "--",
                                 "--script", script, "--seed", str(seed),
                                 "--sample-index", str(k),
                                 "--member-slot", str(member_slot),
                                 "--member-count", str(member_count),
                                 "--preview", "1" if preview else "0",
                                 "--preview-frame-start", str(preview_start),
                                 "--preview-frame-step", str(render_frame_step),
                                 "--diversity-profile", diversity_profile],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                start_new_session=True)
        try:
            out, err = proc.communicate(timeout=RENDER_TIMEOUT or None)
        except subprocess.TimeoutExpired:
            # A runaway Blender (e.g. a transmission-heavy scene on Cycles) would otherwise
            # block this worker thread forever. Kill its process group (SIGKILL after a
            # grace period), record what it printed, reclaim its scratch dir, and retry.
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except OSError:
                pass
            try:
                out, err = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except OSError:
                    pass
                out, err = proc.communicate()
            status = "RENDER_TIMEOUT"
            err_out = _tail_text(out)
            err_err = (_tail_text(err) + f"\nrender exceeded {RENDER_TIMEOUT}s and was "
                       f"killed (attempt {attempt + 1}/{1 + MAX_RETRIES})")
            _reclaim(_scratch_workdir(out))
            continue
        m = re.search(r"^OUTDIR=(.+)$", out, re.M)
        if m:
            status = "OK"
            break
        status = "RENDER_FAIL"
        err_out, err_err = out[-4000:], err[-4000:]
        _reclaim(_scratch_workdir(out))

    if status != "OK":
        with open(os.path.join(sdir, "ERROR.txt"), "w") as f:
            f.write(err_out + "\n---\n" + err_err)
        return (gid, k, status)

    rd = m.group(1).strip()
    workdir = _scratch_workdir(out)
    try:
        seq = frame_seq(rd)
        if not seq:
            with open(os.path.join(sdir, "ERROR.txt"), "w") as f:
                f.write("no frames in " + rd)
            return (gid, k, "NO_FRAMES")
        # Full video is stitched only as the frame-accurate cutting source for
        # input/target and deleted after a successful split — it is not shipped.
        mp4 = os.path.join(sdir, ".full.mp4")
        ssg = load_ssg(rd)
        source_fps = float((ssg or {}).get("fps") or 24)
        fps = output_video_fps(preview, render_frame_step, source_fps)
        # Glob (sorted) is robust to non-contiguous frame numbering — preview mode renders
        # a sparse subset (e.g. 0001, 0007, 0013, ...), which the printf %0Nd + -start_number
        # path silently truncates to a single frame. Zero-padded names sort in capture order.
        ff = subprocess.run(["ffmpeg", "-y", "-framerate", str(fps), "-pattern_type", "glob",
                             "-i", os.path.join(os.path.dirname(seq[0]), "*.png"),
                             "-c:v", "libx264", "-pix_fmt", "yuv420p", mp4], capture_output=True)
        if ff.returncode != 0:
            err = ff.stderr.decode(errors="replace")[-4000:] if isinstance(ff.stderr, bytes) else ff.stderr[-4000:]
            with open(os.path.join(sdir, "ERROR.txt"), "w") as f:
                f.write("ffmpeg failed:\n" + err)
            return (gid, k, "FFMPEG_FAIL")
        ap = os.path.join(rd, "aligned_prompt.txt")
        if os.path.exists(ap):
            shutil.copyfile(ap, os.path.join(sdir, "prompt.txt"))
        sr = {}
        mi = re.search(r"^SR_INFO (.+)$", out, re.M)
        if mi:
            try:
                sr = json.loads(mi.group(1))
            except Exception:
                pass

        # trajectory.npz + input/target video (V2V / TV2V)
        if ssg:
            try:
                write_trajectory_npz(sdir, ssg)
            except Exception as e:
                with open(os.path.join(sdir, "ERROR.txt"), "a") as f:
                    f.write("\ntrajectory failed: " + str(e))
        split, split_info = compute_split(
            ssg,
            split_mode,
            len(seq),
            rendered_frames=frame_numbers(seq),
            task_split=task_video_split,
        )
        f1 = cut_subvideo(
            mp4, os.path.join(sdir, "input_video.mp4"),
            split_info["input_start_index"], split_info["input_end_index"], fps,
            pad_start_frames=split_info["input_pad_start_frames"],
        )
        f2 = cut_subvideo(
            mp4, os.path.join(sdir, "target_video.mp4"),
            split_info["target_start_index"], split_info["target_end_index"], fps,
            pad_end_frames=split_info["target_pad_end_frames"],
        )
        cuts_ok = True
        for fr, lbl in ((f1, "input_video"), (f2, "target_video")):
            if fr.returncode != 0:
                cuts_ok = False
                err = fr.stderr.decode(errors="replace")[-2000:] if isinstance(fr.stderr, bytes) else (fr.stderr or "")[-2000:]
                with open(os.path.join(sdir, "ERROR.txt"), "a") as f:
                    f.write(f"\n{lbl} ffmpeg failed:\n" + err)
        if cuts_ok:
            try:
                os.remove(mp4)
            except OSError:
                pass

        build_metadata(sdir, script, idx, seed, sr, preview, split_info,
                       diversity_profile=diversity_profile,
                       requested_preview_frame_step=requested_render_frame_step,
                       effective_preview_frame_step=render_frame_step,
                       source_fps=source_fps, output_fps=fps)
    finally:
        # reclaim the blender scratch dir (frames / .blend) on every exit path.
        # render.py roots OUT_DIR two levels under its /tmp/sr_* workdir; when the
        # WORKDIR marker is absent, derive it from rd (same sr_ prefix contract).
        if workdir is None:
            wd = os.path.dirname(os.path.dirname(rd))
            if os.path.basename(wd).startswith("sr_") and wd.startswith("/tmp/"):
                workdir = wd
        _reclaim(workdir)

    def _present(fname):
        p = os.path.join(sdir, fname)
        return os.path.isfile(p) and os.path.getsize(p) > 0

    missing = [f for f in ("input_video.mp4", "target_video.mp4", "prompt.txt",
                           "trajectory.npz", "metadata.json") if not _present(f)]
    if missing:
        with open(os.path.join(sdir, "ERROR.txt"), "a") as f:
            f.write("\nmissing: " + ",".join(missing))
        return (gid, k, "MISSING")
    if not cuts_ok:
        # ffmpeg can leave truncated cut files behind, so a failed cut is fatal
        # even when the completeness check passes.
        return (gid, k, "CUT_FAIL")
    if os.path.exists(os.path.join(sdir, "ERROR.txt")):
        # keep the driver's notion of success aligned with the audit, which
        # fails any sample carrying a recorded failure.
        return (gid, k, "PARTIAL")
    return (gid, k, "OK")


def _fmt_dur(s):
    """Human-readable duration: 9s / 3m07s / 1h04m."""
    s = int(s)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def _progress_bar(done, total, width=24):
    filled = int(width * done / total) if total else width
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def build_jobs(sel, blender, out, per, start=0, preview=False, split_mode="half",
               diversity_profile="task"):
    """Expand a task selection into per-sample render jobs.

    ``k`` is the member index and it is the sample's identity: it picks the
    source script and feeds ``deterministic_seed``. Rendering k = start..start+per-1
    therefore produces the same samples as that slice of a full 0..N run, so a
    task can be rendered in pieces — across machines, or resumed after one dies.
    """
    return [(blender, task_dir, out, gid, name, k, members[k % len(members)],
             k % len(members), len(members), bool(preview), split_mode, diversity_profile)
            for gid, name, members, task_dir in sel
            for k in range(start, start + per)]


def build_parser(parser=None):
    if parser is None:
        parser = argparse.ArgumentParser(description="Object-permanence dataset generator")
    parser.add_argument("--out", default="./out")
    parser.add_argument("--blender", default=_find_blender())
    parser.add_argument("--gen", default="all", help="single task id, e.g. G18, or 'all'")
    parser.add_argument("--gens", default=None, help="task range, e.g. G01-G11")
    parser.add_argument("--task", default=None, help="alias for a single task id")
    parser.add_argument("--per", type=int, default=20)
    parser.add_argument("--start", type=int, default=0,
                        help="first member index to render (default 0). Renders "
                             "k = start .. start+per-1, so a task can be rendered in "
                             "pieces or resumed part-way. The index drives the seed and "
                             "the source-script pick, so a piece yields the same samples "
                             "as that slice of a full run.")
    parser.add_argument("--preview", type=int, default=0, help="1 = low-resolution preview (360p)")
    parser.add_argument("--preview-frame-step", type=int, default=6,
                        help="preview temporal stride; use 1 for frame-continuous event QA (default 6)")
    parser.add_argument("--split-mode", dest="split_mode", default="half", choices=["event", "half"],
                        help="how to cut input_video / target_video: 'half' = temporal midpoint (default), "
                             "'event' = deepest-occlusion frame (falls back to midpoint)")
    parser.add_argument("--diversity-profile", default="task", choices=["task", "surface"],
                        help="'task' samples manifest-owned semantic-safe parameters in addition "
                             "to surface variation; 'surface' preserves the previous appearance-only behavior")
    parser.add_argument("--parallel", type=int, default=3)
    parser.add_argument("--render-timeout", dest="render_timeout", type=int, default=RENDER_TIMEOUT,
                        help="hard cap per Blender render in seconds, 0 = no timeout "
                             f"(default {RENDER_TIMEOUT})")
    parser.add_argument("--list", action="store_true", help="list tasks and exit")
    return parser


def main(args=None):
    if args is None:
        args = build_parser().parse_args()

    global RENDER_TIMEOUT, PREVIEW_FRAME_STEP
    RENDER_TIMEOUT = max(0, getattr(args, "render_timeout", RENDER_TIMEOUT) or 0)
    PREVIEW_FRAME_STEP = max(1, getattr(args, "preview_frame_step", PREVIEW_FRAME_STEP) or 1)

    tasks = load_tasks()
    if args.list:
        for gid, name, members, td in tasks:
            print(f"{gid}  {name:34s} members={members}")
        print(f"\n{len(tasks)} tasks")
        return
    sel = select(tasks, args.gen, args.gens, args.task)
    if not sel:
        raise SystemExit("no task matching selection")
    if args.per <= 0:
        raise SystemExit(f"--per must be >= 1 (got {args.per}); a typo here used to report DONE 0/0 OK")
    if args.parallel <= 0:
        raise SystemExit(f"--parallel must be >= 1 (got {args.parallel})")
    if not args.blender:
        raise SystemExit("Blender not found: pass --blender /path/to/blender or set OP_BLENDER. "
                         "Searched $PATH and: " + ", ".join(_BLENDER_CANDIDATES))

    first_index = max(0, args.start)
    jobs = build_jobs(sel, args.blender, args.out, args.per, first_index,
                      bool(args.preview), args.split_mode, args.diversity_profile)
    total = len(jobs)
    span = f"k={first_index}..{first_index + args.per - 1}"
    print(f"{len(sel)} task(s) x {args.per} = {total} samples ({span}), "
          f"preview={args.preview}, parallel={args.parallel}")
    results = []
    done = ok = 0
    t0 = time.time()
    live = sys.stdout.isatty()  # carriage-return updates on a terminal; plain lines when piped/logged
    with cf.ThreadPoolExecutor(max_workers=args.parallel) as ex:
        # as_completed → progress reflects real completion order, so ETA stays honest
        # even when one sample is much slower than the rest.
        futures = [ex.submit(run_one, job) for job in jobs]
        for fut in cf.as_completed(futures):
            r = fut.result()
            results.append(r)
            done += 1
            if r[2] == "OK":
                ok += 1
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate if rate > 0 else 0
            status = (f"{_progress_bar(done, total)} {done}/{total} ({100 * done // total}%) "
                      f"| ok={ok} fail={done - ok} | {_fmt_dur(elapsed)} elapsed | ETA {_fmt_dur(eta)}")
            if r[2] != "OK":
                # persist the failure on its own line, above the live status line
                fail_line = f"   ! {r[0]} k={r[1]} {r[2]}"
                print(("\r" + fail_line.ljust(len(status))) if live else fail_line)
            if live:
                sys.stdout.write("\r" + status + "  ")
                sys.stdout.flush()
            else:
                print(status)
    if live:
        sys.stdout.write("\n")
    fail = total - ok
    print(f"DONE {ok}/{total} OK" + (f", {fail} failed" if fail else "")
          + f" in {_fmt_dur(time.time() - t0)}")
    if fail:
        # A fleet driver must see failure in the exit code: "object-permanence
        # generate && aws s3 sync" would otherwise sync a fully failed shard as
        # success.
        sys.exit(1)


if __name__ == "__main__":
    main()
