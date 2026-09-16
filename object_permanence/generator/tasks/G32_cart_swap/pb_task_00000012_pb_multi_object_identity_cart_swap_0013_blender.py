# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

ITEM_ID = "PB_MULTI_OBJECT_IDENTITY_CART_SWAP_0013"

FPS = 24
FRAME_START = 1
FRAME_END = 120

# Timing
DOOR_CLOSE_START = 20
DOOR_CLOSE_END = 38

CART_SWAP_START = 42
CART_SWAP_END = 88

DOOR_OPEN_START = 92
DOOR_OPEN_END = 112

# Cart start/end positions
CART_A_START_X = -1.75
CART_A_FINAL_X = 1.75
CART_A_Y = -0.42

CART_B_START_X = 1.75
CART_B_FINAL_X = -1.75
CART_B_Y = 0.42

# Cart geometry
CART_LEN_X = 1.28
CART_WIDTH_Y = 0.92
CART_WALL_H = 0.72
WALL_T = 0.085
FLOOR_T = 0.10
ROOF_T = 0.085
FLOOR_WIDTH_Y = CART_WIDTH_Y - 2.0 * WALL_T

# Wheels support the cart floor directly: wheel top == floor bottom.
WHEEL_RADIUS = 0.12
WHEEL_THICKNESS = 0.085
WHEEL_Z = 0.15
WHEEL_Y_OFFSET = FLOOR_WIDTH_Y / 2.0

FLOOR_BOTTOM_Z = WHEEL_Z + WHEEL_RADIUS
FLOOR_TOP_Z = FLOOR_BOTTOM_Z + FLOOR_T
FLOOR_CENTER_Z = FLOOR_TOP_Z - FLOOR_T / 2.0
WALL_CENTER_Z = FLOOR_TOP_Z + CART_WALL_H / 2.0
WALL_TOP_Z = FLOOR_TOP_Z + CART_WALL_H
ROOF_CENTER_Z = WALL_TOP_Z + ROOF_T / 2.0 + 0.010

FRONT_Y = -CART_WIDTH_Y / 2.0
BACK_Y = CART_WIDTH_Y / 2.0

# Sliding front doors
DOOR_W = 0.78
DOOR_H = 0.58
DOOR_T = 0.065
DOOR_OPEN_X = -0.76
DOOR_CLOSED_X = 0.0
DOOR_Y = FRONT_Y - DOOR_T / 2.0 - 0.018
DOOR_BOTTOM_Z = FLOOR_TOP_Z + 0.08
DOOR_CENTER_Z = DOOR_BOTTOM_Z + DOOR_H / 2.0

# Balls
BALL_RADIUS = 0.18
BALL_REL_X = 0.02
BALL_REL_Y = -0.10
BALL_REL_Z = FLOOR_TOP_Z + BALL_RADIUS + 0.022

INPUT_FRAME_1 = 1
OPTIONAL_HIDDEN_SWAP_FRAME = 65
OPTIONAL_AFTER_OPEN_FRAME = 116

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

OUT_DIR = os.path.join(PROJECT_ROOT, "permanence_blender_outputs", ITEM_ID)
FRAMES_DIR = os.path.join(OUT_DIR, f"{ITEM_ID}_reference_frames")
SCENE_FILE = os.path.join(OUT_DIR, f"{ITEM_ID}_scene.blend")
TASK_JSON_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_task.json")

INPUT_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_input_frame_01.png")
OPTIONAL_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_hidden_swap_frame_02.png")
OPTIONAL_FRAME_02B_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_after_open_frame_02B.png")


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


def swap_progress(frame):
    if frame <= CART_SWAP_START:
        return 0.0
    if frame >= CART_SWAP_END:
        return 1.0
    return smooth01((frame - CART_SWAP_START) / max(1, CART_SWAP_END - CART_SWAP_START))


def cart_a_origin(frame):
    t = swap_progress(frame)
    return Vector((lerp(CART_A_START_X, CART_A_FINAL_X, t), CART_A_Y, 0.0))


def cart_b_origin(frame):
    t = swap_progress(frame)
    return Vector((lerp(CART_B_START_X, CART_B_FINAL_X, t), CART_B_Y, 0.0))


