# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_TWO_SUPPORTED_SCREENS_CLOSE_REOPEN_OBJECTS_0070",
  "kind": "two_supported_screens_close",
  "prompt": "Front view. An orange ball is on the left pedestal and a blue cube is on the right pedestal. Two opaque foreground screens slide inward on visible support rails and hide both objects, then slide outward again. The screens are supported and do not pass through the objects. The same orange ball must remain on the left pedestal and the same blue cube must remain on the right pedestal."
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
            if "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = alpha
    except Exception:
        pass

    return mat


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), roughness=0.85)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.92)

    MATS["gray"] = make_mat("mat_gray", (0.62, 0.63, 0.66), roughness=0.75)
    MATS["dark"] = make_mat("mat_dark", (0.18, 0.20, 0.24), roughness=0.55)
    MATS["screen"] = make_mat("mat_screen", (0.46, 0.48, 0.53), roughness=0.88)
    MATS["support"] = make_mat("mat_support", (0.16, 0.18, 0.22), roughness=0.60)

    MATS["red"] = make_mat("mat_red", (0.92, 0.18, 0.18), roughness=0.28)
    MATS["blue"] = make_mat("mat_blue", (0.16, 0.36, 0.95), roughness=0.28)
    MATS["yellow"] = make_mat("mat_yellow", (0.98, 0.78, 0.15), roughness=0.28)
    MATS["orange"] = make_mat("mat_orange", (0.97, 0.45, 0.10), roughness=0.28)


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
        "dynamic_object" if is_dynamic else "static_solid",
        "cube",
        color_name,
        is_dynamic,
        solid=solid,
    )
    return obj


def add_ball(name, radius, location, material, color_name):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=48, ring_count=24)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)

    tag(
        obj,
        name,
        "target",
        "dynamic_object",
        "sphere",
        color_name,
        True,
        solid=True,
        pb_radius=radius,
    )
    return obj


def add_pyramid(name, size, location, material, color_name):
    bpy.ops.mesh.primitive_cone_add(
        vertices=3,
        radius1=size * 0.62,
        radius2=0.0,
        depth=size,
        location=location,
        rotation=(0.0, 0.0, math.radians(-30)),
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, "target", "dynamic_object", "triangular_pyramid", color_name, True, solid=True)
    return obj


def add_cylinder_between(name, p1, p2, radius, material, role, color_name):
    p1 = Vector(p1)
    p2 = Vector(p2)
    diff = p2 - p1
    length = diff.length
    mid = (p1 + p2) / 2.0

    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=length, vertices=24, location=mid)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = diff.to_track_quat("Z", "Y").to_euler()

    if material is not None:
        obj.data.materials.append(material)

    tag(obj, name, role, "static_solid", "cylinder", color_name, False, solid=True)
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


def setup_base(camera_loc, target, ortho_scale):
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (11.0, 7.0, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.05, 1.65), (11.0, 0.08, 3.3), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-2.8, -4.5, 5.8))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 950
    key.data.size = 5.5

    bpy.ops.object.light_add(type="POINT", location=(3.0, 1.8, 3.3))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 120

    bpy.ops.object.camera_add(location=camera_loc)
    cam = bpy.context.object
    cam.name = "camera_main"
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = ortho_scale
    look_at(cam, target)
    scene.camera = cam

    return scene


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


