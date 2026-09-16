# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_POOL_RACK_BREAK_0184",
  "scene_kind": "pool_rack_break",
  "prompt": "A ball rolls across a flat surface and strikes a triangular rack of six resting balls. On impact the rack breaks apart - the balls scatter outward along diverging directions and roll to rest - while the striker slows. All balls remain, the total count is conserved, and no ball passes through another."
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
    MATS["cue"] = make_mat("mat_cue_ball", (0.95, 0.94, 0.90), roughness=0.20)
    MATS["rack_red"] = make_mat("mat_rack_red", (0.78, 0.12, 0.12), roughness=0.24)
    MATS["rack_yellow"] = make_mat("mat_rack_yellow", (0.88, 0.72, 0.10), roughness=0.24)
    MATS["rack_blue"] = make_mat("mat_rack_blue", (0.12, 0.28, 0.72), roughness=0.24)
    MATS["rack_green"] = make_mat("mat_rack_green", (0.10, 0.52, 0.24), roughness=0.24)
    MATS["rack_orange"] = make_mat("mat_rack_orange", (0.86, 0.42, 0.08), roughness=0.24)
    MATS["rack_purple"] = make_mat("mat_rack_purple", (0.42, 0.14, 0.56), roughness=0.24)


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube(
        "large_floor_base",
        (0.0, 0.6, -0.05),
        (14.0, 10.0, 0.10),
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
# Pool-rack-break scene
# ============================================================
#
# A cue ball rolls in from -X and strikes the apex of a tight triangular rack of
# six balls (rows 1 + 2 + 3). On impact every rack ball scatters outward along a
# distinct, diverging direction and decelerates to rest (friction); the cue ball
# slows and drifts. Directions are chosen so the balls fan apart -- pairwise
# centre distance only grows after the break, so spheres never interpenetrate
# (min pairwise clearance stays >= 0). Ball count is conserved (1 cue + 6 rack).

BALL_RADIUS = 0.30
BALL_Z = BALL_RADIUS
CONTACT_D = 2.0 * BALL_RADIUS

RACK_GAP = 1.20                                                      # rest clearance in the rack
RACK_APEX_X = 0.60
ROW_DX = 2.0 * BALL_RADIUS * math.cos(math.radians(30.0)) * RACK_GAP  # row-to-row spacing (+X)
ROW_DY = BALL_RADIUS * RACK_GAP                                       # half in-row spacing (Y)

CUE_START_X = -3.6
CUE_START_Y = 0.0
CUE_CONTACT_X = RACK_APEX_X - CONTACT_D

IMPACT_FRAME = 34
SETTLE_FRAME = 100

RACK_MAT_KEYS = ["rack_red", "rack_yellow", "rack_blue", "rack_green", "rack_orange", "rack_purple"]
RACK_COLOR_NAMES = ["red", "yellow", "blue", "green", "orange", "purple"]

# Per rack ball: outward fan angle from +X (deg) and travel distance. The angle
# SIGN follows the ball's rest side (rows alternate -Y, +Y, see _rack_layout);
# balls on the same side get a wide angular gap and the outer ball travels
# farther, so every path diverges from every other -> no crossings, no overlap.
# _rack_layout order: b0=(apex,y=0), b1=(-Y), b2=(+Y), b3=(-Y outer),
#                     b4=(centre,y=0), b5=(+Y outer).
SCATTER_SPECS = [
    (-6.0, 2.30),    # b0 apex - nearly head-on, drifts slightly -Y
    (-32.0, 1.70),   # b1 row1 -Y (inner)
    (32.0, 1.70),    # b2 row1 +Y (inner)
    (-76.0, 2.10),   # b3 row2 -Y (outer, wide + far so it pulls clear of b1)
    (8.0, 2.90),     # b4 row2 centre - forward, drifts +Y, farthest
    (76.0, 2.10),    # b5 row2 +Y (outer, wide + far so it pulls clear of b2)
]


def _rack_layout():
    positions = []
    for row in range(3):
        rx = RACK_APEX_X + row * ROW_DX
        n = row + 1
        for j in range(n):
            ry = (j - (n - 1) / 2.0) * (2.0 * ROW_DY)
            positions.append((rx, ry))
    return positions


def build_pool_rack_break_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(-1.1, -8.8, 4.0), target=(1.5, 0.1, BALL_Z), lens=38)

    rack_positions = _rack_layout()

    cue = add_sphere(
        "cue_ball",
        BALL_RADIUS,
        (CUE_START_X, CUE_START_Y, BALL_Z),
        MATS["cue"],
        "white",
        role="cue_ball",
    )
    cue["pb_ball_index"] = 0
    cue["pb_count_conserved"] = True
    cue["pb_motion_constraint"] = "rolls_on_flat_surface"

    rack_balls = []
    scatter = []
    for k, (rx, ry) in enumerate(rack_positions):
        ball = add_sphere(
            f"rack_ball_{k}",
            BALL_RADIUS,
            (rx, ry, BALL_Z),
            MATS[RACK_MAT_KEYS[k]],
            RACK_COLOR_NAMES[k],
            role="rack_ball",
        )
        ball["pb_ball_index"] = k + 1
        ball["pb_count_conserved"] = True
        ball["pb_motion_constraint"] = "rolls_on_flat_surface"
        rack_balls.append(ball)

        ang, dist = SCATTER_SPECS[k]
        d = Vector((math.cos(math.radians(ang)), math.sin(math.radians(ang)), 0.0))
        scatter.append((d, dist))

    return {
        "scene": scene,
        "kind": "pool_rack_break",
        "cue": cue,
        "rack_balls": rack_balls,
        "rack_positions": rack_positions,
        "scatter": scatter,
    }


