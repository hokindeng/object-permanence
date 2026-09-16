# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_TWO_LANE_TRAYS_PASS_BEHIND_SCREEN_0076",
  "kind": "two_lane_trays_objects_inside",
  "prompt": "Two open shallow trays move left to right on two parallel rails. The upper tray clearly contains a red ball, and the lower tray clearly contains a blue cube. Both trays pass behind the same fixed foreground screen and then reappear. The objects must remain in their original trays and lanes."
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
    for block in list(bpy.data.worlds):
        if block.users == 0:
            bpy.data.worlds.remove(block)


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
        obj, name, role,
        "dynamic_object" if is_dynamic else "static_solid",
        "cube", color_name, is_dynamic, solid=solid
    )
    return obj


def add_ball(name, radius, location, material, color_name):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=48, ring_count=24)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(
        obj, name, "target", "dynamic_object", "sphere", color_name, True,
        solid=True, pb_radius=radius
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


def make_root(name, location=(0.0, 0.0, 0.0), role="dynamic_root"):
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=location)
    root = bpy.context.object
    root.name = name
    tag(root, name, role, "dynamic_object", "empty", "gray", True, solid=False)
    return root


def parent_to(obj, parent):
    obj.parent = parent
    return obj


def setup_base(camera_loc, target, ortho_scale, floor_size=(12.0, 8.0), backdrop_x=12.0):
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (floor_size[0], floor_size[1], 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.40, 1.85), (backdrop_x, 0.08, 3.70), MATS["backdrop"], "background", "off_white")

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


def create_open_tray(prefix, root, width=1.30, depth=0.78, floor_thickness=0.06, wall_thickness=0.06, wall_h=0.18):
    floor_top = floor_thickness
    floor = add_cube(f"{prefix}_floor", (0.0, 0.0, floor_thickness / 2), (width, depth, floor_thickness), MATS["tray"], "tray_floor", "gray", is_dynamic=True)
    left = add_cube(f"{prefix}_left_wall", (-width/2 + wall_thickness/2, 0.0, floor_top + wall_h/2), (wall_thickness, depth, wall_h), MATS["tray"], "tray_wall", "gray", is_dynamic=True)
    right = add_cube(f"{prefix}_right_wall", (width/2 - wall_thickness/2, 0.0, floor_top + wall_h/2), (wall_thickness, depth, wall_h), MATS["tray"], "tray_wall", "gray", is_dynamic=True)
    back = add_cube(f"{prefix}_back_wall", (0.0, depth/2 - wall_thickness/2, floor_top + wall_h/2), (width, wall_thickness, wall_h), MATS["tray"], "tray_wall", "gray", is_dynamic=True)
    front_lip = add_cube(f"{prefix}_front_lip", (0.0, -depth/2 + wall_thickness/2, floor_top + 0.045), (width, wall_thickness, 0.09), MATS["tray"], "tray_front_lip", "gray", is_dynamic=True)

    for obj in [floor, left, right, back, front_lip]:
        obj.parent = root

    root["pb_real_open_tray_not_solid_block"] = True
    root["pb_floor_top_z_local"] = float(floor_top)
    return floor_top


def build_slit_mask_three_balls_far():
    scene = setup_base((0.0, -11.0, 4.4), (0.0, 0.0, 0.90), 10.8, floor_size=(16.0, 8.0), backdrop_x=16.0)

    add_ball("red_ball", 0.24, (-1.05, 0.25, 0.24), MATS["red"], "red")
    add_ball("blue_ball", 0.24, (0.0, 0.25, 0.24), MATS["blue"], "blue")
    add_ball("yellow_ball", 0.24, (1.05, 0.25, 0.24), MATS["yellow"], "yellow")

    y = -0.82
    slit = 0.34
    panel_w = 1.35
    x0 = -3.40

    left = add_cube("slit_mask_left_panel", (x0 - slit/2 - panel_w/2, y, 1.00), (panel_w, 0.10, 2.00), MATS["screen"], "foreground_mask_panel", "gray", is_dynamic=True)
    right = add_cube("slit_mask_right_panel", (x0 + slit/2 + panel_w/2, y, 1.00), (panel_w, 0.10, 2.00), MATS["screen"], "foreground_mask_panel", "gray", is_dynamic=True)
    slider = add_cube("slit_mask_slider", (x0, y, 2.16), (2.95, 0.16, 0.10), MATS["support"], "mask_slider", "dark_gray", is_dynamic=True)
    wheel_a = add_cube("slit_mask_wheel_a", (x0 - 1.12, y, 2.30), (0.15, 0.18, 0.15), MATS["support"], "mask_wheel", "dark_gray", is_dynamic=True)
    wheel_b = add_cube("slit_mask_wheel_b", (x0 + 1.12, y, 2.30), (0.15, 0.18, 0.15), MATS["support"], "mask_wheel", "dark_gray", is_dynamic=True)
    add_cube("fixed_slit_mask_rail", (0.0, y, 2.48), (9.6, 0.12, 0.08), MATS["support"], "fixed_mask_support_rail", "dark_gray")

    return scene, {"kind": "slit_mask_three_balls_far", "objs": [left, right, slider, wheel_a, wheel_b], "x0": x0, "x1": 3.40, "y": y}


