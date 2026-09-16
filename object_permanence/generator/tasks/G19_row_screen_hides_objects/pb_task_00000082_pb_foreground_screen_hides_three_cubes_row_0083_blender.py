# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "kind": "row_screen",
  "variant": "three_cubes",
  "prompt": "Three colored cubes are visible in a row. A supported foreground screen slides across in front of them and then moves away. The cubes must reappear with the same colors, count, positions, and identities.",
  "item_id": "PB_FOREGROUND_SCREEN_HIDES_THREE_CUBES_ROW_0083"
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
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "cube", color_name, is_dynamic, solid=solid)
    return obj


def add_ball(name, radius, location, material, color_name):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=48, ring_count=24)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, "target", "dynamic_object", "sphere", color_name, True, solid=True, pb_radius=radius)
    return obj


def add_pyramid(name, size, location, material, color_name):
    bpy.ops.mesh.primitive_cone_add(vertices=3, radius1=size * 0.62, radius2=0.0, depth=size, location=location, rotation=(0.0, 0.0, math.radians(-30)))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, "target", "dynamic_object", "triangular_pyramid", color_name, True, solid=True)
    return obj


def add_cylinder_z(name, radius, depth, location, material, role, color_name, is_dynamic=False):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, vertices=64, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "cylinder", color_name, is_dynamic, solid=True)
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
    obj.data.materials.append(material)
    tag(obj, name, role, "static_solid", "cylinder", color_name, False, solid=True)
    return obj


def make_root(name, role="dynamic_root"):
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0.0, 0.0, 0.0))
    root = bpy.context.object
    root.name = name
    tag(root, name, role, "dynamic_object", "empty", "gray", True, solid=False)
    return root


def parent_to(obj, parent):
    obj.parent = parent
    return obj


def setup_base(camera_loc, target, ortho_scale, floor_size=(14.0, 8.0), backdrop_x=14.0):
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (floor_size[0], floor_size[1], 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.45, 1.85), (backdrop_x, 0.08, 3.70), MATS["backdrop"], "background", "off_white")

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


def add_shape(name, shape, color, x, y=0.25):
    if shape == "ball":
        return add_ball(name, 0.22, (x, y, 0.22), MATS[color], color)
    if shape == "cube":
        return add_cube(name, (x, y, 0.23), (0.46, 0.46, 0.46), MATS[color], "target_cube", color, is_dynamic=True)
    if shape == "pyramid":
        return add_pyramid(name, 0.56, (x, y, 0.28), MATS[color], color)
    raise RuntimeError("Unknown shape: " + shape)


def create_supported_screen_group(prefix, x, y, z=0.98, panel_w=1.35, panel_h=1.96):
    group = [
        add_cube(f"{prefix}_panel", (x, y, z), (panel_w, 0.10, panel_h), MATS["screen"], "foreground_occluder", "gray", is_dynamic=True),
        add_cube(f"{prefix}_top_slider", (x, y, z + panel_h/2 + 0.16), (panel_w + 0.10, 0.16, 0.10), MATS["support"], "screen_slider", "dark_gray", is_dynamic=True),
        add_cube(f"{prefix}_wheel_a", (x - panel_w*0.32, y, z + panel_h/2 + 0.30), (0.15, 0.18, 0.15), MATS["support"], "screen_wheel", "dark_gray", is_dynamic=True),
        add_cube(f"{prefix}_wheel_b", (x + panel_w*0.32, y, z + panel_h/2 + 0.30), (0.15, 0.18, 0.15), MATS["support"], "screen_wheel", "dark_gray", is_dynamic=True),
    ]
    return group


def create_open_tray(prefix, root, width=1.35, depth=0.78):
    floor_thick = 0.06
    wall_t = 0.06
    wall_h = 0.18
    top = floor_thick

    parts = [
        add_cube(f"{prefix}_floor", (0, 0, floor_thick/2), (width, depth, floor_thick), MATS["tray"], "tray_floor", "gray", is_dynamic=True),
        add_cube(f"{prefix}_left_wall", (-width/2 + wall_t/2, 0, top + wall_h/2), (wall_t, depth, wall_h), MATS["tray"], "tray_wall", "gray", is_dynamic=True),
        add_cube(f"{prefix}_right_wall", (width/2 - wall_t/2, 0, top + wall_h/2), (wall_t, depth, wall_h), MATS["tray"], "tray_wall", "gray", is_dynamic=True),
        add_cube(f"{prefix}_back_wall", (0, depth/2 - wall_t/2, top + wall_h/2), (width, wall_t, wall_h), MATS["tray"], "tray_wall", "gray", is_dynamic=True),
        add_cube(f"{prefix}_front_lip", (0, -depth/2 + wall_t/2, top + 0.045), (width, wall_t, 0.09), MATS["tray"], "tray_front_lip", "gray", is_dynamic=True),
    ]
    for p in parts:
        parent_to(p, root)
    root["pb_real_open_tray_not_solid_block"] = True
    return top


