# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

ITEM_ID = "PB_HIDDEN_OBJECT_MOVES_WITH_CART_0011"

FPS = 24
FRAME_START = 1
FRAME_END = 120

# Timing
DOOR_CLOSE_START = 22
DOOR_CLOSE_END = 42

CART_MOVE_START = 45
CART_MOVE_END = 92

DOOR_OPEN_START = 94
DOOR_OPEN_END = 114

# Cart motion
CART_START_X = -1.55
CART_FINAL_X = 1.55
CART_Y = 0.0
CART_Z = 0.0

# Cart dimensions
CART_LEN_X = 1.90
CART_WIDTH_Y = 1.22
CART_WALL_H = 0.92
WALL_T = 0.10
FLOOR_T = 0.12
ROOF_T = 0.10

# The gray position markers are thin overlays on the white floor. Wheels rest
# on their top surface, and the cart floor rests directly on the wheel tops.
GROUND_CENTER_Z = -0.04
GROUND_T = 0.10
GROUND_TOP_Z = GROUND_CENTER_Z + GROUND_T / 2.0
MARKER_T = 0.025
MARKER_TOP_Z = GROUND_TOP_Z + 0.002
MARKER_CENTER_Z = MARKER_TOP_Z - MARKER_T / 2.0

WHEEL_RADIUS = 0.17
WHEEL_THICKNESS = 0.12
WHEEL_Z = MARKER_TOP_Z + WHEEL_RADIUS

FLOOR_BOTTOM_Z = WHEEL_Z + WHEEL_RADIUS
FLOOR_TOP_Z = FLOOR_BOTTOM_Z + FLOOR_T
FLOOR_CENTER_Z = FLOOR_TOP_Z - FLOOR_T / 2.0
WALL_CENTER_Z = FLOOR_TOP_Z + CART_WALL_H / 2.0
WALL_TOP_Z = FLOOR_TOP_Z + CART_WALL_H
ROOF_CENTER_Z = WALL_TOP_Z + ROOF_T / 2.0 + 0.015

FRONT_Y = -CART_WIDTH_Y / 2.0
BACK_Y = CART_WIDTH_Y / 2.0

# Front door opening
DOOR_W = 1.08
DOOR_H = 0.78
DOOR_T = 0.075
DOOR_OPEN_X = -1.05
DOOR_CLOSED_X = 0.0
DOOR_Y = FRONT_Y - DOOR_T / 2.0 - 0.018
DOOR_BOTTOM_Z = FLOOR_TOP_Z + 0.08
DOOR_CENTER_Z = DOOR_BOTTOM_Z + DOOR_H / 2.0

# Ball
BALL_RADIUS = 0.22
BALL_REL_X = 0.08
BALL_REL_Y = -0.15
BALL_REL_Z = FLOOR_TOP_Z + BALL_RADIUS + 0.025

INPUT_FRAME_1 = 1
OPTIONAL_HIDDEN_MOVING_FRAME = 68
OPTIONAL_REVEALED_FINAL_FRAME = 118

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

OUT_DIR = os.path.join(PROJECT_ROOT, "permanence_blender_outputs", ITEM_ID)
FRAMES_DIR = os.path.join(OUT_DIR, f"{ITEM_ID}_reference_frames")
SCENE_FILE = os.path.join(OUT_DIR, f"{ITEM_ID}_scene.blend")
TASK_JSON_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_task.json")

INPUT_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_input_frame_01.png")
OPTIONAL_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_hidden_moving_frame_02.png")
OPTIONAL_FRAME_02B_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_revealed_final_frame_02B.png")


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


def cart_offset_x(frame):
    if frame <= CART_MOVE_START:
        return 0.0

    if frame >= CART_MOVE_END:
        return CART_FINAL_X - CART_START_X

    t = (frame - CART_MOVE_START) / max(1, CART_MOVE_END - CART_MOVE_START)
    return (CART_FINAL_X - CART_START_X) * smooth01(t)


def cart_origin_at_frame(frame):
    return Vector((CART_START_X + cart_offset_x(frame), CART_Y, CART_Z))


