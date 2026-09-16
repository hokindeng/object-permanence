# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

ITEM_ID = "PB_THREE_BALLS_PARALLEL_TUNNELS_IDENTITY_0039"

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
OPTIONAL_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_hidden_frame_02.png")
OPTIONAL_FRAME_02B_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_final_frame_02B.png")


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


def lerp(a, b, t):
    return a + (b - a) * t


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def make_mat(name, color, roughness=0.55, metallic=0.0, alpha=1.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (color[0], color[1], color[2], alpha)

    try:
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            if "Base Color" in bsdf.inputs:
                bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], alpha)
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = roughness
            if "Metallic" in bsdf.inputs:
                bsdf.inputs["Metallic"].default_value = metallic
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


def add_sphere(name, radius, location, material, color_name):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, "target", "dynamic_object", "sphere", color_name, True, solid=True, pb_radius=radius)
    return obj


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), roughness=0.84)
    MATS["track"] = make_mat("mat_track_gray", (0.45, 0.45, 0.47), roughness=0.70)
    MATS["tunnel"] = make_mat("mat_opaque_tunnel", (0.36, 0.37, 0.39), roughness=0.72)
    MATS["dark"] = make_mat("mat_dark_opening", (0.36, 0.37, 0.39), roughness=0.80)
    MATS["red"] = make_mat("mat_red_ball", (0.92, 0.12, 0.10), roughness=0.30)
    MATS["blue"] = make_mat("mat_blue_ball", (0.16, 0.36, 0.95), roughness=0.30)
    MATS["yellow"] = make_mat("mat_yellow_ball", (1.0, 0.76, 0.08), roughness=0.30)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.92)


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

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (9.5, 5.5, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 2.55, 1.55), (9.5, 0.08, 3.10), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.4, -4.2, 5.4))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 960
    key.data.size = 6.0

    bpy.ops.object.light_add(type="POINT", location=(3.3, -2.7, 3.0))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 150

    return scene


def setup_camera(scene):
    bpy.ops.object.camera_add(location=(0.0, -7.6, 2.35))
    cam = bpy.context.object
    cam.name = "camera_three_parallel_tunnels"
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 5.6
    cam.data.dof.use_dof = False
    look_at(cam, (0.0, 0.0, 0.48))
    scene.camera = cam


def build_lane(name, y, mat_ball, color_name):
    track_z = 0.055
    ball_r = 0.13
    ball_z = track_z + ball_r + 0.004
    tunnel_inner_half_width = 0.25
    tunnel_wall_y = tunnel_inner_half_width + 0.04

    # Visible tracks extend inward to meet the hidden in-tunnel track flush (inner ends at
    # x = -0.90 / +0.90), so the balls stay supported across the tunnel mouths.
    add_cube(f"{name}_left_visible_track", (-2.225, y, track_z), (2.65, 0.30, 0.07), MATS["track"], "track", "gray")
    add_cube(f"{name}_hidden_track_inside_tunnel", (0.0, y, track_z), (1.80, 0.30, 0.07), MATS["track"], "hidden_track", "gray")
    add_cube(f"{name}_right_visible_track", (2.225, y, track_z), (2.65, 0.30, 0.07), MATS["track"], "track", "gray")

    add_cube(f"{name}_opaque_tunnel_front_wall", (0.0, y - tunnel_wall_y, 0.42), (1.86, 0.08, 0.68), MATS["tunnel"], "opaque_tunnel_wall", "dark_gray")
    add_cube(f"{name}_opaque_tunnel_back_wall", (0.0, y + tunnel_wall_y, 0.42), (1.86, 0.08, 0.68), MATS["tunnel"], "opaque_tunnel_wall", "dark_gray")
    add_cube(f"{name}_opaque_tunnel_roof", (0.0, y, 0.75), (1.86, 2.0 * tunnel_inner_half_width, 0.09), MATS["tunnel"], "opaque_tunnel_roof", "dark_gray")

    # These dark mouth cards are visual depth cues, not physical barriers.  Mark
    # them non-solid so the trajectory never intersects a supposedly solid cube.
    add_cube(f"{name}_left_dark_opening", (-0.96, y, 0.42), (0.02, 2.0 * tunnel_inner_half_width, 0.55), MATS["dark"], "tunnel_opening", "dark_inside", solid=False)
    add_cube(f"{name}_right_dark_opening", (0.96, y, 0.42), (0.02, 2.0 * tunnel_inner_half_width, 0.55), MATS["dark"], "tunnel_opening", "dark_inside", solid=False)

    ball = add_sphere(f"{name}_{color_name}_ball", ball_r, (-3.30, y, ball_z), mat_ball, color_name)
    ball["pb_lane_identity"] = name
    ball["pb_color_identity"] = color_name
    ball["pb_radius"] = ball_r

    return {
        "name": name,
        "y": y,
        "ball": ball,
        "ball_r": ball_r,
        "ball_z": ball_z,
        "x0": -3.30,
        "x1": 3.30,
    }


def build_scene():
    scene = build_base_scene()
    setup_camera(scene)

    upper = build_lane("upper_lane", 0.72, MATS["red"], "red")
    middle = build_lane("middle_lane", 0.0, MATS["blue"], "blue")
    lower = build_lane("lower_lane", -0.72, MATS["yellow"], "yellow")

    return {
        "scene": scene,
        "lanes": [upper, middle, lower],
    }


def animate_scene(objs):
    scene = objs["scene"]
    lanes = objs["lanes"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        t = (frame - FRAME_START) / float(FRAME_END - FRAME_START)

        for lane in lanes:
            ball = lane["ball"]
            x = lerp(lane["x0"], lane["x1"], t)
            y = lane["y"]
            z = lane["ball_z"]

            ball.location = (x, y, z)

            dist = x - lane["x0"]
            spin = -dist / max(lane["ball_r"], 0.001)
            ball.rotation_euler = (0.0, spin, 0.0)

            ball.keyframe_insert(data_path="location", frame=frame)
            ball.keyframe_insert(data_path="rotation_euler", frame=frame)

            if x < -0.96:
                state = "visible_before_entering_own_tunnel"
            elif x <= 0.96:
                state = "hidden_inside_own_opaque_tunnel_but_continuing"
            else:
                state = "visible_after_exiting_own_tunnel"

            ball["pb_state"] = state
            ball["pb_identity_preserved"] = True
            ball["pb_lane_identity_preserved"] = True
            ball["pb_must_not_swap_lanes"] = True

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
            "text_prompt": (
                "Three colored balls roll from left to right on three parallel gray tracks. "
                "The upper lane has a red ball, the middle lane has a blue ball, and the lower lane has a yellow ball. "
                "Each ball enters its own opaque gray tunnel, becomes hidden while inside, and then exits on the right side. "
                "The balls must preserve identity, color, size, count, lane order, and continuous motion. "
                "They must not swap lanes, merge, disappear, or reappear in the wrong tunnel."
            ),
        },
        "reference_completion_frames_dir": "frames",
        "scene_file": f"{ITEM_ID}_scene.blend",
    }

    with open(TASK_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(task, f, indent=2, ensure_ascii=False)


def save_scene():
    bpy.ops.wm.save_as_mainfile(filepath=SCENE_FILE)


def main():
    ensure_dirs()
    clear_scene()

    objs = build_scene()
    scene = objs["scene"]
    animate_scene(objs)

    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, 60, OPTIONAL_FRAME_PATH)
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
