# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

ITEM_ID = "PB_DRAWER_CLOSES_MOVES_HIDDEN_CUBE_AND_BALL_0038"

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
OPTIONAL_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_hidden_move_frame_02.png")
OPTIONAL_FRAME_02B_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_reopen_frame_02B.png")


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


def make_mat(name, color, roughness=0.55, metallic=0.0, alpha=1.0, transparent=False):
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
            if "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = alpha
    except Exception:
        pass

    if transparent:
        try:
            mat.blend_method = "BLEND"
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


def add_cube(name, location, dimensions, material, role, color_name, is_dynamic=False, solid=True, rotation=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=rotation)
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
    MATS["drawer"] = make_mat("mat_drawer_gray", (0.55, 0.56, 0.58), roughness=0.66)
    MATS["drawer_dark"] = make_mat("mat_drawer_dark", (0.55, 0.56, 0.58), roughness=0.72)
    MATS["orange"] = make_mat("mat_orange_ball", (1.0, 0.38, 0.06), roughness=0.28)
    MATS["blue"] = make_mat("mat_blue_cube", (0.18, 0.42, 0.95), roughness=0.35)
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
        scene.eevee.gtao_distance = 3.0
        scene.eevee.gtao_factor = 1.2
    except Exception:
        pass

    if scene.world is None:
        scene.world = bpy.data.worlds.new("clean_world")
    scene.world.color = (1.0, 1.0, 1.0)

    try:
        scene.view_settings.view_transform = "Filmic"
        scene.view_settings.look = "Medium High Contrast"
    except Exception:
        pass


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (10.0, 5.0, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 2.35, 1.60), (10.0, 0.08, 3.20), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.2, -4.2, 5.6))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 980
    key.data.size = 6.0

    bpy.ops.object.light_add(type="POINT", location=(3.1, -2.8, 3.2))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 145

    return scene


def setup_camera(scene):
    # High front-top view so first frame clearly sees both objects in the open drawer.
    bpy.ops.object.camera_add(location=(1.25, -4.35, 4.35))
    cam = bpy.context.object
    cam.name = "camera_drawer_hidden_two_objects"
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 8.0
    cam.data.dof.use_dof = False
    look_at(cam, (0.0, -0.05, 0.50))
    scene.camera = cam


