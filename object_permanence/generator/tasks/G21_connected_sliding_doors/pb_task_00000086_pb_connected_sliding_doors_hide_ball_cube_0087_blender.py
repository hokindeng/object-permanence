# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "kind": "connected_sliding_doors",
  "variant": "ball_cube",
  "prompt": "An orange ball is on the left and a blue cube is on the right. Two connected sliding doors close tightly on a top rail frame, hide both objects, and reopen. The ball and cube must reappear in the same positions.",
  "item_id": "PB_CONNECTED_SLIDING_DOORS_HIDE_BALL_CUBE_0087"
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
    except Exception:
        pass

    if scene.world is None:
        scene.world = bpy.data.worlds.new("clean_world")
    scene.world.color = (1.0, 1.0, 1.0)


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def make_mat(name, color, roughness=0.55, alpha=1.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (color[0], color[1], color[2], alpha)
    try:
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], alpha)
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = roughness
            if "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = alpha
        if alpha < 1.0:
            mat.blend_method = "BLEND"
            mat.show_transparent_back = True
    except Exception:
        pass
    return mat


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), 0.85)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), 0.92)
    MATS["gray"] = make_mat("mat_gray", (0.62, 0.63, 0.66), 0.75)
    MATS["dark"] = make_mat("mat_dark", (0.18, 0.20, 0.24), 0.55)
    MATS["screen"] = make_mat("mat_screen", (0.46, 0.48, 0.53), 0.88)
    MATS["support"] = make_mat("mat_support", (0.16, 0.18, 0.22), 0.60)
    MATS["case"] = make_mat("mat_case", (0.70, 0.71, 0.74), 0.74)
    MATS["red"] = make_mat("mat_red", (0.92, 0.18, 0.18), 0.28)
    MATS["blue"] = make_mat("mat_blue", (0.16, 0.36, 0.95), 0.28)
    MATS["yellow"] = make_mat("mat_yellow", (0.98, 0.78, 0.15), 0.28)
    MATS["orange"] = make_mat("mat_orange", (0.97, 0.45, 0.10), 0.28)


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


def add_cube(name, location, dimensions, material, role, color_name, is_dynamic=False, solid=True, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
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
    bpy.ops.mesh.primitive_cone_add(vertices=3, radius1=size * 0.62, radius2=0, depth=size, location=location, rotation=(0, 0, math.radians(-30)))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, "target", "dynamic_object", "triangular_pyramid", color_name, True, solid=True)
    return obj


def add_cylinder_between(name, p1, p2, radius, material, role, color_name):
    p1 = Vector(p1)
    p2 = Vector(p2)
    diff = p2 - p1
    mid = (p1 + p2) / 2
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=diff.length, vertices=32, location=mid)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = diff.to_track_quat("Z", "Y").to_euler()
    obj.data.materials.append(material)
    tag(obj, name, role, "static_solid", "cylinder", color_name, False, solid=True)
    return obj


def make_root(name, loc=(0, 0, 0), role="dynamic_root"):
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=loc)
    root = bpy.context.object
    root.name = name
    tag(root, name, role, "dynamic_object", "empty", "gray", True, solid=False)
    return root


def parent_to(obj, parent):
    obj.parent = parent
    return obj


def setup_base(camera_loc=(0, -9, 3.8), target=(0, 0, 0.9), ortho=8.0):
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0, 0, -0.05), (14, 8, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0, 3.45, 1.85), (14, 0.08, 3.70), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3, -4.5, 5.8))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 950
    key.data.size = 5.5

    bpy.ops.object.light_add(type="POINT", location=(3, 1.8, 3.3))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 120

    bpy.ops.object.camera_add(location=camera_loc)
    cam = bpy.context.object
    cam.name = "camera_main"
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = ortho
    look_at(cam, target)
    scene.camera = cam
    return scene