def build_row_screen():
    scene = setup_base((0.0, -10.5, 3.9), (0.0, 0.0, 0.92), 9.6, floor_size=(16, 8), backdrop_x=16)

    variant = CASE["variant"]
    if variant == "three_shapes":
        specs = [("orange_ball", "ball", "orange", -1.05), ("blue_cube", "cube", "blue", 0.0), ("yellow_pyramid", "pyramid", "yellow", 1.05)]
    elif variant == "four_balls":
        specs = [("red_ball", "ball", "red", -1.35), ("blue_ball", "ball", "blue", -0.45), ("yellow_ball", "ball", "yellow", 0.45), ("orange_ball", "ball", "orange", 1.35)]
    elif variant == "three_cubes":
        specs = [("red_cube", "cube", "red", -1.05), ("blue_cube", "cube", "blue", 0.0), ("yellow_cube", "cube", "yellow", 1.05)]
    else:
        raise RuntimeError("Unknown row_screen variant")

    for name, shape, color, x in specs:
        add_shape(name, shape, color, x)

    y = -0.82
    x0, x1 = -3.60, 3.60
    group = create_supported_screen_group("moving_screen", x0, y)
    add_cube("fixed_overhead_screen_rail", (0, y, 2.45), (9.2, 0.12, 0.08), MATS["support"], "fixed_screen_support_rail", "dark_gray")
    return scene, {"kind": "x_group", "group": group, "x0": x0, "x1": x1, "y": y, "z": 0.98}


def build_vertical_panel():
    scene = setup_base((0.0, -8.8, 3.4), (0.0, 0.0, 0.92), 7.2)

    if CASE["variant"] == "ball_cube":
        specs = [("orange_ball", "ball", "orange", -0.65), ("blue_cube", "cube", "blue", 0.65)]
    else:
        specs = [("orange_ball", "ball", "orange", -1.0), ("blue_cube", "cube", "blue", 0.0), ("yellow_pyramid", "pyramid", "yellow", 1.0)]

    for name, shape, color, x in specs:
        add_cube(f"{name}_pedestal", (x, 0.25, 0.10), (0.55, 0.50, 0.20), MATS["gray"], "pedestal", "gray")
        obj = add_shape(name, shape, color, x, y=0.25)
        obj.location.z += 0.20

    y = -0.82
    panel = add_cube("vertical_sliding_panel", (0, y, 2.70), (2.80, 0.10, 1.75), MATS["screen"], "foreground_vertical_panel", "gray", is_dynamic=True)
    add_cube("left_vertical_guide_rail", (-1.60, y, 1.55), (0.08, 0.12, 3.10), MATS["support"], "vertical_support_rail", "dark_gray")
    add_cube("right_vertical_guide_rail", (1.60, y, 1.55), (0.08, 0.12, 3.10), MATS["support"], "vertical_support_rail", "dark_gray")
    add_cube("top_crossbar", (0, y, 3.10), (3.40, 0.12, 0.08), MATS["support"], "top_support_crossbar", "dark_gray")
    return scene, {"kind": "vertical_panel", "panel": panel, "y": y, "z_open": 2.70, "z_closed": 0.98}


def build_two_doors():
    scene = setup_base((0.0, -8.8, 3.2), (0.0, 0.0, 0.90), 7.6)

    if CASE["variant"] == "single_ball":
        add_shape("center_orange_ball", "ball", "orange", 0.0)
    else:
        add_shape("left_orange_ball", "ball", "orange", -0.55)
        add_shape("right_blue_cube", "cube", "blue", 0.55)

    y = -0.82
    left_group = create_supported_screen_group("left_door", -1.35, y, panel_w=0.85)
    right_group = create_supported_screen_group("right_door", 1.35, y, panel_w=0.85)
    add_cube("top_door_rail", (0, y, 2.45), (4.2, 0.12, 0.08), MATS["support"], "door_support_rail", "dark_gray")
    add_cube("left_post", (-2.05, y, 1.05), (0.08, 0.12, 2.10), MATS["support"], "door_support_post", "dark_gray")
    add_cube("right_post", (2.05, y, 1.05), (0.08, 0.12, 2.10), MATS["support"], "door_support_post", "dark_gray")
    return scene, {"kind": "two_doors", "left_group": left_group, "right_group": right_group, "y": y}