def build_moving_tray_ball_cube_inside():
    scene = setup_base((7.6, -7.8, 5.1), (0.0, 0.0, 0.70), 7.8)

    root = make_root("moving_tray_root", (0.0, 0.0, 0.0), role="open_tray_root")
    floor_top = create_open_tray("moving_tray", root, width=1.35, depth=0.78)

    ball = add_ball("tray_orange_ball", 0.18, (-0.24, 0.00, floor_top + 0.18), MATS["orange"], "orange")
    cube = add_cube("tray_blue_cube", (0.22, 0.00, floor_top + 0.17), (0.34, 0.34, 0.34), MATS["blue"], "target_cube", "blue", is_dynamic=True)
    parent_to(ball, root)
    parent_to(cube, root)

    root.location = (-2.70, 0.30, 0.09)

    add_cube("fixed_foreground_screen", (0.0, -0.82, 0.84), (1.30, 0.10, 1.68), MATS["screen"], "foreground_occluder", "gray")
    add_cube("screen_support_rail", (0.0, -0.82, 1.80), (1.60, 0.12, 0.08), MATS["support"], "screen_support_rail", "dark_gray")
    add_cylinder_between("tray_left_rail", (-3.30, 0.10, 0.04), (3.30, 0.10, 0.04), 0.04, MATS["support"], "tray_track_rail", "dark_gray")
    add_cylinder_between("tray_right_rail", (-3.30, 0.50, 0.04), (3.30, 0.50, 0.04), 0.04, MATS["support"], "tray_track_rail", "dark_gray")

    return scene, {"kind": "moving_tray_ball_cube_inside", "root": root, "x0": -2.70, "x1": 2.70, "y": 0.30, "z": 0.09}


def build_two_lane_trays_objects_inside():
    scene = setup_base((7.8, -8.0, 5.2), (0.0, 0.20, 0.70), 8.0)
    tray_width = 1.05

    upper = make_root("upper_tray_root", (0.0, 0.0, 0.0), role="open_tray_root")
    upper_top = create_open_tray("upper_tray", upper, width=tray_width, depth=0.58)
    upper_ball = add_ball("upper_red_ball", 0.18, (0.0, 0.0, upper_top + 0.18), MATS["red"], "red")
    parent_to(upper_ball, upper)
    upper.location = (-2.80, 0.72, 0.09)

    lower = make_root("lower_tray_root", (0.0, 0.0, 0.0), role="open_tray_root")
    lower_top = create_open_tray("lower_tray", lower, width=tray_width, depth=0.58)
    lower_cube = add_cube("lower_blue_cube", (0.0, 0.0, lower_top + 0.17), (0.34, 0.34, 0.34), MATS["blue"], "target_cube", "blue", is_dynamic=True)
    parent_to(lower_cube, lower)
    lower.location = (-2.80, -0.05, 0.09)

    add_cube("wide_fixed_foreground_screen", (0.0, -0.65, 0.84), (1.35, 0.10, 1.68), MATS["screen"], "foreground_occluder", "gray")
    add_cube("screen_overhead_support", (0.0, -0.65, 1.80), (1.60, 0.12, 0.08), MATS["support"], "screen_support_rail", "dark_gray")

    for y in [0.72, -0.05]:
        add_cylinder_between(f"lane_{str(y).replace('.', '_')}_left_rail", (-3.30, y - 0.22, 0.04), (3.30, y - 0.22, 0.04), 0.035, MATS["support"], "tray_track_rail", "dark_gray")
        add_cylinder_between(f"lane_{str(y).replace('.', '_')}_right_rail", (-3.30, y + 0.22, 0.04), (3.30, y + 0.22, 0.04), 0.035, MATS["support"], "tray_track_rail", "dark_gray")

    return scene, {"kind": "two_lane_trays_objects_inside", "roots": [upper, lower], "x0": -2.80, "x1": 2.80}


