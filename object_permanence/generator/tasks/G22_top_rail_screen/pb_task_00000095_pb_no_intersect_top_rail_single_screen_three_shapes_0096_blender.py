# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "kind": "top_rail_single_screen",
  "variant": "three_shapes",
  "prompt": "An orange ball, a blue cube, and a yellow pyramid are visible on a tabletop. A single large opaque screen hangs from visible hangers attached to an overhead rail. The screen starts parked on the left without intersecting the support posts, slides to the center foreground to fully hide the three objects, then slides back left. The same three objects must reappear unchanged.",
  "item_id": "PB_NO_INTERSECT_TOP_RAIL_SINGLE_SCREEN_THREE_SHAPES_0096"
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
        scene.eevee.gtao_distance = 3.0
        scene.eevee.gtao_factor = 1.2
    except Exception:
        pass

    if scene.world is None:
        scene.world = bpy.data.worlds.new("clean_world")
    scene.world.color = (1.0, 1.0, 1.0)


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
            bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = roughness
    except Exception:
        pass
    return mat


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), 0.85)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), 0.92)
    MATS["case"] = make_mat("mat_case", (0.70, 0.71, 0.74), 0.74)
    MATS["screen"] = make_mat("mat_screen", (0.46, 0.48, 0.53), 0.88)
    MATS["support"] = make_mat("mat_support", (0.16, 0.18, 0.22), 0.60)
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
    obj["pb_component_first_design"] = True
    for k, v in extras.items():
        obj[k] = v


def add_cube(name, location, dimensions, material, role, color_name, is_dynamic=False, solid=True):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
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
    mid = (p1 + p2) / 2.0
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=diff.length, vertices=32, location=mid)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = diff.to_track_quat("Z", "Y").to_euler()
    obj.data.materials.append(material)
    tag(obj, name, role, "static_solid", "cylinder", color_name, False, solid=True)
    return obj


TARGET_Y = 0.32
OCC_Y = -0.92


def setup_base(ortho=9.0, camera_loc=(0.0, -10.4, 4.0), target=(0.0, 0.0, 0.95)):
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (16.5, 8.5, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.55, 1.95), (16.5, 0.08, 3.90), MATS["backdrop"], "background", "off_white")

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
    cam.data.ortho_scale = ortho
    look_at(cam, target)
    scene.camera = cam
    return scene


def add_targets_three_shapes():
    add_ball("orange_ball", 0.20, (-0.78, TARGET_Y, 0.20), MATS["orange"], "orange")
    add_cube("blue_cube", (0.0, TARGET_Y, 0.21), (0.42, 0.42, 0.42), MATS["blue"], "target_cube", "blue", is_dynamic=True)
    add_pyramid("yellow_pyramid", 0.50, (0.78, TARGET_Y, 0.25), MATS["yellow"], "yellow")


def add_targets_ball_cube():
    add_ball("orange_ball", 0.20, (-0.55, TARGET_Y, 0.20), MATS["orange"], "orange")
    add_cube("blue_cube", (0.55, TARGET_Y, 0.21), (0.42, 0.42, 0.42), MATS["blue"], "target_cube", "blue", is_dynamic=True)


def add_targets_three_balls():
    add_ball("red_ball", 0.20, (-0.70, TARGET_Y, 0.20), MATS["red"], "red")
    add_ball("blue_ball", 0.20, (0.0, TARGET_Y, 0.20), MATS["blue"], "blue")
    add_ball("yellow_ball", 0.20, (0.70, TARGET_Y, 0.20), MATS["yellow"], "yellow")


def mark_group(group, motion):
    for obj in group:
        obj["pb_motion"] = motion
        obj["pb_target_y"] = TARGET_Y
        obj["pb_occluder_y"] = OCC_Y
        obj["pb_foreground_depth_separated_from_targets"] = True
        obj["pb_large_enough_to_fully_hide_targets"] = True
        obj["pb_no_panel_panel_intersection"] = True


