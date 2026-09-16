# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_LIGHT_BALL_REBOUNDS_OFF_HEAVY_0187",
  "scene_kind": "light_ball_rebounds_off_heavy",
  "prompt": "A small light ball rolls into a large heavy stationary ball. On impact the light ball rebounds backward, reversing direction and rolling back the way it came before settling, while the heavy ball only creeps forward slightly. Both balls remain; neither passes through the other."
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
    # Two distinct ball colours so the heavy and light balls are clearly told apart.
    MATS["ball_heavy"] = make_mat("mat_ball_heavy", (0.80, 0.24, 0.20), roughness=0.34, metallic=0.10)
    MATS["ball_light"] = make_mat("mat_ball_light", (0.20, 0.42, 0.82), roughness=0.34, metallic=0.10)


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube(
        "large_floor_base",
        (0.0, 0.0, -0.05),
        (11.0, 9.8, 0.10),
        material=MATS["floor"],
        role="ground",
        color_name="warm_beige",
    )

    add_cube(
        "rear_backdrop_panel",
        (0.0, 3.6, 1.60),
        (11.0, 0.08, 3.20),
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
# Light-ball-rebounds-off-heavy scene  (MASS-ASYMMETRIC HEAD-ON)
# ============================================================
#
# Layout (X = right, Y = into scene, Z = up):
#   A SMALL LIGHT ball rolls in +X along the floor into a BIG HEAVY stationary
#   ball. Both roll on the floor (centre z = own radius); at contact the 3-D
#   centre distance equals R_HEAVY + R_LIGHT (gap >= 0, NO clip). For a light
#   ball hitting a much heavier stationary ball the light ball REBOUNDS:
#       v_light'  = (m - M)/(m + M) * v_in  ->  negative (reverses)
#       v_heavy'  = 2m/(m + M) * v_in       ->  small positive (creeps forward)
#   We use an effective restitution ~0.35 so the light ball clearly rolls BACK
#   the way it came, decelerating to rest, while the heavy ball barely moves.

R_HEAVY = 0.62                          # big heavy ball radius
R_LIGHT = 0.24                          # small light ball radius
FLOOR_Z = 0.0
HEAVY_Z = FLOOR_Z + R_HEAVY
LIGHT_Z = FLOOR_Z + R_LIGHT
CONTACT_DIST = R_HEAVY + R_LIGHT        # 3-D centre distance when touching

HEAVY_X = 1.5                           # heavy ball rest centre X
HEAVY_Y = 0.0
LINE_Y = 0.0

# The two centres sit at different heights (balls of different size on the
# floor), so the horizontal offset at contact solves
#   dx = sqrt(CONTACT_DIST^2 - dz^2)  with  dz = HEAVY_Z - LIGHT_Z.
_DZ = HEAVY_Z - LIGHT_Z
_HORIZ_OFFSET = math.sqrt(max(0.0, CONTACT_DIST * CONTACT_DIST - _DZ * _DZ))
LIGHT_CONTACT_X = HEAVY_X - _HORIZ_OFFSET     # light ball centre X at contact

CONTACT_FRAME = 40
INCOMING_SPEED = 0.100                   # light ball approach speed (units/frame)

# Effective restitution for the rebound and post-impact travel budgets.
RESTITUTION = 0.35                       # light rebounds SLOWER than it came (heavy target)
HEAVY_CREEP = 0.12                       # heavy ball forward creep (barely moves)
LIGHT_SETTLE_FRAME = 92                  # light ball at rest after rolling back
HEAVY_SETTLE_FRAME = 66                  # heavy ball at rest (short creep)
# Rebound speed = RESTITUTION * incoming. With ease_out_quad the peak (initial)
# rebound speed == 2*REBOUND_DIST/window, so deriving REBOUND_DIST from that
# speed guarantees the light ball leaves at RESTITUTION*v_in and then only
# DECELERATES (rolling friction) to rest -- a modest recoil that never speeds up.
REBOUND_DIST = RESTITUTION * INCOMING_SPEED * (LIGHT_SETTLE_FRAME - CONTACT_FRAME) / 2.0
ROLL_AXIS_SCALE = 1.0


def _light_position(frame, objs):
    """Light ball: constant-speed +X approach to contact, then REBOUND back
    along -X (ease-out decel) to rest."""
    start = objs["light_start"]
    contact = objs["light_contact"]

    if frame <= CONTACT_FRAME:
        t = clamp01((frame - FRAME_START) / float(CONTACT_FRAME - FRAME_START))
        return start + (contact - start) * t      # linear -> constant speed

    # Rebound: reverse direction, roll back -X, decelerating to rest.
    t = clamp01((frame - CONTACT_FRAME) / float(LIGHT_SETTLE_FRAME - CONTACT_FRAME))
    dist = REBOUND_DIST * ease_out_quad(t)
    pos = contact + Vector((-1.0, 0.0, 0.0)) * dist
    pos.z = LIGHT_Z
    return pos


def _heavy_position(frame, objs):
    """Heavy ball: stationary until contact, then a tiny forward creep and stop."""
    start = objs["heavy_start"]
    if frame <= CONTACT_FRAME:
        return Vector(start)
    t = clamp01((frame - CONTACT_FRAME) / float(HEAVY_SETTLE_FRAME - CONTACT_FRAME))
    pos = start + Vector((1.0, 0.0, 0.0)) * (HEAVY_CREEP * ease_out_quad(t))
    pos.z = HEAVY_Z
    return pos


def build_light_ball_rebounds_off_heavy_scene():
    scene = build_base_scene()
    light_contact = Vector((LIGHT_CONTACT_X, LINE_Y, LIGHT_Z))
    travel = INCOMING_SPEED * (CONTACT_FRAME - FRAME_START)
    light_start = Vector((LIGHT_CONTACT_X - travel, LINE_Y, LIGHT_Z))
    heavy_start = Vector((HEAVY_X, HEAVY_Y, HEAVY_Z))
    light_end_x = LIGHT_CONTACT_X - REBOUND_DIST
    heavy_end_x = HEAVY_X + HEAVY_CREEP
    view_min_x = min(light_start.x, light_end_x)
    view_max_x = max(heavy_end_x, HEAVY_X)
    view_center_x = 0.5 * (view_min_x + view_max_x)
    setup_camera(
        scene,
        location=(view_center_x, -9.8, 3.0),
        target=(view_center_x, 0.0, 0.5),
        lens=40,
    )

    light = add_sphere(
        "light_ball",
        R_LIGHT,
        light_start,
        MATS["ball_light"],
        "blue",
        role="projectile",
    )
    light["pb_ball_role"] = "light_incoming"
    light["pb_motion_constraint"] = "rolls_on_surface"
    light["pb_count_conserved"] = True
    light["pb_mass"] = 1.0

    heavy = add_sphere(
        "heavy_ball",
        R_HEAVY,
        heavy_start,
        MATS["ball_heavy"],
        "red",
        role="target",
    )
    heavy["pb_ball_role"] = "heavy_stationary"
    heavy["pb_motion_constraint"] = "rolls_on_surface"
    heavy["pb_count_conserved"] = True
    heavy["pb_mass"] = 12.0

    return {
        "scene": scene,
        "kind": "light_ball_rebounds_off_heavy",
        "light": light,
        "heavy": heavy,
        "light_start": light_start,
        "light_contact": light_contact,
        "heavy_start": heavy_start,
    }


# ============================================================
# Animation
# ============================================================

def _roll_rotation(obj, radius, prev_pos, cur_pos):
    """Roll about the horizontal axis perpendicular to travel by dist/radius."""
    delta = cur_pos - prev_pos
    delta.z = 0.0
    dist = delta.length
    if dist < 1e-7:
        return
    travel_d = delta.normalized()
    up = Vector((0.0, 0.0, 1.0))
    axis = travel_d.cross(up)
    if axis.length < 1e-7:
        return
    axis.normalize()
    angle = (dist / radius) * ROLL_AXIS_SCALE
    from mathutils import Quaternion
    q = Quaternion(axis, angle)
    cur = obj.rotation_euler.to_quaternion()
    new = q @ cur
    obj.rotation_euler = new.to_euler()


def animate_light_ball_rebounds_off_heavy(objs, frame, prev):
    light = objs["light"]
    heavy = objs["heavy"]

    light_pos = _light_position(frame, objs)
    heavy_pos = _heavy_position(frame, objs)

    # Safety: never let the two centres come closer than CONTACT_DIST in 3-D
    # (no interpenetration). Push the (moving) light ball back along the
    # separation direction if it would clip the heavy ball.
    sep = light_pos - heavy_pos
    if sep.length < CONTACT_DIST - 1e-4 and sep.length > 1e-6:
        push = CONTACT_DIST - sep.length
        light_pos = light_pos + sep.normalized() * push
        light_pos.z = LIGHT_Z

    prev_light = prev.get("light")
    prev_heavy = prev.get("heavy")
    if prev_light is not None:
        _roll_rotation(light, R_LIGHT, prev_light, light_pos)
    if prev_heavy is not None:
        _roll_rotation(heavy, R_HEAVY, prev_heavy, heavy_pos)

    light.location = light_pos
    light.keyframe_insert(data_path="location", frame=frame)
    light.keyframe_insert(data_path="rotation_euler", frame=frame)

    heavy.location = heavy_pos
    heavy.keyframe_insert(data_path="location", frame=frame)
    heavy.keyframe_insert(data_path="rotation_euler", frame=frame)

    light["pb_is_moving"] = bool((light_pos - (prev_light if prev_light is not None else light_pos)).length > 1e-4)
    heavy["pb_is_moving"] = bool(prev_heavy is not None and (heavy_pos - prev_heavy).length > 1e-4)
    light["pb_state"] = "rolling_in" if frame <= CONTACT_FRAME else "rebounding_back"
    heavy["pb_state"] = "stationary" if frame <= CONTACT_FRAME else "creeping_forward"

    prev["light"] = light_pos
    prev["heavy"] = heavy_pos


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    prev = {}
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "light_ball_rebounds_off_heavy":
            animate_light_ball_rebounds_off_heavy(objs, frame, prev)
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

    if kind == "light_ball_rebounds_off_heavy":
        return build_light_ball_rebounds_off_heavy_scene()

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