# ============================================================
# Animation
# ============================================================


def _cue_position(frame):
    if frame <= IMPACT_FRAME:
        t = clamp01((frame - FRAME_START) / float(IMPACT_FRAME - FRAME_START))
        x = lerp(CUE_START_X, CUE_CONTACT_X, ease_in_quad(t))
        return Vector((x, CUE_START_Y, BALL_Z))
    t = clamp01((frame - IMPACT_FRAME) / float(SETTLE_FRAME - IMPACT_FRAME))
    s = ease_out_quad(t)
    x = lerp(CUE_CONTACT_X, CUE_CONTACT_X + 0.45, s)
    y = lerp(CUE_START_Y, -0.22, s)
    return Vector((x, y, BALL_Z))


def _rack_position(frame, rest_pos, spec):
    rx, ry = rest_pos
    d, dist = spec
    if frame <= IMPACT_FRAME:
        return Vector((rx, ry, BALL_Z))
    t = clamp01((frame - IMPACT_FRAME) / float(SETTLE_FRAME - IMPACT_FRAME))
    s = ease_out_quad(t)
    return Vector((rx + d.x * dist * s, ry + d.y * dist * s, BALL_Z))


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


def animate_pool_rack_break(objs, frame, prev):
    cue = objs["cue"]
    rack_balls = objs["rack_balls"]
    rack_positions = objs["rack_positions"]
    scatter = objs["scatter"]

    cpos = _cue_position(frame)
    prev_cue = prev.get("cue")
    if prev_cue is not None:
        _roll_rotation(cue, prev_cue, cpos, BALL_RADIUS)
    cue.location = cpos
    cue.keyframe_insert(data_path="location", frame=frame)
    cue.keyframe_insert(data_path="rotation_euler", frame=frame)
    cue["pb_state"] = "cue_rolling" if frame <= IMPACT_FRAME else "cue_slowing"
    cue["pb_is_moving"] = bool(prev_cue is not None and (cpos - prev_cue).length > 1e-5)
    prev["cue"] = cpos

    for k, ball in enumerate(rack_balls):
        pos = _rack_position(frame, rack_positions[k], scatter[k])
        key = f"rack_{k}"
        prev_pos = prev.get(key)
        if prev_pos is not None:
            _roll_rotation(ball, prev_pos, pos, BALL_RADIUS)
        ball.location = pos
        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)
        if frame <= IMPACT_FRAME:
            ball["pb_state"] = "rack_stationary"
            ball["pb_is_moving"] = False
        elif frame < SETTLE_FRAME:
            ball["pb_state"] = "scattering"
            ball["pb_is_moving"] = True
        else:
            ball["pb_state"] = "scattered_at_rest"
            ball["pb_is_moving"] = False
        prev[key] = pos


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    prev = {}
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if kind == "pool_rack_break":
            animate_pool_rack_break(objs, frame, prev)
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

    if kind == "pool_rack_break":
        return build_pool_rack_break_scene()

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
