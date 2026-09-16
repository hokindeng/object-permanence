# -*- coding: utf-8 -*-
"""
Blender render backend for object-permanence samples.

Runs inside Blender, driven by core/generate.py. It copies a task's
pb_task_*_blender.py scene script into a scratch workdir, executes it and calls
its main(). Before execution it applies manifest-owned, constraint-reviewed
task parameters, then layers the balanced observation factors and seeded
nuisance transforms.

  FACTORIALLY CROSSED per sample:
    - member/object variant: selected by the driver from authored member scripts
    - target colour  : grouped by logical identity (same shape + original colour
                       gets one new colour, so multi-instance objects stay
                       consistent); eight exact levels, prompt rewritten to match
    - camera angle   : three clearly separated orbits around the authored focus
    - task parameters: two safe interior levels for manifest-owned geometry,
                       placement, motion, and dynamics parameters

  SEEDED NUISANCE VARIATION:
    - target material: metallic / roughness
    - apparatus colour: one muted tone for the rig, skipping floor/backdrop and
                       any scripted transparent surface
    - lighting       : energy / position / warm-cool tint

  NEVER touched:
    - mesh topology, semantic contract, or input/target split boundary

Alongside the scene's own render output it writes aligned_prompt.txt and
scene_state_graph.json (per-frame world transforms of the target and apparatus
objects) into that output directory.

Blender must be 4.4.x unless OP_ALLOW_BLENDER_MISMATCH is set. With no OpenGL
context the engine preference is rewritten to Cycles; OP_FORCE_EEVEE=1 keeps
EEVEE instead.

Run inside Blender:
    blender --background --python render.py -- --script <orig.py> --seed <s> [--preview 1]

Prints WORKDIR=<scratch> up front, a RENDER_ENGINE: line when the engine
preference is overridden, then SR_INFO <json> and OUTDIR=<path> on success.
"""

import bpy, os, sys, json, random, glob, re, math
from mathutils import Matrix, Vector

PACKAGE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, PACKAGE_ROOT)

from object_permanence.generator.core.diversity import apply_source_bindings, load_script_diversity
from object_permanence.generator.core.state_graph import prioritize_recorded_objects

# object colours — 16 vivid, clearly-named, mutually-distinct tones (all visible on
# the light scene). Names are real colour words so the prompt can be rewritten cleanly.
PALETTE = {
    "orange": (0.97, 0.45, 0.10), "red": (0.90, 0.15, 0.15),
    "pink": (0.96, 0.58, 0.74), "magenta": (0.85, 0.18, 0.62),
    "purple": (0.55, 0.25, 0.80), "navy": (0.10, 0.18, 0.50),
    "blue": (0.18, 0.40, 0.95), "cyan": (0.10, 0.72, 0.82),
    "teal": (0.08, 0.52, 0.52), "green": (0.18, 0.68, 0.30),
    "lime": (0.62, 0.85, 0.20), "yellow": (0.98, 0.80, 0.15),
    "gold": (0.83, 0.62, 0.12), "brown": (0.42, 0.26, 0.14),
    "gray": (0.45, 0.46, 0.48), "black": (0.05, 0.05, 0.06),
}
# muted tones for APPARATUS (low saturation, stays "rig-like", keeps contrast)
APPARATUS_TONES = [
    (0.62, 0.63, 0.66), (0.55, 0.57, 0.62), (0.70, 0.69, 0.66),
    (0.48, 0.52, 0.58), (0.66, 0.62, 0.58), (0.58, 0.60, 0.55),
]
APPARATUS_ROLES = ("wall", "screen", "rail", "post", "tray", "door", "panel", "lid",
                   "support", "disk", "beam", "mask", "frame", "gate", "bridge",
                   "cover", "drawer", "cabinet", "curtain", "turntable", "slider",
                   "wheel", "track", "tube", "tunnel", "box", "shutter", "flap",
                   "sign", "envelope", "locker", "platform", "rod", "guide")