def build_scene():
    scene = build_base_scene()
    setup_camera(scene)

    # Cabinet shell dimensions
    cabinet_x0 = 0.0
    cabinet_y0 = 0.0

    # Cabinet / outer case
    cabinet_floor = add_cube("cabinet_floor", (cabinet_x0, cabinet_y0 - 0.015, 0.17), (1.60, 1.21, 0.10), MATS["drawer_dark"], "cabinet_floor", "dark_gray", is_dynamic=True)
    cabinet_left_wall = add_cube("cabinet_left_wall", (cabinet_x0 - 0.80, cabinet_y0 - 0.025, 0.45), (0.10, 1.23, 0.66), MATS["drawer_dark"], "cabinet_wall", "dark_gray", is_dynamic=True)
    cabinet_right_wall = add_cube("cabinet_right_wall", (cabinet_x0 + 0.80, cabinet_y0 - 0.025, 0.45), (0.10, 1.23, 0.66), MATS["drawer_dark"], "cabinet_wall", "dark_gray", is_dynamic=True)
    cabinet_back_wall = add_cube("cabinet_back_wall", (cabinet_x0, cabinet_y0 + 0.59, 0.45), (1.70, 0.10, 0.66), MATS["drawer_dark"], "cabinet_wall", "dark_gray", is_dynamic=True)
    cabinet_top = add_cube("cabinet_top_cover", (cabinet_x0, cabinet_y0 - 0.015, 0.78), (1.60, 1.21, 0.08), MATS["drawer_dark"], "cabinet_top", "dark_gray", is_dynamic=True)

    # Drawer tray parts
    drawer_floor = add_cube("drawer_floor", (cabinet_x0, cabinet_y0 - 0.78, 0.22), (1.45, 0.90, 0.08), MATS["drawer"], "drawer_floor", "gray", is_dynamic=True)
    drawer_left_wall = add_cube("drawer_left_wall", (cabinet_x0 - 0.68, cabinet_y0 - 0.78, 0.37), (0.08, 0.90, 0.30), MATS["drawer"], "drawer_wall", "gray", is_dynamic=True)
    drawer_right_wall = add_cube("drawer_right_wall", (cabinet_x0 + 0.68, cabinet_y0 - 0.78, 0.37), (0.08, 0.90, 0.30), MATS["drawer"], "drawer_wall", "gray", is_dynamic=True)
    drawer_back_wall = add_cube("drawer_back_wall", (cabinet_x0, cabinet_y0 - 0.38, 0.37), (1.45, 0.08, 0.30), MATS["drawer"], "drawer_wall", "gray", is_dynamic=True)
    drawer_front_wall = add_cube("drawer_front_wall", (cabinet_x0, cabinet_y0 - 1.18, 0.37), (1.45, 0.08, 0.30), MATS["drawer"], "drawer_front", "gray", is_dynamic=True)

    # Handle
    handle = add_cube("drawer_handle", (cabinet_x0, cabinet_y0 - 1.24, 0.42), (0.38, 0.05, 0.08), MATS["drawer_dark"], "drawer_handle", "dark_gray", is_dynamic=True)

    # Two objects inside drawer
    ball_r = 0.13
    ball = add_sphere("orange_ball_inside_drawer", ball_r, (cabinet_x0 - 0.22, cabinet_y0 - 0.88, 0.22 + ball_r + 0.01), MATS["orange"], "orange")

    cube = add_cube("blue_cube_inside_drawer", (cabinet_x0 + 0.24, cabinet_y0 - 0.67, 0.22 + 0.12), (0.24, 0.24, 0.24), MATS["blue"], "contained_cube", "blue", is_dynamic=True)

    return {
        "scene": scene,
        "cabinet_parts": [cabinet_floor, cabinet_left_wall, cabinet_right_wall, cabinet_back_wall, cabinet_top],
        "drawer_parts": [drawer_floor, drawer_left_wall, drawer_right_wall, drawer_back_wall, drawer_front_wall, handle],
        "ball": ball,
        "cube": cube,
        "ball_r": ball_r,
    }


