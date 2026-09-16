# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "kind": "vertical_panel_two_objects",
  "prompt": "An orange ball and a blue cube are visible on two small pedestals. A solid opaque panel lowers in the foreground along two visible vertical guide rails, hiding both objects without touching them. The panel then rises again. The same ball and cube must still be present in the same places.",
  "item_id": "PB_VERTICAL_RAIL_PANEL_HIDES_TWO_OBJECTS_0073"
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
    for block in list(bpy.data.curves):
        if block.users == 0:
            bpy.data.curves.remove(block)


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

        if alpha < 1.0:
            mat.blend_method = "BLEND"
            mat.use_screen_refraction = True
            mat.show_transparent_back = True
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
    MATS["tray"] = make_mat("mat_tray", (0.72, 0.73, 0.76), roughness=0.70)
    MATS["transparent"] = make_mat("mat_transparent_panel", (0.65, 0.85, 1.0), roughness=0.15, alpha=0.32)

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


def add_cylinder_z(name, radius, depth, location, material, role, color_name, is_dynamic=False):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, vertices=64, location=location)
    obj = bpy.context.object
    obj.name = name
    if material is not None:
        obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "cylinder", color_name, is_dynamic, solid=True)
    return obj


def parent_keep(obj, parent):
    obj.parent = parent
    return obj


def add_open_tray(prefix, x, y, z, width=1.25, depth=0.72, wall_h=0.16):
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(x, y, 0.0))
    root = bpy.context.object
    root.name = f"{prefix}_root"
    tag(root, root.name, "open_tray_root", "dynamic_object", "empty", "gray", True)

    floor_top = z + 0.035

    floor = add_cube(f"{prefix}_floor", (0.0, 0.0, z), (width, depth, 0.07), MATS["tray"], "tray_floor", "gray", is_dynamic=True)
    left = add_cube(f"{prefix}_left_wall", (-width/2 + 0.035, 0.0, floor_top + wall_h/2), (0.07, depth, wall_h), MATS["tray"], "tray_wall", "gray", is_dynamic=True)
    right = add_cube(f"{prefix}_right_wall", (width/2 - 0.035, 0.0, floor_top + wall_h/2), (0.07, depth, wall_h), MATS["tray"], "tray_wall", "gray", is_dynamic=True)
    back = add_cube(f"{prefix}_back_wall", (0.0, depth/2 - 0.035, floor_top + wall_h/2), (width, 0.07, wall_h), MATS["tray"], "tray_wall", "gray", is_dynamic=True)
    front_lip = add_cube(f"{prefix}_front_lip", (0.0, -depth/2 + 0.035, floor_top + 0.045), (width, 0.07, 0.09), MATS["tray"], "tray_front_lip", "gray", is_dynamic=True)

    for obj in [floor, left, right, back, front_lip]:
        obj.parent = root

    root["pb_real_open_tray_not_solid_block"] = True
    root["pb_floor_top_z"] = float(floor_top)
    return root, floor_top



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

def setup_base(camera_loc, target, ortho_scale, floor_size=(12.0, 8.0), backdrop_x=12.0):
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (floor_size[0], floor_size[1], 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.35, 1.80), (backdrop_x, 0.08, 3.60), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.0, -4.5, 5.8))
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


def keyframe_group(group, anchor, offsets, frame):
    for obj, off in zip(group, offsets):
        obj.location = anchor + off
        obj.keyframe_insert(data_path="location", frame=frame)


# =============================================================================
# Builders
# =============================================================================