ENVIRONMENT_ROLES = frozenset({"floor", "backdrop", "ground", "background"})
SKIP_ROLES = tuple(sorted(ENVIRONMENT_ROLES))
WIDE_VIEW_ENVIRONMENT_SCALE = 3.0

PROMPT_PREFIX = "Continue this scene as a short video."
_PROMPT_PREFIX_RE = re.compile(
    r"^(?:continue\s+this\s+scene\s+as\s+a\s+short\s+video[.!?]?\s*)+",
    re.IGNORECASE,
)


def normalize_prompt_prefix(prompt):
    """Give every generated sample one canonical continuation instruction."""
    body = _PROMPT_PREFIX_RE.sub("", str(prompt).strip()).strip()
    return PROMPT_PREFIX if not body else PROMPT_PREFIX + " " + body


def parse_args():
    a = sys.argv
    a = a[a.index("--") + 1:] if "--" in a else []
    out = {}
    i = 0
    while i < len(a):
        if a[i].startswith("--"):
            out[a[i][2:]] = a[i + 1] if i + 1 < len(a) else ""
            i += 2
        else:
            i += 1
    return out


ARGS = parse_args()
SCRIPT = ARGS["script"]
SEED = int(ARGS.get("seed", 0))
PREVIEW = ARGS.get("preview", "0") == "1"
PREVIEW_FRAME_START = int(ARGS.get("preview-frame-start", "1"))
PREVIEW_FRAME_STEP = max(1, int(ARGS.get("preview-frame-step", "6")))
DIVERSITY_PROFILE = ARGS.get("diversity-profile", "task")
SAMPLE_INDEX = int(ARGS.get("sample-index", 0))
MEMBER_SLOT = int(ARGS.get("member-slot", 0))
MEMBER_COUNT = int(ARGS.get("member-count", 1))
rng = random.Random(SEED)
TASK_DIVERSITY = load_script_diversity(
    SCRIPT, SEED, DIVERSITY_PROFILE, SAMPLE_INDEX, MEMBER_SLOT, MEMBER_COUNT
)


# fallback for scene scripts without pb_ tags: detect targets / colours by name
OBJ_KEYWORDS = ("target", "ball", "sphere", "cube", "pyramid", "cone", "block", "car")
NAME_APPARATUS = APPARATUS_ROLES + SKIP_ROLES + ("cap", "rim", "handle", "hole",
                 "plug", "peg", "pin", "ring", "stand", "base", "leg", "arm", "spine", "hinge")


def object_role(o):
    """Return one normalized semantic role without inferring it from the name."""
    return str(o.get("pb_role", "") or "").strip().lower()


def is_static_environment(o):
    """True only for an explicitly tagged, unparented, static scene surface.

    Exact role matching is deliberate: apparatus roles such as
    ``foreground_screen`` contain the substring ``ground`` but are not part of
    the background environment and must never be enlarged or omitted from the
    state graph.
    """
    return (
        o.type == "MESH"
        and object_role(o) in ENVIRONMENT_ROLES
        and not bool(o.get("pb_is_dynamic"))
        and o.parent is None
    )


def is_target(o):
    if o.type != "MESH":
        return False
    role = object_role(o)
    shape = (o.get("pb_shape", "") or "")
    if role or shape or o.get("pb_is_dynamic") is not None:
        if "target" in role:
            return True
        if o.get("pb_is_dynamic") and shape in ("sphere", "triangular_pyramid", "cube"):
            return not any(b in role for b in APPARATUS_ROLES + ("root",)) \
                and role not in ENVIRONMENT_ROLES
        return False
    name = o.name.lower()
    if "target" in name:
        return True
    if any(b in name for b in NAME_APPARATUS):
        return False
    return any(k in name for k in OBJ_KEYWORDS)