def door_rel_x(frame):
    if frame <= DOOR_CLOSE_START:
        return DOOR_OPEN_X

    if frame <= DOOR_CLOSE_END:
        t = (frame - DOOR_CLOSE_START) / max(1, DOOR_CLOSE_END - DOOR_CLOSE_START)
        return lerp(DOOR_OPEN_X, DOOR_CLOSED_X, smooth01(t))

    if frame <= DOOR_OPEN_START:
        return DOOR_CLOSED_X

    if frame <= DOOR_OPEN_END:
        t = (frame - DOOR_OPEN_START) / max(1, DOOR_OPEN_END - DOOR_OPEN_START)
        return lerp(DOOR_CLOSED_X, DOOR_OPEN_X, smooth01(t))

    return DOOR_OPEN_X


def make_mat(name, color, roughness=0.55, metallic=0.0, alpha=1.0, blend=None):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (color[0], color[1], color[2], alpha)

    try:
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            if "Base Color" in bsdf.inputs:
                bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], alpha)
            if "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = alpha
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = roughness
            if "Metallic" in bsdf.inputs:
                bsdf.inputs["Metallic"].default_value = metallic
    except Exception:
        pass

    if blend is None:
        blend = "BLEND" if alpha < 1.0 else "OPAQUE"

    try:
        mat.blend_method = blend
        mat.show_transparent_back = True
        mat.alpha_threshold = 0.01
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