def build_turntable_variant(variant):
    scene = setup_base((6.8, -7.1, 4.9), (0.0, 0.0, 0.72), 7.0)

    root = make_root("turntable_root", (0.0, 0.25, 0.0), role="turntable_root")
    disk = add_cylinder_z("supported_turntable_disk", 1.05, 0.12, (0.0, 0.0, 0.08), MATS["gray"], "turntable", "gray", is_dynamic=True)
    parent_to(disk, root)

    obj_loc = (0.45, -0.35, 0.25)

    if variant == "cube":
        obj = add_cube("blue_cube_on_turntable", obj_loc, (0.34, 0.34, 0.34), MATS["blue"], "target_cube", "blue", is_dynamic=True)
    elif variant == "ball":
        obj = add_ball("orange_ball_on_turntable", 0.18, (obj_loc[0], obj_loc[1], 0.26), MATS["orange"], "orange")
    elif variant == "pyramid":
        obj = add_pyramid("yellow_pyramid_on_turntable", 0.42, (obj_loc[0], obj_loc[1], 0.29), MATS["yellow"], "yellow")
    else:
        raise RuntimeError("Unknown turntable variant")

    parent_to(obj, root)

    add_cube("foreground_partial_screen", (0.0, -0.78, 0.86), (1.20, 0.10, 1.72), MATS["screen"], "foreground_occluder", "gray")
    add_cube("turntable_base_support", (0.0, 0.25, -0.02), (1.80, 1.80, 0.08), MATS["support"], "turntable_support_base", "dark_gray")

    return scene, {"kind": "turntable_rotate_360", "root": root}


def build_front_view_turntable_ball_tall_panel_180():
    scene = setup_base((0.0, -9.5, 3.8), (0.0, 0.0, 0.90), 8.8, floor_size=(14.0, 8.0), backdrop_x=14.0)

    root = make_root("turntable_root_front_view", (0.0, 0.25, 0.0), role="turntable_root")
    disk = add_cylinder_z("supported_turntable_disk", 1.10, 0.12, (0.0, 0.0, 0.08), MATS["gray"], "turntable", "gray", is_dynamic=True)
    parent_to(disk, root)

    ball = add_ball("left_orange_ball", 0.18, (-0.62, 0.00, 0.26), MATS["orange"], "orange")
    panel = add_cube("tall_panel_behind_ball", (-0.62, 0.42, 0.62), (0.32, 0.06, 1.24), MATS["screen"], "tall_panel", "gray", is_dynamic=True)
    parent_to(ball, root)
    parent_to(panel, root)

    add_cube("turntable_base_support", (0.0, 0.25, -0.02), (1.90, 1.90, 0.08), MATS["support"], "turntable_support_base", "dark_gray")
    return scene, {"kind": "turntable_rotate_180", "root": root}


def build_double_sliding_doors_single_ball():
    scene = setup_base((0.0, -8.8, 3.2), (0.0, 0.0, 0.82), 7.4)

    add_ball("center_orange_ball", 0.22, (0.0, 0.25, 0.22), MATS["orange"], "orange")

    y = -0.78
    left = add_cube("left_sliding_door", (-1.05, y, 0.88), (0.70, 0.10, 1.76), MATS["screen"], "sliding_door_panel", "gray", is_dynamic=True)
    right = add_cube("right_sliding_door", (1.05, y, 0.88), (0.70, 0.10, 1.76), MATS["screen"], "sliding_door_panel", "gray", is_dynamic=True)
    add_cube("top_support_rail", (0.0, y, 1.90), (3.10, 0.12, 0.08), MATS["support"], "door_support_rail", "dark_gray")
    add_cube("left_post", (-1.55, y, 0.95), (0.08, 0.12, 1.90), MATS["support"], "door_support_post", "dark_gray")
    add_cube("right_post", (1.55, y, 0.95), (0.08, 0.12, 1.90), MATS["support"], "door_support_post", "dark_gray")

    return scene, {
        "kind": "double_sliding_doors_single_ball",
        "left": left,
        "right": right,
        "left_open_x": -1.05,
        "right_open_x": 1.05,
        "left_closed_x": -0.35,
        "right_closed_x": 0.35,
        "y": y,
    }


def build_scene():
    kind = CASE["kind"]
    if kind == "slit_mask_three_balls_far":
        return build_slit_mask_three_balls_far()
    if kind == "moving_tray_ball_cube_inside":
        return build_moving_tray_ball_cube_inside()
    if kind == "two_lane_trays_objects_inside":
        return build_two_lane_trays_objects_inside()
    if kind == "turntable_single_cube_360":
        return build_turntable_variant("cube")
    if kind == "turntable_single_ball_360":
        return build_turntable_variant("ball")
    if kind == "turntable_single_pyramid_360":
        return build_turntable_variant("pyramid")
    if kind == "front_view_turntable_ball_tall_panel_180":
        return build_front_view_turntable_ball_tall_panel_180()
    if kind == "double_sliding_doors_single_ball":
        return build_double_sliding_doors_single_ball()
    raise RuntimeError("Unknown kind: " + str(kind))