def target_identity(o):
    """(shape, original_colour) for grouping — from pb_ tags, else parsed from names."""
    shape = (o.get("pb_shape", "") or "").lower()
    color = (o.get("pb_color_name", "") or "").strip().lower()
    if not shape or not color:
        text = o.name.lower() + " " + " ".join(m.name.lower() for m in o.data.materials if m)
        tokens = set(re.split(r"[^a-z]+", text))
        if not shape:
            if tokens & {"sphere", "ball"}:
                shape = "sphere"
            elif tokens & {"pyramid", "cone"}:
                shape = "triangular_pyramid"
            elif tokens & {"cube", "block"}:
                shape = "cube"
        if not color:
            for cw in PALETTE:
                if cw in tokens:
                    color = cw; break
    return (shape, color)


def new_mat(name, color, metallic=0.0, rough=0.4):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    if b:
        b.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
        b.inputs["Metallic"].default_value = metallic
        b.inputs["Roughness"].default_value = rough
    return m


def knob_recolor_and_material(rng, factorial):
    """Apply the balanced colour factor; randomise only within-cell material."""
    tgts = [o for o in bpy.data.objects if is_target(o)]
    if not tgts:
        return {"targets": 0}
    groups = {}
    for o in tgts:
        groups.setdefault(target_identity(o), []).append(o)
    names = list(PALETTE.keys())
    color_factor = ((factorial or {}).get("factors") or {}).get("object_color", {})
    selected = color_factor.get("value", names[0])
    start = names.index(selected) if selected in names else 0
    # A stride of five is coprime with the 16-colour palette, so multi-object
    # scenes get distinct colours while the first logical target exactly follows
    # the factorial colour assignment recorded in metadata.
    names = [names[(start + 5 * i) % len(names)] for i in range(len(names))]
    color_map = {}
    used = []
    for gi, (key, objs) in enumerate(groups.items()):
        cn = names[gi % len(names)]
        metallic = round(rng.choice([0.0, 0.0, 0.3, 0.6, 0.85]), 2)
        rough = round(rng.uniform(0.15, 0.65), 2)
        for o in objs:
            m = new_mat(f"obj_{cn}_{gi}", PALETTE[cn], metallic, rough)
            o.data.materials.clear(); o.data.materials.append(m)
            o["pb_color_name"] = cn
        old = key[1]
        if old and old in PALETTE:
            color_map[old] = cn
        used.append({"old": key[1], "shape": key[0], "new": cn, "metallic": metallic,
                     "rough": rough, "instances": len(objs)})
    return {"targets": len(tgts), "groups": used, "color_map": color_map}


def _has_transparent_material(o):
    """True if the object already carries a transparent/glass material — low alpha or
    nonzero transmission on its Principled BSDF. Used to avoid overwriting scripted glass
    with an opaque apparatus tone (which would break visible-but-solid tasks, e.g. G36)."""
    for slot in getattr(o, "material_slots", []):
        m = slot.material
        if not m or not getattr(m, "use_nodes", False):
            continue
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        if bsdf is None:
            continue
        a = bsdf.inputs.get("Alpha")
        if a is not None and getattr(a, "default_value", 1.0) < 0.999:
            return True
        for key in ("Transmission Weight", "Transmission"):  # Blender 4.x renamed the socket
            t = bsdf.inputs.get(key)
            if t is not None and getattr(t, "default_value", 0.0) > 0.001:
                return True
    return False


def knob_apparatus_color(rng):
    """One muted tone for the rig (apparatus), kept opaque + contrasting."""
    tone = list(rng.choice(APPARATUS_TONES))
    n = 0
    for o in bpy.data.objects:
        if o.type != "MESH" or is_target(o):
            continue
        role = object_role(o)
        if is_static_environment(o):
            continue
        if not any(s in role for s in APPARATUS_ROLES):
            continue
        # Preserve scripted transparent/glass surfaces — never overwrite them with an opaque
        # tone, else visible-but-solid tasks (G36 glass box, G03 transparent wall) degenerate.
        if o.get("pb_transparent") or _has_transparent_material(o):
            continue
        c = [min(1, max(0, t + rng.uniform(-0.05, 0.05))) for t in tone]
        m = new_mat(f"app_{n}", c, 0.0, rng.uniform(0.5, 0.85))
        o.data.materials.clear(); o.data.materials.append(m)
        n += 1
    return {"tone": [round(x, 2) for x in tone], "n": n}