def add_basic_objects(variant):
    if variant == "single_ball":
        add_ball("center_orange_ball", 0.22, (0, 0.28, 0.22), MATS["orange"], "orange")
    elif variant == "ball_cube":
        add_ball("left_orange_ball", 0.20, (-0.55, 0.28, 0.20), MATS["orange"], "orange")
        add_cube("right_blue_cube", (0.55, 0.28, 0.21), (0.42, 0.42, 0.42), MATS["blue"], "target_cube", "blue", is_dynamic=True)
    elif variant == "three_shapes":
        add_ball("orange_ball", 0.20, (-0.78, 0.28, 0.20), MATS["orange"], "orange")
        add_cube("blue_cube", (0, 0.28, 0.21), (0.42, 0.42, 0.42), MATS["blue"], "target_cube", "blue", is_dynamic=True)
        add_pyramid("yellow_pyramid", 0.50, (0.78, 0.28, 0.25), MATS["yellow"], "yellow")
    elif variant == "two_balls":
        add_ball("left_red_ball", 0.20, (-0.45, 0.28, 0.20), MATS["red"], "red")
        add_ball("right_blue_ball", 0.20, (0.45, 0.28, 0.20), MATS["blue"], "blue")
    elif variant == "three_balls":
        add_ball("red_ball", 0.20, (-0.70, 0.28, 0.20), MATS["red"], "red")
        add_ball("blue_ball", 0.20, (0, 0.28, 0.20), MATS["blue"], "blue")
        add_ball("yellow_ball", 0.20, (0.70, 0.28, 0.20), MATS["yellow"], "yellow")


def build_connected_vertical_panel():
    scene = setup_base(ortho=7.6)
    add_basic_objects(CASE["variant"])

    y = -0.82
    # Solid connected frame: posts physically touch top and bottom bars.
    add_cube("left_guide_post", (-1.70, y, 1.45), (0.12, 0.14, 2.90), MATS["support"], "vertical_guide_post", "dark_gray")
    add_cube("right_guide_post", (1.70, y, 1.45), (0.12, 0.14, 2.90), MATS["support"], "vertical_guide_post", "dark_gray")
    add_cube("top_frame_bar", (0, y, 2.92), (3.52, 0.14, 0.12), MATS["support"], "connected_top_frame", "dark_gray")
    add_cube("bottom_frame_bar", (0, y, 0.08), (3.52, 0.14, 0.12), MATS["support"], "connected_bottom_frame", "dark_gray")

    group = [
        add_cube("sliding_panel", (0, y, 2.55), (2.42, 0.10, 1.48), MATS["screen"], "foreground_vertical_panel", "gray", is_dynamic=True),
        add_cube("left_slider_block", (-1.43, y, 2.55), (0.34, 0.18, 0.22), MATS["support"], "panel_slider_connector", "dark_gray", is_dynamic=True),
        add_cube("right_slider_block", (1.43, y, 2.55), (0.34, 0.18, 0.22), MATS["support"], "panel_slider_connector", "dark_gray", is_dynamic=True),
        add_cube("left_upper_connector", (-1.30, y, 3.05), (0.32, 0.08, 0.08), MATS["support"], "panel_connector", "dark_gray", is_dynamic=True),
        add_cube("right_upper_connector", (1.30, y, 3.05), (0.32, 0.08, 0.08), MATS["support"], "panel_connector", "dark_gray", is_dynamic=True),
    ]
    for obj in group:
        obj["pb_connected_to_side_guides"] = True
        obj["pb_panel_inside_rails_not_through_posts"] = True

    return scene, {"kind": "vertical_group", "group": group, "z_open": 2.55, "z_closed": 0.95, "y": y}