def build_top_rail_single_screen():
    scene = setup_base(ortho=9.4)

    y = OCC_Y

    # Fixed frame first. Posts are far outside the moving screen's parked extent.
    left_post_x = -5.15
    right_post_x = 5.15
    add_cube("left_overhead_post", (left_post_x, y, 1.38), (0.12, 0.16, 2.76), MATS["support"], "overhead_post", "dark_gray")
    add_cube("right_overhead_post", (right_post_x, y, 1.38), (0.12, 0.16, 2.76), MATS["support"], "overhead_post", "dark_gray")
    add_cube("top_overhead_beam", (0.0, y, 2.82), (10.42, 0.16, 0.12), MATS["support"], "overhead_beam", "dark_gray")
    add_cube("inner_trolley_rail", (0.0, y, 2.60), (9.70, 0.10, 0.08), MATS["support"], "trolley_rail", "dark_gray")

    # Motion range calculated from panel half width:
    # panel width 2.70, half 1.35. x_open=-3.10 gives extent [-4.45, -1.75],
    # safely inside left post at -5.15 and clear of targets around x [-1, 1].
    x_open = -3.10
    x_closed = 0.0

    add_targets_three_shapes()

    group = [
        add_cube("single_large_screen_panel", (x_open, y, 1.12), (2.70, 0.10, 2.24), MATS["screen"], "single_sliding_screen_panel", "gray", is_dynamic=True),
        add_cube("screen_top_carrier", (x_open, y, 2.36), (2.35, 0.16, 0.12), MATS["support"], "screen_top_carrier", "dark_gray", is_dynamic=True),
        add_cube("left_hanger", (x_open - 0.78, y, 2.20), (0.08, 0.08, 0.34), MATS["support"], "screen_hanger", "dark_gray", is_dynamic=True),
        add_cube("right_hanger", (x_open + 0.78, y, 2.20), (0.08, 0.08, 0.34), MATS["support"], "screen_hanger", "dark_gray", is_dynamic=True),
        add_cube("left_trolley_block", (x_open - 0.78, y, 2.58), (0.24, 0.18, 0.12), MATS["support"], "trolley_block", "dark_gray", is_dynamic=True),
        add_cube("right_trolley_block", (x_open + 0.78, y, 2.58), (0.24, 0.18, 0.12), MATS["support"], "trolley_block", "dark_gray", is_dynamic=True),
    ]

    mark_group(group, "single_panel_slides_on_top_rail")
    return scene, {"kind": "x", "group": group, "x0": x_open, "x1": x_closed}


def build_side_groove_gate():
    scene = setup_base(ortho=8.8)

    y = OCC_Y

    # Fixed frame first.
    left_post_x = -1.92
    right_post_x = 1.92
    add_cube("left_groove_post", (left_post_x, y, 1.55), (0.18, 0.18, 3.10), MATS["support"], "left_groove_post", "dark_gray")
    add_cube("right_groove_post", (right_post_x, y, 1.55), (0.18, 0.18, 3.10), MATS["support"], "right_groove_post", "dark_gray")
    add_cube("top_gate_beam", (0.0, y, 3.16), (4.02, 0.18, 0.14), MATS["support"], "top_gate_beam", "dark_gray")
    add_cube("bottom_gate_beam", (0.0, y, 0.06), (4.02, 0.18, 0.12), MATS["support"], "bottom_gate_beam", "dark_gray")

    # Motion range: panel stays BETWEEN posts.
    z_open = 2.58
    z_closed = 1.02

    add_targets_ball_cube()

    group = [
        add_cube("large_gate_panel", (0.0, y, z_open), (3.02, 0.10, 1.84), MATS["screen"], "single_gate_panel", "gray", is_dynamic=True),
        add_cube("left_gate_slider", (-1.62, y, z_open), (0.18, 0.20, 0.30), MATS["support"], "left_gate_slider", "dark_gray", is_dynamic=True),
        add_cube("right_gate_slider", (1.62, y, z_open), (0.18, 0.20, 0.30), MATS["support"], "right_gate_slider", "dark_gray", is_dynamic=True),
        add_cube("gate_top_connector", (0.0, y, z_open + 0.96), (2.72, 0.08, 0.08), MATS["support"], "gate_connector", "dark_gray", is_dynamic=True),
    ]

    mark_group(group, "single_panel_moves_vertically_inside_side_grooves")
    return scene, {"kind": "z", "group": group, "z0": z_open, "z1": z_closed}