def knob_light(rng):
    tint = rng.uniform(-0.10, 0.10)
    for o in bpy.data.objects:
        if o.type == "LIGHT":
            try:
                o.data.energy *= rng.uniform(0.7, 1.4)
                o.location.x += rng.uniform(-1.0, 1.0)
                o.location.y += rng.uniform(-1.0, 1.0)
                c = o.data.color
                o.data.color = (min(1, c[0] + max(0, tint)), c[1], min(1, c[2] + max(0, -tint)))
            except Exception:
                pass


def knob_expand_view_environment(values):
    """Extend static floor/backdrop surfaces exposed by a wide camera orbit.

    Authored shots often use a finite plane sized exactly for the canonical
    camera.  A wider side view can otherwise reveal the black world beyond its
    edge.  Only the two broad axes of explicitly tagged static environment
    meshes are enlarged; their thin/collision axis and all task objects remain
    unchanged.
    """
    if abs(float(values.get("camera_azimuth_deg", 0.0))) < 8.0:
        return {"expanded": 0}
    expanded = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if not is_static_environment(obj):
            continue
        dims = list(obj.dimensions)
        broad_axes = sorted(range(3), key=lambda axis: dims[axis], reverse=True)[:2]
        for axis in broad_axes:
            obj.scale[axis] *= WIDE_VIEW_ENVIRONMENT_SCALE
        expanded.append(obj.name)
    return {"expanded": len(expanded), "objects": expanded}