def write_task_json(task):
    with open(TASK_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(task, f, indent=2, ensure_ascii=False)


def save_scene():
    bpy.ops.wm.save_as_mainfile(filepath=SCENE_FILE)


# =============================================================================
# 00000067
# =============================================================================

def build_supported_screen_three_balls():
    scene = setup_base(
        camera_loc=(7.3, -7.4, 5.2),
        target=(0.0, 0.0, 0.58),
        ortho_scale=7.4,
    )

    add_ball("red_ball", 0.18, (-0.80, 0.25, 0.18), MATS["red"], "red")
    add_ball("blue_ball", 0.18, (0.0, 0.25, 0.18), MATS["blue"], "blue")
    add_ball("yellow_ball", 0.18, (0.80, 0.25, 0.18), MATS["yellow"], "yellow")

    y = -0.76
    screen_parts = []

    screen_parts.append(add_cube("supported_foreground_screen_panel", (-3.05, y, 0.88), (1.25, 0.10, 1.76), MATS["screen"], "foreground_occluder", "gray", is_dynamic=True))
    screen_parts.append(add_cube("screen_top_slider", (-3.05, y, 1.82), (1.35, 0.16, 0.10), MATS["support"], "screen_slider", "dark_gray", is_dynamic=True))
    screen_parts.append(add_cube("screen_left_wheel", (-3.48, y, 1.96), (0.15, 0.18, 0.15), MATS["support"], "screen_wheel", "dark_gray", is_dynamic=True))
    screen_parts.append(add_cube("screen_right_wheel", (-2.62, y, 1.96), (0.15, 0.18, 0.15), MATS["support"], "screen_wheel", "dark_gray", is_dynamic=True))

    add_cube("fixed_long_overhead_screen_rail", (0.0, y, 2.08), (7.4, 0.12, 0.08), MATS["support"], "fixed_screen_support_rail", "dark_gray")

    return scene, {"screen_parts": screen_parts, "base_y": y}


def animate_supported_screen_three_balls(scene, meta):
    parts = meta["screen_parts"]
    offsets = [Vector(p.location) - Vector(parts[0].location) for p in parts]

    x0 = -3.05
    x1 = 3.05

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 12:
            x = x0
        elif frame <= 108:
            t = (frame - 12) / float(108 - 12)
            x = x0 + (x1 - x0) * t
        else:
            x = x1

        anchor = Vector((x, meta["base_y"], 0.88))

        for part, off in zip(parts, offsets):
            part.location = anchor + off
            part.keyframe_insert(data_path="location", frame=frame)
            part["pb_motion"] = "slides_on_extended_fixed_foreground_rail"

    scene.frame_set(FRAME_START)


# =============================================================================
# 00000068
# =============================================================================

def build_supported_window_mask_three_objects():
    # Front view.
    scene = setup_base(
        camera_loc=(0.0, -7.6, 2.25),
        target=(0.0, 0.0, 0.72),
        ortho_scale=5.9,
    )

    # Object widths:
    # ball diameter = 0.46
    # cube width = 0.48
    # pyramid base approx > 0.48
    # slit_width = 0.34, so it is visible but smaller than any object width.
    add_ball("orange_ball", 0.23, (-1.05, 0.25, 0.23), MATS["orange"], "orange")
    add_cube("blue_cube", (0.0, 0.25, 0.24), (0.48, 0.48, 0.48), MATS["blue"], "target_cube", "blue", is_dynamic=True)
    add_pyramid("yellow_pyramid", 0.58, (1.05, 0.25, 0.29), MATS["yellow"], "yellow")

    y = -0.78
    slit_width = 0.34
    panel_width = 1.45
    panel_height = 1.90
    zc = 0.95

    # Same supported screen style as 00000067, but with a real center slit.
    mask_parts = []
    mask_parts.append(add_cube("slit_mask_left_panel", (-1.0 - slit_width / 2.0 - panel_width / 2.0, y, zc), (panel_width, 0.10, panel_height), MATS["screen"], "foreground_mask_panel", "gray", is_dynamic=True))
    mask_parts.append(add_cube("slit_mask_right_panel", (-1.0 + slit_width / 2.0 + panel_width / 2.0, y, zc), (panel_width, 0.10, panel_height), MATS["screen"], "foreground_mask_panel", "gray", is_dynamic=True))
    mask_parts.append(add_cube("slit_mask_top_slider", (-1.0, y, 2.03), (2.90 + slit_width, 0.16, 0.10), MATS["support"], "mask_slider", "dark_gray", is_dynamic=True))
    mask_parts.append(add_cube("slit_mask_left_wheel", (-2.30, y, 2.17), (0.15, 0.18, 0.15), MATS["support"], "mask_wheel", "dark_gray", is_dynamic=True))
    mask_parts.append(add_cube("slit_mask_right_wheel", (0.30, y, 2.17), (0.15, 0.18, 0.15), MATS["support"], "mask_wheel", "dark_gray", is_dynamic=True))

    add_cube("fixed_long_window_mask_rail", (0.0, y, 2.30), (7.0, 0.12, 0.08), MATS["support"], "fixed_mask_support_rail", "dark_gray")

    return scene, {
        "mask_parts": mask_parts,
        "base_y": y,
        "slit_width": slit_width,
    }


def animate_supported_window_mask_three_objects(scene, meta):
    parts = meta["mask_parts"]

    # The anchor is the slit center.
    start_anchor = Vector((-1.0, meta["base_y"], 0.95))
    offsets = [Vector(p.location) - start_anchor for p in parts]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 20:
            x = -1.05
        elif frame <= 60:
            t = (frame - 20) / float(60 - 20)
            x = -1.05 + 1.05 * t
        elif frame <= 100:
            t = (frame - 60) / float(100 - 60)
            x = 0.0 + 1.05 * t
        else:
            x = 1.05

        anchor = Vector((x, meta["base_y"], 0.95))

        for part, off in zip(parts, offsets):
            part.location = anchor + off
            part.keyframe_insert(data_path="location", frame=frame)
            part["pb_motion"] = "front_view_supported_slit_mask"
            part["pb_slit_width"] = float(meta["slit_width"])
            part["pb_slit_narrower_than_object_width"] = True

    scene.frame_set(FRAME_START)


# =============================================================================
# 00000069
# =============================================================================

def build_two_supported_screens_close():
    # Front view.
    scene = setup_base(
        camera_loc=(0.0, -7.4, 2.20),
        target=(0.0, 0.0, 0.72),
        ortho_scale=5.9,
    )

    add_cube("left_pedestal", (-0.78, 0.25, 0.10), (0.58, 0.50, 0.20), MATS["gray"], "pedestal", "gray")
    add_cube("right_pedestal", (0.78, 0.25, 0.10), (0.58, 0.50, 0.20), MATS["gray"], "pedestal", "gray")

    add_ball("left_orange_ball", 0.22, (-0.78, 0.25, 0.42), MATS["orange"], "orange")
    add_cube("right_blue_cube", (0.78, 0.25, 0.42), (0.44, 0.44, 0.44), MATS["blue"], "target_cube", "blue", is_dynamic=True)

    y = -0.78

    left_group = []
    right_group = []

    left_group.append(add_cube("left_supported_screen_panel", (-2.25, y, 0.95), (1.35, 0.10, 1.90), MATS["screen"], "left_foreground_screen", "gray", is_dynamic=True))
    left_group.append(add_cube("left_screen_top_slider", (-2.25, y, 2.03), (1.45, 0.16, 0.10), MATS["support"], "left_screen_slider", "dark_gray", is_dynamic=True))
    left_group.append(add_cube("left_screen_wheel_a", (-2.70, y, 2.17), (0.15, 0.18, 0.15), MATS["support"], "screen_wheel", "dark_gray", is_dynamic=True))
    left_group.append(add_cube("left_screen_wheel_b", (-1.80, y, 2.17), (0.15, 0.18, 0.15), MATS["support"], "screen_wheel", "dark_gray", is_dynamic=True))

    right_group.append(add_cube("right_supported_screen_panel", (2.25, y, 0.95), (1.35, 0.10, 1.90), MATS["screen"], "right_foreground_screen", "gray", is_dynamic=True))
    right_group.append(add_cube("right_screen_top_slider", (2.25, y, 2.03), (1.45, 0.16, 0.10), MATS["support"], "right_screen_slider", "dark_gray", is_dynamic=True))
    right_group.append(add_cube("right_screen_wheel_a", (1.80, y, 2.17), (0.15, 0.18, 0.15), MATS["support"], "screen_wheel", "dark_gray", is_dynamic=True))
    right_group.append(add_cube("right_screen_wheel_b", (2.70, y, 2.17), (0.15, 0.18, 0.15), MATS["support"], "screen_wheel", "dark_gray", is_dynamic=True))

    add_cube("two_screen_long_overhead_rail", (0.0, y, 2.30), (7.0, 0.12, 0.08), MATS["support"], "fixed_screen_support_rail", "dark_gray")

    return scene, {
        "left_group": left_group,
        "right_group": right_group,
        "base_y": y,
    }


def animate_two_supported_screens_close(scene, meta):
    left_group = meta["left_group"]
    right_group = meta["right_group"]

    left_anchor0 = Vector(left_group[0].location)
    right_anchor0 = Vector(right_group[0].location)
    left_offsets = [Vector(p.location) - left_anchor0 for p in left_group]
    right_offsets = [Vector(p.location) - right_anchor0 for p in right_group]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 20:
            close_t = 0.0
        elif frame <= 48:
            close_t = (frame - 20) / float(48 - 20)
        elif frame <= 82:
            close_t = 1.0
        elif frame <= 112:
            close_t = 1.0 - (frame - 82) / float(112 - 82)
        else:
            close_t = 0.0

        left_x = -2.25 + 1.55 * close_t
        right_x = 2.25 - 1.55 * close_t

        left_anchor = Vector((left_x, meta["base_y"], 0.95))
        right_anchor = Vector((right_x, meta["base_y"], 0.95))

        for p, off in zip(left_group, left_offsets):
            p.location = left_anchor + off
            p.keyframe_insert(data_path="location", frame=frame)
            p["pb_motion"] = "front_view_supported_left_screen"

        for p, off in zip(right_group, right_offsets):
            p.location = right_anchor + off
            p.keyframe_insert(data_path="location", frame=frame)
            p["pb_motion"] = "front_view_supported_right_screen"

    scene.frame_set(FRAME_START)


# =============================================================================
# 00000070
# =============================================================================

def build_ramp_ball_slotted_screen():
    scene = setup_base(
        camera_loc=(6.8, -6.9, 4.8),
        target=(-0.12, 0.0, 0.70),
        ortho_scale=7.2,
    )

    ball_radius = 0.17
    rail_radius = 0.045
    rail_gap = 0.24
    rail_dy = rail_gap / 2.0
    rail_z_drop = math.sqrt((ball_radius + rail_radius) ** 2 - rail_dy ** 2)

    ramp_start = Vector((-3.15, 0.0, 1.28))
    ramp_end = Vector((-1.18, 0.0, 0.40))
    straight_end = Vector((3.20, 0.0, 0.40))

    for side, dy in [("left", -rail_dy), ("right", rail_dy)]:
        add_cylinder_between(
            f"ramp_{side}_rail",
            (ramp_start.x, dy, ramp_start.z - rail_z_drop),
            (ramp_end.x, dy, ramp_end.z - rail_z_drop),
            rail_radius,
            MATS["dark"],
            "ramp_rail",
            "dark_gray",
        )
        add_cylinder_between(
            f"straight_{side}_rail",
            (ramp_end.x, dy, ramp_end.z - rail_z_drop),
            (straight_end.x, dy, straight_end.z - rail_z_drop),
            rail_radius,
            MATS["dark"],
            "straight_rail",
            "dark_gray",
        )

    for i in range(11):
        x = -1.05 + i * 0.40
        add_cube(
            f"straight_tie_{i:02d}",
            (x, 0.0, ramp_end.z - rail_z_drop - 0.08),
            (0.10, 0.42, 0.055),
            MATS["support"],
            "track_tie",
            "dark_gray",
        )

    # Real slotted screen.
    screen_x = 0.35
    thickness = 0.18
    total_y = 2.35
    total_z = 1.82
    opening_y = 0.78
    opening_z = 0.58
    opening_center_z = ramp_end.z

    opening_top = opening_center_z + opening_z / 2.0
    opening_bottom = opening_center_z - opening_z / 2.0

    top_h = total_z - opening_top
    add_cube("slotted_screen_top_piece", (screen_x, 0.0, opening_top + top_h / 2.0), (thickness, total_y, top_h), MATS["screen"], "solid_screen_piece", "gray")

    if opening_bottom > 0.04:
        add_cube("slotted_screen_bottom_piece", (screen_x, 0.0, opening_bottom / 2.0), (thickness, total_y, opening_bottom), MATS["screen"], "solid_screen_piece", "gray")

    side_w = (total_y - opening_y) / 2.0
    side_center_abs_y = opening_y / 2.0 + side_w / 2.0
    add_cube("slotted_screen_near_side_piece", (screen_x, -side_center_abs_y, opening_center_z), (thickness, side_w, opening_z), MATS["screen"], "solid_screen_piece", "gray")
    add_cube("slotted_screen_far_side_piece", (screen_x, side_center_abs_y, opening_center_z), (thickness, side_w, opening_z), MATS["screen"], "solid_screen_piece", "gray")

    add_cube("slotted_screen_near_support", (screen_x, -total_y / 2.0 - 0.08, 0.72), (thickness, 0.10, 1.44), MATS["support"], "screen_support_post", "dark_gray")
    add_cube("slotted_screen_far_support", (screen_x, total_y / 2.0 + 0.08, 0.72), (thickness, 0.10, 1.44), MATS["support"], "screen_support_post", "dark_gray")

    ball = add_ball("ramp_orange_ball", ball_radius, ramp_start, MATS["orange"], "orange")
    ball["pb_path"] = "gravity_accelerated_ramp_to_straight_through_real_screen_slot"
    ball["pb_screen_has_real_opening"] = True

    return scene, {
        "ball": ball,
        "ramp_start": ramp_start,
        "ramp_end": ramp_end,
        "straight_end": straight_end,
        "ball_radius": ball_radius,
    }


def animate_ramp_ball_slotted_screen(scene, meta):
    ball = meta["ball"]
    ramp_start = meta["ramp_start"]
    ramp_end = meta["ramp_end"]
    straight_end = meta["straight_end"]
    radius = meta["ball_radius"]

    ramp_vec = ramp_end - ramp_start
    ramp_len = ramp_vec.length
    straight_vec = straight_end - ramp_end
    straight_len = straight_vec.length
    total_len = ramp_len + straight_len

    drop = max(0.0, ramp_start.z - ramp_end.z)
    sin_theta = drop / ramp_len

    # Visual gravity acceleration along ramp.
    # This makes the ramp part obviously non-uniform: s = 0.5*a*t^2.
    g_visual = 3.0
    a_ramp = g_visual * sin_theta
    t_ramp = math.sqrt(2.0 * ramp_len / a_ramp)
    v_exit = a_ramp * t_ramp

    rest_frames = 8

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= rest_frames:
            s = 0.0
            state = "rest_at_top_of_ramp"
        else:
            t = (frame - rest_frames) / FPS

            if t <= t_ramp:
                s = 0.5 * a_ramp * t * t
                state = "accelerating_down_ramp_under_gravity"
            else:
                s = ramp_len + v_exit * (t - t_ramp)
                state = "rolling_on_straight_after_gravity_acceleration"

            s = min(total_len, s)

        if s <= ramp_len:
            u = s / ramp_len
            pos = ramp_start + ramp_vec * u
        else:
            u = (s - ramp_len) / straight_len
            pos = ramp_end + straight_vec * u

        ball.location = pos
        ball.rotation_euler = (0.0, s / radius, 0.0)
        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)

        if s <= ramp_len:
            ball["pb_state"] = state
        elif pos.x < 0.12:
            ball["pb_state"] = "straight_track_before_screen"
        elif pos.x <= 0.58:
            ball["pb_state"] = "passing_through_real_screen_opening"
        else:
            ball["pb_state"] = "straight_track_after_screen"

        ball["pb_gravity_accelerated_ramp_motion"] = True
        ball["pb_path_s"] = float(s)

    scene.frame_set(FRAME_START)