def create_sliding_door_group(prefix, x, y):
    group = [
        add_cube(f"{prefix}_door_panel", (x, y, 0.95), (0.98, 0.10, 1.90), MATS["screen"], "sliding_door_panel", "gray", is_dynamic=True),
        add_cube(f"{prefix}_top_carrier", (x, y, 1.98), (1.08, 0.16, 0.12), MATS["support"], "door_top_carrier", "dark_gray", is_dynamic=True),
        add_cube(f"{prefix}_hanger_a", (x - 0.30, y, 1.86), (0.07, 0.07, 0.18), MATS["support"], "door_hanger", "dark_gray", is_dynamic=True),
        add_cube(f"{prefix}_hanger_b", (x + 0.30, y, 1.86), (0.07, 0.07, 0.18), MATS["support"], "door_hanger", "dark_gray", is_dynamic=True),
        add_cube(f"{prefix}_slider_wheel_a", (x - 0.32, y, 2.10), (0.16, 0.18, 0.16), MATS["support"], "slider_wheel", "dark_gray", is_dynamic=True),
        add_cube(f"{prefix}_slider_wheel_b", (x + 0.32, y, 2.10), (0.16, 0.18, 0.16), MATS["support"], "slider_wheel", "dark_gray", is_dynamic=True),
    ]
    for obj in group:
        obj["pb_has_visible_rail_connection"] = True
    return group


def build_connected_sliding_doors():
    scene = setup_base(ortho=7.8)
    add_basic_objects(CASE["variant"])

    y = -0.82
    # Complete portal frame. Side posts touch the top beam.
    add_cube("left_frame_post", (-2.05, y, 1.05), (0.12, 0.14, 2.10), MATS["support"], "door_frame_post", "dark_gray")
    add_cube("right_frame_post", (2.05, y, 1.05), (0.12, 0.14, 2.10), MATS["support"], "door_frame_post", "dark_gray")
    add_cube("top_frame_beam", (0, y, 2.12), (4.22, 0.14, 0.12), MATS["support"], "connected_top_beam", "dark_gray")
    add_cube("inner_top_rail", (0, y, 1.98), (3.82, 0.10, 0.08), MATS["support"], "inner_sliding_rail", "dark_gray")

    left_group = create_sliding_door_group("left", -1.35, y)
    right_group = create_sliding_door_group("right", 1.35, y)
    return scene, {"kind": "two_door_groups", "left": left_group, "right": right_group, "y": y}


def build_hinged_case():
    scene = setup_base((6.8, -7.2, 4.8), (0, 0.15, 0.70), 7.2)

    # Real shallow cavity.
    add_cube("case_floor", (0, 0.25, 0.05), (2.40, 1.20, 0.10), MATS["case"], "case_floor", "gray")
    add_cube("case_back_wall", (0, 0.83, 0.34), (2.40, 0.08, 0.58), MATS["case"], "case_back_wall", "gray")
    add_cube("case_left_wall", (-1.16, 0.25, 0.34), (0.08, 1.20, 0.58), MATS["case"], "case_side_wall", "gray")
    add_cube("case_right_wall", (1.16, 0.25, 0.34), (0.08, 1.20, 0.58), MATS["case"], "case_side_wall", "gray")
    add_cube("case_front_lip", (0, -0.33, 0.18), (2.40, 0.08, 0.26), MATS["case"], "case_front_lip", "gray")
    add_cylinder_between("rear_hinge_rod", (-1.20, 0.91, 0.67), (1.20, 0.91, 0.67), 0.04, MATS["support"], "hinge_rod", "dark_gray")

    if CASE["variant"] == "three_shapes":
        add_ball("orange_ball_inside_case", 0.17, (-0.55, 0.22, 0.22), MATS["orange"], "orange")
        add_cube("blue_cube_inside_case", (0.05, 0.22, 0.22), (0.34, 0.34, 0.34), MATS["blue"], "target_cube", "blue", is_dynamic=True)
        add_pyramid("yellow_pyramid_inside_case", 0.38, (0.60, 0.22, 0.25), MATS["yellow"], "yellow")
    else:
        add_ball("left_red_ball_inside_case", 0.18, (-0.42, 0.22, 0.23), MATS["red"], "red")
        add_ball("right_blue_ball_inside_case", 0.18, (0.42, 0.22, 0.23), MATS["blue"], "blue")

    lid_root = make_root("hinged_lid_root", (0, 0.91, 0.67), "hinged_lid_root")
    lid = add_cube("opaque_hinged_lid", (0, 0.30, 0.03), (2.44, 1.22, 0.08), MATS["screen"], "hinged_lid", "gray", is_dynamic=True)
    parent_to(lid, lid_root)
    lid["pb_connected_by_rear_hinge"] = True
    return scene, {"kind": "hinge_root", "root": lid_root, "open_angle": math.radians(-72), "closed_angle": 0.0}