def add_cube(name, location, dimensions, material=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    if material is not None:
        obj.data.materials.append(material)

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
    except Exception:
        pass

    try:
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


def set_object_from_rel(obj, origin, rel_xyz):
    obj.location = origin + Vector(rel_xyz)


def make_cart_part(name, origin, rel_loc, dims, mat, role, cart_id, color_name="gray", solid=True, **extras):
    obj = add_cube(
        name=name,
        location=origin + Vector(rel_loc),
        dimensions=dims,
        material=mat,
    )
    tag(
        obj,
        name,
        role,
        "dynamic_cart_part",
        "cube",
        color_name,
        True,
        solid=solid,
        pb_cart_id=cart_id,
        **extras,
    )
    obj["pb_rel_x"] = float(rel_loc[0])
    obj["pb_rel_y"] = float(rel_loc[1])
    obj["pb_rel_z"] = float(rel_loc[2])
    return obj


def make_wheel(name, origin, rel_loc, mat, cart_id):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=40,
        radius=WHEEL_RADIUS,
        depth=WHEEL_THICKNESS,
        location=origin + Vector(rel_loc),
        rotation=(math.pi / 2.0, 0.0, 0.0),
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    tag(
        obj,
        name,
        "cart_wheel",
        "dynamic_cart_part",
        "cylinder",
        "dark_gray",
        True,
        solid=True,
        pb_cart_id=cart_id,
    )
    obj["pb_rel_x"] = float(rel_loc[0])
    obj["pb_rel_y"] = float(rel_loc[1])
    obj["pb_rel_z"] = float(rel_loc[2])
    return obj


def build_cart(cart_id, name_prefix, origin, mat_cart, mat_edge, mat_door, mat_wheel):
    parts = []

    # Floor
    bottom = make_cart_part(
        f"{name_prefix}_bottom_floor",
        origin,
        (0.0, 0.0, FLOOR_CENTER_Z),
        # Edge-decoupled: nest floor inside the four walls (shrink both cross dims
        # by 2*WALL_T) so its outer faces no longer coincide with side/back walls.
        (CART_LEN_X - 2.0 * WALL_T, FLOOR_WIDTH_Y, FLOOR_T),
        mat_cart,
        role="cart_floor",
        cart_id=cart_id,
    )
    bottom["pb_supported_by_wheels"] = True
    parts.append(bottom)

    # Back wall
    back_wall = make_cart_part(
        f"{name_prefix}_back_wall",
        origin,
        (0.0, BACK_Y - WALL_T / 2.0, WALL_CENTER_Z),
        (CART_LEN_X, WALL_T, CART_WALL_H),
        mat_cart,
        role="cart_wall",
        cart_id=cart_id,
    )
    parts.append(back_wall)

    # Left/right walls
    left_wall = make_cart_part(
        f"{name_prefix}_left_side_wall",
        origin,
        (-CART_LEN_X / 2.0 + WALL_T / 2.0, 0.0, WALL_CENTER_Z),
        # Edge-decoupled: inset in depth (Y) so it retreats behind the back wall
        # and the front door-frame plane -> no coincident outer Y faces.
        (WALL_T, CART_WIDTH_Y - 2.0 * WALL_T, CART_WALL_H),
        mat_cart,
        role="cart_wall",
        cart_id=cart_id,
    )
    parts.append(left_wall)

    right_wall = make_cart_part(
        f"{name_prefix}_right_side_wall",
        origin,
        (CART_LEN_X / 2.0 - WALL_T / 2.0, 0.0, WALL_CENTER_Z),
        # Edge-decoupled: inset in depth (Y), mirror of the left wall.
        (WALL_T, CART_WIDTH_Y - 2.0 * WALL_T, CART_WALL_H),
        mat_cart,
        role="cart_wall",
        cart_id=cart_id,
    )
    parts.append(right_wall)

    # Roof
    roof = make_cart_part(
        f"{name_prefix}_roof",
        origin,
        (0.0, 0.0, ROOF_CENTER_Z),
        # Edge-decoupled: nest roof inside the four walls (shrink both cross dims
        # by 2*WALL_T). Footprint still fully covers the ball from above.
        (CART_LEN_X - 2.0 * WALL_T, CART_WIDTH_Y - 2.0 * WALL_T, ROOF_T),
        mat_cart,
        role="cart_roof",
        cart_id=cart_id,
        pb_occludes=True,
    )
    parts.append(roof)

    # Front door frame
    side_post_w = (CART_LEN_X - DOOR_W) / 2.0
    left_post_x = -DOOR_W / 2.0 - side_post_w / 2.0
    right_post_x = DOOR_W / 2.0 + side_post_w / 2.0

    parts.append(make_cart_part(
        f"{name_prefix}_front_left_door_frame",
        origin,
        (left_post_x, FRONT_Y + WALL_T / 2.0, WALL_CENTER_Z),
        (side_post_w, WALL_T, CART_WALL_H),
        mat_cart,
        role="cart_front_door_frame",
        cart_id=cart_id,
        pb_front_opening_frame=True,
    ))

    parts.append(make_cart_part(
        f"{name_prefix}_front_right_door_frame",
        origin,
        (right_post_x, FRONT_Y + WALL_T / 2.0, WALL_CENTER_Z),
        (side_post_w, WALL_T, CART_WALL_H),
        mat_cart,
        role="cart_front_door_frame",
        cart_id=cart_id,
        pb_front_opening_frame=True,
    ))

    sill_h = max(0.04, DOOR_BOTTOM_Z - FLOOR_TOP_Z)
    parts.append(make_cart_part(
        f"{name_prefix}_front_bottom_sill",
        origin,
        (0.0, FRONT_Y + WALL_T / 2.0, FLOOR_TOP_Z + sill_h / 2.0),
        (DOOR_W, WALL_T, sill_h),
        mat_edge,
        role="cart_front_door_sill",
        cart_id=cart_id,
        color_name="medium_gray",
        pb_front_opening_frame=True,
    ))

    top_bar_h = max(0.06, WALL_TOP_Z - (DOOR_BOTTOM_Z + DOOR_H))
    parts.append(make_cart_part(
        f"{name_prefix}_front_top_bar",
        origin,
        (0.0, FRONT_Y + WALL_T / 2.0, WALL_TOP_Z - top_bar_h / 2.0),
        (DOOR_W, WALL_T, top_bar_h),
        mat_edge,
        role="cart_front_door_top_bar",
        cart_id=cart_id,
        color_name="medium_gray",
        pb_front_opening_frame=True,
    ))

    # Sliding door
    door = make_cart_part(
        f"{name_prefix}_sliding_front_door",
        origin,
        (DOOR_OPEN_X, DOOR_Y, DOOR_CENTER_Z),
        (DOOR_W, DOOR_T, DOOR_H),
        mat_door,
        role="sliding_cart_door",
        cart_id=cart_id,
        color_name="dark_gray",
        pb_door_can_hide_ball=True,
    )

    # Wheels
    wheel_positions = [
        (-0.43, -WHEEL_Y_OFFSET, WHEEL_Z),
        (0.43, -WHEEL_Y_OFFSET, WHEEL_Z),
        (-0.43, WHEEL_Y_OFFSET, WHEEL_Z),
        (0.43, WHEEL_Y_OFFSET, WHEEL_Z),
    ]

    wheels = []
    for idx, rel in enumerate(wheel_positions):
        wheels.append(make_wheel(f"{name_prefix}_wheel_{idx:02d}", origin, rel, mat_wheel, cart_id))
    parts.extend(wheels)

    return parts, door


def build_scene():
    scene = bpy.context.scene
    set_render(scene)

    mat_floor = make_mat("mat_floor_warm", (0.82, 0.80, 0.75), roughness=0.82)
    mat_cart = make_mat("mat_opaque_gray_carts", (0.32, 0.33, 0.35), roughness=0.82)
    mat_edge = make_mat("mat_cart_edge_medium_gray", (0.52, 0.53, 0.55), roughness=0.72)
    mat_door = make_mat("mat_cart_doors_dark_gray", (0.32, 0.33, 0.35), roughness=0.78)
    mat_wheel = make_mat("mat_dark_cart_wheels", (0.32, 0.33, 0.35), roughness=0.65)
    mat_red = make_mat("mat_red_identity_A_ball", (0.95, 0.03, 0.02), roughness=0.30)
    mat_blue = make_mat("mat_blue_identity_B_ball", (0.05, 0.20, 0.95), roughness=0.30)
    mat_marker = make_mat("mat_neutral_motion_marker", (0.45, 0.45, 0.45), roughness=0.80)
    mat_backdrop = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)

    floor = add_cube(
        "large_floor_base",
        (0.0, 0.0, -0.04),
        (7.9, 3.8, 0.10),
        material=mat_floor,
    )
    tag(floor, "large_floor_base", "ground", "static_solid", "cube", "warm_beige", False, solid=True)

    backdrop = add_cube(
        "rear_backdrop_panel",
        (0.0, 2.05, 1.55),
        (7.9, 0.08, 3.1),
        material=mat_backdrop,
    )
    tag(backdrop, "rear_backdrop_panel", "background", "static_solid", "cube", "off_white", False, solid=True)

    # Neutral start/end markers, no red/blue color cue.
    marker_specs = [
        ("neutral_left_start_cart_A_marker", CART_A_START_X, CART_A_Y),
        ("neutral_right_start_cart_B_marker", CART_B_START_X, CART_B_Y),
        ("neutral_right_final_cart_A_marker", CART_A_FINAL_X, CART_A_Y),
        ("neutral_left_final_cart_B_marker", CART_B_FINAL_X, CART_B_Y),
    ]
    for name, x, y in marker_specs:
        m = add_cube(
            name,
            (x, y, 0.015),
            (CART_LEN_X + 0.20, CART_WIDTH_Y + 0.20, 0.025),
            material=mat_marker,
        )
        tag(m, name, "motion_reference_marker", "static_visual_marker", "cube", "gray", False, solid=False)

    cart_a_origin_start = Vector((CART_A_START_X, CART_A_Y, 0.0))
    cart_b_origin_start = Vector((CART_B_START_X, CART_B_Y, 0.0))

    cart_a_parts, door_a = build_cart(
        cart_id="cart_A_started_left_contains_red",
        name_prefix="cart_A_started_left",
        origin=cart_a_origin_start,
        mat_cart=mat_cart,
        mat_edge=mat_edge,
        mat_door=mat_door,
        mat_wheel=mat_wheel,
    )

    cart_b_parts, door_b = build_cart(
        cart_id="cart_B_started_right_contains_blue",
        name_prefix="cart_B_started_right",
        origin=cart_b_origin_start,
        mat_cart=mat_cart,
        mat_edge=mat_edge,
        mat_door=mat_door,
        mat_wheel=mat_wheel,
    )

    # Red ball inside cart A, visible in first frame.
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=48,
        ring_count=24,
        radius=BALL_RADIUS,
        location=cart_a_origin_start + Vector((BALL_REL_X, BALL_REL_Y, BALL_REL_Z)),
    )
    red_ball = bpy.context.object
    red_ball.name = "identity_A_red_ball_inside_cart_A"
    red_ball.data.materials.append(mat_red)
    tag(
        red_ball,
        "identity_A_red_ball_inside_cart_A",
        "target",
        "dynamic_object",
        "sphere",
        "red",
        True,
        solid=True,
        pb_identity_id="A",
        pb_container_id="cart_A_started_left_contains_red",
        pb_expected_final_side="right",
        pb_should_move_with_container=True,
        pb_radius=BALL_RADIUS,
    )
    red_ball["pb_rel_x"] = float(BALL_REL_X)
    red_ball["pb_rel_y"] = float(BALL_REL_Y)
    red_ball["pb_rel_z"] = float(BALL_REL_Z)

    # Blue ball inside cart B, visible in first frame.
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=48,
        ring_count=24,
        radius=BALL_RADIUS,
        location=cart_b_origin_start + Vector((BALL_REL_X, BALL_REL_Y, BALL_REL_Z)),
    )
    blue_ball = bpy.context.object
    blue_ball.name = "identity_B_blue_ball_inside_cart_B"
    blue_ball.data.materials.append(mat_blue)
    tag(
        blue_ball,
        "identity_B_blue_ball_inside_cart_B",
        "target",
        "dynamic_object",
        "sphere",
        "blue",
        True,
        solid=True,
        pb_identity_id="B",
        pb_container_id="cart_B_started_right_contains_blue",
        pb_expected_final_side="left",
        pb_should_move_with_container=True,
        pb_radius=BALL_RADIUS,
    )
    blue_ball["pb_rel_x"] = float(BALL_REL_X)
    blue_ball["pb_rel_y"] = float(BALL_REL_Y)
    blue_ball["pb_rel_z"] = float(BALL_REL_Z)

    # Lights
    bpy.ops.object.light_add(type="AREA", location=(-2.8, -3.9, 5.9))
    key_light = bpy.context.object
    key_light.name = "large_softbox_light"
    key_light.data.energy = 850
    key_light.data.size = 5.8

    bpy.ops.object.light_add(type="POINT", location=(3.7, -2.7, 3.5))
    fill_light = bpy.context.object
    fill_light.name = "right_fill_light"
    fill_light.data.energy = 135

    # Camera sees both open front doors and both balls in first frame.
    bpy.ops.object.camera_add(location=(4.85, -6.65, 3.10))
    camera = bpy.context.object
    camera.name = "camera_multi_object_identity_cart_swap"
    camera.data.lens = 34
    look_at(camera, (0.0, 0.0, 0.82))
    camera.data.dof.use_dof = False
    scene.camera = camera

    return {
        "scene": scene,
        "cart_a_parts": cart_a_parts,
        "cart_b_parts": cart_b_parts,
        "door_a": door_a,
        "door_b": door_b,
        "red_ball": red_ball,
        "blue_ball": blue_ball,
    }