def knob_camera_viewpoint(values):
    """Apply a visible camera orbit around the existing optical axis.

    The focus stays at the median target depth along the authored camera ray, so
    the composition remains centered. Distance only increases, preventing the
    perturbation from creating a tighter crop than the canonical shot.
    """
    scene = bpy.context.scene
    cam = scene.camera
    if cam is None:
        return {"status": "no_camera"}

    origin = cam.matrix_world.to_translation()
    forward = cam.matrix_world.to_quaternion() @ Vector((0.0, 0.0, -1.0))
    targets = [o for o in bpy.data.objects if is_target(o)]
    depths = sorted(
        (o.matrix_world.to_translation() - origin).dot(forward)
        for o in targets
        if (o.matrix_world.to_translation() - origin).dot(forward) > 0.1
    )
    focus_distance = depths[len(depths) // 2] if depths else 8.0
    focus = origin + forward * focus_distance
    offset = origin - focus

    azimuth = math.radians(float(values.get("camera_azimuth_deg", 0.0)))
    elevation = math.radians(float(values.get("camera_elevation_deg", 0.0)))
    distance_scale = float(values.get("camera_distance_scale", 1.0))
    offset = Matrix.Rotation(azimuth, 4, Vector((0.0, 0.0, 1.0))) @ offset
    right = offset.cross(Vector((0.0, 0.0, 1.0)))
    if right.length > 1e-6:
        offset = Matrix.Rotation(elevation, 4, right.normalized()) @ offset
    offset *= distance_scale

    cam.location = focus + offset
    cam.rotation_euler = (focus - cam.location).to_track_quat("-Z", "Y").to_euler()
    return {
        "azimuth_deg": round(math.degrees(azimuth), 3),
        "elevation_deg": round(math.degrees(elevation), 3),
        "distance_scale": round(distance_scale, 4),
        "focus_distance": round(float(focus_distance), 4),
        "target_count": len(targets),
    }


def set_preview(scene):
    """Render a standard-resolution QA preview at the requested temporal stride."""
    # Continuous event QA must remain visually comparable with the established
    # 640x360 review pages. The former 320x180 special case obscured small contact
    # gaps and made the continuous rerender look like a different-quality dataset.
    scene.render.resolution_x = 640
    scene.render.resolution_y = 360
    # The driver aligns this start to a manifest event boundary when one exists,
    # so sparse previews show the exact contact/release frame instead of jumping
    # from pre-event motion directly to its aftermath.
    scene.frame_start = max(1, PREVIEW_FRAME_START)
    scene.frame_step = PREVIEW_FRAME_STEP
    try:
        scene.eevee.taa_render_samples = 16
    except Exception:
        pass


STATE = {"info": None}


def apply_transforms():
    if STATE["info"] is not None:
        return
    info = {"task_diversity": TASK_DIVERSITY}
    def safe(name, fn, *a):
        try:
            info[name] = fn(*a)
        except Exception as e:
            info[name] = f"skip:{e}"
    safe("recolor_material", knob_recolor_and_material, rng, TASK_DIVERSITY.get("factorial"))
    safe("apparatus", knob_apparatus_color, rng)
    safe("light", knob_light, rng)
    safe("view_environment", knob_expand_view_environment, TASK_DIVERSITY.get("values", {}))
    safe("camera_viewpoint", knob_camera_viewpoint, TASK_DIVERSITY.get("values", {}))
    if PREVIEW:
        try:
            set_preview(bpy.context.scene); info["preview"] = True
        except Exception as e:
            info["preview"] = f"skip:{e}"
    STATE["info"] = info


# Lazily-probed Cycles compute device ("OPTIX"/"CUDA"), or None when no GPU is
# available (Cycles then stays on CPU). Probed at most once per process.
_CYCLES_GPU = None
_CYCLES_GPU_PROBED = False


def _enable_cycles_gpu():
    """Enable a GPU compute device for Cycles (OptiX preferred, then CUDA).

    Headless Cycles defaults to CPU; on a GPU box that makes renders ~10-50x
    slower than they need to be. Returns the device type enabled, or None.
    """
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
    except Exception:
        return None
    for dtype in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = dtype
        except Exception:
            continue
        try:
            prefs.refresh_devices()
        except Exception:
            pass
        devs = []
        try:
            devs = list(prefs.devices)
        except Exception:
            devs = []
        gpu_on = False
        for d in devs:
            is_gpu = getattr(d, "type", "") in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL")
            try:
                d.use = bool(is_gpu)
            except Exception:
                pass
            gpu_on = gpu_on or is_gpu
        if gpu_on:
            return dtype
    return None


def _probe_cycles_gpu():
    global _CYCLES_GPU, _CYCLES_GPU_PROBED
    if not _CYCLES_GPU_PROBED:
        _CYCLES_GPU = _enable_cycles_gpu()
        _CYCLES_GPU_PROBED = True
    return _CYCLES_GPU


def _render_init_handler(*args):
    apply_transforms()
    # Whenever the scene lands on Cycles (headless rewrite, or an EEVEE assignment
    # that fell through under OP_FORCE_EEVEE), steer it onto the GPU when one
    # exists and cap the sample count — the scene scripts only tune EEVEE samples,
    # so Cycles would otherwise use its 4096-sample default on the CPU (extremely
    # slow, watchdog-killed).
    try:
        sc = bpy.context.scene
        if sc.render.engine == "CYCLES":
            if _probe_cycles_gpu():
                sc.cycles.device = "GPU"
            sc.cycles.samples = 16 if PREVIEW else 96
            sc.cycles.use_denoising = True
    except Exception:
        pass


def align_prompt(ns, out_dir, info):
    prompt = None
    case = ns.get("CASE")
    if isinstance(case, dict):
        prompt = case.get("prompt") or (case.get("inputs", {}) or {}).get("text_prompt")
    if not prompt:
        for tj in glob.glob(os.path.join(out_dir, "*task*.json")):
            try:
                with open(tj, encoding="utf-8") as f:
                    d = json.load(f)
                prompt = ((d.get("inputs", {}) or {}).get("text_prompt") or d.get("prompt")
                          or (d.get("semantic_ground_truth", {}) or {}).get("task_summary_en"))
                if prompt:
                    break
            except Exception:
                pass
    if not prompt:
        return {"status": "no_prompt"}
    cmap = ((info or {}).get("recolor_material") or {})
    cmap = cmap.get("color_map", {}) if isinstance(cmap, dict) else {}
    # filter out empty keys to prevent regex matching every word boundary
    cmap = {k: v for k, v in cmap.items() if k}
    aligned = prompt
    if cmap:
        def repl(m):
            art, col = m.group(1), m.group(2)
            new = cmap[col.lower()]
            new = new if not col[0].isupper() else new.capitalize()
            if art:
                a = "an" if new.lower()[0] in "aeiou" else "a"
                if art[0].isupper():
                    a = a.capitalize()
                return a + " " + new
            return new
        pat = re.compile(r"\b(an?\b\s+)?(" + "|".join(re.escape(k) for k in cmap) + r")\b", re.IGNORECASE)
        aligned = pat.sub(repl, prompt)
    aligned = normalize_prompt_prefix(aligned)
    with open(os.path.join(out_dir, "aligned_prompt.txt"), "w", encoding="utf-8") as f:
        f.write(aligned.strip() + "\n")
    return {"status": "ok", "color_map": cmap, "changed": aligned != prompt}


def record_scene_state_graph(out_dir):
    """Per-frame world transforms of the target + apparatus objects (the GT object
    states the evaluator needs). Recorded over the FULL frame range regardless of
    any preview subsampling."""
    scene = bpy.context.scene
    fe = scene.frame_end or 120
    candidates = [o for o in bpy.data.objects
                  if o.type == "MESH" and not is_static_environment(o)]
    # The trajectory format intentionally remains bounded, but semantic targets and
    # moving bodies must never be displaced by decorative track/apparatus meshes.
    objs = prioritize_recorded_objects(
        candidates,
        is_target=is_target,
        is_dynamic=lambda o: bool(o.get("pb_is_dynamic")),
        limit=48,
    )
    meta_objs = {o.name: {"shape": o.get("pb_shape", "") or "", "role": o.get("pb_role", "") or "",
                          "color": o.get("pb_color_name", "") or "", "is_target": is_target(o)} for o in objs}
    frames = []
    for f in range(1, fe + 1):
        scene.frame_set(f)
        st = {}
        for o in objs:
            m = o.matrix_world; t = m.to_translation(); e = m.to_euler(); q = m.to_quaternion()
            st[o.name] = {"loc": [round(t.x, 4), round(t.y, 4), round(t.z, 4)],
                          "rot": [round(e.x, 4), round(e.y, 4), round(e.z, 4)],
                          "quat": [round(q.w, 4), round(q.x, 4), round(q.y, 4), round(q.z, 4)]}
        frames.append({"frame": f, "objects": st})
    scene.frame_set(1)
    ssg = {"schema": "permanencebench_scene_state_graph_v3_generator",
           "fps": scene.render.fps or 24, "frame_start": 1, "frame_end": fe,
           "objects": meta_objs, "frames": frames}
    with open(os.path.join(out_dir, "scene_state_graph.json"), "w", encoding="utf-8") as f:
        json.dump(ssg, f, ensure_ascii=False)
    return {"objects": len(objs), "frames": len(frames)}


def main():
    import shutil as _sh
    # Hard version gate. Discovery order can silently pick apt's Blender 3.x
    # (no headless EEVEE) or a future major with different pixels, with no
    # warning at all. Production is pinned to 4.4; OP_ALLOW_BLENDER_MISMATCH
    # is an escape hatch for local experiments only.
    if bpy.app.version[:2] != (4, 4) and not os.environ.get("OP_ALLOW_BLENDER_MISMATCH"):
        raise RuntimeError(
            f"Blender {bpy.app.version_string} is not the pinned 4.4.x -- pixels would "
            "silently diverge across the fleet. Install 4.4.x (README: Install) or set "
            "OP_ALLOW_BLENDER_MISMATCH=1 to override for local experiments.")
    workdir = os.path.join("/tmp", f"sr_{SEED}_{os.getpid()}")
    sdir = os.path.join(workdir, "scripts")
    os.makedirs(sdir, exist_ok=True)
    # Machine-parsable marker for the driver, flushed immediately so it survives a
    # watchdog kill — generate.py uses it to reclaim this scratch dir on failure.
    print("WORKDIR=" + workdir, flush=True)
    local_script = os.path.join(sdir, os.path.basename(SCRIPT))
    _sh.copyfile(SCRIPT, local_script)

    bpy.app.handlers.render_init.append(_render_init_handler)

    with open(local_script, "r", encoding="utf-8") as f:
        src = f.read()
    src, source_binding_info = apply_source_bindings(src, TASK_DIVERSITY)

    # EEVEE (Next and legacy) is a GPU rasteriser and needs a live OpenGL context.
    # On a headless box with no OpenGL ("No OpenGL vendor detected"), bpy.ops.render.render()
    # segfaults inside the GL/EEVEE backend — a C-level crash the task scripts' try/except
    # around `scene.render.engine = engine` cannot catch (assigning the engine never raises,
    # so the loop always sticks on BLENDER_EEVEE_NEXT). Cycles needs no OpenGL, so when no GL
    # context exists we rewrite the engine preference to Cycles only. GPU/desktop boxes keep EEVEE.
    #
    # CAVEAT: gpu.platform.vendor() also fails in --background mode on boxes where headless
    # EEVEE actually works (Blender 4.4+ with an NVIDIA GPU renders EEVEE headless fine, and
    # is ~2-5x faster than capped Cycles; transmission-heavy tasks like G01 are 10x+ faster).
    # OP_FORCE_EEVEE=1 skips the Cycles rewrite for that case. Only set it on Blender 4.4+
    # with a GPU — on a truly GL-less box or Blender <= 4.2 headless it will segfault.
    def _has_opengl():
        try:
            import gpu
            return bool(gpu.platform.vendor())
        except Exception:
            return False

    if os.environ.get("OP_FORCE_EEVEE", "").strip().lower() not in ("", "0", "false", "no"):
        print("RENDER_ENGINE: OP_FORCE_EEVEE set -> keeping EEVEE engine preference "
              "(requires Blender 4.4+ with a GPU)")
    elif not _has_opengl():
        src = src.replace(
            '["BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"]',
            '["CYCLES"]',
        )
        gpu = _probe_cycles_gpu()
        print("RENDER_ENGINE: no OpenGL detected -> forcing CYCLES (headless-safe); "
              + (f"GPU={gpu}" if gpu else "GPU=none (CPU)"))

    ns = {
        "__name__": "pb_safe_import",
        "__file__": os.path.abspath(local_script),
        "DIVERSITY": dict(TASK_DIVERSITY.get("values") or {}),
    }
    exec(compile(src, local_script, "exec"), ns)

    if "main" in ns and callable(ns["main"]):
        ns["main"]()

    out_dir = ns.get("OUT_DIR") or ""
    if not out_dir:
        # No guessing: a stale directory harvested by an mtime scan would silently
        # produce mismatched samples. The missing OUTDIR= marker makes the driver
        # record this run as RENDER_FAIL with this traceback.
        raise RuntimeError("scene script did not set OUT_DIR; cannot locate its rendered output")

    prompt_info = align_prompt(ns, out_dir, STATE["info"])
    try:
        ssg_info = record_scene_state_graph(out_dir)
    except Exception as e:
        ssg_info = {"status": f"skip:{e}"}
    # Provenance: which Blender actually ran and which engine actually rendered.
    # Without these a Cycles-fallback shard or a wrong-Blender box is forever
    # indistinguishable from a clean EEVEE render.
    engine = ""
    try:
        engine = bpy.context.scene.render.engine
    except Exception:
        pass
    STATE["info"]["source_bindings"] = source_binding_info
    print("SR_INFO", json.dumps({"transforms": STATE["info"], "prompt": prompt_info, "ssg": ssg_info,
                                 "blender_version": bpy.app.version_string,
                                 "render_engine": engine}))
    print("OUTDIR=" + str(out_dir))

    # The scene scripts root OUT_DIR at PROJECT_ROOT = <script_dir>/.. , which lands
    # inside this workdir. Only drop the script copy here — the driver (generate.py)
    # still needs the rendered frames in out_dir and reclaims the workdir afterwards.
    _sh.rmtree(sdir, ignore_errors=True)


if __name__ == "__main__":
    main()