def add_tray_objects(root, variant):
    top = create_open_tray(root.name.replace("_root", ""), root)
    if variant == "three_shapes":
        objs = [
            add_ball("tray_orange_ball", 0.16, (-0.32, 0, top + 0.16), MATS["orange"], "orange"),
            add_cube("tray_blue_cube", (0.08, 0, top + 0.15), (0.30, 0.30, 0.30), MATS["blue"], "target_cube", "blue", is_dynamic=True),
            add_pyramid("tray_yellow_pyramid", 0.34, (0.40, 0, top + 0.17), MATS["yellow"], "yellow"),
        ]
    else:
        objs = [add_ball("tray_orange_ball", 0.17, (0, 0, top + 0.17), MATS["orange"], "orange")]
    for obj in objs:
        parent_to(obj, root)


def build_moving_tray():
    scene = setup_base((7.8, -8.0, 5.2), (0, 0.05, 0.76), 8.0)

    root = make_root("moving_tray_root", role="open_tray_root")
    add_tray_objects(root, CASE["variant"])
    root.location = (-2.90, 0.35, 0.09)

    add_cube("fixed_foreground_screen", (0, -0.82, 0.88), (1.35, 0.10, 1.76), MATS["screen"], "foreground_occluder", "gray")
    add_cube("screen_support_rail", (0, -0.82, 1.90), (1.65, 0.12, 0.08), MATS["support"], "screen_support_rail", "dark_gray")
    add_cylinder_between("tray_left_rail", (-3.5, 0.12, 0.04), (3.5, 0.12, 0.04), 0.04, MATS["support"], "tray_track_rail", "dark_gray")
    add_cylinder_between("tray_right_rail", (-3.5, 0.58, 0.04), (3.5, 0.58, 0.04), 0.04, MATS["support"], "tray_track_rail", "dark_gray")

    return scene, {"kind": "root_x", "roots": [root], "x0": -2.90, "x1": 2.90}


def build_two_trays():
    scene = setup_base((7.9, -8.1, 5.3), (0, 0.20, 0.76), 8.2)

    if CASE["variant"] == "ball_cube":
        upper_obj = ("upper_red_ball", "ball", "red")
        lower_obj = ("lower_blue_cube", "cube", "blue")
    else:
        upper_obj = ("upper_blue_cube", "cube", "blue")
        lower_obj = ("lower_yellow_pyramid", "pyramid", "yellow")

    roots = []
    lanes = [0.75, -0.05]

    for prefix, lane_y, obj_spec in [("upper_tray", lanes[0], upper_obj), ("lower_tray", lanes[1], lower_obj)]:
        root = make_root(prefix + "_root", role="open_tray_root")
        top = create_open_tray(prefix, root, width=1.10, depth=0.62)
        name, shape, color = obj_spec
        if shape == "ball":
            obj = add_ball(name, 0.17, (0, 0, top + 0.17), MATS[color], color)
        elif shape == "cube":
            obj = add_cube(name, (0, 0, top + 0.16), (0.32, 0.32, 0.32), MATS[color], "target_cube", color, is_dynamic=True)
        else:
            obj = add_pyramid(name, 0.34, (0, 0, top + 0.17), MATS[color], color)
        parent_to(obj, root)
        root.location = (-2.90, lane_y, 0.09)
        roots.append(root)

        add_cylinder_between(f"{prefix}_rail_a", (-3.5, lane_y - 0.22, 0.04), (3.5, lane_y - 0.22, 0.04), 0.035, MATS["support"], "tray_track_rail", "dark_gray")
        add_cylinder_between(f"{prefix}_rail_b", (-3.5, lane_y + 0.22, 0.04), (3.5, lane_y + 0.22, 0.04), 0.035, MATS["support"], "tray_track_rail", "dark_gray")

    add_cube("fixed_foreground_screen", (0, -0.72, 0.88), (1.40, 0.10, 1.76), MATS["screen"], "foreground_occluder", "gray")
    add_cube("screen_support_rail", (0, -0.72, 1.90), (1.70, 0.12, 0.08), MATS["support"], "screen_support_rail", "dark_gray")
    return scene, {"kind": "root_x", "roots": roots, "x0": -2.90, "x1": 2.90}


