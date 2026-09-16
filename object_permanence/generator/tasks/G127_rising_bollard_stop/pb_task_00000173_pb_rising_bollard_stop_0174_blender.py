# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_RISING_BOLLARD_STOP_0174",
  "scene_kind": "rising_bollard_stop",
  "prompt": "A ball rolls along the table toward a spot at constant speed. Before it arrives, a solid cylindrical bollard rises up out of the floor into the ball's path. The ball reaches the bollard and stops against it, blocked, decelerating to rest on contact without passing through or overlapping the post."
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
OPTIONAL_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_bollard_up_frame_02.png")
OPTIONAL_FRAME_02B_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_ball_blocked_frame_02B.png")


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


def lerp(a, b, t):
    return a + (b - a) * t


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def make_mat(name, color, roughness=0.55):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (color[0], color[1], color[2], 1.0)

    try:
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            if "Base Color" in bsdf.inputs:
                bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = roughness
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


def add_cube(name, location, dimensions, material, role, color_name, is_dynamic=False, solid=True):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
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


def add_cylinder(name, location, radius, depth, material, role, color_name, is_dynamic=False, solid=True, vertices=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
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
    )
    return obj


def add_sphere(name, radius, location, material, color_name, role="moving_ball"):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object", "sphere", color_name, True, solid=True, pb_radius=radius)
    return obj


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor_warm", (0.82, 0.80, 0.75), roughness=0.82)
    MATS["track"] = make_mat("mat_track_gray", (0.46, 0.46, 0.46), roughness=0.62)
    MATS["bollard"] = make_mat("mat_bollard_gray", (0.60, 0.61, 0.64), roughness=0.55)
    MATS["slot"] = make_mat("mat_dark_slot", (0.10, 0.10, 0.12), roughness=0.78)
    MATS["orange"] = make_mat("mat_orange_ball", (1.0, 0.38, 0.06), roughness=0.30)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)


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


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0, 0, -0.05), (10.0, 5.0, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0, 2.48, 1.62), (10.2, 0.08, 3.24), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.6, -4.3, 5.5))
    key = bpy.context.object
    key.name = "large_softbox_light"
    key.data.energy = 960
    key.data.size = 6.2

    bpy.ops.object.light_add(type="POINT", location=(3.6, -3.0, 3.0))
    fill = bpy.context.object
    fill.name = "fill_light"
    fill.data.energy = 145

    return scene


def setup_camera(scene):
    # Left-front side view. The ball rolls left -> right along +X; this camera sees the
    # near (blocking) face of the bollard that rises into its path.
    bpy.ops.object.camera_add(location=(-2.55, -7.15, 2.05))
    cam = bpy.context.object
    cam.name = "camera_left_front_view_rising_bollard"
    cam.data.lens = 32
    cam.data.dof.use_dof = False
    look_at(cam, (0.78, 0.0, 0.42))
    scene.camera = cam


# --- geometry constants (shared by build + animate) ---
BALL_R = 0.22
BALL_START_X = -3.0
ROLL_Z = BALL_R                 # ball-centre height rolling on the floor (top z = 0)

BLOCK_X = 1.0                   # x where the bollard rises
BOLL_R = 0.18                   # bollard radius
BOLL_H = 0.90                   # bollard height
BOLL_DOWN_Z = -BOLL_H / 2.0 - 0.12   # centre while hidden below the floor
BOLL_UP_Z = BOLL_H / 2.0             # centre while raised (bottom flush at z = 0)
BOLL_NEAR_FACE_X = BLOCK_X - BOLL_R  # 0.82 -- the -X face the ball must not cross

# contact kinematics: the ball rolls at CONSTANT speed until it actually touches
# the bollard (centre exactly one radius short of the near face -- zero gap, zero
# penetration), then a short damped impact response: it leaves contact with a
# fraction of the impact speed reversed (restitution) and decelerates uniformly
# to rest a small rollback distance in front of the post.
CONTACT_X = BOLL_NEAR_FACE_X - BALL_R        # 0.60 -- ball centre at first contact

BALL_V = 0.06                                # units/frame, constant approach speed
BALL_H0 = 1                                  # hold frame before motion starts
F_CONTACT = BALL_H0 + (CONTACT_X - BALL_START_X) / BALL_V   # = 61.0 (exact frame)

RESTITUTION = 0.25                           # damped impact: exit/impact speed ratio
REBOUND_V = BALL_V * RESTITUTION             # 0.015 units/frame, direction reversed
REBOUND_T = 16                               # frames of uniform decel until rest
REBOUND_DIST = REBOUND_V * REBOUND_T / 2.0   # 0.12 total rollback
REST_X = CONTACT_X - REBOUND_DIST            # 0.48 -- final resting centre x
F_REST = F_CONTACT + REBOUND_T               # 77.0

