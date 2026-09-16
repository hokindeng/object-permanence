# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

ITEM_ID = "PB_DRAWER_CLOSES_MOVES_HIDDEN_BALL_0037"

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
OPTIONAL_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_closed_moving_frame_02.png")
OPTIONAL_FRAME_02B_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_reopened_frame_02B.png")


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


def add_sphere(name, radius, location, material, color_name):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, "target", "dynamic_object", "sphere", color_name, True, solid=True, pb_radius=radius)
    return obj


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor_warm", (0.82, 0.80, 0.75), roughness=0.82)
    MATS["cabinet"] = make_mat("mat_cabinet_light_gray", (0.55, 0.56, 0.58), roughness=0.70)
    MATS["drawer"] = make_mat("mat_drawer_gray", (0.55, 0.56, 0.58), roughness=0.66)
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

    add_cube("large_floor_base", (0, 0, -0.05), (8.0, 5.0, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0, 2.45, 1.55), (8.0, 0.08, 3.10), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.5, -4.0, 5.5))
    key = bpy.context.object
    key.name = "large_softbox_light"
    key.data.energy = 930
    key.data.size = 5.8

    bpy.ops.object.light_add(type="POINT", location=(3.5, -3.0, 3.0))
    fill = bpy.context.object
    fill.name = "fill_light"
    fill.data.energy = 140

    return scene


def setup_camera(scene):
    # High oblique / almost top-down view.
    # It sees into the open drawer, but still shows the drawer going into the cabinet.
    bpy.ops.object.camera_add(location=(1.25, -2.75, 5.20))
    cam = bpy.context.object
    cam.name = "camera_high_oblique_drawer_topview"
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 3.30
    look_at(cam, (0.22, -0.62, 0.38))
    scene.camera = cam


def build_scene():
    scene = build_base_scene()
    setup_camera(scene)

    cabinet_parts = []
    drawer_parts = []

    base_z = 0.28

    # Cabinet coordinates are the final/closed cabinet frame.
    # The drawer slides along Y into this cabinet.
    def cabinet_part(name, rel, dims):
        obj = add_cube(
            name,
            rel,
            dims,
            MATS["cabinet"],
            "drawer_outer_case",
            "light_gray",
            is_dynamic=True,
            solid=True,
        )
        obj["pb_rel_x"] = rel[0]
        obj["pb_rel_y"] = rel[1]
        obj["pb_rel_z"] = rel[2]
        cabinet_parts.append(obj)
        return obj

    def drawer_part(name, rel, dims, role="drawer_part"):
        obj = add_cube(
            name,
            rel,
            dims,
            MATS["drawer"],
            role,
            "gray",
            is_dynamic=True,
            solid=True,
        )
        obj["pb_rel_x"] = rel[0]
        obj["pb_rel_y"] = rel[1]
        obj["pb_rel_z"] = rel[2]
        drawer_parts.append(obj)
        return obj

    # Opaque cabinet with top cover. In top view, closed ball is hidden under this cover.
    cabinet_part("drawer_outer_case_bottom", (0.0, -0.015, base_z), (1.64, 1.03, 0.10))
    cabinet_part("drawer_outer_case_top_cover", (0.0, -0.015, base_z + 0.72), (1.64, 1.03, 0.10))
    cabinet_part("drawer_outer_case_left_wall", (-0.82, -0.025, base_z + 0.36), (0.10, 1.05, 0.72))
    cabinet_part("drawer_outer_case_right_wall", (0.82, -0.025, base_z + 0.36), (0.10, 1.05, 0.72))
    cabinet_part("drawer_outer_case_back_wall", (0.0, 0.50, base_z + 0.36), (1.72, 0.10, 0.72))

    # Front frame: makes the cabinet look like a real drawer slot.
    cabinet_part("drawer_outer_case_front_left_frame", (-0.82, -0.58, base_z + 0.36), (0.12, 0.10, 0.72))
    cabinet_part("drawer_outer_case_front_right_frame", (0.82, -0.58, base_z + 0.36), (0.12, 0.10, 0.72))
    cabinet_part("drawer_outer_case_front_top_frame", (0.0, -0.58, base_z + 0.70), (1.72, 0.10, 0.14))

    # Drawer closed coordinates. At frame 1 an open offset is added.
    # Closed drawer is inside the cabinet; open drawer protrudes toward camera.
    drawer_part("drawer_floor", (0.0, -0.12, base_z + 0.13), (1.20, 0.78, 0.08))
    drawer_part("drawer_left_wall", (-0.56, -0.12, base_z + 0.31), (0.08, 0.78, 0.36))
    drawer_part("drawer_right_wall", (0.56, -0.12, base_z + 0.31), (0.08, 0.78, 0.36))
    drawer_part("drawer_back_wall", (0.0, 0.24, base_z + 0.31), (1.20, 0.08, 0.36))
    lip = drawer_part("drawer_low_front_lip", (0.0, -0.50, base_z + 0.22), (1.20, 0.08, 0.20), role="drawer_front_lip")
    lip["pb_low_lip_does_not_hide_ball_in_first_frame"] = True

    ball = add_sphere("orange_ball_inside_drawer", 0.145, (-0.12, -0.12, base_z + 0.31), MATS["orange"], "orange")
    ball["pb_rel_x"] = -0.12
    ball["pb_rel_y"] = -0.12
    ball["pb_rel_z"] = base_z + 0.31
    ball["pb_inside_drawer"] = True

    return {
        "scene": scene,
        "cabinet_parts": cabinet_parts,
        "drawer_parts": drawer_parts,
        "ball": ball,
    }


