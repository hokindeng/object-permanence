# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_KNOCK_BALL_OFF_LEDGE_0189",
  "scene_kind": "knock_ball_off_ledge",
  "prompt": "A ball rolls along the top of a raised platform toward a second ball resting at the platform's front edge. It strikes the resting ball, which is knocked off the edge, falls to the floor below, bounces once and rolls to a stop. The rolling ball halts at the edge after the strike. Both balls are conserved; nothing appears or vanishes."
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


def add_cylinder(name, radius, height, location, material, color_name, role="tee_post", is_dynamic=False, solid=True):
    bpy.ops.mesh.primitive_cylinder_add(vertices=40, radius=radius, depth=height, location=location)
    obj = bpy.context.object
    obj.name = name
    if material is not None:
        obj.data.materials.append(material)
    tag(
        obj,
        name,
        role,
        "dynamic_object" if is_dynamic else ("static_solid" if solid else "non_solid_marker"),
        "cylinder",
        color_name,
        is_dynamic,
        solid=solid,
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
    MATS["ball_a"] = make_mat("mat_ball_a", (0.90, 0.68, 0.10), roughness=0.24)   # resting ball
    MATS["ball_b"] = make_mat("mat_ball_b", (0.15, 0.55, 0.85), roughness=0.24)   # striker ball
    MATS["platform"] = make_mat("mat_platform", (0.46, 0.46, 0.46), roughness=0.62)


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
# Knock-ball-off-ledge scene  (TWO-BODY COLLISION off a raised platform)
# ============================================================
#
# A gray RAISED PLATFORM (apparatus) stands on the table. Resting ball A sits
# on the platform top, right at the platform's FRONT (+X) EDGE. Striker ball B
# rolls along the platform top in +X at constant speed and strikes A. Both
# balls roll at the same height (z = PLAT_TOP + radius) so the 3D center
# distance reaches 2R exactly at contact (gap >= 0, NO clip). On impact A is
# knocked OFF the front edge: it rolls forward off the platform, then free-falls
# to the floor BELOW (z = R_A), bounces once (~0.5 restitution), rolls forward
# and settles. Striker B halts at the edge (never past the contact point, never
# penetrating A). Two balls + one platform, clean momentum transfer, no cascade.

_DIVERSITY = globals().get("DIVERSITY", {})

R_A = float(_DIVERSITY.get("ball_radius", 0.24))
R_B = R_A

PLAT_TOP = float(_DIVERSITY.get("platform_height", 1.00))
EDGE_X = float(_DIVERSITY.get("edge_x", 0.60))
PLAT_LEN_X = 3.40   # platform length along X
PLAT_W_Y = 1.80     # platform width along Y
PLAT_CX = EDGE_X - PLAT_LEN_X / 2.0   # platform center X
PLAT_CZ = PLAT_TOP / 2.0              # platform center Z (floor top at z=0)

ROLL_Z = PLAT_TOP + R_A     # ball center height while on the platform top

A_X0 = EDGE_X - R_A         # ball A rest center: sits fully supported at the edge
A_Z0 = ROLL_Z
B_Z = ROLL_Z                # striker rolls at the same height on the platform

# Contact between the two equal spheres at the same height: center distance 2R.
_SUM_R = R_A + R_B
_B_CONTACT_X = A_X0 - _SUM_R          # ball B CENTER at contact (surfaces just touch, gap = 0)

CUE_START_X = float(_DIVERSITY.get("cue_start_x", -2.40))
CONTACT_FRAME = 36          # ball B reaches ball A
APPROACH_START_FRAME = 8    # brief hold, then a normal-speed approach

# Ball A projectile (per-frame integration units).
_A_VX0 = float(_DIVERSITY.get("launch_speed", 0.060))
_A_G = float(_DIVERSITY.get("gravity", 0.011))
_A_E = float(_DIVERSITY.get("restitution", 0.50))
_A_FRIC = float(_DIVERSITY.get("rolling_friction", 0.040))

_A_TRAJ = None              # cached {frame: (x, z)}
_A_APEX_Z = A_Z0


def _compute_ball_a_traj():
    """Integrate ball A after the strike: rolls forward on the platform top
    until its center passes the front edge, then free-falls to the floor
    (z=R_A), bounces once, rolls and settles. Returns {frame:(x,z)}."""
    global _A_APEX_Z
    traj = {}
    x = A_X0
    z = A_Z0
    vx = _A_VX0
    vz = 0.0
    on_platform = True
    landed_apex = R_A
    for f in range(CONTACT_FRAME, FRAME_END + 1):
        traj[f] = (x, z)
        if on_platform:
            x += vx
            if x >= EDGE_X:          # center passes the front edge -> loses support
                on_platform = False
        else:
            vz -= _A_G
            z += vz
            x += vx
            if z <= R_A:
                z = R_A
                if vz < 0.0:
                    if abs(vz) > 0.030:
                        vz = -vz * _A_E      # bounce
                    else:
                        vz = 0.0             # settle vertically
                vx *= (1.0 - _A_FRIC)        # grounded friction
                if abs(vx) < 0.0015:
                    vx = 0.0
            else:
                if z > landed_apex:
                    landed_apex = z
    _A_APEX_Z = landed_apex
    return traj


def _ball_a_position(frame):
    global _A_TRAJ
    if frame < CONTACT_FRAME:
        return Vector((A_X0, 0.0, A_Z0))          # resting at the edge
    if _A_TRAJ is None:
        _A_TRAJ = _compute_ball_a_traj()
    x, z = _A_TRAJ.get(frame, _A_TRAJ[FRAME_END])
    return Vector((x, 0.0, z))


def _ball_b_position(frame):
    """Constant speed in along the platform top, parked at the contact point
    (never past the front edge, never past ball A)."""
    if frame <= CONTACT_FRAME:
        t = clamp01((frame - APPROACH_START_FRAME) / float(CONTACT_FRAME - APPROACH_START_FRAME))
        x = lerp(CUE_START_X, _B_CONTACT_X, t)     # linear -> constant speed
        return Vector((x, 0.0, B_Z))
    return Vector((_B_CONTACT_X, 0.0, B_Z))


def build_knock_ball_off_ledge_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(-1.6, -9.4, 3.6), target=(0.5, 0.0, 0.7), lens=38)

    platform = add_cube(
        "raised_platform",
        (PLAT_CX, 0.0, PLAT_CZ),
        (PLAT_LEN_X, PLAT_W_Y, PLAT_TOP),
        material=MATS["platform"],
        role="raised_platform",
        color_name="gray",
        is_dynamic=False,
    )
    platform["pb_count_conserved"] = True

    ball_b = add_sphere(
        "striker_ball",
        R_B,
        (CUE_START_X, 0.0, B_Z),
        MATS["ball_b"],
        "blue",
        role="striker_ball",
    )
    ball_b["pb_count_conserved"] = True
    ball_b["pb_motion_constraint"] = "rolls_on_platform_top"

    ball_a = add_sphere(
        "resting_ball",
        R_A,
        (A_X0, 0.0, A_Z0),
        MATS["ball_a"],
        "yellow",
        role="resting_ball",
    )
    ball_a["pb_count_conserved"] = True
    ball_a["pb_motion_constraint"] = "knocked_off_ledge_projectile"

    return {
        "scene": scene,
        "kind": "knock_ball_off_ledge",
        "platform": platform,
        "ball_a": ball_a,
        "ball_b": ball_b,
    }