def build_side_hinged_cabinet():
    scene = setup_base((0, -8.8, 3.4), (0, 0, 0.85), 7.4)

    add_cube("cabinet_floor", (0, 0.25, 0.08), (2.50, 0.90, 0.16), MATS["case"], "cabinet_floor", "gray")
    add_cube("cabinet_back", (0, 0.68, 0.75), (2.50, 0.08, 1.34), MATS["case"], "cabinet_back", "gray")
    add_cube("cabinet_left_side", (-1.21, 0.25, 0.75), (0.08, 0.90, 1.34), MATS["case"], "cabinet_side", "gray")
    add_cube("cabinet_right_side", (1.21, 0.25, 0.75), (0.08, 0.90, 1.34), MATS["case"], "cabinet_side", "gray")
    add_cube("cabinet_top", (0, 0.25, 1.44), (2.50, 0.90, 0.12), MATS["case"], "cabinet_top", "gray")

    add_basic_objects(CASE["variant"])

    add_cylinder_between("left_vertical_hinge", (-1.28, -0.24, 0.20), (-1.28, -0.24, 1.36), 0.035, MATS["support"], "vertical_hinge", "dark_gray")
    add_cylinder_between("right_vertical_hinge", (1.28, -0.24, 0.20), (1.28, -0.24, 1.36), 0.035, MATS["support"], "vertical_hinge", "dark_gray")

    left_root = make_root("left_door_hinge_root", (-1.28, -0.24, 0.78), "hinged_door_root")
    right_root = make_root("right_door_hinge_root", (1.28, -0.24, 0.78), "hinged_door_root")
    left_door = add_cube("left_hinged_door", (0.55, 0.0, 0.0), (1.10, 0.07, 1.25), MATS["screen"], "hinged_door", "gray", is_dynamic=True)
    right_door = add_cube("right_hinged_door", (-0.55, 0.0, 0.0), (1.10, 0.07, 1.25), MATS["screen"], "hinged_door", "gray", is_dynamic=True)
    parent_to(left_door, left_root)
    parent_to(right_door, right_root)
    return scene, {"kind": "two_hinges", "left": left_root, "right": right_root}


def build_pivot_sign():
    scene = setup_base(ortho=7.6)
    add_basic_objects(CASE["variant"])

    y = -0.82
    add_cylinder_between("side_pivot_post", (-1.65, y, 0.05), (-1.65, y, 2.25), 0.05, MATS["support"], "pivot_post", "dark_gray")
    root = make_root("pivot_sign_root", (-1.65, y, 1.05), "pivot_sign_root")
    sign = add_cube("pivoting_foreground_signboard", (0.80, 0.0, 0.0), (1.60, 0.10, 1.80), MATS["screen"], "pivot_sign", "gray", is_dynamic=True)
    brace = add_cube("sign_to_post_brace", (0.15, 0.0, 0.75), (0.30, 0.08, 0.10), MATS["support"], "sign_brace", "dark_gray", is_dynamic=True)
    parent_to(sign, root)
    parent_to(brace, root)
    return scene, {"kind": "pivot_sign", "root": root}