def build_turntable():
    scene = setup_base((7.0, -7.4, 5.0), (0, 0.15, 0.78), 7.2)

    root = make_root("turntable_root", role="turntable_root")
    disk = add_cylinder_z("supported_turntable_disk", 1.10, 0.12, (0, 0, 0.08), MATS["gray"], "turntable", "gray", is_dynamic=True)
    parent_to(disk, root)

    variant = CASE["variant"]
    if variant == "single_cube_360":
        obj = add_cube("blue_cube_on_turntable", (0.48, -0.34, 0.25), (0.34, 0.34, 0.34), MATS["blue"], "target_cube", "blue", is_dynamic=True)
        angle = 360
    elif variant == "ball_cube_180":
        obj = add_ball("orange_ball_on_turntable", 0.18, (-0.42, 0.32, 0.26), MATS["orange"], "orange")
        obj2 = add_cube("blue_cube_on_turntable", (0.48, -0.34, 0.25), (0.34, 0.34, 0.34), MATS["blue"], "target_cube", "blue", is_dynamic=True)
        parent_to(obj2, root)
        angle = 180
    else:
        obj = add_ball("orange_ball_on_turntable", 0.17, (-0.52, 0.0, 0.25), MATS["orange"], "orange")
        obj2 = add_cube("blue_cube_on_turntable", (0.42, -0.36, 0.25), (0.32, 0.32, 0.32), MATS["blue"], "target_cube", "blue", is_dynamic=True)
        obj3 = add_pyramid("yellow_pyramid_on_turntable", 0.36, (0.36, 0.42, 0.27), MATS["yellow"], "yellow")
        parent_to(obj2, root)
        parent_to(obj3, root)
        angle = 240

    parent_to(obj, root)
    root.location = (0, 0.25, 0)

    add_cube("foreground_partial_screen", (0, -0.82, 0.90), (1.25, 0.10, 1.80), MATS["screen"], "foreground_occluder", "gray")
    add_cube("turntable_base_support", (0, 0.25, -0.02), (2.05, 2.05, 0.08), MATS["support"], "turntable_support_base", "dark_gray")
    return scene, {"kind": "turntable", "root": root, "angle": angle}


def build_lift():
    scene = setup_base((0, -9.0, 3.7), (0, 0, 1.05), 7.0)

    root = make_root("lift_platform_root", role="lift_platform_root")
    platform = add_cube("lift_platform", (0, 0, 0.18), (1.05, 0.70, 0.12), MATS["gray"], "lift_platform", "gray", is_dynamic=True)
    parent_to(platform, root)

    if CASE["variant"] == "ball":
        obj = add_ball("orange_ball_on_lift", 0.20, (0, 0, 0.50), MATS["orange"], "orange")
    else:
        obj = add_cube("blue_cube_on_lift", (0, 0, 0.47), (0.38, 0.38, 0.38), MATS["blue"], "target_cube", "blue", is_dynamic=True)
    parent_to(obj, root)
    root.location = (0, 0.25, 0)

    add_cube("left_lift_rail", (-0.70, 0.25, 1.20), (0.08, 0.10, 2.40), MATS["support"], "lift_vertical_rail", "dark_gray")
    add_cube("right_lift_rail", (0.70, 0.25, 1.20), (0.08, 0.10, 2.40), MATS["support"], "lift_vertical_rail", "dark_gray")

    y = -0.82
    door_group = create_supported_screen_group("lift_door", -2.05, y, z=1.00, panel_w=1.70, panel_h=2.00)
    add_cube("door_top_rail", (0, y, 2.45), (4.6, 0.12, 0.08), MATS["support"], "door_support_rail", "dark_gray")
    return scene, {"kind": "lift", "root": root, "door_group": door_group, "y": y}


