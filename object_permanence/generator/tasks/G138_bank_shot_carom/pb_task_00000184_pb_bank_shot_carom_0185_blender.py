# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_BANK_SHOT_CAROM_0185",
  "scene_kind": "bank_shot_carom",
  "prompt": "A ball rolls across a flat surface, banks off a straight cushion at an angle (a clean rebound where the outgoing angle mirrors the incoming one), then travels on and strikes a resting target ball, sending it rolling away while the striker slows. Both balls remain and neither passes through the cushion or through the other ball."
}""")
ITEM_ID = CASE["item_id"]

FPS = 24
FRAME_START = 1
FRAME_END = 120

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

OUT_DIR = os.path.join(PROJECT_ROOT, "permanence_blender_outputs", ITEM_ID)
FRAMES_DIR = os.path.join(OUT_DIR, "frames")
SCENE_FILE = os.path.join(OUT_DIR, f"{ITEM_ID}_scene.blend")
TASK_JSON_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_task.json")

INPUT_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_input_frame_01.png")
OPTIONAL_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_event_frame_02.png")
OPTIONAL_FRAME_02B_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_final_frame_02B.png")


# ============================================================
# General helpers
# ============================================================

def ensure_dirs():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(FRAMES_DIR, exist_ok=True)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    for block in list(bpy.data.meshes):
        if block.users == 0:
            bpy.data.meshes.remove(block)
    for block in list(bpy.data.materials):
        if block.users == 0:
            bpy.data.materials.remove(block)
    for block in list(bpy.data.cameras):
        if block.users == 0:
            bpy.data.cameras.remove(block)
    for block in list(bpy.data.lights):
        if block.users == 0:
            bpy.data.lights.remove(block)


def clamp01(t):
    return max(0.0, min(1.0, float(t)))


def smooth01(t):
    t = clamp01(t)
    return 3.0 * t * t - 2.0 * t * t * t


def ease_in_quad(t):
    t = clamp01(t)
    return t * t


def ease_out_quad(t):
    t = clamp01(t)
    return 1.0 - (1.0 - t) * (1.0 - t)


def lerp(a, b, t):
    return a + (b - a) * t


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def make_mat(name, color, roughness=0.55, metallic=0.0, alpha=1.0, blend=None):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (color[0], color[1], color[2], alpha)

    try:
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            if "Base Color" in bsdf.inputs:
                bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], alpha)
            if "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = alpha
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = roughness
            if "Metallic" in bsdf.inputs:
                bsdf.inputs["Metallic"].default_value = metallic
    except Exception:
        pass

    if blend is None:
        blend = "BLEND" if alpha < 1.0 else "OPAQUE"

    try:
        mat.blend_method = blend
        mat.show_transparent_back = True
        mat.use_screen_refraction = alpha < 1.0
    except Exception:
        pass

    return mat


def tag(obj, object_id, role, category, shape, color_name, is_dynamic, solid=True, **extras):
    obj["pb_object_id"] = object_id
    obj["pb_role"] = role
    obj["pb_category"] = category
    obj["pb_shape"] = shape
    obj["pb_color_name"] = color_name
    obj["pb_is_dynamic"] = bool(is_dynamic)
    obj["pb_solid"] = bool(solid)
    obj["pb_can_disappear"] = False
    obj["pb_can_change_color"] = False
    obj["pb_can_change_size"] = False
    for k, v in extras.items():
        obj[k] = v


def add_cube(name, location, dimensions, material=None, role="static_solid", color_name="gray", is_dynamic=False, solid=True):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material is not None:
        obj.data.materials.append(material)

    tag(
        obj,
        name,
        role,
        "dynamic_object" if is_dynamic else ("static_solid" if solid else "non_solid_marker"),
        "cube",
        color_name,
        is_dynamic,
        solid=solid,
    )
    return obj


def add_sphere(name, radius, location, material, color_name, role="target"):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(
        obj,
        name,
        role,
        "dynamic_object",
        "sphere",
        color_name,
        True,
        solid=True,
        pb_radius=radius,
    )
    return obj


def set_render(scene):
    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    scene.frame_set(FRAME_START)
    scene.render.fps = FPS
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False

    for engine in ["BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"]:
        try:
            scene.render.engine = engine
            break
        except Exception:
            pass

    try:
        scene.eevee.taa_render_samples = 64
        scene.eevee.use_gtao = True
        scene.eevee.gtao_distance = 3
        scene.eevee.gtao_factor = 1.2
    except Exception:
        pass

    if scene.world is None:
        scene.world = bpy.data.worlds.new("clean_world")
    scene.world.color = (1.0, 1.0, 1.0)

    try:
        scene.view_settings.view_transform = "Filmic"
        scene.view_settings.look = "Medium High Contrast"
        scene.view_settings.exposure = 0.0
        scene.view_settings.gamma = 1.0
    except Exception:
        pass


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor_warm", (0.82, 0.80, 0.75), roughness=0.82)
    MATS["gray"] = make_mat("mat_neutral_gray", (0.46, 0.46, 0.46), roughness=0.62)
    MATS["dark_gray"] = make_mat("mat_dark_gray", (0.18, 0.18, 0.20), roughness=0.72)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)
    MATS["cushion"] = make_mat("mat_cushion", (0.30, 0.31, 0.34), roughness=0.55)
    # Two distinct ball colours so the striker and target read apart.
    MATS["striker"] = make_mat("mat_striker_ball", (0.80, 0.24, 0.20), roughness=0.34, metallic=0.10)
    MATS["target"] = make_mat("mat_target_ball", (0.20, 0.42, 0.82), roughness=0.34, metallic=0.10)


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube(
        "large_floor_base",
        (0.0, 0.4, -0.05),
        (13.0, 9.0, 0.10),
        material=MATS["floor"],
        role="ground",
        color_name="warm_beige",
    )

    add_cube(
        "rear_backdrop_panel",
        (0.0, 3.6, 1.60),
        (12.0, 0.08, 3.20),
        material=MATS["backdrop"],
        role="background",
        color_name="off_white",
    )

    bpy.ops.object.light_add(type="AREA", location=(-3.8, -4.4, 6.5))
    key = bpy.context.object
    key.name = "large_softbox_light"
    key.data.energy = 1050
    key.data.size = 6.0

    bpy.ops.object.light_add(type="POINT", location=(3.7, -2.8, 4.2))
    fill = bpy.context.object
    fill.data.energy = 165
    fill.name = "right_fill_light"

    return scene


def setup_camera(scene, location=(0.0, -9.2, 1.45), target=(0.0, 0.0, 1.15), lens=34):
    bpy.ops.object.camera_add(location=location)
    camera = bpy.context.object
    camera.name = "camera_main"
    camera.data.lens = lens
    look_at(camera, target)
    camera.data.dof.use_dof = False
    scene.camera = camera
    return camera


# ============================================================
# Bank-shot-carom scene
# ============================================================
#
# A striker ball rolls in from the lower-left, banks off a straight cushion that
# runs along +X (a clean reflection: the Y-component of its velocity flips while
# the X-component is unchanged, so the outgoing angle mirrors the incoming one),
# then carries on along the reflected ray and strikes a resting target ball. The
# target rolls away along the reflected direction; the striker slows to rest.
# The striker centre never crosses the cushion contact line (no penetration) and
# never comes within 2R of the target before contact.

BALL_RADIUS = 0.40
BALL_Z = BALL_RADIUS
CONTACT_D = 2.0 * BALL_RADIUS

# Cushion: a straight gray wall running along X. Its front face is at CUSHION_Y;
# a ball centre banks when it reaches BANK_LINE_Y = CUSHION_Y - R.
CUSHION_Y = 1.70
CUSHION_THICK = 0.24
CUSHION_H = 0.80
BANK_LINE_Y = CUSHION_Y - BALL_RADIUS

# Striker approach.
STRIKER_START = Vector((-2.80, -1.10, BALL_Z))
# Incoming direction toward the cushion (heads +X and +Y).
_D_IN = Vector((2.5, 2.2, 0.0)).normalized()

# Post-carom target travel and striker creep.
CAROM_LEG = 2.60          # striker travel W->contact (sets the carom-leg speed)
STRIKER_CREEP = 0.35

F_BANK = 34      # striker reaches the cushion and rebounds
F_HIT = 72       # striker reaches the target
F_SETTLE = 110   # target has rolled to rest

# Struck target leaves slower than the striker's carom leg and eases OUT to rest.
# With ease_out_quad the peak (initial) speed == 2*TARGET_TRAVEL/window, so
# deriving TARGET_TRAVEL from the carom-leg speed pins the target's PEAK speed
# and lets it decelerate monotonically to rest (no sudden speed-up).
_STRIKER_CAROM_SPEED = CAROM_LEG / float(F_HIT - F_BANK)
TARGET_TRAVEL = _STRIKER_CAROM_SPEED * (F_SETTLE - F_HIT) / 2.0 * 0.6   # struck ball moves slower than the striker's carom leg


def _geometry():
    """Bank point W, reflected unit direction d_out, target rest centre T, and
    the striker contact centre (T - d_out * 2R)."""
    # Advance from the start along d_in until the centre y reaches BANK_LINE_Y.
    dy_needed = BANK_LINE_Y - STRIKER_START.y
    s = dy_needed / _D_IN.y
    W = STRIKER_START + _D_IN * s
    W.z = BALL_Z
    d_out = Vector((_D_IN.x, -_D_IN.y, 0.0)).normalized()  # reflection about the horizontal cushion
    # Place the target one striker-travel down the reflected ray from the bank.
    striker_contact = W + d_out * CAROM_LEG
    striker_contact.z = BALL_Z
    T = striker_contact + d_out * CONTACT_D    # target centre one diameter beyond contact centre
    T.z = BALL_Z
    return W, d_out, T, striker_contact


def build_bank_shot_carom_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(0.3, -8.6, 5.4), target=(0.6, 0.1, BALL_Z), lens=40)

    W, d_out, T, striker_contact = _geometry()

    # Cushion wall (apparatus -> repainted gray by render.py via the "wall" role).
    add_cube(
        "cushion_wall",
        (0.6, CUSHION_Y + CUSHION_THICK * 0.5, CUSHION_H * 0.5),
        (8.0, CUSHION_THICK, CUSHION_H),
        material=MATS["cushion"],
        role="cushion_wall",
        color_name="dark_gray",
    )

    striker = add_sphere(
        "striker_ball",
        BALL_RADIUS,
        Vector(STRIKER_START),
        MATS["striker"],
        "red",
        role="striker_ball",
    )
    striker["pb_count_conserved"] = True
    striker["pb_motion_constraint"] = "rolls_on_flat_surface"

    target = add_sphere(
        "target_ball",
        BALL_RADIUS,
        T,
        MATS["target"],
        "blue",
        role="target_ball",
    )
    target["pb_count_conserved"] = True
    target["pb_motion_constraint"] = "rolls_on_flat_surface"

    return {
        "scene": scene,
        "kind": "bank_shot_carom",
        "striker": striker,
        "target": target,
        "bank_point": W,
        "d_out": d_out,
        "target_start": T,
        "striker_contact": striker_contact,
    }


# ============================================================
# Animation
# ============================================================


def _striker_position(frame, objs):
    W = objs["bank_point"]
    d_out = objs["d_out"]
    contact = objs["striker_contact"]

    if frame <= F_BANK:
        t = clamp01((frame - FRAME_START) / float(F_BANK - FRAME_START))
        return STRIKER_START + (W - STRIKER_START) * t
    if frame <= F_HIT:
        t = clamp01((frame - F_BANK) / float(F_HIT - F_BANK))
        return W + (contact - W) * t
    # After the carom the striker slows to rest, creeping a little along d_out.
    t = clamp01((frame - F_HIT) / float(F_SETTLE - F_HIT))
    s = ease_out_quad(t)
    pos = contact + d_out * (STRIKER_CREEP * s)
    pos.z = BALL_Z
    return pos


def _target_position(frame, objs):
    T = objs["target_start"]
    d_out = objs["d_out"]
    if frame <= F_HIT:
        return Vector(T)
    t = clamp01((frame - F_HIT) / float(F_SETTLE - F_HIT))
    s = ease_out_quad(t)
    pos = T + d_out * (TARGET_TRAVEL * s)
    pos.z = BALL_Z
    return pos


def _roll_rotation(obj, prev_pos, cur_pos, radius):
    delta = cur_pos - prev_pos
    delta.z = 0.0
    dist = delta.length
    if dist < 1e-7:
        return
    travel_dir = delta.normalized()
    up = Vector((0.0, 0.0, 1.0))
    axis = travel_dir.cross(up)
    if axis.length < 1e-7:
        return
    axis.normalize()
    angle = dist / radius
    from mathutils import Quaternion
    q = Quaternion(axis, angle)
    cur = obj.rotation_euler.to_quaternion()
    new = q @ cur
    obj.rotation_euler = new.to_euler()


def animate_bank_shot_carom(objs, frame, prev):
    striker = objs["striker"]
    target = objs["target"]

    spos = _striker_position(frame, objs)
    tpos = _target_position(frame, objs)

    prev_s = prev.get("striker")
    prev_t = prev.get("target")
    if prev_s is not None:
        _roll_rotation(striker, prev_s, spos, BALL_RADIUS)
    if prev_t is not None:
        _roll_rotation(target, prev_t, tpos, BALL_RADIUS)

    striker.location = spos
    striker.keyframe_insert(data_path="location", frame=frame)
    striker.keyframe_insert(data_path="rotation_euler", frame=frame)

    target.location = tpos
    target.keyframe_insert(data_path="location", frame=frame)
    target.keyframe_insert(data_path="rotation_euler", frame=frame)

    striker["pb_is_moving"] = bool(prev_s is not None and (spos - prev_s).length > 1e-5)
    target["pb_is_moving"] = bool(frame > F_HIT and prev_t is not None and (tpos - prev_t).length > 1e-5)
    if frame <= F_BANK:
        striker["pb_state"] = "approaching_cushion"
    elif frame <= F_HIT:
        striker["pb_state"] = "caroming_to_target"
    else:
        striker["pb_state"] = "slowing"
    target["pb_state"] = "stationary" if frame <= F_HIT else "struck_moving"

    prev["striker"] = spos
    prev["target"] = tpos


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    prev = {}
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if kind == "bank_shot_carom":
            animate_bank_shot_carom(objs, frame, prev)
        else:
            raise RuntimeError("Unknown kind: " + str(kind))

    scene.frame_set(FRAME_START)


# ============================================================
# Output
# ============================================================

def render_png(scene, frame, path):
    scene.frame_set(frame)
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def render_animation(scene):
    if os.path.exists(FRAMES_DIR):
        shutil.rmtree(FRAMES_DIR)
    os.makedirs(FRAMES_DIR, exist_ok=True)

    scene.frame_set(FRAME_START)
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = os.path.join(FRAMES_DIR, f"{ITEM_ID}_frame_")
    bpy.ops.render.render(animation=True)


def write_task_json():
    task = {
        "item_id": ITEM_ID,
        "visual_regime": "3D_procedural_control",
        "fps": FPS,
        "inputs": {
            "text_prompt": CASE["prompt"],
        },
        "reference_completion_frames_dir": "frames",
        "reference_completion_video": None,
        "scene_file": f"{ITEM_ID}_scene.blend",
    }

    with open(TASK_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(task, f, indent=2, ensure_ascii=False)


def save_scene():
    bpy.ops.wm.save_as_mainfile(filepath=SCENE_FILE)


def build_scene_by_kind():
    kind = CASE["scene_kind"]

    if kind == "bank_shot_carom":
        return build_bank_shot_carom_scene()

    raise RuntimeError("Unknown scene_kind: " + str(kind))


def main():
    ensure_dirs()
    clear_scene()

    objs = build_scene_by_kind()
    scene = objs["scene"]

    animate_scene(objs)

    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, 72, OPTIONAL_FRAME_PATH)
    render_png(scene, 120, OPTIONAL_FRAME_02B_PATH)

    render_animation(scene)
    write_task_json()
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("scene_kind:", CASE["scene_kind"])
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