def build_sliding_panel_three_shapes():
    scene = setup_base((7.8, -8.0, 5.4), (0.0, 0.0, 0.75), 8.2, floor_size=(14, 8), backdrop_x=14)

    add_ball("orange_ball", 0.22, (-0.95, 0.30, 0.22), MATS["orange"], "orange")
    add_cube("blue_cube", (0.0, 0.30, 0.24), (0.46, 0.46, 0.46), MATS["blue"], "target_cube", "blue", is_dynamic=True)
    add_pyramid("yellow_pyramid", 0.56, (0.95, 0.30, 0.28), MATS["yellow"], "yellow")

    y = -0.82
    group = [
        add_cube("foreground_screen_panel", (-3.30, y, 0.98), (1.35, 0.10, 1.96), MATS["screen"], "foreground_occluder", "gray", is_dynamic=True),
        add_cube("screen_top_slider", (-3.30, y, 2.12), (1.45, 0.16, 0.10), MATS["support"], "screen_slider", "dark_gray", is_dynamic=True),
        add_cube("screen_wheel_a", (-3.75, y, 2.26), (0.15, 0.18, 0.15), MATS["support"], "screen_wheel", "dark_gray", is_dynamic=True),
        add_cube("screen_wheel_b", (-2.85, y, 2.26), (0.15, 0.18, 0.15), MATS["support"], "screen_wheel", "dark_gray", is_dynamic=True),
    ]
    add_cube("fixed_overhead_screen_rail", (0.0, y, 2.40), (8.4, 0.12, 0.08), MATS["support"], "fixed_screen_support_rail", "dark_gray")

    return scene, {"kind": "x_group", "group": group, "x0": -3.30, "x1": 3.30, "y": y, "z": 0.98}


def build_vertical_panel_two_objects():
    scene = setup_base((0.0, -8.0, 3.0), (0.0, 0.0, 0.80), 6.2)

    add_cube("left_pedestal", (-0.65, 0.25, 0.10), (0.55, 0.50, 0.20), MATS["gray"], "pedestal", "gray")
    add_cube("right_pedestal", (0.65, 0.25, 0.10), (0.55, 0.50, 0.20), MATS["gray"], "pedestal", "gray")
    add_ball("orange_ball", 0.22, (-0.65, 0.25, 0.42), MATS["orange"], "orange")
    add_cube("blue_cube", (0.65, 0.25, 0.42), (0.44, 0.44, 0.44), MATS["blue"], "target_cube", "blue", is_dynamic=True)

    y = -0.80
    panel_w = 2.10
    panel_h = 1.55
    panel_d = 0.10
    rail_w = 0.08
    rail_d = 0.12
    rail_h = 2.80
    rail_center_z = 1.45
    rail_inner_x = panel_w / 2.0
    rail_center_x = rail_inner_x + rail_w / 2.0
    rail_top_z = rail_center_z + rail_h / 2.0
    crossbar_h = 0.08
    z_open = 2.00
    z_closed = 0.92

    panel = add_cube(
        "vertical_sliding_panel",
        (0.0, y, z_open),
        (panel_w, panel_d, panel_h),
        MATS["screen"],
        "foreground_vertical_panel",
        "gray",
        is_dynamic=True,
    )
    left_rail = add_cube(
        "left_vertical_guide_rail",
        (-rail_center_x, y, rail_center_z),
        (rail_w, rail_d, rail_h),
        MATS["support"],
        "vertical_support_rail",
        "dark_gray",
    )
    right_rail = add_cube(
        "right_vertical_guide_rail",
        (rail_center_x, y, rail_center_z),
        (rail_w, rail_d, rail_h),
        MATS["support"],
        "vertical_support_rail",
        "dark_gray",
    )
    crossbar = add_cube(
        "top_crossbar",
        (0.0, y, rail_top_z + crossbar_h / 2.0),
        (panel_w + 2.0 * rail_w, rail_d, crossbar_h),
        MATS["support"],
        "top_support_crossbar",
        "dark_gray",
    )

    panel["pb_guide_rail_clearance"] = 0.0
    panel["pb_guided_by"] = f"{left_rail.name},{right_rail.name}"
    panel["pb_stays_inside_rail_span"] = True
    crossbar["pb_touches_rail_tops"] = True

    return scene, {
        "kind": "vertical_panel",
        "panel": panel,
        "z_open": z_open,
        "z_closed": z_closed,
        "y": y,
    }