def build_single_rod_curtain():
    scene = setup_base(ortho=9.4)

    y = OCC_Y

    left_post_x = -5.05
    right_post_x = 5.05
    add_cube("left_curtain_post", (left_post_x, y, 1.35), (0.12, 0.16, 2.70), MATS["support"], "curtain_post", "dark_gray")
    add_cube("right_curtain_post", (right_post_x, y, 1.35), (0.12, 0.16, 2.70), MATS["support"], "curtain_post", "dark_gray")
    add_cylinder_between("top_curtain_rod", (left_post_x, y, 2.66), (right_post_x, y, 2.66), 0.045, MATS["support"], "top_curtain_rod", "dark_gray")

    # Panel width 2.70. x_open=-3.05 extent [-4.40,-1.70], not intersecting left post.
    x_open = -3.05
    x_closed = 0.0

    add_targets_three_balls()

    group = [
        add_cube("single_curtain_panel", (x_open, y, 1.12), (2.70, 0.08, 2.24), MATS["screen"], "single_curtain_panel", "gray", is_dynamic=True),
        add_cube("curtain_bottom_weight_bar", (x_open, y, 0.03), (2.78, 0.10, 0.08), MATS["support"], "curtain_weight_bar", "dark_gray", is_dynamic=True),
        add_cube("curtain_ring_1", (x_open - 0.95, y, 2.58), (0.18, 0.12, 0.14), MATS["support"], "curtain_ring", "dark_gray", is_dynamic=True),
        add_cube("curtain_ring_2", (x_open - 0.32, y, 2.58), (0.18, 0.12, 0.14), MATS["support"], "curtain_ring", "dark_gray", is_dynamic=True),
        add_cube("curtain_ring_3", (x_open + 0.32, y, 2.58), (0.18, 0.12, 0.14), MATS["support"], "curtain_ring", "dark_gray", is_dynamic=True),
        add_cube("curtain_ring_4", (x_open + 0.95, y, 2.58), (0.18, 0.12, 0.14), MATS["support"], "curtain_ring", "dark_gray", is_dynamic=True),
    ]

    mark_group(group, "single_curtain_panel_slides_on_rod")
    return scene, {"kind": "x", "group": group, "x0": x_open, "x1": x_closed}


def build_display_box_front_cover():
    scene = setup_base(
        ortho=8.8,
        camera_loc=(6.8, -8.0, 5.0),
        target=(0.0, 0.15, 0.85),
    )

    # Fixed box with real empty interior.
    box_y = TARGET_Y
    add_cube("display_box_floor", (0.0, box_y, 0.06), (2.80, 1.05, 0.12), MATS["case"], "display_box_floor", "gray")
    add_cube("display_box_back", (0.0, box_y + 0.50, 0.70), (2.80, 0.08, 1.28), MATS["case"], "display_box_back", "gray")
    add_cube("display_box_left_side", (-1.36, box_y, 0.70), (0.08, 1.05, 1.28), MATS["case"], "display_box_left_side", "gray")
    add_cube("display_box_right_side", (1.36, box_y, 0.70), (0.08, 1.05, 1.28), MATS["case"], "display_box_right_side", "gray")
    add_cube("display_box_top", (0.0, box_y, 1.38), (2.80, 1.05, 0.12), MATS["case"], "display_box_top", "gray")

    y = OCC_Y
    add_cube("front_upper_rail", (0.0, y, 1.54), (4.10, 0.10, 0.08), MATS["support"], "front_cover_rail", "dark_gray")
    add_cube("front_lower_rail", (0.0, y, 0.12), (4.10, 0.10, 0.08), MATS["support"], "front_cover_rail", "dark_gray")
    add_cube("left_cover_stop", (-2.08, y, 0.83), (0.10, 0.12, 1.50), MATS["support"], "cover_stop", "dark_gray")
    add_cube("right_cover_stop", (2.08, y, 0.83), (0.10, 0.12, 1.50), MATS["support"], "cover_stop", "dark_gray")

    # Targets inside box.
    add_ball("orange_ball_inside_box", 0.18, (-0.42, box_y, 0.30), MATS["orange"], "orange")
    add_cube("blue_cube_inside_box", (0.42, box_y, 0.29), (0.36, 0.36, 0.36), MATS["blue"], "target_cube", "blue", is_dynamic=True)

    # Cover parked to the LEFT beyond the box, with a far left stop.
    x_open = -3.25
    x_closed = 0.0

    add_cube("far_left_cover_stop", (-4.75, y, 0.83), (0.10, 0.12, 1.50), MATS["support"], "cover_stop", "dark_gray")
    add_cube("far_right_cover_stop", (4.75, y, 0.83), (0.10, 0.12, 1.50), MATS["support"], "cover_stop", "dark_gray")
    add_cube("extended_front_upper_rail", (0.0, y, 1.68), (9.60, 0.08, 0.06), MATS["support"], "extended_front_cover_rail", "dark_gray")
    add_cube("extended_front_lower_rail", (0.0, y, 0.02), (9.60, 0.08, 0.06), MATS["support"], "extended_front_cover_rail", "dark_gray")

    group = [
        add_cube("single_front_cover_panel", (x_open, y, 0.83), (2.88, 0.08, 1.42), MATS["screen"], "single_front_cover", "gray", is_dynamic=True),
        add_cube("front_cover_top_slider", (x_open, y, 1.55), (2.60, 0.12, 0.08), MATS["support"], "front_cover_slider", "dark_gray", is_dynamic=True),
        add_cube("front_cover_bottom_slider", (x_open, y, 0.11), (2.60, 0.12, 0.08), MATS["support"], "front_cover_slider", "dark_gray", is_dynamic=True),
    ]

    mark_group(group, "single_front_cover_slides_on_box_front_rails")
    return scene, {"kind": "x", "group": group, "x0": x_open, "x1": x_closed}