def animate_scene(objs):
    scene = objs["scene"]
    cabinet_parts = objs["cabinet_parts"]
    drawer_parts = objs["drawer_parts"]
    ball = objs["ball"]
    cube = objs["cube"]
    ball_r = objs["ball_r"]

    # Base positions
    base_cabinet_x = 0.0
    base_cabinet_y = 0.0
    drawer_open_offset = -0.78 * DIVERSITY.get("drawer_travel_scale", 1.0)
    drawer_closed_offset = 0.0

    # Relative positions inside drawer (in drawer local frame)
    rel_ball_x = -0.22
    rel_ball_y = -0.10
    rel_ball_z = 0.22 + ball_r + 0.01

    rel_cube_x = 0.24
    rel_cube_y = 0.11
    rel_cube_z = 0.22 + 0.12

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        # Motion schedule:
        # 1-30   : drawer open, visible
        # 31-60  : drawer closes
        # 61-95  : whole cabinet moves right
        # 96-120 : drawer opens again at new position

        if frame <= 30:
            close_t = 0.0
            move_t = 0.0
            reopen_t = 0.0
        elif frame <= 60:
            close_t = smooth01((frame - 30) / 30.0)
            move_t = 0.0
            reopen_t = 0.0
        elif frame <= 95:
            close_t = 1.0
            move_t = smooth01((frame - 60) / 35.0)
            reopen_t = 0.0
        else:
            close_t = 1.0
            move_t = 1.0
            reopen_t = smooth01((frame - 95) / 25.0)

        cabinet_dx = lerp(0.0, 2.30, move_t)

        # Drawer offset along Y: open -> closed -> open again
        if reopen_t == 0.0:
            drawer_y_offset = lerp(drawer_open_offset, drawer_closed_offset, close_t)
        else:
            drawer_y_offset = lerp(drawer_closed_offset, drawer_open_offset, reopen_t)

        # Animate cabinet shell
        cabinet_positions = [
            (base_cabinet_x + cabinet_dx, base_cabinet_y - 0.015, 0.17),
            (base_cabinet_x - 0.80 + cabinet_dx, base_cabinet_y - 0.025, 0.45),
            (base_cabinet_x + 0.80 + cabinet_dx, base_cabinet_y - 0.025, 0.45),
            (base_cabinet_x + cabinet_dx, base_cabinet_y + 0.59, 0.45),
            (base_cabinet_x + cabinet_dx, base_cabinet_y - 0.015, 0.78),
        ]

        for obj, loc in zip(cabinet_parts, cabinet_positions):
            obj.location = loc
            obj.keyframe_insert(data_path="location", frame=frame)

        # Animate drawer tray parts
        drawer_positions = [
            (base_cabinet_x + cabinet_dx, base_cabinet_y + drawer_y_offset, 0.22),
            (base_cabinet_x - 0.68 + cabinet_dx, base_cabinet_y + drawer_y_offset, 0.37),
            (base_cabinet_x + 0.68 + cabinet_dx, base_cabinet_y + drawer_y_offset, 0.37),
            (base_cabinet_x + cabinet_dx, base_cabinet_y + drawer_y_offset + 0.40, 0.37),
            (base_cabinet_x + cabinet_dx, base_cabinet_y + drawer_y_offset - 0.40, 0.37),
            (base_cabinet_x + cabinet_dx, base_cabinet_y + drawer_y_offset - 0.46, 0.42),
        ]

        for obj, loc in zip(drawer_parts, drawer_positions):
            obj.location = loc
            obj.keyframe_insert(data_path="location", frame=frame)

        # Animate objects so they rigidly move with the drawer
        ball.location = (
            base_cabinet_x + cabinet_dx + rel_ball_x,
            base_cabinet_y + drawer_y_offset + rel_ball_y,
            rel_ball_z,
        )
        ball.rotation_euler = (0.0, 0.0, 0.0)
        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)

        cube.location = (
            base_cabinet_x + cabinet_dx + rel_cube_x,
            base_cabinet_y + drawer_y_offset + rel_cube_y,
            rel_cube_z,
        )
        cube.rotation_euler = (0.0, 0.0, 0.0)
        cube.keyframe_insert(data_path="location", frame=frame)
        cube.keyframe_insert(data_path="rotation_euler", frame=frame)

        # Semantic states
        if frame <= 30:
            drawer_state = "open_initially"
            object_state = "visible_inside_open_drawer"
        elif frame <= 60:
            drawer_state = "closing"
            object_state = "becoming_hidden_as_drawer_closes"
        elif frame <= 95:
            drawer_state = "closed_and_moving_right"
            object_state = "hidden_inside_drawer_moving_with_drawer"
        else:
            drawer_state = "reopening_at_new_position"
            object_state = "revealed_inside_drawer_after_move"

        for obj in drawer_parts:
            obj["pb_state"] = drawer_state

        for obj in cabinet_parts:
            obj["pb_state"] = "cabinet_moves_right" if frame > 60 else "cabinet_static_before_move"

        ball["pb_state"] = object_state
        cube["pb_state"] = object_state
        ball["pb_moves_with_drawer"] = True
        cube["pb_moves_with_drawer"] = True
        ball["pb_identity_preserved"] = True
        cube["pb_identity_preserved"] = True

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
                "A gray drawer starts open, and two objects are clearly visible inside: one orange ball and one blue cube. "
                "The drawer closes and hides both objects. Then the entire drawer cabinet moves to the right. "
                "Finally the drawer opens again, revealing that the same orange ball and the same blue cube are still inside the drawer at the new position. "
                "Both objects must continue to exist while hidden, must move with the drawer, and must preserve identity, color, size, and count."
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
    render_png(scene, 75, OPTIONAL_FRAME_PATH)
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
