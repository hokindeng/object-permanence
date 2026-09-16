# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_KNOCK_BALL_OFF_TEE_0181",
  "scene_kind": "knock_ball_off_tee",
  "prompt": "A ball rests on top of a short stand on the table. A second ball rolls across the flat surface and strikes the resting ball. On impact the resting ball is knocked off the stand, launching into a short forward arc, then falls, lands on the floor and rolls to a stop. The rolling ball halts at the stand after the strike. Both balls are conserved; nothing appears or vanishes."
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
    MATS["tee"] = make_mat("mat_tee", (0.46, 0.46, 0.46), roughness=0.62)


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
# Knock-ball-off-tee scene  (TWO-BODY COLLISION)
# ============================================================
#
# A short gray TEE/stand (apparatus) sits on the table with resting ball A on
# top (center = tee_top + radius). Striker ball B rolls in along +X at constant
# speed and strikes ball A low (B rolls on the floor, A sits above it) so the
# 3D center-distance closes to R_A + R_B at contact (a slight press, no clip). On impact
# ball A is knocked OFF the tee: it launches up + forward into a short arc, then
# gravity brings it down; it lands on the floor (z = R_A), bounces once, rolls
# forward and settles. Ball B halts at the tee (never penetrating the tee or
# ball A). Two balls + one tee, clean momentum transfer, no cascade.

R_A = 0.24          # resting ball (on the tee)
R_B = 0.24          # striker ball (rolls on the floor)

TEE_R = 0.07        # tee post radius
TEE_H = 0.30        # tee post height (top surface at z = TEE_H)
TEE_X = 0.0         # tee center X

A_X0 = TEE_X
A_Z0 = TEE_H + R_A          # ball A center at rest = tee_top + radius
B_Z = R_B                   # ball B rolls on the floor

# 3D contact between the two spheres: center distance = R_A + R_B.
_SUM_R = R_A + R_B
_DZ = A_Z0 - B_Z                                   # vertical offset of centers
_HORIZ_OFFSET = math.sqrt(max(0.0, _SUM_R * _SUM_R - _DZ * _DZ))
_B_CONTACT_X = TEE_X - _HORIZ_OFFSET               # exact sphere-surface contact
TEE_CLEARANCE_MARGIN = 0.01
_TEE_CLEARANCE = abs(_B_CONTACT_X - TEE_X) - (R_B + TEE_R)
if _TEE_CLEARANCE < TEE_CLEARANCE_MARGIN:
    raise ValueError(
        "unsafe tee geometry: striker intersects tee before ball contact "
        f"(clearance={_TEE_CLEARANCE:.4f})"
    )

CUE_START_X = -3.8
CONTACT_FRAME = 36          # ball B reaches ball A
APPROACH_START_FRAME = 8    # brief hold, then a normal-speed approach

# Ball A projectile (per-frame integration units).
_A_VX0 = 0.068              # forward launch speed (+X)
_A_VZ0 = 0.065              # upward launch speed (brisk but controlled arc)
_A_G = 0.014                # gravity per frame^2
_A_E = 0.42                 # restitution on landing
_A_FRIC = 0.055             # horizontal friction once grounded

_A_TRAJ = None              # cached {frame: (x, z)}
_A_APEX_Z = A_Z0


def _compute_ball_a_traj():
    """Integrate ball A after the strike: up+forward arc, land at z=R_A, one
    small bounce, roll and settle. Returns {frame:(x,z)} and records apex z."""
    global _A_APEX_Z
    traj = {}
    x = A_X0
    z = A_Z0
    vx = _A_VX0
    vz = _A_VZ0
    apex = A_Z0
    for f in range(CONTACT_FRAME, FRAME_END + 1):
        traj[f] = (x, z)
        if z > apex:
            apex = z
        # integrate one frame
        vz -= _A_G
        z += vz
        x += vx
        if z <= R_A:
            z = R_A
            if vz < 0.0:
                if abs(vz) > 0.030:
                    vz = -vz * _A_E          # bounce
                else:
                    vz = 0.0                 # settle vertically
            # grounded: horizontal friction
            vx *= (1.0 - _A_FRIC)
            if abs(vx) < 0.0015:
                vx = 0.0
    _A_APEX_Z = apex
    return traj