def set_part_positions(parts, origin, frame):
    roll_ref = origin.x
    for obj in parts:
        rel = (obj["pb_rel_x"], obj["pb_rel_y"], obj["pb_rel_z"])
        set_object_from_rel(obj, origin, rel)
        obj.keyframe_insert(data_path="location", frame=frame)

        if obj.get("pb_role") == "cart_wheel":
            obj.rotation_euler = (math.pi / 2.0, -roll_ref / max(1e-6, WHEEL_RADIUS), 0.0)
            obj.keyframe_insert(data_path="rotation_euler", frame=frame)


def set_door_position(door, origin, frame):
    rel = (
        door_rel_x(frame),
        DOOR_Y,
        DOOR_CENTER_Z,
    )
    set_object_from_rel(door, origin, rel)
    door.keyframe_insert(data_path="location", frame=frame)


def set_ball_position(ball, origin, frame):
    rel = (
        ball["pb_rel_x"],
        ball["pb_rel_y"],
        ball["pb_rel_z"],
    )
    set_object_from_rel(ball, origin, rel)
    ball.keyframe_insert(data_path="location", frame=frame)


def semantic_phase(frame):
    if frame <= DOOR_CLOSE_START:
        return "visible_inside_open_carts"
    if frame <= DOOR_CLOSE_END:
        return "doors_closing_balls_becoming_hidden"
    if frame <= CART_SWAP_END:
        return "hidden_inside_closed_swapping_carts"
    if frame <= DOOR_OPEN_END:
        return "doors_opening_after_swap"
    return "visible_inside_swapped_carts"