def build_transparent_panel():
    scene = setup_base((7.0, -7.5, 5.0), (0, 0, 0.85), 7.2)

    if CASE["variant"] == "two_objects":
        specs = [("orange_ball", "ball", "orange", -0.45), ("blue_cube", "cube", "blue", 0.45)]
    else:
        specs = [("red_ball", "ball", "red", -0.75), ("blue_ball", "ball", "blue", 0), ("yellow_ball", "ball", "yellow", 0.75)]
    for name, shape, color, x in specs:
        add_shape(name, shape, color, x, y=0.38)

    panel = add_cube("transparent_solid_panel", (0, 0.05, 0.82), (2.20, 0.06, 1.64), MATS["transparent"], "transparent_solid_barrier", "transparent_blue", solid=True)
    panel["pb_transparent_but_solid"] = True
    add_cube("transparent_panel_left_post", (-1.16, 0.05, 0.86), (0.08, 0.10, 1.72), MATS["support"], "transparent_panel_support", "dark_gray")
    add_cube("transparent_panel_right_post", (1.16, 0.05, 0.86), (0.08, 0.10, 1.72), MATS["support"], "transparent_panel_support", "dark_gray")

    y = -0.82
    group = create_supported_screen_group("foreground_screen", -2.60, y, z=0.98)
    add_cube("fixed_screen_rail", (0, y, 2.45), (6.4, 0.12, 0.08), MATS["support"], "fixed_screen_rail", "dark_gray")
    return scene, {"kind": "x_group", "group": group, "x0": -2.60, "x1": 2.60, "y": y, "z": 0.98}


def build_tunnel_trays():
    scene = setup_base((8.0, -8.2, 5.3), (0, 0.20, 0.78), 8.3)

    if CASE["variant"] == "two_lanes":
        lane_defs = [("upper", 0.72, "ball", "red"), ("lower", -0.05, "cube", "blue")]
    else:
        lane_defs = [("upper", 0.92, "ball", "red"), ("middle", 0.25, "ball", "blue"), ("lower", -0.42, "ball", "yellow")]

    roots = []
    for prefix, lane_y, shape, color in lane_defs:
        root = make_root(prefix + "_tray_root", role="open_tray_root")
        top = create_open_tray(prefix + "_tray", root, width=1.00, depth=0.55)
        if shape == "ball":
            obj = add_ball(prefix + "_" + color + "_ball", 0.16, (0, 0, top + 0.16), MATS[color], color)
        else:
            obj = add_cube(prefix + "_" + color + "_cube", (0, 0, top + 0.15), (0.30, 0.30, 0.30), MATS[color], "target_cube", color, is_dynamic=True)
        parent_to(obj, root)
        root.location = (-2.95, lane_y, 0.09)
        roots.append(root)

        add_cylinder_between(prefix + "_rail_a", (-3.6, lane_y - 0.20, 0.04), (3.6, lane_y - 0.20, 0.04), 0.035, MATS["support"], "tray_track_rail", "dark_gray")
        add_cylinder_between(prefix + "_rail_b", (-3.6, lane_y + 0.20, 0.04), (3.6, lane_y + 0.20, 0.04), 0.035, MATS["support"], "tray_track_rail", "dark_gray")

    # Open-ended opaque tunnel with roof and side walls, no end caps.
    add_cube("tunnel_roof", (0, 0.25, 1.15), (1.85, 2.10, 0.14), MATS["screen"], "opaque_tunnel_roof", "gray")
    add_cube("tunnel_far_wall", (0, 1.28, 0.66), (1.85, 0.12, 1.05), MATS["screen"], "opaque_tunnel_side_wall", "gray")
    add_cube("tunnel_near_wall", (0, -0.80, 0.66), (1.85, 0.12, 1.05), MATS["screen"], "opaque_tunnel_side_wall", "gray")
    add_cube("tunnel_left_support", (-0.98, 0.25, 0.62), (0.10, 2.10, 1.24), MATS["support"], "tunnel_support_post", "dark_gray")
    add_cube("tunnel_right_support", (0.98, 0.25, 0.62), (0.10, 2.10, 1.24), MATS["support"], "tunnel_support_post", "dark_gray")
    return scene, {"kind": "root_x", "roots": roots, "x0": -2.95, "x1": 2.95}


def build_scene():
    kind = CASE["kind"]
    if kind == "row_screen":
        return build_row_screen()
    if kind == "vertical_panel":
        return build_vertical_panel()
    if kind == "two_doors":
        return build_two_doors()
    if kind == "moving_tray":
        return build_moving_tray()
    if kind == "two_trays":
        return build_two_trays()
    if kind == "turntable":
        return build_turntable()
    if kind == "lift":
        return build_lift()
    if kind == "transparent_panel":
        return build_transparent_panel()
    if kind == "tunnel_trays":
        return build_tunnel_trays()
    raise RuntimeError("Unknown kind: " + kind)