def _ball_a_position(frame):
    global _A_TRAJ
    if frame < CONTACT_FRAME:
        return Vector((A_X0, 0.0, A_Z0))          # resting on the tee
    if _A_TRAJ is None:
        _A_TRAJ = _compute_ball_a_traj()
    x, z = _A_TRAJ.get(frame, _A_TRAJ[FRAME_END])
    return Vector((x, 0.0, z))


def _ball_b_position(frame):
    """Constant speed in, parked at the contact point (never past the tee)."""
    if frame <= CONTACT_FRAME:
        t = clamp01((frame - APPROACH_START_FRAME) / float(CONTACT_FRAME - APPROACH_START_FRAME))
        x = lerp(CUE_START_X, _B_CONTACT_X, t)     # linear -> constant speed
        return Vector((x, 0.0, B_Z))
    return Vector((_B_CONTACT_X, 0.0, B_Z))


def build_knock_ball_off_tee_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(-1.8, -8.6, 3.0), target=(0.5, 0.0, 0.5), lens=40)

    tee = add_cylinder(
        "tee_post",
        TEE_R,
        TEE_H,
        (TEE_X, 0.0, TEE_H / 2.0),
        MATS["tee"],
        "gray",
        role="tee_post",
        is_dynamic=False,
    )
    tee["pb_count_conserved"] = True

    ball_b = add_sphere(
        "striker_ball",
        R_B,
        (CUE_START_X, 0.0, B_Z),
        MATS["ball_b"],
        "blue",
        role="striker_ball",
    )
    ball_b["pb_count_conserved"] = True
    ball_b["pb_motion_constraint"] = "rolls_on_flat_floor"

    ball_a = add_sphere(
        "resting_ball",
        R_A,
        (A_X0, 0.0, A_Z0),
        MATS["ball_a"],
        "yellow",
        role="resting_ball",
    )
    ball_a["pb_count_conserved"] = True
    ball_a["pb_motion_constraint"] = "knocked_off_tee_projectile"

    return {
        "scene": scene,
        "kind": "knock_ball_off_tee",
        "tee": tee,
        "ball_a": ball_a,
        "ball_b": ball_b,
    }


# ============================================================
# Animation
# ============================================================

def animate_knock_ball_off_tee(objs, frame):
    ball_a = objs["ball_a"]
    ball_b = objs["ball_b"]

    # Striker ball B
    bpos = _ball_b_position(frame)
    ball_b.location = bpos
    ball_b.rotation_euler = (0.0, -(bpos.x - CUE_START_X) / R_B, 0.0)
    ball_b.keyframe_insert(data_path="location", frame=frame)
    ball_b.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball_b["pb_state"] = "rolling_in" if frame < CONTACT_FRAME else "stopped_at_tee"
    ball_b["pb_is_moving"] = bool(frame < CONTACT_FRAME)

    # Resting ball A
    apos = _ball_a_position(frame)
    ball_a.location = apos
    # roll about Y proportional to forward travel (visual)
    ball_a.rotation_euler = (0.0, -(apos.x - A_X0) / R_A, 0.0)
    ball_a.keyframe_insert(data_path="location", frame=frame)
    ball_a.keyframe_insert(data_path="rotation_euler", frame=frame)
    if frame < CONTACT_FRAME:
        ball_a["pb_state"] = "resting_on_tee"
        ball_a["pb_is_moving"] = False
    elif apos.z > R_A + 1e-3:
        ball_a["pb_state"] = "airborne"
        ball_a["pb_is_moving"] = True
    else:
        ball_a["pb_state"] = "rolling_on_floor"
        ball_a["pb_is_moving"] = True


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "knock_ball_off_tee":
            animate_knock_ball_off_tee(objs, frame)
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

    if kind == "knock_ball_off_tee":
        return build_knock_ball_off_tee_scene()

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