def door_rel_x_at_frame(frame):
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


def rel_to_world(rel):
    return Vector((CART_START_X, CART_Y, CART_Z)) + Vector(rel)


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


def make_cart_part(name, rel_loc, dims, mat, role, color_name="gray", solid=True, **extras):
    obj = add_cube(
        name=name,
        location=rel_to_world(rel_loc),
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
        **extras,
    )
    obj["pb_rel_x"] = float(rel_loc[0])
    obj["pb_rel_y"] = float(rel_loc[1])
    obj["pb_rel_z"] = float(rel_loc[2])
    return obj


def make_wheel(name, rel_loc, mat):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=48,
        radius=WHEEL_RADIUS,
        depth=WHEEL_THICKNESS,
        location=rel_to_world(rel_loc),
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
        pb_cart_id="moving_opaque_cart",
    )
    obj["pb_rel_x"] = float(rel_loc[0])
    obj["pb_rel_y"] = float(rel_loc[1])
    obj["pb_rel_z"] = float(rel_loc[2])
    return obj


def build_scene():
    scene = bpy.context.scene
    set_render(scene)

    mat_floor = make_mat("mat_floor_warm", (0.82, 0.80, 0.75), roughness=0.82)
    mat_cart = make_mat("mat_opaque_gray_cart", (0.32, 0.33, 0.35), roughness=0.82)
    mat_cart_edge = make_mat("mat_cart_edge_medium_gray", (0.52, 0.53, 0.55), roughness=0.72)
    mat_door = make_mat("mat_sliding_cart_door_dark_gray", (0.20, 0.21, 0.23), roughness=0.78)
    mat_wheel = make_mat("mat_dark_cart_wheels", (0.055, 0.055, 0.060), roughness=0.65)
    mat_ball = make_mat("mat_orange_ball_inside_cart", (1.0, 0.38, 0.05), roughness=0.30)
    mat_marker = make_mat("mat_neutral_motion_marker", (0.45, 0.45, 0.45), roughness=0.80)
    mat_backdrop = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)

    floor = add_cube(
        "large_floor_base",
        (0.0, 0.0, GROUND_CENTER_Z),
        (7.9, 3.6, GROUND_T),
        material=mat_floor,
    )
    tag(floor, "large_floor_base", "ground", "static_solid", "cube", "warm_beige", False, solid=True)

    backdrop = add_cube(
        "rear_backdrop_panel",
        (0.0, 1.92, 1.55),
        (7.9, 0.08, 3.1),
        material=mat_backdrop,
    )
    tag(backdrop, "rear_backdrop_panel", "background", "static_solid", "cube", "off_white", False, solid=True)

    start_marker = add_cube(
        "neutral_cart_start_position_marker",
        (CART_START_X, 0.0, MARKER_CENTER_Z),
        (CART_LEN_X + 0.22, CART_WIDTH_Y + 0.22, MARKER_T),
        material=mat_marker,
    )
    tag(start_marker, "neutral_cart_start_position_marker", "motion_reference_marker", "static_visual_marker", "cube", "gray", False, solid=False)

    end_marker = add_cube(
        "neutral_cart_end_position_marker",
        (CART_FINAL_X, 0.0, MARKER_CENTER_Z),
        (CART_LEN_X + 0.22, CART_WIDTH_Y + 0.22, MARKER_T),
        material=mat_marker,
    )
    tag(end_marker, "neutral_cart_end_position_marker", "motion_reference_marker", "static_visual_marker", "cube", "gray", False, solid=False)

    cart_parts = []

    # Cart bottom
    bottom = make_cart_part(
        "moving_gray_cart_bottom_floor",
        (0.0, 0.0, FLOOR_CENTER_Z),
        (CART_LEN_X, CART_WIDTH_Y, FLOOR_T),
        mat_cart,
        role="cart_floor",
        pb_cart_id="moving_opaque_cart",
    )
    bottom["pb_supported_by_wheels"] = True
    cart_parts.append(bottom)

    # Back wall
    back_wall = make_cart_part(
        "moving_gray_cart_back_wall",
        (0.0, BACK_Y - WALL_T / 2.0, WALL_CENTER_Z),
        (CART_LEN_X, WALL_T, CART_WALL_H),
        mat_cart,
        role="cart_wall",
        pb_cart_id="moving_opaque_cart",
    )
    cart_parts.append(back_wall)

    # Left and right side walls
    left_wall = make_cart_part(
        "moving_gray_cart_left_side_wall",
        (-CART_LEN_X / 2.0 + WALL_T / 2.0, 0.0, WALL_CENTER_Z),
        (WALL_T, CART_WIDTH_Y, CART_WALL_H),
        mat_cart,
        role="cart_wall",
        pb_cart_id="moving_opaque_cart",
    )
    cart_parts.append(left_wall)

    right_wall = make_cart_part(
        "moving_gray_cart_right_side_wall",
        (CART_LEN_X / 2.0 - WALL_T / 2.0, 0.0, WALL_CENTER_Z),
        (WALL_T, CART_WIDTH_Y, CART_WALL_H),
        mat_cart,
        role="cart_wall",
        pb_cart_id="moving_opaque_cart",
    )
    cart_parts.append(right_wall)

    # Roof: makes the cart opaque when the front door is closed.
    roof = make_cart_part(
        "moving_gray_cart_roof",
        (0.0, 0.0, ROOF_CENTER_Z),
        (CART_LEN_X, CART_WIDTH_Y, ROOF_T),
        mat_cart,
        role="cart_roof",
        pb_cart_id="moving_opaque_cart",
        pb_occludes=True,
    )
    cart_parts.append(roof)

    # Front wall frame around the door opening.
    side_post_w = (CART_LEN_X - DOOR_W) / 2.0
    left_post_x = -DOOR_W / 2.0 - side_post_w / 2.0
    right_post_x = DOOR_W / 2.0 + side_post_w / 2.0

    front_left_post = make_cart_part(
        "moving_gray_cart_front_left_door_frame",
        (left_post_x, FRONT_Y + WALL_T / 2.0, WALL_CENTER_Z),
        (side_post_w, WALL_T, CART_WALL_H),
        mat_cart,
        role="cart_front_door_frame",
        pb_cart_id="moving_opaque_cart",
        pb_front_opening_frame=True,
    )
    cart_parts.append(front_left_post)

    front_right_post = make_cart_part(
        "moving_gray_cart_front_right_door_frame",
        (right_post_x, FRONT_Y + WALL_T / 2.0, WALL_CENTER_Z),
        (side_post_w, WALL_T, CART_WALL_H),
        mat_cart,
        role="cart_front_door_frame",
        pb_cart_id="moving_opaque_cart",
        pb_front_opening_frame=True,
    )
    cart_parts.append(front_right_post)

    bottom_sill_h = DOOR_BOTTOM_Z - FLOOR_TOP_Z
    front_bottom_sill = make_cart_part(
        "moving_gray_cart_front_bottom_sill",
        (0.0, FRONT_Y + WALL_T / 2.0, FLOOR_TOP_Z + bottom_sill_h / 2.0),
        (DOOR_W, WALL_T, bottom_sill_h),
        mat_cart_edge,
        role="cart_front_door_sill",
        color_name="medium_gray",
        pb_cart_id="moving_opaque_cart",
        pb_front_opening_frame=True,
    )
    cart_parts.append(front_bottom_sill)

    top_bar_h = max(0.06, WALL_TOP_Z - (DOOR_BOTTOM_Z + DOOR_H))
    front_top_bar = make_cart_part(
        "moving_gray_cart_front_top_bar",
        (0.0, FRONT_Y + WALL_T / 2.0, WALL_TOP_Z - top_bar_h / 2.0),
        (DOOR_W, WALL_T, top_bar_h),
        mat_cart_edge,
        role="cart_front_door_top_bar",
        color_name="medium_gray",
        pb_cart_id="moving_opaque_cart",
        pb_front_opening_frame=True,
    )
    cart_parts.append(front_top_bar)

    # Sliding front door. It starts open to the left, then slides closed over the opening.
    door = make_cart_part(
        "moving_opaque_gray_cart_sliding_door",
        (DOOR_OPEN_X, DOOR_Y, DOOR_CENTER_Z),
        (DOOR_W, DOOR_T, DOOR_H),
        mat_door,
        role="sliding_cart_door",
        color_name="dark_gray",
        pb_cart_id="moving_opaque_cart",
        pb_door_can_hide_ball=True,
    )

    # Wheels
    wheel_positions = [
        (-0.66, -0.54, WHEEL_Z),
        (0.66, -0.54, WHEEL_Z),
        (-0.66, 0.54, WHEEL_Z),
        (0.66, 0.54, WHEEL_Z),
    ]
    wheels = []
    for idx, rel in enumerate(wheel_positions):
        wheels.append(make_wheel(f"moving_cart_wheel_{idx:02d}", rel, mat_wheel))

    cart_parts.extend(wheels)

    # Ball initially visible through the open cart door.
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=48,
        ring_count=24,
        radius=BALL_RADIUS,
        location=rel_to_world((BALL_REL_X, BALL_REL_Y, BALL_REL_Z)),
    )
    ball = bpy.context.object
    ball.name = "target_orange_ball_inside_moving_cart"
    ball.data.materials.append(mat_ball)
    tag(
        ball,
        "target_orange_ball_inside_moving_cart",
        "target",
        "dynamic_object",
        "sphere",
        "orange",
        True,
        solid=True,
        pb_identity_id="target_ball",
        pb_radius=BALL_RADIUS,
        pb_cart_id="moving_opaque_cart",
        pb_inside_cart=True,
        pb_should_move_with_cart=True,
    )
    ball["pb_rel_x"] = float(BALL_REL_X)
    ball["pb_rel_y"] = float(BALL_REL_Y)
    ball["pb_rel_z"] = float(BALL_REL_Z)

    # Lights
    bpy.ops.object.light_add(type="AREA", location=(-2.8, -3.9, 5.9))
    key_light = bpy.context.object
    key_light.name = "large_softbox_light"
    key_light.data.energy = 840
    key_light.data.size = 5.7

    bpy.ops.object.light_add(type="POINT", location=(3.7, -2.7, 3.5))
    fill_light = bpy.context.object
    fill_light.name = "right_fill_light"
    fill_light.data.energy = 135

    # Camera: front-right view, so first frame clearly sees ball through open door.
    bpy.ops.object.camera_add(location=(4.65, -6.25, 2.95))
    camera = bpy.context.object
    camera.name = "camera_hidden_object_moves_with_cart"
    camera.data.lens = 36
    look_at(camera, (0.0, -0.10, 0.88))
    camera.data.dof.use_dof = False
    scene.camera = camera

    return {
        "scene": scene,
        "cart_parts": cart_parts,
        "door": door,
        "ball": ball,
    }