def build_slit_mask_three_balls():
    scene = setup_base((0.0, -9.5, 3.6), (0.0, 0.0, 0.90), 8.7, floor_size=(15, 8), backdrop_x=15)

    add_ball("red_ball", 0.24, (-1.05, 0.25, 0.24), MATS["red"], "red")
    add_ball("blue_ball", 0.24, (0.0, 0.25, 0.24), MATS["blue"], "blue")
    add_ball("yellow_ball", 0.24, (1.05, 0.25, 0.24), MATS["yellow"], "yellow")

    y = -0.82
    slit = 0.34
    panel_w = 1.35
    x0 = -3.20

    group = [
        add_cube("slit_mask_left_panel", (x0 - slit/2 - panel_w/2, y, 1.00), (panel_w, 0.10, 2.00), MATS["screen"], "foreground_mask_panel", "gray", is_dynamic=True),
        add_cube("slit_mask_right_panel", (x0 + slit/2 + panel_w/2, y, 1.00), (panel_w, 0.10, 2.00), MATS["screen"], "foreground_mask_panel", "gray", is_dynamic=True),
        add_cube("slit_mask_slider", (x0, y, 2.16), (2.95, 0.16, 0.10), MATS["support"], "mask_slider", "dark_gray", is_dynamic=True),
        add_cube("slit_mask_wheel_a", (x0 - 1.12, y, 2.30), (0.15, 0.18, 0.15), MATS["support"], "mask_wheel", "dark_gray", is_dynamic=True),
        add_cube("slit_mask_wheel_b", (x0 + 1.12, y, 2.30), (0.15, 0.18, 0.15), MATS["support"], "mask_wheel", "dark_gray", is_dynamic=True),
    ]
    add_cube("fixed_slit_mask_rail", (0.0, y, 2.48), (8.6, 0.12, 0.08), MATS["support"], "fixed_mask_support_rail", "dark_gray")

    return scene, {"kind": "x_group", "group": group, "x0": -3.20, "x1": 3.20, "y": y, "z": 1.00, "slit_width": slit}


def build_moving_tray_behind_screen():
    scene = setup_base((7.4, -7.6, 5.0), (0.0, 0.0, 0.65), 7.4)

    tray, floor_top = add_open_tray("moving_tray", -2.55, 0.30, 0.09, width=1.35, depth=0.78)
    ball = add_ball("tray_orange_ball", 0.18, (-2.78, 0.30, floor_top + 0.18), MATS["orange"], "orange")
    cube = add_cube("tray_blue_cube", (-2.35, 0.30, floor_top + 0.17), (0.34, 0.34, 0.34), MATS["blue"], "target_cube", "blue", is_dynamic=True)
    ball.parent = tray
    cube.parent = tray

    add_cube("fixed_foreground_screen", (0.0, -0.82, 0.78), (1.30, 0.10, 1.56), MATS["screen"], "foreground_occluder", "gray")
    add_cube("screen_support_rail", (0.0, -0.82, 1.70), (1.60, 0.12, 0.08), MATS["support"], "screen_support_rail", "dark_gray")

    add_cylinder_between("tray_left_rail", (-3.20, 0.10, 0.04), (3.20, 0.10, 0.04), 0.04, MATS["support"], "tray_track_rail", "dark_gray")
    add_cylinder_between("tray_right_rail", (-3.20, 0.50, 0.04), (3.20, 0.50, 0.04), 0.04, MATS["support"], "tray_track_rail", "dark_gray")

    return scene, {"kind": "root_x", "root": tray, "x0": -2.55, "x1": 2.55, "y": 0.30}


def build_two_trays_behind_screen():
    scene = setup_base((7.6, -7.8, 5.1), (0.0, 0.15, 0.65), 7.7)

    top_tray, top_z = add_open_tray("upper_tray", -2.65, 0.70, 0.09, width=1.05, depth=0.58)
    low_tray, low_z = add_open_tray("lower_tray", -2.65, -0.05, 0.09, width=1.05, depth=0.58)

    red = add_ball("upper_red_ball", 0.18, (-2.65, 0.70, top_z + 0.18), MATS["red"], "red")
    cube = add_cube("lower_blue_cube", (-2.65, -0.05, low_z + 0.17), (0.34, 0.34, 0.34), MATS["blue"], "target_cube", "blue", is_dynamic=True)
    red.parent = top_tray
    cube.parent = low_tray

    add_cube("wide_fixed_foreground_screen", (0.0, -0.65, 0.78), (1.35, 0.10, 1.56), MATS["screen"], "foreground_occluder", "gray")
    add_cube("screen_overhead_support", (0.0, -0.65, 1.70), (1.60, 0.12, 0.08), MATS["support"], "screen_support_rail", "dark_gray")

    for y in [0.70, -0.05]:
        add_cylinder_between(f"lane_{y}_left_rail", (-3.20, y - 0.22, 0.04), (3.20, y - 0.22, 0.04), 0.035, MATS["support"], "tray_track_rail", "dark_gray")
        add_cylinder_between(f"lane_{y}_right_rail", (-3.20, y + 0.22, 0.04), (3.20, y + 0.22, 0.04), 0.035, MATS["support"], "tray_track_rail", "dark_gray")

    return scene, {"kind": "two_roots_x", "roots": [top_tray, low_tray], "x0": -2.65, "x1": 2.65}