def build_sliding_sleeve():
    scene = setup_base((7.0, -7.4, 5.0), (0, 0.1, 0.82), 7.4)
    add_basic_objects(CASE["variant"])

    y = -0.20
    x0, x1 = -2.50, 0.00
    group = [
        add_cube("sleeve_top", (x0, y, 1.25), (2.10, 0.95, 0.12), MATS["screen"], "sleeve_top", "gray", is_dynamic=True),
        add_cube("sleeve_front", (x0, -0.45, 0.70), (2.10, 0.10, 1.10), MATS["screen"], "sleeve_front", "gray", is_dynamic=True),
        add_cube("sleeve_left_wall", (x0 - 1.00, y, 0.70), (0.10, 0.95, 1.10), MATS["screen"], "sleeve_side", "gray", is_dynamic=True),
        add_cube("sleeve_right_wall", (x0 + 1.00, y, 0.70), (0.10, 0.95, 1.10), MATS["screen"], "sleeve_side", "gray", is_dynamic=True),
        add_cube("sleeve_slider_left", (x0 - 0.85, -0.78, 1.42), (0.22, 0.12, 0.12), MATS["support"], "sleeve_slider", "dark_gray", is_dynamic=True),
        add_cube("sleeve_slider_right", (x0 + 0.85, -0.78, 1.42), (0.22, 0.12, 0.12), MATS["support"], "sleeve_slider", "dark_gray", is_dynamic=True),
    ]
    add_cube("left_tabletop_rail", (-0.55, -0.78, 1.55), (4.50, 0.08, 0.08), MATS["support"], "sleeve_support_rail", "dark_gray")
    add_cube("right_tabletop_rail", (-0.55, 0.32, 1.55), (4.50, 0.08, 0.08), MATS["support"], "sleeve_support_rail", "dark_gray")
    return scene, {"kind": "x_group_custom", "group": group, "x0": x0, "x1": x1}


def build_rope_curtain():
    scene = setup_base(ortho=7.6)
    add_basic_objects(CASE["variant"])

    y = -0.82
    add_cube("overhead_curtain_bar", (0, y, 2.55), (3.10, 0.12, 0.10), MATS["support"], "curtain_overhead_bar", "dark_gray")
    group = [
        add_cube("rope_left", (-0.90, y, 2.00), (0.04, 0.04, 0.90), MATS["support"], "curtain_rope", "dark_gray", is_dynamic=True),
        add_cube("rope_right", (0.90, y, 2.00), (0.04, 0.04, 0.90), MATS["support"], "curtain_rope", "dark_gray", is_dynamic=True),
        add_cube("curtain_panel", (0, y, 1.15), (2.20, 0.08, 1.55), MATS["screen"], "rope_suspended_curtain", "gray", is_dynamic=True),
        add_cube("curtain_bottom_weight", (0, y, 0.36), (2.30, 0.10, 0.08), MATS["support"], "curtain_weight_bar", "dark_gray", is_dynamic=True),
    ]
    return scene, {"kind": "vertical_group", "group": group, "z_open": 2.00, "z_closed": 1.05, "y": y}


def build_peep_window_box():
    scene = setup_base((6.8, -7.2, 4.8), (0, 0.1, 0.82), 7.2)

    add_cube("display_box_floor", (0, 0.28, 0.06), (2.50, 1.00, 0.12), MATS["case"], "box_floor", "gray")
    add_cube("display_box_back", (0, 0.76, 0.70), (2.50, 0.08, 1.28), MATS["case"], "box_back", "gray")
    add_cube("display_box_left_side", (-1.22, 0.28, 0.70), (0.08, 1.00, 1.28), MATS["case"], "box_side", "gray")
    add_cube("display_box_right_side", (1.22, 0.28, 0.70), (0.08, 1.00, 1.28), MATS["case"], "box_side", "gray")
    add_cube("display_box_top", (0, 0.28, 1.38), (2.50, 1.00, 0.12), MATS["case"], "box_top", "gray")

    add_basic_objects(CASE["variant"])

    x0, x1 = -0.90, 0.90
    y = -0.34
    # Front panel with real rectangular window: four moving pieces around empty center.
    group = [
        add_cube("front_panel_left_piece", (x0 - 0.62, y, 0.75), (0.62, 0.08, 1.30), MATS["screen"], "sliding_front_panel_piece", "gray", is_dynamic=True),
        add_cube("front_panel_right_piece", (x0 + 0.62, y, 0.75), (0.62, 0.08, 1.30), MATS["screen"], "sliding_front_panel_piece", "gray", is_dynamic=True),
        add_cube("front_panel_top_piece", (x0, y, 1.20), (0.62, 0.08, 0.40), MATS["screen"], "sliding_front_panel_piece", "gray", is_dynamic=True),
        add_cube("front_panel_bottom_piece", (x0, y, 0.30), (0.62, 0.08, 0.40), MATS["screen"], "sliding_front_panel_piece", "gray", is_dynamic=True),
        add_cube("front_panel_top_slider", (x0, y, 1.55), (1.40, 0.12, 0.08), MATS["support"], "front_panel_slider", "dark_gray", is_dynamic=True),
    ]
    add_cube("front_panel_upper_rail", (0, y, 1.68), (3.30, 0.10, 0.08), MATS["support"], "front_panel_support_rail", "dark_gray")
    add_cube("front_panel_lower_rail", (0, y, 0.10), (3.30, 0.10, 0.08), MATS["support"], "front_panel_support_rail", "dark_gray")
    return scene, {"kind": "x_group_custom", "group": group, "x0": x0, "x1": x1}