def animate_scene(scene, meta):
    kind = meta["kind"]

    if kind == "slit_mask_three_balls_far":
        left, right, slider, wheel_a, wheel_b = meta["objs"]
        x0 = meta["x0"]
        x1 = meta["x1"]
        y = meta["y"]

        left_off = Vector(left.location) - Vector((x0, y, 1.00))
        right_off = Vector(right.location) - Vector((x0, y, 1.00))
        slider_off = Vector(slider.location) - Vector((x0, y, 1.00))
        wheel_a_off = Vector(wheel_a.location) - Vector((x0, y, 1.00))
        wheel_b_off = Vector(wheel_b.location) - Vector((x0, y, 1.00))

        for frame in range(FRAME_START, FRAME_END + 1):
            scene.frame_set(frame)
            if frame <= 10:
                x = x0
            elif frame <= 110:
                t = (frame - 10) / 100.0
                x = x0 + (x1 - x0) * t
            else:
                x = x1

            base = Vector((x, y, 1.00))
            left.location = base + left_off
            right.location = base + right_off
            slider.location = base + slider_off
            wheel_a.location = base + wheel_a_off
            wheel_b.location = base + wheel_b_off

            for obj in [left, right, slider, wheel_a, wheel_b]:
                obj.keyframe_insert(data_path="location", frame=frame)
                obj["pb_motion"] = "supported_foreground_mask"

    elif kind == "moving_tray_ball_cube_inside":
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
            root.location = (x, meta["y"], meta["z"])
            root.keyframe_insert(data_path="location", frame=frame)
            root["pb_motion"] = "tray_moves_on_rails"

    elif kind == "two_lane_trays_objects_inside":
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
                root["pb_motion"] = "tray_moves_on_rails"

    elif kind == "turntable_rotate_360":
        root = meta["root"]
        for frame in range(FRAME_START, FRAME_END + 1):
            scene.frame_set(frame)
            if frame <= 15:
                a = 0.0
            elif frame <= 105:
                t = (frame - 15) / 90.0
                a = math.radians(360.0) * t
            else:
                a = math.radians(360.0)
            root.rotation_euler = (0.0, 0.0, a)
            root.keyframe_insert(data_path="rotation_euler", frame=frame)
            root["pb_motion"] = "supported_turntable_rotation"

    elif kind == "turntable_rotate_180":
        root = meta["root"]
        for frame in range(FRAME_START, FRAME_END + 1):
            scene.frame_set(frame)
            if frame <= 15:
                a = 0.0
            elif frame <= 105:
                t = (frame - 15) / 90.0
                a = math.radians(180.0) * t
            else:
                a = math.radians(180.0)
            root.rotation_euler = (0.0, 0.0, a)
            root.keyframe_insert(data_path="rotation_euler", frame=frame)
            root["pb_motion"] = "supported_turntable_rotation"

    elif kind == "double_sliding_doors_single_ball":
        left = meta["left"]
        right = meta["right"]

        for frame in range(FRAME_START, FRAME_END + 1):
            scene.frame_set(frame)

            if frame <= 18:
                lx = meta["left_open_x"]
                rx = meta["right_open_x"]
            elif frame <= 45:
                t = (frame - 18) / 27.0
                lx = meta["left_open_x"] + (meta["left_closed_x"] - meta["left_open_x"]) * t
                rx = meta["right_open_x"] + (meta["right_closed_x"] - meta["right_open_x"]) * t
            elif frame <= 82:
                lx = meta["left_closed_x"]
                rx = meta["right_closed_x"]
            elif frame <= 112:
                t = (frame - 82) / 30.0
                lx = meta["left_closed_x"] + (meta["left_open_x"] - meta["left_closed_x"]) * t
                rx = meta["right_closed_x"] + (meta["right_open_x"] - meta["right_closed_x"]) * t
            else:
                lx = meta["left_open_x"]
                rx = meta["right_open_x"]

            left.location = (lx, meta["y"], 0.88)
            right.location = (rx, meta["y"], 0.88)
            left.keyframe_insert(data_path="location", frame=frame)
            right.keyframe_insert(data_path="location", frame=frame)
            left["pb_motion"] = "supported_sliding_door"
            right["pb_motion"] = "supported_sliding_door"

    else:
        raise RuntimeError("Unknown animation kind: " + str(kind))

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
    print("kind:", CASE["kind"])
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
