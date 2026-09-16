# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_LEVER_LAUNCH_TRANSFER_0182",
  "scene_kind": "lever_launch_transfer",
  "prompt": "A ball drops onto the raised end of a see-saw lever resting on a fulcrum. The impact drives that end down and swings the other end up, launching a second ball that was resting on it into a short arc through the air. The launched ball rises, then falls back and settles on the floor, while the dropped ball moves down with the lever, rolls off its lowered end, and settles on the floor. Energy transfers through the lever; nothing appears or vanishes."
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
    MATS["frame"] = make_mat("mat_metal_frame", (0.30, 0.31, 0.34), roughness=0.40, metallic=0.85)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)
    MATS["ball_a"] = make_mat("mat_ball_a", (0.86, 0.16, 0.12), roughness=0.26)   # dropped ball (red)
    MATS["ball_b"] = make_mat("mat_ball_b", (0.14, 0.34, 0.80), roughness=0.26)   # launched ball (blue)


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube(
        "large_floor_base",
        (0.0, 0.6, -0.05),
        (13.0, 9.0, 0.10),
        material=MATS["floor"],
        role="ground",
        color_name="warm_beige",
    )

    add_cube(
        "rear_backdrop_panel",
        (0.0, 2.42, 1.60),
        (10.0, 0.08, 3.20),
        material=MATS["backdrop"],
        role="background",
        color_name="off_white",
    )

    bpy.ops.object.light_add(type="AREA", location=(-3.8, -4.4, 5.5))
    key = bpy.context.object
    key.name = "large_softbox_light"
    key.data.energy = 950
    key.data.size = 6.0

    bpy.ops.object.light_add(type="POINT", location=(3.7, -2.8, 3.2))
    fill = bpy.context.object
    fill.data.energy = 145
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
# Lever-launch-transfer scene
# ============================================================
#
# A see-saw lever (a plank balanced on a fulcrum, both apparatus/gray) starts
# tilted so its LEFT end is raised and its RIGHT end is low. A ball (red) drops
# from above onto the raised LEFT end. The impact drives the LEFT end DOWN and
# swings the RIGHT end UP, launching a second ball (blue) that rested on the
# right end into a short projectile arc. The launched ball rises, arcs over,
# and falls back to the floor, rolling to rest (center z = radius). The dropped
# ball rides the lowered left end down and rolls off onto the floor. Energy
# transfers through the lever; count is conserved.

BALL_RADIUS = 0.26

FULCRUM_Z = 1.0                 # pivot height (top of fulcrum)
PLANK_HALF = 1.5                # half-length of the plank
PLANK_THICK = 0.12
PLANK_WIDTH = 0.5
THETA0 = math.radians(15.0)     # initial tilt: LEFT end up (+theta)
THETA1 = math.radians(15.0)     # final tilt: LEFT end down (-theta)

IMPACT_FRAME = 32               # dropped ball reaches the raised left end
TIP_DUR = 10                    # frames for the lever to swing (theta0 -> -theta1)
LAUNCH_FRAME = 38               # launched ball leaves the rising right end
SETTLE_A_FRAME = 74             # dropped ball settled on the floor

# ball-center offset above the plank end center (half-thickness + ball radius)
_BALL_ON_PLANK = PLANK_THICK / 2.0 + BALL_RADIUS

BALL_A_DROP_Z = 2.60            # start height of the dropped ball

# projectile parameters for the launched ball (per-frame units)
_VZ0 = 0.16
_VX0 = 0.030
_G = 0.010
_ROLL_TAU = 8.0
_BALL_A_EXIT_SPEED = 0.045
_BALL_A_G = 0.006
_BALL_A_ROLL_TAU = 10.0


def _plank_end(theta, xl):
    """World position of a plank point at local x = xl (0 = pivot) for tilt theta.
    Rotation is about the world Y axis at the pivot (0, 0, FULCRUM_Z)."""
    return Vector((xl * math.cos(theta), 0.0, FULCRUM_Z - xl * math.sin(theta)))