def animate_x_group(scene, group, x0, x1, y, z):
    start = Vector((x0, y, z))
    offsets = [Vector(obj.location) - start for obj in group]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if frame <= 10:
            x = x0
        elif frame <= 110:
            t = (frame - 10) / 100.0
            x = x0 + (x1 - x0) * t
        else:
            x = x1
        anchor = Vector((x, y, z))
        for obj, off in zip(group, offsets):
            obj.location = anchor + off
            obj.keyframe_insert(data_path="location", frame=frame)
            obj["pb_motion"] = "supported_foreground_occluder"
            obj["pb_no_object_intersection"] = True


def animate_scene(scene, meta):
    kind = meta["kind"]

    if kind == "x_group":
        animate_x_group(scene, meta["group"], meta["x0"], meta["x1"], meta["y"], meta["z"])

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
            panel.location = (0, meta["y"], z)
            panel.keyframe_insert(data_path="location", frame=frame)
            panel["pb_motion"] = "vertical_rail_supported_panel"

    elif kind == "two_doors":
        left = meta["left_group"]
        right = meta["right_group"]
        left_start = Vector(left[0].location)
        right_start = Vector(right[0].location)
        left_offsets = [Vector(o.location) - left_start for o in left]
        right_offsets = [Vector(o.location) - right_start for o in right]
        for frame in range(FRAME_START, FRAME_END + 1):
            scene.frame_set(frame)
            if frame <= 18:
                t = 0.0
            elif frame <= 45:
                t = (frame - 18) / 27.0
            elif frame <= 82:
                t = 1.0
            elif frame <= 112:
                t = 1.0 - (frame - 82) / 30.0
            else:
                t = 0.0

            left_anchor = Vector((-1.35 + 0.85 * t, meta["y"], 0.98))
            right_anchor = Vector((1.35 - 0.85 * t, meta["y"], 0.98))
            for obj, off in zip(left, left_offsets):
                obj.location = left_anchor + off
                obj.keyframe_insert(data_path="location", frame=frame)
                obj["pb_motion"] = "supported_sliding_door"
            for obj, off in zip(right, right_offsets):
                obj.location = right_anchor + off
                obj.keyframe_insert(data_path="location", frame=frame)
                obj["pb_motion"] = "supported_sliding_door"

    elif kind == "root_x":
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
                root["pb_motion"] = "tray_or_cart_moves_on_visible_rails"

    elif kind == "turntable":
        root = meta["root"]
        total = math.radians(float(meta["angle"]))
        for frame in range(FRAME_START, FRAME_END + 1):
            scene.frame_set(frame)
            if frame <= 15:
                a = 0.0
            elif frame <= 105:
                t = (frame - 15) / 90.0
                a = total * t
            else:
                a = total
            root.rotation_euler = (0, 0, a)
            root.keyframe_insert(data_path="rotation_euler", frame=frame)
            root["pb_motion"] = "supported_turntable_rotation"

    elif kind == "lift":
        root = meta["root"]
        door_group = meta["door_group"]
        door_start = Vector(door_group[0].location)
        door_offsets = [Vector(o.location) - door_start for o in door_group]

        for frame in range(FRAME_START, FRAME_END + 1):
            scene.frame_set(frame)
            if frame <= 20:
                door_x = -2.05
                z = 0.0
            elif frame <= 45:
                t = (frame - 20) / 25.0
                door_x = -2.05 + 2.05 * t
                z = 0.0
            elif frame <= 85:
                door_x = 0.0
                t = (frame - 45) / 40.0
                z = 1.05 * t
            elif frame <= 112:
                t = (frame - 85) / 27.0
                door_x = 0.0 - 2.05 * t
                z = 1.05
            else:
                door_x = -2.05
                z = 1.05

            root.location = (0, 0.25, z)
            root.keyframe_insert(data_path="location", frame=frame)
            root["pb_motion"] = "lift_platform_moves_on_vertical_rails"

            anchor = Vector((door_x, meta["y"], 0.98))
            for obj, off in zip(door_group, door_offsets):
                obj.location = anchor + off
                obj.keyframe_insert(data_path="location", frame=frame)
                obj["pb_motion"] = "supported_foreground_door"

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
    print("kind:", CASE["kind"], "variant:", CASE["variant"])
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