def build_turntable_behind_screen():
    scene = setup_base((6.5, -7.0, 4.9), (0.0, 0.0, 0.65), 6.9)

    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0.0, 0.25, 0.0))
    root = bpy.context.object
    root.name = "turntable_root"
    tag(root, root.name, "turntable_root", "dynamic_object", "empty", "gray", True)

    disk = add_cylinder_z("supported_turntable_disk", 1.05, 0.12, (0.0, 0.0, 0.08), MATS["gray"], "turntable", "gray", is_dynamic=True)
    ball = add_ball("orange_ball_on_turntable", 0.18, (-0.55, 0.0, 0.26), MATS["orange"], "orange")
    cube = add_cube("blue_cube_on_turntable", (0.45, -0.35, 0.25), (0.34, 0.34, 0.34), MATS["blue"], "target_cube", "blue", is_dynamic=True)
    pyr = add_pyramid("yellow_pyramid_on_turntable", 0.42, (0.35, 0.45, 0.29), MATS["yellow"], "yellow")

    for obj in [disk, ball, cube, pyr]:
        obj.parent = root

    add_cube("foreground_partial_screen", (0.0, -0.78, 0.82), (1.20, 0.10, 1.64), MATS["screen"], "foreground_occluder", "gray")
    add_cube("turntable_base_support", (0.0, 0.25, -0.02), (1.80, 1.80, 0.08), MATS["support"], "turntable_support_base", "dark_gray")

    return scene, {"kind": "rotate_root", "root": root, "angle0": 0.0, "angle1": math.radians(120)}


def build_sliding_cover_over_tray():
    scene = setup_base((6.8, -7.0, 4.7), (0.0, 0.0, 0.65), 6.9)

    tray, floor_top = add_open_tray("fixed_open_tray", 0.0, 0.25, 0.09, width=1.45, depth=0.78)
    add_ball("tray_orange_ball", 0.18, (-0.25, 0.25, floor_top + 0.18), MATS["orange"], "orange")
    add_cube("tray_blue_cube", (0.28, 0.25, floor_top + 0.17), (0.34, 0.34, 0.34), MATS["blue"], "target_cube", "blue", is_dynamic=True)

    y = -0.68
    cover = add_cube("supported_sliding_cover", (-1.85, y, 0.70), (1.55, 0.12, 1.20), MATS["screen"], "supported_sliding_cover", "gray", is_dynamic=True)
    slider = add_cube("cover_top_slider", (-1.85, y, 1.38), (1.65, 0.16, 0.10), MATS["support"], "cover_slider", "dark_gray", is_dynamic=True)
    add_cube("cover_fixed_rail", (0.0, y, 1.58), (4.6, 0.12, 0.08), MATS["support"], "fixed_cover_support_rail", "dark_gray")

    return scene, {"kind": "cover_over_tray", "cover": cover, "slider": slider, "x_open": -1.85, "x_closed": 0.0, "y": y}