def assign_semantics(frame, cart_a_parts, cart_b_parts, door_a, door_b, red_ball, blue_ball):
    phase = semantic_phase(frame)
    moving_now = CART_SWAP_START <= frame <= CART_SWAP_END
    doors_closed = DOOR_CLOSE_END < frame < DOOR_OPEN_START

    for obj in cart_a_parts:
        obj["pb_state"] = "swapping_right" if moving_now else "stationary"
        obj["pb_cart_id"] = "cart_A_started_left_contains_red"
        obj["pb_moves_as_rigid_cart"] = True
        obj["pb_contains_identity"] = "A_red_ball"

    for obj in cart_b_parts:
        obj["pb_state"] = "swapping_left" if moving_now else "stationary"
        obj["pb_cart_id"] = "cart_B_started_right_contains_blue"
        obj["pb_moves_as_rigid_cart"] = True
        obj["pb_contains_identity"] = "B_blue_ball"

    door_a["pb_state"] = phase
    door_a["pb_cart_id"] = "cart_A_started_left_contains_red"
    door_a["pb_hides_ball_when_closed"] = doors_closed

    door_b["pb_state"] = phase
    door_b["pb_cart_id"] = "cart_B_started_right_contains_blue"
    door_b["pb_hides_ball_when_closed"] = doors_closed

    red_ball["pb_state"] = phase
    red_ball["pb_visibility_state"] = "hidden_inside_cart_A" if doors_closed else "visible_inside_cart_A"
    red_ball["pb_container_id"] = "cart_A_started_left_contains_red"
    red_ball["pb_identity_id"] = "A"
    red_ball["pb_expected_color"] = "red"
    red_ball["pb_should_move_with_container"] = True
    red_ball["pb_must_not_switch_to_cart_B"] = True
    red_ball["pb_identity_preserved"] = True

    blue_ball["pb_state"] = phase
    blue_ball["pb_visibility_state"] = "hidden_inside_cart_B" if doors_closed else "visible_inside_cart_B"
    blue_ball["pb_container_id"] = "cart_B_started_right_contains_blue"
    blue_ball["pb_identity_id"] = "B"
    blue_ball["pb_expected_color"] = "blue"
    blue_ball["pb_should_move_with_container"] = True
    blue_ball["pb_must_not_switch_to_cart_A"] = True
    blue_ball["pb_identity_preserved"] = True