def build_bottom_rail_screen():
    scene = setup_base(ortho=9.4)

    y = OCC_Y

    left_post_x = -5.10
    right_post_x = 5.10
    add_cube("left_bottom_rail_post", (left_post_x, y, 0.38), (0.12, 0.16, 0.76), MATS["support"], "bottom_rail_post", "dark_gray")
    add_cube("right_bottom_rail_post", (right_post_x, y, 0.38), (0.12, 0.16, 0.76), MATS["support"], "bottom_rail_post", "dark_gray")
    add_cube("front_bottom_rail", (0.0, y - 0.08, 0.08), (10.10, 0.08, 0.08), MATS["support"], "front_bottom_rail", "dark_gray")
    add_cube("rear_bottom_rail", (0.0, y + 0.08, 0.08), (10.10, 0.08, 0.08), MATS["support"], "rear_bottom_rail", "dark_gray")

    # Panel width 2.70, x_open=3.10 extent [1.75, 4.45], not intersecting right post at 5.10.
    x_open = 3.10
    x_closed = 0.0

    add_targets_three_shapes()

    group = [
        add_cube("single_bottom_rail_screen", (x_open, y, 1.18), (2.70, 0.10, 2.20), MATS["screen"], "single_bottom_rail_screen", "gray", is_dynamic=True),
        add_cube("screen_bottom_carriage", (x_open, y, 0.18), (2.45, 0.28, 0.14), MATS["support"], "screen_bottom_carriage", "dark_gray", is_dynamic=True),
        add_cube("left_wheel_block", (x_open - 0.82, y, 0.06), (0.22, 0.20, 0.10), MATS["support"], "left_wheel_block", "dark_gray", is_dynamic=True),
        add_cube("right_wheel_block", (x_open + 0.82, y, 0.06), (0.22, 0.20, 0.10), MATS["support"], "right_wheel_block", "dark_gray", is_dynamic=True),
    ]

    mark_group(group, "single_screen_slides_on_bottom_double_rail")
    return scene, {"kind": "x", "group": group, "x0": x_open, "x1": x_closed}


def build_scene():
    kind = CASE["kind"]
    if kind == "top_rail_single_screen":
        return build_top_rail_single_screen()
    if kind == "side_groove_gate":
        return build_side_groove_gate()
    if kind == "single_rod_curtain":
        return build_single_rod_curtain()
    if kind == "display_box_front_cover":
        return build_display_box_front_cover()
    if kind == "bottom_rail_screen":
        return build_bottom_rail_screen()
    raise RuntimeError("Unknown kind: " + str(kind))


def animate_x(scene, group, x0, x1):
    loc0 = [Vector(obj.location) for obj in group]
    dx = x1 - x0

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 18:
            t = 0.0
        elif frame <= 48:
            t = (frame - 18) / 30.0
        elif frame <= 82:
            t = 1.0
        elif frame <= 112:
            t = 1.0 - (frame - 82) / 30.0
        else:
            t = 0.0

        for obj, base in zip(group, loc0):
            obj.location = base + Vector((dx * t, 0.0, 0.0))
            obj.keyframe_insert(data_path="location", frame=frame)
            obj["pb_state"] = "open" if t == 0.0 else ("closed" if t == 1.0 else "moving")


def animate_z(scene, group, z0, z1):
    loc0 = [Vector(obj.location) for obj in group]
    dz = z1 - z0

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 18:
            t = 0.0
        elif frame <= 48:
            t = (frame - 18) / 30.0
        elif frame <= 82:
            t = 1.0
        elif frame <= 112:
            t = 1.0 - (frame - 82) / 30.0
        else:
            t = 0.0

        for obj, base in zip(group, loc0):
            obj.location = base + Vector((0.0, 0.0, dz * t))
            obj.keyframe_insert(data_path="location", frame=frame)
            obj["pb_state"] = "open" if t == 0.0 else ("closed" if t == 1.0 else "moving")


def animate_scene(scene, meta):
    if meta["kind"] == "x":
        animate_x(scene, meta["group"], meta["x0"], meta["x1"])
    elif meta["kind"] == "z":
        animate_z(scene, meta["group"], meta["z0"], meta["z1"])
    else:
        raise RuntimeError("Unknown animation kind: " + str(meta["kind"]))
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