def _ball_on_plank(theta, xl):
    """Ball center tangent to the tilted plank at local coordinate ``xl``."""
    contact = _plank_end(theta, xl)
    normal = Vector((math.sin(theta), 0.0, math.cos(theta)))
    return contact + normal * _BALL_ON_PLANK


def build_lever_launch_transfer_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(0.0, -9.0, 2.15), target=(0.15, 0.0, 1.30), lens=38)

    # Fulcrum: a static support block under the pivot (apparatus / gray).
    add_cube(
        "lever_fulcrum",
        (0.0, 0.0, FULCRUM_Z / 2.0),
        (0.5, 0.7, FULCRUM_Z),
        material=MATS["frame"],
        role="fulcrum_support",
        color_name="dark_gray",
    )

    # Plank: origin at its center = the pivot, so rotating about Y tilts it as a
    # see-saw. Apparatus role ("beam" keyword) keeps it gray at render time.
    plank = add_cube(
        "lever_plank",
        (0.0, 0.0, FULCRUM_Z),
        (2.0 * PLANK_HALF, PLANK_WIDTH, PLANK_THICK),
        material=MATS["gray"],
        role="lever_plank_beam",
        color_name="gray",
        is_dynamic=False,
    )
    plank["pb_motion_constraint"] = "see_saw_rotation_about_fulcrum"

    # Dropped ball (red), starting above the raised LEFT end.
    left0 = _ball_on_plank(THETA0, -PLANK_HALF)
    ball_a = add_sphere(
        "dropping_ball",
        BALL_RADIUS,
        (left0.x, 0.0, BALL_A_DROP_Z),
        MATS["ball_a"],
        "red",
        role="dropping_ball",
    )
    ball_a["pb_count_conserved"] = True
    ball_a["pb_motion_constraint"] = "falls_then_rides_lever_down_to_floor"

    # Launched ball (blue), resting on the RIGHT end.
    right0 = _ball_on_plank(THETA0, PLANK_HALF)
    ball_b = add_sphere(
        "launched_ball",
        BALL_RADIUS,
        right0,
        MATS["ball_b"],
        "blue",
        role="launched_ball",
    )
    ball_b["pb_count_conserved"] = True
    ball_b["pb_motion_constraint"] = "launched_into_projectile_arc"

    return {
        "scene": scene,
        "kind": "lever_launch_transfer",
        "plank": plank,
        "ball_a": ball_a,
        "ball_b": ball_b,
        "ball_a_x": left0.x,
    }


# ============================================================
# Animation
# ============================================================

def _lever_theta(frame):
    if frame <= IMPACT_FRAME:
        return THETA0
    t = clamp01((frame - IMPACT_FRAME) / float(TIP_DUR))
    return lerp(THETA0, -THETA1, smooth01(t))


def _ball_a_pos(frame):
    """Dropped ball: falls onto the raised left end, rides it down, rolls to floor."""
    left0 = _ball_on_plank(THETA0, -PLANK_HALF)
    contact_z = left0.z

    if frame <= IMPACT_FRAME:
        t = clamp01((frame - FRAME_START) / float(IMPACT_FRAME - FRAME_START))
        z = lerp(BALL_A_DROP_Z, contact_z, ease_in_quad(t))
        return Vector((left0.x, 0.0, z))

    if frame <= IMPACT_FRAME + TIP_DUR:
        theta = _lever_theta(frame)
        return _ball_on_plank(theta, -PLANK_HALF)

    # Leave the lowered end along the plank tangent, then follow a short ballistic
    # arc.  Interpolating directly toward the floor cuts the sphere through the
    # finite plank corner for several frames.
    left_end = _ball_on_plank(-THETA1, -PLANK_HALF)
    theta = -THETA1
    vx = -math.cos(theta) * _BALL_A_EXIT_SPEED
    vz = math.sin(theta) * _BALL_A_EXIT_SPEED
    dt_land = (vz + math.sqrt(vz * vz + 2.0 * _BALL_A_G * (left_end.z - BALL_RADIUS))) / _BALL_A_G
    dt = frame - (IMPACT_FRAME + TIP_DUR)

    if dt <= dt_land:
        x = left_end.x + vx * dt
        z = left_end.z + vz * dt - 0.5 * _BALL_A_G * dt * dt
        return Vector((x, 0.0, max(z, BALL_RADIUS)))

    x_land = left_end.x + vx * dt_land
    x = x_land + vx * _BALL_A_ROLL_TAU * (1.0 - math.exp(-(dt - dt_land) / _BALL_A_ROLL_TAU))
    return Vector((x, 0.0, BALL_RADIUS))