def animate_scene(scene, cart_a_parts, cart_b_parts, door_a, door_b, red_ball, blue_ball):
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        origin_a = cart_a_origin(frame)
        origin_b = cart_b_origin(frame)

        set_part_positions(cart_a_parts, origin_a, frame)
        set_part_positions(cart_b_parts, origin_b, frame)

        set_door_position(door_a, origin_a, frame)
        set_door_position(door_b, origin_b, frame)

        set_ball_position(red_ball, origin_a, frame)
        set_ball_position(blue_ball, origin_b, frame)

        assign_semantics(
            frame,
            cart_a_parts,
            cart_b_parts,
            door_a,
            door_b,
            red_ball,
            blue_ball,
        )

        red_ball.rotation_euler = (0.0, -origin_a.x / max(1e-6, BALL_RADIUS), 0.0)
        blue_ball.rotation_euler = (0.0, -origin_b.x / max(1e-6, BALL_RADIUS), 0.0)
        red_ball.keyframe_insert(data_path="rotation_euler", frame=frame)
        blue_ball.keyframe_insert(data_path="rotation_euler", frame=frame)

    # Do NOT use obj.animation_data.action.fcurves in Blender 5.x.
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
                "In the first frame, there are two gray opaque carts with their front doors open. "
                "The left cart contains a clearly visible red ball. "
                "The right cart contains a clearly visible blue ball. "
                "Both cart doors then close, hiding the balls inside the opaque carts. "
                "While the balls are hidden, the two carts swap left and right positions. "
                "After the carts finish swapping, both doors open again. "
                "The red ball must still be inside the same cart that started on the left, now on the right. "
                "The blue ball must still be inside the same cart that started on the right, now on the left. "
                "The balls must not swap identities, swap colors, switch carts, merge, disappear, teleport independently, duplicate, or change size."
            ),
        },
        "reference_completion_frames_dir": f"{ITEM_ID}_reference_frames",
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

    animate_scene(
        scene=scene,
        cart_a_parts=objs["cart_a_parts"],
        cart_b_parts=objs["cart_b_parts"],
        door_a=objs["door_a"],
        door_b=objs["door_b"],
        red_ball=objs["red_ball"],
        blue_ball=objs["blue_ball"],
    )

    render_png(scene, INPUT_FRAME_1, INPUT_FRAME_PATH)
    render_png(scene, OPTIONAL_HIDDEN_SWAP_FRAME, OPTIONAL_FRAME_PATH)
    render_png(scene, OPTIONAL_AFTER_OPEN_FRAME, OPTIONAL_FRAME_02B_PATH)

    render_animation(scene)
    write_task_json()
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("Output:", OUT_DIR)
    print("RULES:")
    print(" - first frame: red ball visible inside left open cart")
    print(" - first frame: blue ball visible inside right open cart")
    print(" - doors close and hide both balls")
    print(" - carts swap positions")
    print(" - red stays with original left cart, blue stays with original right cart")
    print(" - no identity swap / color swap / cart swap / count error")
    print("=" * 100)


if __name__ == "__main__":
    main()