def build_connected_portcullis():
    scene = setup_base(ortho=7.6)
    add_basic_objects(CASE["variant"])

    y = -0.82
    add_cube("left_groove_post", (-1.55, y, 1.45), (0.14, 0.16, 2.90), MATS["support"], "portcullis_groove_post", "dark_gray")
    add_cube("right_groove_post", (1.55, y, 1.45), (0.14, 0.16, 2.90), MATS["support"], "portcullis_groove_post", "dark_gray")
    add_cube("top_gate_beam", (0, y, 2.92), (3.24, 0.16, 0.12), MATS["support"], "portcullis_top_beam", "dark_gray")
    group = [
        add_cube("portcullis_panel", (0, y, 2.45), (2.70, 0.10, 1.60), MATS["screen"], "connected_portcullis_panel", "gray", is_dynamic=True),
        add_cube("left_groove_slider", (-1.42, y, 2.45), (0.20, 0.18, 0.26), MATS["support"], "portcullis_slider", "dark_gray", is_dynamic=True),
        add_cube("right_groove_slider", (1.42, y, 2.45), (0.20, 0.18, 0.26), MATS["support"], "portcullis_slider", "dark_gray", is_dynamic=True),
    ]
    return scene, {"kind": "vertical_group", "group": group, "z_open": 2.45, "z_closed": 0.95, "y": y}


def build_scene():
    kind = CASE["kind"]
    if kind == "connected_vertical_panel":
        return build_connected_vertical_panel()
    if kind == "connected_sliding_doors":
        return build_connected_sliding_doors()
    if kind == "hinged_case":
        return build_hinged_case()
    if kind == "side_hinged_cabinet":
        return build_side_hinged_cabinet()
    if kind == "pivot_sign":
        return build_pivot_sign()
    if kind == "sliding_sleeve":
        return build_sliding_sleeve()
    if kind == "rope_curtain":
        return build_rope_curtain()
    if kind == "peep_window_box":
        return build_peep_window_box()
    if kind == "connected_portcullis":
        return build_connected_portcullis()
    raise RuntimeError("Unknown kind: " + str(kind))


def animate_x_group_custom(scene, group, x0, x1):
    start = [Vector(o.location) for o in group]
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if frame <= 15:
            dx = 0
        elif frame <= 60:
            t = (frame - 15) / 45.0
            dx = (x1 - x0) * t
        elif frame <= 85:
            dx = x1 - x0
        elif frame <= 115:
            t = (frame - 85) / 30.0
            dx = (x1 - x0) * (1.0 - t)
        else:
            dx = 0
        for obj, loc0 in zip(group, start):
            obj.location = loc0 + Vector((dx, 0, 0))
            obj.keyframe_insert(data_path="location", frame=frame)