# =============================================================================
# Dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["kind"]

    if kind == "supported_screen_three_balls":
        return build_supported_screen_three_balls()
    if kind == "supported_window_mask_three_objects":
        return build_supported_window_mask_three_objects()
    if kind == "two_supported_screens_close":
        return build_two_supported_screens_close()
    if kind == "ramp_ball_slotted_screen":
        return build_ramp_ball_slotted_screen()

    raise RuntimeError("Unknown kind: " + str(kind))


def animate_scene_by_kind(scene, meta):
    kind = CASE["kind"]

    if kind == "supported_screen_three_balls":
        return animate_supported_screen_three_balls(scene, meta)
    if kind == "supported_window_mask_three_objects":
        return animate_supported_window_mask_three_objects(scene, meta)
    if kind == "two_supported_screens_close":
        return animate_two_supported_screens_close(scene, meta)
    if kind == "ramp_ball_slotted_screen":
        return animate_ramp_ball_slotted_screen(scene, meta)

    raise RuntimeError("Unknown kind: " + str(kind))


def main():
    ensure_dirs()
    clear_scene()

    scene, meta = build_scene_by_kind()
    animate_scene_by_kind(scene, meta)

    task = {
        "item_id": ITEM_ID,
        "visual_regime": "3D_procedural_control",
        "fps": FPS,
        "inputs": {
            "text_prompt": CASE["prompt"],
        },
        "reference_completion_frames_dir": "frames",
        "scene_file": f"{ITEM_ID}_scene.blend",
    }

    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, 60, OPTIONAL_FRAME_PATH)
    render_png(scene, 120, OPTIONAL_FRAME_02B_PATH)
    render_animation(scene)
    write_task_json(task)
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("kind:", CASE["kind"])
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