# bollard rise timing (fully up long before the ball arrives)
BOLL_RISE_START = 15
BOLL_RISE_END = 35


def build_scene():
    scene = build_base_scene()
    setup_camera(scene)

    # Flat table/track the ball rolls along (apparatus -> gray). Top flush with floor.
    add_cube(
        "straight_roll_track",
        (0.0, 0.0, 0.005),
        (9.6, 0.9, 0.02),
        MATS["track"], "roll_track", "gray",
    )

    # Dark floor slot the bollard emerges from (apparatus -> gray).
    add_cube(
        "bollard_floor_slot",
        (BLOCK_X, 0.0, 0.012),
        (2.0 * BOLL_R + 0.08, 2.0 * BOLL_R + 0.08, 0.03),
        MATS["slot"], "bollard_guide_slot", "dark_gray",
    )

    # Rising bollard: a solid cylindrical post (apparatus -> gray). Starts hidden below
    # the floor and rises straight up in +Z into the ball's path.
    bollard = add_cylinder(
        "rising_bollard_post",
        (BLOCK_X, 0.0, BOLL_DOWN_Z),
        BOLL_R, BOLL_H,
        MATS["bollard"], "rising_bollard_post", "light_gray",
        is_dynamic=True,
    )
    bollard["pb_rises_out_of_floor"] = True

    # The BALL: the target (vivid). Rolls in +X toward the block spot.
    ball = add_sphere("rolling_ball", BALL_R, (BALL_START_X, 0.0, ROLL_Z), MATS["orange"], "orange")
    ball["pb_rolls_and_is_blocked_by_bollard"] = True

    return {
        "scene": scene,
        "bollard": bollard,
        "ball": ball,
    }


def ball_x_at_frame(frame):
    if frame <= BALL_H0:
        return BALL_START_X
    if frame <= F_CONTACT:
        # constant speed all the way to actual contact -- no anticipatory braking
        return BALL_START_X + BALL_V * (frame - BALL_H0)
    if frame <= F_REST:
        # damped rebound: leaves contact at REBOUND_V in -X, uniform decel to rest
        tau = frame - F_CONTACT
        return CONTACT_X - REBOUND_V * tau + (REBOUND_V / (2.0 * REBOUND_T)) * tau * tau
    return REST_X


def bollard_z_at_frame(frame):
    if frame <= BOLL_RISE_START:
        return BOLL_DOWN_Z
    if frame >= BOLL_RISE_END:
        return BOLL_UP_Z
    t = (frame - BOLL_RISE_START) / float(BOLL_RISE_END - BOLL_RISE_START)
    return lerp(BOLL_DOWN_Z, BOLL_UP_Z, smooth01(t))


def animate_scene(objs):
    scene = objs["scene"]
    bollard = objs["bollard"]
    ball = objs["ball"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        # Bollard rises out of the floor into the ball's path, well before arrival.
        bz = bollard_z_at_frame(frame)
        bollard.location = (BLOCK_X, 0.0, bz)
        bollard.keyframe_insert(data_path="location", frame=frame)
        if bz >= BOLL_UP_Z - 1e-4:
            bollard["pb_state"] = "raised_blocking_ball_path"
        elif bz <= BOLL_DOWN_Z + 1e-4:
            bollard["pb_state"] = "hidden_below_floor"
        else:
            bollard["pb_state"] = "rising_out_of_floor"

        # Ball rolls in +X at constant speed until its leading edge actually
        # REACHES the bollard near face (frame 61: centre x = 0.60, leading edge
        # exactly at x = 0.82, zero penetration), then a small damped rebound
        # (restitution 0.25) eases it to rest 0.12 in front of the post.
        # Rotation follows rolling contact in both directions and stops with it.
        bx = ball_x_at_frame(frame)
        ball.location = (bx, 0.0, ROLL_Z)
        ball.rotation_euler = (0.0, -(bx - BALL_START_X) / BALL_R, 0.0)
        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)

        if frame < F_CONTACT:
            ball["pb_state"] = "rolling_toward_block_spot"
        elif frame < F_REST:
            ball["pb_state"] = "impact_and_damped_rebound_off_bollard"
        else:
            ball["pb_state"] = "stopped_at_rest_blocked_by_bollard"
        ball["pb_must_not_penetrate_bollard"] = True

    scene.frame_set(FRAME_START)


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


def main():
    ensure_dirs()
    clear_scene()

    kind = CASE["scene_kind"]
    if kind != "rising_bollard_stop":
        raise RuntimeError("Unknown scene_kind: " + str(kind))

    objs = build_scene()
    scene = objs["scene"]
    animate_scene(objs)

    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, 45, OPTIONAL_FRAME_PATH)
    render_png(scene, 120, OPTIONAL_FRAME_02B_PATH)

    render_animation(scene)
    write_task_json()
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