def _ball_b_launch_origin():
    """Position of the launched ball at LAUNCH_FRAME (still riding the right end)."""
    theta = _lever_theta(LAUNCH_FRAME)
    return _ball_on_plank(theta, PLANK_HALF)


def _ball_b_pos(frame):
    """Launched ball: rests, rides the rising right end, then flies a ballistic
    arc, lands on the floor and rolls to rest."""
    rest = _ball_on_plank(THETA0, PLANK_HALF)

    if frame <= IMPACT_FRAME:
        return rest

    if frame <= LAUNCH_FRAME:
        theta = _lever_theta(frame)
        return _ball_on_plank(theta, PLANK_HALF)

    # ballistic flight from the launch origin
    p0 = _ball_b_launch_origin()
    dt_land = (_VZ0 + math.sqrt(_VZ0 * _VZ0 + 2.0 * _G * (p0.z - BALL_RADIUS))) / _G
    x_land = p0.x + _VX0 * dt_land

    dt = frame - LAUNCH_FRAME
    if dt <= dt_land:
        x = p0.x + _VX0 * dt
        z = p0.z + _VZ0 * dt - 0.5 * _G * dt * dt
        z = max(z, BALL_RADIUS)
        return Vector((x, 0.0, z))

    # landed: roll forward, decelerating to rest
    x = x_land + _VX0 * _ROLL_TAU * (1.0 - math.exp(-(dt - dt_land) / _ROLL_TAU))
    return Vector((x, 0.0, BALL_RADIUS))


def animate_lever_launch_transfer(objs, frame):
    plank = objs["plank"]
    ball_a = objs["ball_a"]
    ball_b = objs["ball_b"]

    theta = _lever_theta(frame)
    plank.location = (0.0, 0.0, FULCRUM_Z)
    plank.rotation_euler = (0.0, theta, 0.0)
    plank.keyframe_insert(data_path="location", frame=frame)
    plank.keyframe_insert(data_path="rotation_euler", frame=frame)
    plank["pb_state"] = "tilted_left_up" if frame <= IMPACT_FRAME else "tipping_left_down"

    pa = _ball_a_pos(frame)
    ball_a.location = pa
    ball_a.rotation_euler = (0.0, -0.12 * frame, 0.0)
    ball_a.keyframe_insert(data_path="location", frame=frame)
    ball_a.keyframe_insert(data_path="rotation_euler", frame=frame)
    if frame <= IMPACT_FRAME:
        ball_a["pb_state"] = "falling_onto_lever"
    elif frame <= IMPACT_FRAME + TIP_DUR:
        ball_a["pb_state"] = "riding_lever_down"
    else:
        ball_a["pb_state"] = "rolling_to_rest_on_floor"

    pb = _ball_b_pos(frame)
    ball_b.location = pb
    ball_b.rotation_euler = (0.0, 0.14 * frame, 0.0)
    ball_b.keyframe_insert(data_path="location", frame=frame)
    ball_b.keyframe_insert(data_path="rotation_euler", frame=frame)
    if frame <= IMPACT_FRAME:
        ball_b["pb_state"] = "resting_on_lever_end"
    elif frame <= LAUNCH_FRAME:
        ball_b["pb_state"] = "being_flung_up"
    else:
        ball_b["pb_state"] = "airborne_then_landing"


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "lever_launch_transfer":
            animate_lever_launch_transfer(objs, frame)
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

    if kind == "lever_launch_transfer":
        return build_lever_launch_transfer_scene()

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