def animate_scene(objs):
    scene = objs["scene"]
    cabinet_parts = objs["cabinet_parts"]
    drawer_parts = objs["drawer_parts"]
    ball = objs["ball"]
    drawer_travel = 0.72 * DIVERSITY.get("drawer_travel_scale", 1.0)

    # Open offset: -0.78 puts the drawer outside the cabinet, visible from top view.
    # Closed offset: 0.0 puts drawer fully inside the cabinet.
    # After closing, the whole unit shifts right only 0.72, so it stays in frame.
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 45:
            close_frac = smooth01((frame - 1) / 44.0)
            unit_shift_x = 0.0
            reopen_frac = 0.0
        elif frame <= 88:
            close_frac = 1.0
            unit_shift_x = drawer_travel * smooth01((frame - 45) / 43.0)
            reopen_frac = 0.0
        else:
            close_frac = 1.0
            unit_shift_x = drawer_travel
            reopen_frac = smooth01((frame - 88) / 32.0)

        open_offset_y = -0.78 * (1.0 - close_frac + reopen_frac)
        open_offset_y = max(-0.78, min(0.0, open_offset_y))

        for obj in cabinet_parts:
            obj.location = (
                obj.get("pb_rel_x", 0.0) + unit_shift_x,
                obj.get("pb_rel_y", 0.0),
                obj.get("pb_rel_z", 0.0),
            )
            obj.keyframe_insert(data_path="location", frame=frame)
            obj["pb_state"] = "drawer_unit_moving_right" if frame > 45 else "cabinet_initial"

        for obj in drawer_parts:
            obj.location = (
                obj.get("pb_rel_x", 0.0) + unit_shift_x,
                obj.get("pb_rel_y", 0.0) + open_offset_y,
                obj.get("pb_rel_z", 0.0),
            )
            obj.keyframe_insert(data_path="location", frame=frame)

            if frame <= 45:
                state = "sliding_into_cabinet"
            elif frame <= 88:
                state = "closed_inside_cabinet_moving_right"
            else:
                state = "sliding_open_after_move"
            obj["pb_state"] = state

        ball.location = (
            ball.get("pb_rel_x", 0.0) + unit_shift_x,
            ball.get("pb_rel_y", 0.0) + open_offset_y,
            ball.get("pb_rel_z", 0.0),
        )
        ball.keyframe_insert(data_path="location", frame=frame)

        if frame <= 12:
            ball["pb_state"] = "clearly_visible_inside_open_drawer"
        elif frame <= 45:
            ball["pb_state"] = "becoming_hidden_as_drawer_slides_in"
        elif frame <= 88:
            ball["pb_state"] = "hidden_inside_closed_drawer_moving_right"
        else:
            ball["pb_state"] = "visible_again_inside_reopened_drawer"

        ball["pb_moves_with_drawer"] = True
        ball["pb_not_left_behind"] = True

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
                "A gray drawer starts open, viewed from a high top-down angle, and an orange ball is clearly visible inside the open drawer. "
                "The drawer slides closed into its outer case, hiding the ball. "
                "Then the entire closed drawer unit moves to the right. "
                "Finally the drawer opens again, revealing that the same orange ball is still inside at the new position. "
                "The ball must move with the drawer and must not remain behind, disappear, or pass through the drawer walls."
            ),
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
    objs = build_scene()
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
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