# ============================================================
# Animation
# ============================================================

def animate_knock_ball_off_ledge(objs, frame):
    ball_a = objs["ball_a"]
    ball_b = objs["ball_b"]

    # Striker ball B
    bpos = _ball_b_position(frame)
    ball_b.location = bpos
    ball_b.rotation_euler = (0.0, -(bpos.x - CUE_START_X) / R_B, 0.0)
    ball_b.keyframe_insert(data_path="location", frame=frame)
    ball_b.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball_b["pb_state"] = "rolling_in" if frame < CONTACT_FRAME else "stopped_at_edge"
    ball_b["pb_is_moving"] = bool(frame < CONTACT_FRAME)

    # Resting ball A
    apos = _ball_a_position(frame)
    ball_a.location = apos
    # roll about Y proportional to forward travel (visual)
    ball_a.rotation_euler = (0.0, -(apos.x - A_X0) / R_A, 0.0)
    ball_a.keyframe_insert(data_path="location", frame=frame)
    ball_a.keyframe_insert(data_path="rotation_euler", frame=frame)
    if frame < CONTACT_FRAME:
        ball_a["pb_state"] = "resting_at_edge"
        ball_a["pb_is_moving"] = False
    elif apos.z > R_A + 1e-3:
        ball_a["pb_state"] = "falling_off_ledge"
        ball_a["pb_is_moving"] = True
    else:
        ball_a["pb_state"] = "rolling_on_floor"
        ball_a["pb_is_moving"] = True


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "knock_ball_off_ledge":
            animate_knock_ball_off_ledge(objs, frame)
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

    if kind == "knock_ball_off_ledge":
        return build_knock_ball_off_ledge_scene()

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