def build_transparent_panel_plus_occluder():
    scene = setup_base((6.6, -7.0, 4.7), (0.0, 0.0, 0.75), 6.8)

    add_ball("orange_ball_behind_transparent_panel", 0.20, (-0.45, 0.35, 0.20), MATS["orange"], "orange")
    add_cube("blue_cube_behind_transparent_panel", (0.45, 0.35, 0.22), (0.42, 0.42, 0.42), MATS["blue"], "target_cube", "blue", is_dynamic=True)

    panel = add_cube("transparent_solid_panel", (0.0, 0.05, 0.75), (1.80, 0.06, 1.50), MATS["transparent"], "transparent_solid_barrier", "transparent_blue", solid=True)
    panel["pb_transparent_but_solid"] = True
    add_cube("transparent_panel_left_post", (-0.95, 0.05, 0.75), (0.08, 0.10, 1.65), MATS["support"], "transparent_panel_support", "dark_gray")
    add_cube("transparent_panel_right_post", (0.95, 0.05, 0.75), (0.08, 0.10, 1.65), MATS["support"], "transparent_panel_support", "dark_gray")

    y = -0.78
    screen = add_cube("foreground_screen", (-2.35, y, 0.90), (1.20, 0.10, 1.80), MATS["screen"], "foreground_occluder", "gray", is_dynamic=True)
    slider = add_cube("foreground_screen_slider", (-2.35, y, 1.92), (1.30, 0.16, 0.10), MATS["support"], "screen_slider", "dark_gray", is_dynamic=True)
    add_cube("fixed_screen_rail", (0.0, y, 2.12), (5.8, 0.12, 0.08), MATS["support"], "fixed_screen_rail", "dark_gray")

    return scene, {"kind": "x_pair", "items": [screen, slider], "x0": -2.35, "x1": 2.35, "y": y}


def build_lift_platform_behind_door():
    scene = setup_base((0.0, -8.2, 3.4), (0.0, 0.0, 1.0), 6.4)

    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0.0, 0.25, 0.0))
    lift = bpy.context.object
    lift.name = "lift_platform_root"
    tag(lift, lift.name, "lift_platform_root", "dynamic_object", "empty", "gray", True)

    platform = add_cube("lift_platform", (0.0, 0.0, 0.18), (1.05, 0.70, 0.12), MATS["gray"], "lift_platform", "gray", is_dynamic=True)
    ball = add_ball("orange_ball_on_lift", 0.20, (0.0, 0.0, 0.50), MATS["orange"], "orange")
    platform.parent = lift
    ball.parent = lift

    add_cube("left_lift_rail", (-0.70, 0.25, 1.10), (0.08, 0.10, 2.20), MATS["support"], "lift_vertical_rail", "dark_gray")
    add_cube("right_lift_rail", (0.70, 0.25, 1.10), (0.08, 0.10, 2.20), MATS["support"], "lift_vertical_rail", "dark_gray")

    y = -0.78
    door = add_cube("foreground_lift_door", (0.0, y, 0.95), (1.85, 0.10, 1.90), MATS["screen"], "foreground_door", "gray", is_dynamic=True)
    add_cylinder_between("door_top_rail", (-1.2, y, 2.10), (1.2, y, 2.10), 0.04, MATS["support"], "door_support_rail", "dark_gray")

    return scene, {"kind": "lift", "lift": lift, "door": door, "door_x_open": -2.0, "door_x_closed": 0.0, "z0": 0.0, "z1": 1.05, "y": y}


def build_covered_tunnel_carts():
    scene = setup_base((7.4, -7.6, 5.0), (0.0, 0.15, 0.65), 7.6)

    upper, uz = add_open_tray("upper_cart", -2.70, 0.65, 0.09, width=0.95, depth=0.55)
    lower, lz = add_open_tray("lower_cart", -2.70, -0.10, 0.09, width=0.95, depth=0.55)

    red = add_ball("red_ball_on_upper_cart", 0.17, (-2.70, 0.65, uz + 0.17), MATS["red"], "red")
    cube = add_cube("blue_cube_on_lower_cart", (-2.70, -0.10, lz + 0.16), (0.32, 0.32, 0.32), MATS["blue"], "target_cube", "blue", is_dynamic=True)
    red.parent = upper
    cube.parent = lower

    # Opaque tunnel with real empty interior and open ends.
    add_cube("tunnel_roof", (0.0, 0.28, 1.08), (1.65, 1.70, 0.14), MATS["screen"], "opaque_tunnel_roof", "gray")
    add_cube("tunnel_far_wall", (0.0, 1.10, 0.60), (1.65, 0.12, 0.95), MATS["screen"], "opaque_tunnel_side_wall", "gray")
    add_cube("tunnel_near_wall", (0.0, -0.55, 0.60), (1.65, 0.12, 0.95), MATS["screen"], "opaque_tunnel_side_wall", "gray")
    add_cube("tunnel_support_left", (-0.90, 0.28, 0.55), (0.10, 1.70, 1.10), MATS["support"], "tunnel_support_post", "dark_gray")
    add_cube("tunnel_support_right", (0.90, 0.28, 0.55), (0.10, 1.70, 1.10), MATS["support"], "tunnel_support_post", "dark_gray")

    for y in [0.65, -0.10]:
        add_cylinder_between(f"cart_lane_{y}_rail_a", (-3.2, y-0.20, 0.04), (3.2, y-0.20, 0.04), 0.035, MATS["support"], "cart_track_rail", "dark_gray")
        add_cylinder_between(f"cart_lane_{y}_rail_b", (-3.2, y+0.20, 0.04), (3.2, y+0.20, 0.04), 0.035, MATS["support"], "cart_track_rail", "dark_gray")

    return scene, {"kind": "two_roots_x", "roots": [upper, lower], "x0": -2.70, "x1": 2.70}