def animate_scene(scene, meta):
    kind = meta["kind"]

    if kind == "vertical_group":
        group = meta["group"]
        start = [Vector(o.location) for o in group]
        z0 = meta["z_open"]
        z1 = meta["z_closed"]
        dz_close = z1 - z0
        for frame in range(FRAME_START, FRAME_END + 1):
            scene.frame_set(frame)
            if frame <= 20:
                dz = 0
            elif frame <= 45:
                t = (frame - 20) / 25.0
                dz = dz_close * t
            elif frame <= 80:
                dz = dz_close
            elif frame <= 110:
                t = (frame - 80) / 30.0
                dz = dz_close * (1.0 - t)
            else:
                dz = 0
            for obj, loc0 in zip(group, start):
                obj.location = loc0 + Vector((0, 0, dz))
                obj.keyframe_insert(data_path="location", frame=frame)
                obj["pb_motion"] = "connected_vertical_guided_motion"

    elif kind == "two_door_groups":
        left = meta["left"]
        right = meta["right"]
        left_start = [Vector(o.location) for o in left]
        right_start = [Vector(o.location) for o in right]
        for frame in range(FRAME_START, FRAME_END + 1):
            scene.frame_set(frame)
            if frame <= 18:
                t = 0
            elif frame <= 45:
                t = (frame - 18) / 27.0
            elif frame <= 82:
                t = 1
            elif frame <= 112:
                t = 1 - (frame - 82) / 30.0
            else:
                t = 0
            # Closed edges meet/overlap slightly at x=0.
            left_dx = 0.86 * t
            right_dx = -0.86 * t
            for obj, loc0 in zip(left, left_start):
                obj.location = loc0 + Vector((left_dx, 0, 0))
                obj.keyframe_insert(data_path="location", frame=frame)
                obj["pb_motion"] = "connected_sliding_door_on_top_rail"
            for obj, loc0 in zip(right, right_start):
                obj.location = loc0 + Vector((right_dx, 0, 0))
                obj.keyframe_insert(data_path="location", frame=frame)
                obj["pb_motion"] = "connected_sliding_door_on_top_rail"

    elif kind == "hinge_root":
        root = meta["root"]
        for frame in range(FRAME_START, FRAME_END + 1):
            scene.frame_set(frame)
            if frame <= 18:
                a = meta["open_angle"]
            elif frame <= 45:
                t = (frame - 18) / 27.0
                a = meta["open_angle"] + (meta["closed_angle"] - meta["open_angle"]) * t
            elif frame <= 82:
                a = meta["closed_angle"]
            elif frame <= 112:
                t = (frame - 82) / 30.0
                a = meta["closed_angle"] + (meta["open_angle"] - meta["closed_angle"]) * t
            else:
                a = meta["open_angle"]
            root.rotation_euler = (a, 0, 0)
            root.keyframe_insert(data_path="rotation_euler", frame=frame)
            root["pb_motion"] = "hinged_lid_rotation"

    elif kind == "two_hinges":
        left = meta["left"]
        right = meta["right"]
        for frame in range(FRAME_START, FRAME_END + 1):
            scene.frame_set(frame)
            if frame <= 18:
                t = 0
            elif frame <= 45:
                t = (frame - 18) / 27.0
            elif frame <= 82:
                t = 1
            elif frame <= 112:
                t = 1 - (frame - 82) / 30.0
            else:
                t = 0
            left.rotation_euler = (0, 0, math.radians(-92 * (1 - t)))
            right.rotation_euler = (0, 0, math.radians(92 * (1 - t)))
            left.keyframe_insert(data_path="rotation_euler", frame=frame)
            right.keyframe_insert(data_path="rotation_euler", frame=frame)

    elif kind == "pivot_sign":
        root = meta["root"]
        for frame in range(FRAME_START, FRAME_END + 1):
            scene.frame_set(frame)
            if frame <= 18:
                a = math.radians(-78)
            elif frame <= 50:
                t = (frame - 18) / 32.0
                a = math.radians(-78 + 78 * t)
            elif frame <= 82:
                a = 0
            elif frame <= 112:
                t = (frame - 82) / 30.0
                a = math.radians(-78 * t)
            else:
                a = math.radians(-78)
            root.rotation_euler = (0, 0, a)
            root.keyframe_insert(data_path="rotation_euler", frame=frame)

    elif kind == "x_group_custom":
        animate_x_group_custom(scene, meta["group"], meta["x0"], meta["x1"])

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