def set_object_from_rel(obj, origin, rel_xyz):
    obj.location = origin + Vector(rel_xyz)


def semantic_states(frame, cart_parts, door, ball):
    if frame <= DOOR_CLOSE_START:
        door_state = "open"
        ball_visibility = "visible_inside_open_cart"
        ball_state = "inside_open_cart_visible"
    elif frame <= DOOR_CLOSE_END:
        door_state = "closing"
        ball_visibility = "becoming_hidden_by_cart_door"
        ball_state = "inside_cart_becoming_occluded"
    elif frame <= CART_MOVE_END:
        door_state = "closed"
        ball_visibility = "hidden_inside_closed_moving_cart"
        ball_state = "hidden_inside_cart_moving_with_cart"
    elif frame <= DOOR_OPEN_END:
        door_state = "opening"
        ball_visibility = "becoming_visible_after_cart_moved"
        ball_state = "inside_moved_cart_reappearing"
    else:
        door_state = "open_after_motion"
        ball_visibility = "visible_inside_moved_cart"
        ball_state = "same_ball_visible_inside_moved_cart"

    moving_now = CART_MOVE_START <= frame <= CART_MOVE_END

    for obj in cart_parts:
        obj["pb_state"] = "moving_right" if moving_now else "stationary"
        obj["pb_cart_id"] = "moving_opaque_cart"
        obj["pb_moves_as_rigid_cart"] = True
        obj["pb_hidden_object_should_move_with_this_cart"] = True

    door["pb_state"] = door_state
    door["pb_cart_id"] = "moving_opaque_cart"
    door["pb_door_position_state"] = door_state
    door["pb_hides_ball_when_closed"] = door_state in ["closed", "closing"]

    ball["pb_state"] = ball_state
    ball["pb_visibility_state"] = ball_visibility
    ball["pb_inside_cart"] = True
    ball["pb_cart_id"] = "moving_opaque_cart"
    ball["pb_should_move_with_cart"] = True
    ball["pb_identity_preserved"] = True
    ball["pb_expected_color"] = "orange"
    ball["pb_expected_count"] = 1
    ball["pb_must_not_remain_at_old_location"] = True
    ball["pb_must_not_disappear_while_hidden"] = True