# =============================================================================
# Animation
# =============================================================================

def animate_scene(scene, meta):
    kind = meta["kind"]

    if kind == "x_group":
        group = meta["group"]
        start_anchor = Vector((meta["x0"], meta["y"], meta["z"]))
        offsets = [Vector(obj.location) - start_anchor for obj in group]

        for frame in range(FRAME_START, FRAME_END + 1):
            scene.frame_set(frame)
            if frame <= 10:
                x = meta["x0"]
            elif frame <= 110:
                t = (frame - 10) / 100.0
                x = meta["x0"] + (meta["x1"] - meta["x0"]) * t
            else:
                x = meta["x1"]

            keyframe_group(group, Vector((x, meta["y"], meta["z"])), offsets, frame)

            for obj in group:
                obj["pb_motion"] = "supported_foreground_occluder"
                obj["pb_no_object_intersection"] = True

    elif kind == "vertical_panel":
        panel = meta["panel"]
        for frame in range(FRAME_START, FRAME_END + 1):
            scene.frame_set(frame)
            if frame <= 20:
                z = meta["z_open"]
            elif frame <= 45:
                t = (frame - 20) / 25.0
                z = meta["z_open"] + (meta["z_closed"] - meta["z_open"]) * t
            elif frame <= 80:
                z = meta["z_closed"]
            elif frame <= 110:
                t = (frame - 80) / 30.0
                z = meta["z_closed"] + (meta["z_open"] - meta["z_closed"]) * t
            else:
                z = meta["z_open"]

            panel.location = (0.0, meta["y"], z)
            panel.keyframe_insert(data_path="location", frame=frame)
            panel["pb_motion"] = "vertical_rail_supported_panel"

    elif kind == "root_x":
        root = meta["root"]
        for frame in range(FRAME_START, FRAME_END + 1):
            scene.frame_set(frame)
            if frame <= 12:
                x = meta["x0"]
            elif frame <= 108:
                t = (frame - 12) / 96.0
                x = meta["x0"] + (meta["x1"] - meta["x0"]) * t
            else:
                x = meta["x1"]
            root.location = (x, meta["y"], 0.0)
            root.keyframe_insert(data_path="location", frame=frame)
            root["pb_motion"] = "tray_moves_on_rails"

    elif kind == "two_roots_x":
        for frame in range(FRAME_START, FRAME_END + 1):
            scene.frame_set(frame)
            if frame <= 12:
                x = meta["x0"]
            elif frame <= 108:
                t = (frame - 12) / 96.0
                x = meta["x0"] + (meta["x1"] - meta["x0"]) * t
            else:
                x = meta["x1"]

            for root in meta["roots"]:
                root.location.x = x
                root.keyframe_insert(data_path="location", frame=frame)
                root["pb_motion"] = "cart_or_tray_moves_on_rails"

    elif kind == "rotate_root":
        root = meta["root"]
        for frame in range(FRAME_START, FRAME_END + 1):
            scene.frame_set(frame)
            if frame <= 15:
                a = meta["angle0"]
            elif frame <= 105:
                t = (frame - 15) / 90.0
                a = meta["angle0"] + (meta["angle1"] - meta["angle0"]) * t
            else:
                a = meta["angle1"]

            root.rotation_euler = (0.0, 0.0, a)
            root.keyframe_insert(data_path="rotation_euler", frame=frame)
            root["pb_motion"] = "supported_turntable_rotation"

    elif kind == "cover_over_tray":
        cover = meta["cover"]
        slider = meta["slider"]
        for frame in range(FRAME_START, FRAME_END + 1):
            scene.frame_set(frame)

            if frame <= 18:
                x = meta["x_open"]
            elif frame <= 45:
                t = (frame - 18) / 27.0
                x = meta["x_open"] + (meta["x_closed"] - meta["x_open"]) * t
            elif frame <= 82:
                x = meta["x_closed"]
            elif frame <= 112:
                t = (frame - 82) / 30.0
                x = meta["x_closed"] + (meta["x_open"] - meta["x_closed"]) * t
            else:
                x = meta["x_open"]

            cover.location = (x, meta["y"], 0.70)
            slider.location = (x, meta["y"], 1.38)
            cover.keyframe_insert(data_path="location", frame=frame)
            slider.keyframe_insert(data_path="location", frame=frame)
            cover["pb_motion"] = "supported_cover_slides_over_tray"
            cover["pb_no_solid_tray_intersection"] = True

    elif kind == "x_pair":
        items = meta["items"]
        x0 = meta["x0"]
        x1 = meta["x1"]
        start = [Vector(obj.location) for obj in items]

        for frame in range(FRAME_START, FRAME_END + 1):
            scene.frame_set(frame)
            if frame <= 12:
                x = x0
            elif frame <= 108:
                t = (frame - 12) / 96.0
                x = x0 + (x1 - x0) * t
            else:
                x = x1

            dx = x - x0
            for obj, loc0 in zip(items, start):
                obj.location = loc0 + Vector((dx, 0.0, 0.0))
                obj.keyframe_insert(data_path="location", frame=frame)
                obj["pb_motion"] = "foreground_screen_on_rail"

    elif kind == "lift":
        lift = meta["lift"]
        door = meta["door"]

        for frame in range(FRAME_START, FRAME_END + 1):
            scene.frame_set(frame)

            if frame <= 20:
                door_x = meta["door_x_open"]
                lift_z = meta["z0"]
            elif frame <= 45:
                t = (frame - 20) / 25.0
                door_x = meta["door_x_open"] + (meta["door_x_closed"] - meta["door_x_open"]) * t
                lift_z = meta["z0"]
            elif frame <= 85:
                door_x = meta["door_x_closed"]
                t = (frame - 45) / 40.0
                lift_z = meta["z0"] + (meta["z1"] - meta["z0"]) * t
            elif frame <= 112:
                t = (frame - 85) / 27.0
                door_x = meta["door_x_closed"] + (meta["door_x_open"] - meta["door_x_closed"]) * t
                lift_z = meta["z1"]
            else:
                door_x = meta["door_x_open"]
                lift_z = meta["z1"]

            door.location = (door_x, meta["y"], 0.95)
            lift.location = (0.0, 0.25, lift_z)

            door.keyframe_insert(data_path="location", frame=frame)
            lift.keyframe_insert(data_path="location", frame=frame)
            door["pb_motion"] = "supported_foreground_door"
            lift["pb_motion"] = "lift_platform_moves_on_vertical_rails"

    else:
        raise RuntimeError("Unknown animation kind: " + str(kind))

    scene.frame_set(FRAME_START)


def build_scene():
    kind = CASE["kind"]
    if kind == "sliding_panel_three_shapes":
        return build_sliding_panel_three_shapes()
    if kind == "vertical_panel_two_objects":
        return build_vertical_panel_two_objects()
    if kind == "slit_mask_three_balls":
        return build_slit_mask_three_balls()
    if kind == "moving_tray_behind_screen":
        return build_moving_tray_behind_screen()
    if kind == "two_trays_behind_screen":
        return build_two_trays_behind_screen()
    if kind == "turntable_behind_screen":
        return build_turntable_behind_screen()
    if kind == "sliding_cover_over_tray":
        return build_sliding_cover_over_tray()
    if kind == "transparent_panel_plus_occluder":
        return build_transparent_panel_plus_occluder()
    if kind == "lift_platform_behind_door":
        return build_lift_platform_behind_door()
    if kind == "covered_tunnel_carts":
        return build_covered_tunnel_carts()

    raise RuntimeError("Unknown kind: " + str(kind))


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


def main():
    ensure_dirs()
    clear_scene()

    scene, meta = build_scene()
    animate_scene(scene, meta)

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