def animate_scene(scene, cart_parts, door, ball):
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        origin = cart_origin_at_frame(frame)
        roll = -cart_offset_x(frame) / max(1e-6, WHEEL_RADIUS)

        for obj in cart_parts:
            rel = (
                obj["pb_rel_x"],
                obj["pb_rel_y"],
                obj["pb_rel_z"],
            )
            set_object_from_rel(obj, origin, rel)
            obj.keyframe_insert(data_path="location", frame=frame)

            if obj.get("pb_role") == "cart_wheel":
                obj.rotation_euler = (math.pi / 2.0, roll, 0.0)
                obj.keyframe_insert(data_path="rotation_euler", frame=frame)

        door_rel = (
            door_rel_x_at_frame(frame),
            DOOR_Y,
            DOOR_CENTER_Z,
        )
        set_object_from_rel(door, origin, door_rel)
        door.keyframe_insert(data_path="location", frame=frame)

        ball_rel = (
            BALL_REL_X,
            BALL_REL_Y,
            BALL_REL_Z,
        )
        set_object_from_rel(ball, origin, ball_rel)
        ball.rotation_euler = (
            0.0,
            -cart_offset_x(frame) / max(1e-6, BALL_RADIUS),
            0.0,
        )
        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)

        semantic_states(frame, cart_parts, door, ball)

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
                "A single orange ball is initially clearly visible inside an open gray opaque cart. "
                "The cart door is open in the first frame and is about to close. "
                "The sliding cart door then closes, hiding the orange ball inside the opaque cart. "
                "While the ball is hidden, the closed cart moves to the right. "
                "Because the ball is inside the cart, the hidden ball must move together with the cart. "
                "After the cart reaches the new position, the door opens again and the same orange ball should be visible inside the moved cart. "
                "The ball must not stay behind at the original location, must not disappear, must not teleport independently, "
                "must not duplicate, and must preserve its color, size, and identity."
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
        cart_parts=objs["cart_parts"],
        door=objs["door"],
        ball=objs["ball"],
    )

    render_png(scene, INPUT_FRAME_1, INPUT_FRAME_PATH)
    render_png(scene, OPTIONAL_HIDDEN_MOVING_FRAME, OPTIONAL_FRAME_PATH)
    render_png(scene, OPTIONAL_REVEALED_FINAL_FRAME, OPTIONAL_FRAME_02B_PATH)

    render_animation(scene)
    write_task_json()
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("Output:", OUT_DIR)
    print("RULES:")
    print(" - first frame: open gray opaque cart, orange ball clearly visible inside")
    print(" - cart door closes and hides the ball")
    print(" - closed cart moves right")
    print(" - hidden ball moves with the cart")
    print(" - door opens and same ball is visible inside moved cart")
    print("=" * 100)


if __name__ == "__main__":
    main()
