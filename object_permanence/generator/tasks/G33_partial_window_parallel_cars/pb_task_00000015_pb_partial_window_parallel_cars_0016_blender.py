# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

ITEM_ID = "PB_PARTIAL_WINDOW_PARALLEL_CARS_0016"

FPS = 24
FRAME_START = 1
FRAME_END = 120

# ============================================================
# Geometry
# ============================================================

# Low flat solid tracks
TRACK_LENGTH = 9.6
TRACK_WIDTH = 0.36
TRACK_THICKNESS = 0.06
TRACK_TOP_Z = 0.065
TRACK_CENTER_Z = TRACK_TOP_Z - TRACK_THICKNESS / 2.0

RED_TRACK_Y = -0.56   # near camera
BLUE_TRACK_Y = 0.56   # far from camera

# Cars: total height is wheel diameter + body height.
# Blue total height above track = 3x red total height above track.
WHEEL_RADIUS = 0.070
WHEEL_THICKNESS = 0.060
WHEEL_CENTER_Z = TRACK_TOP_Z + WHEEL_RADIUS
WHEEL_DIAMETER = WHEEL_RADIUS * 2.0

CAR_LENGTH = 0.54
CAR_WIDTH = 0.30

RED_BODY_HEIGHT = 0.22
RED_TOTAL_HEIGHT_ABOVE_TRACK = WHEEL_DIAMETER + RED_BODY_HEIGHT

BLUE_TOTAL_HEIGHT_ABOVE_TRACK = RED_TOTAL_HEIGHT_ABOVE_TRACK * 3.0
BLUE_BODY_HEIGHT = BLUE_TOTAL_HEIGHT_ABOVE_TRACK - WHEEL_DIAMETER

BODY_BOTTOM_Z = TRACK_TOP_Z + WHEEL_DIAMETER
RED_BODY_CENTER_Z = BODY_BOTTOM_Z + RED_BODY_HEIGHT / 2.0
BLUE_BODY_CENTER_Z = BODY_BOTTOM_Z + BLUE_BODY_HEIGHT / 2.0

RED_CAR_TOP_Z = TRACK_TOP_Z + RED_TOTAL_HEIGHT_ABOVE_TRACK
BLUE_CAR_TOP_Z = TRACK_TOP_Z + BLUE_TOTAL_HEIGHT_ABOVE_TRACK

# Motion
X_START = -3.20
X_FINAL = 3.70

# Opaque container
COVER_X_MIN = -0.90
COVER_X_MAX = 1.05
COVER_Y_MIN = -1.00   # camera-facing wall
COVER_Y_MAX = 1.00
COVER_Z_MIN = 0.04
COVER_Z_MAX = 1.58
WALL_T = 0.10

# Side window on camera-facing wall.
# Required:
# - bottom > red car top
# - top > blue car top
WINDOW_X_MIN = -0.12
WINDOW_X_MAX = 0.62
WINDOW_Z_MIN = RED_CAR_TOP_Z + 0.24
WINDOW_Z_MAX = BLUE_CAR_TOP_Z + 0.18

OPTIONAL_WINDOW_FRAME = 62
OPTIONAL_AFTER_EXIT_FRAME = 110

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

OUT_DIR = os.path.join(PROJECT_ROOT, "permanence_blender_outputs", ITEM_ID)
FRAMES_DIR = os.path.join(OUT_DIR, "frames")
SCENE_FILE = os.path.join(OUT_DIR, f"{ITEM_ID}_scene.blend")
TASK_JSON_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_task.json")

INPUT_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_input_frame_01.png")
OPTIONAL_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_window_visibility_frame_02.png")
OPTIONAL_FRAME_02B_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_after_exit_frame_02B.png")


# ============================================================
# Utilities
# ============================================================

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


def progress_at_frame(frame):
    return smooth01((frame - FRAME_START) / max(1, FRAME_END - FRAME_START))


def x_at_frame(frame):
    return lerp(X_START, X_FINAL, progress_at_frame(frame))


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


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


def add_cube(name, location, dimensions, rotation=(0, 0, 0), material=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    if material is not None:
        obj.data.materials.append(material)

    return obj


def add_wheel(name, location, material, vehicle_id, side_name):
    # Cylinder axis is rotated to align along Y, like a real wheel axle.
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=40,
        radius=WHEEL_RADIUS,
        depth=WHEEL_THICKNESS,
        location=location,
        rotation=(math.pi / 2.0, 0.0, 0.0),
    )
    obj = bpy.context.object
    obj.name = name
    if material is not None:
        obj.data.materials.append(material)

    tag(
        obj,
        name,
        "vehicle_wheel",
        "dynamic_vehicle_part",
        "cylinder",
        "black",
        True,
        solid=True,
        pb_vehicle_id=vehicle_id,
        pb_wheel_side=side_name,
        pb_wheel_radius=WHEEL_RADIUS,
    )
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


# ============================================================
# Container with side window
# ============================================================

def build_container_with_side_window(mat_cover, mat_frame, mat_shadow):
    parts = []

    x_mid = 0.5 * (COVER_X_MIN + COVER_X_MAX)
    y_mid = 0.5 * (COVER_Y_MIN + COVER_Y_MAX)
    z_mid = 0.5 * (COVER_Z_MIN + COVER_Z_MAX)

    # Bottom floor
    floor = add_cube(
        "gray_window_container_floor",
        (x_mid, y_mid, COVER_Z_MIN + WALL_T / 2.0),
        (COVER_X_MAX - COVER_X_MIN - 2 * WALL_T, COVER_Y_MAX - COVER_Y_MIN - 2 * WALL_T, WALL_T),
        material=mat_cover,
    )
    tag(floor, floor.name, "container_floor", "static_solid", "cube", "gray", False, solid=True)
    parts.append(floor)

    # Far wall
    far_wall = add_cube(
        "gray_window_container_far_wall",
        (x_mid, COVER_Y_MAX - WALL_T / 2.0, z_mid),
        (COVER_X_MAX - COVER_X_MIN, WALL_T, COVER_Z_MAX - COVER_Z_MIN),
        material=mat_cover,
    )
    tag(far_wall, far_wall.name, "container_far_wall", "static_solid", "cube", "gray", False, solid=True)
    parts.append(far_wall)

    # Camera-facing near wall, split into segments around the window opening.
    lower_h = WINDOW_Z_MIN - COVER_Z_MIN
    lower_wall = add_cube(
        "gray_window_container_near_wall_lower_high_sill",
        (x_mid, COVER_Y_MIN + WALL_T / 2.0, COVER_Z_MIN + lower_h / 2.0),
        (COVER_X_MAX - COVER_X_MIN, WALL_T, lower_h),
        material=mat_cover,
    )
    tag(
        lower_wall,
        lower_wall.name,
        "container_near_wall_lower_high_sill",
        "static_solid",
        "cube",
        "gray",
        False,
        solid=True,
        pb_window_bottom_above_red_car=True,
    )
    parts.append(lower_wall)

    upper_h = COVER_Z_MAX - WINDOW_Z_MAX
    upper_wall = add_cube(
        "gray_window_container_near_wall_upper",
        (x_mid, COVER_Y_MIN + WALL_T / 2.0, WINDOW_Z_MAX + upper_h / 2.0),
        (COVER_X_MAX - COVER_X_MIN, WALL_T, upper_h),
        material=mat_cover,
    )
    tag(upper_wall, upper_wall.name, "container_near_wall_upper", "static_solid", "cube", "gray", False, solid=True)
    parts.append(upper_wall)

    left_jamb_w = WINDOW_X_MIN - COVER_X_MIN
    left_jamb = add_cube(
        "gray_window_container_left_jamb",
        (COVER_X_MIN + left_jamb_w / 2.0, COVER_Y_MIN + WALL_T / 2.0, 0.5 * (WINDOW_Z_MIN + WINDOW_Z_MAX)),
        (left_jamb_w, WALL_T, WINDOW_Z_MAX - WINDOW_Z_MIN),
        material=mat_cover,
    )
    tag(left_jamb, left_jamb.name, "container_window_left_jamb", "static_solid", "cube", "gray", False, solid=True)
    parts.append(left_jamb)

    right_jamb_w = COVER_X_MAX - WINDOW_X_MAX
    right_jamb = add_cube(
        "gray_window_container_right_jamb",
        (WINDOW_X_MAX + right_jamb_w / 2.0, COVER_Y_MIN + WALL_T / 2.0, 0.5 * (WINDOW_Z_MIN + WINDOW_Z_MAX)),
        (right_jamb_w, WALL_T, WINDOW_Z_MAX - WINDOW_Z_MIN),
        material=mat_cover,
    )
    tag(right_jamb, right_jamb.name, "container_window_right_jamb", "static_solid", "cube", "gray", False, solid=True)
    parts.append(right_jamb)

    # Roof
    roof = add_cube(
        "gray_window_container_roof",
        (x_mid, y_mid, COVER_Z_MAX - WALL_T / 2.0),
        (COVER_X_MAX - COVER_X_MIN - 2 * WALL_T, COVER_Y_MAX - COVER_Y_MIN - 2 * WALL_T, WALL_T),
        material=mat_cover,
    )
    tag(roof, roof.name, "container_roof", "static_solid", "cube", "gray", False, solid=True)
    parts.append(roof)

    # Entry and tail frames. Tail is the right-side exit from observer perspective.
    for side_name, x, role_prefix in [
        ("entry_left", COVER_X_MIN, "container_entry"),
        ("tail_right_exit", COVER_X_MAX, "container_tail_exit"),
    ]:
        top = add_cube(
            f"{role_prefix}_top_frame",
            (x, y_mid, COVER_Z_MAX + 0.035),
            (WALL_T * 1.25, COVER_Y_MAX - COVER_Y_MIN, 0.070),
            material=mat_frame,
        )
        tag(top, top.name, role_prefix + "_frame", "static_solid", "cube", "light_gray", False, solid=True)
        parts.append(top)

        bottom = add_cube(
            f"{role_prefix}_bottom_frame",
            (x, y_mid, COVER_Z_MIN + 0.060),
            (WALL_T * 1.25, COVER_Y_MAX - COVER_Y_MIN, 0.080),
            material=mat_frame,
        )
        tag(bottom, bottom.name, role_prefix + "_frame", "static_solid", "cube", "light_gray", False, solid=True)
        parts.append(bottom)

        near = add_cube(
            f"{role_prefix}_near_vertical_frame",
            (x, COVER_Y_MIN - 0.035, z_mid),
            (WALL_T * 1.25, 0.070, COVER_Z_MAX - COVER_Z_MIN + 0.12),
            material=mat_frame,
        )
        tag(near, near.name, role_prefix + "_frame", "static_solid", "cube", "light_gray", False, solid=True)
        parts.append(near)

        far = add_cube(
            f"{role_prefix}_far_vertical_frame",
            (x, COVER_Y_MAX + 0.035, z_mid),
            (WALL_T * 1.25, 0.070, COVER_Z_MAX - COVER_Z_MIN + 0.12),
            material=mat_frame,
        )
        tag(far, far.name, role_prefix + "_frame", "static_solid", "cube", "light_gray", False, solid=True)
        parts.append(far)

    # Window sill/top frame are intentionally bright enough to show the high sill.
    sill = add_cube(
        "raised_window_sill_frame_above_red_car",
        (0.5 * (WINDOW_X_MIN + WINDOW_X_MAX), COVER_Y_MIN - 0.025, WINDOW_Z_MIN - 0.020),
        (WINDOW_X_MAX - WINDOW_X_MIN, 0.050, 0.045),
        material=mat_frame,
    )
    tag(
        sill,
        sill.name,
        "window_sill_frame",
        "static_solid",
        "cube",
        "light_gray",
        False,
        solid=True,
        pb_window_bottom_z=WINDOW_Z_MIN,
        pb_red_car_top_z=RED_CAR_TOP_Z,
    )
    parts.append(sill)

    lintel = add_cube(
        "window_top_frame_above_blue_car",
        (0.5 * (WINDOW_X_MIN + WINDOW_X_MAX), COVER_Y_MIN - 0.025, WINDOW_Z_MAX + 0.020),
        (WINDOW_X_MAX - WINDOW_X_MIN, 0.050, 0.045),
        material=mat_frame,
    )
    tag(
        lintel,
        lintel.name,
        "window_top_frame",
        "static_solid",
        "cube",
        "light_gray",
        False,
        solid=True,
        pb_window_top_z=WINDOW_Z_MAX,
        pb_blue_car_top_z=BLUE_CAR_TOP_Z,
    )
    parts.append(lintel)

    # Interior floor shadow
    shadow = add_cube(
        "container_interior_shadow",
        (x_mid, y_mid, COVER_Z_MIN + 0.030),
        ((COVER_X_MAX - COVER_X_MIN) * 0.82, (COVER_Y_MAX - COVER_Y_MIN) * 0.76, 0.030),
        material=mat_shadow,
    )
    tag(shadow, shadow.name, "container_interior_shadow", "static_visual_marker", "cube", "dark_gray", False, solid=False)
    parts.append(shadow)

    return parts


# ============================================================
# Vehicles
# ============================================================

def build_car(prefix, color_name, mat_body, mat_wheel, x, y, body_height, vehicle_id, track_position, height_ratio):
    parts = []

    body_center_z = BODY_BOTTOM_Z + body_height / 2.0
    body = add_cube(
        f"{prefix}_body",
        (x, y, body_center_z),
        (CAR_LENGTH, CAR_WIDTH, body_height),
        material=mat_body,
    )
    tag(
        body,
        body.name,
        "target",
        "dynamic_object",
        "car_body",
        color_name,
        True,
        solid=True,
        pb_vehicle_id=vehicle_id,
        pb_vehicle_type="car_with_wheels",
        pb_track_position=track_position,
        pb_body_height=body_height,
        pb_total_height_above_track=WHEEL_DIAMETER + body_height,
        pb_height_ratio_to_red=height_ratio,
    )
    body["pb_rel_x"] = 0.0
    body["pb_rel_y"] = 0.0
    body["pb_rel_z"] = body_center_z
    parts.append(body)

    # Add 4 visible black wheels.
    wheel_offsets = [
        (-CAR_LENGTH * 0.33, -CAR_WIDTH * 0.58, WHEEL_CENTER_Z, "front_near"),
        ( CAR_LENGTH * 0.33, -CAR_WIDTH * 0.58, WHEEL_CENTER_Z, "rear_near"),
        (-CAR_LENGTH * 0.33,  CAR_WIDTH * 0.58, WHEEL_CENTER_Z, "front_far"),
        ( CAR_LENGTH * 0.33,  CAR_WIDTH * 0.58, WHEEL_CENTER_Z, "rear_far"),
    ]

    for dx, dy, dz, side_name in wheel_offsets:
        wheel = add_wheel(
            f"{prefix}_wheel_{side_name}",
            (x + dx, y + dy, dz),
            mat_wheel,
            vehicle_id,
            side_name,
        )
        wheel["pb_rel_x"] = dx
        wheel["pb_rel_y"] = dy
        wheel["pb_rel_z"] = dz
        parts.append(wheel)

    return body, parts


def set_car_parts(parts, x, y, frame):
    dist = x - X_START
    roll = -dist / max(1e-6, WHEEL_RADIUS)

    for obj in parts:
        rel_x = obj.get("pb_rel_x", 0.0)
        rel_y = obj.get("pb_rel_y", 0.0)
        rel_z = obj.get("pb_rel_z", obj.location.z)

        obj.location = (x + rel_x, y + rel_y, rel_z)

        if obj.get("pb_role") == "vehicle_wheel":
            obj.rotation_euler = (math.pi / 2.0, roll, 0.0)
            obj.keyframe_insert(data_path="rotation_euler", frame=frame)

        obj.keyframe_insert(data_path="location", frame=frame)


# ============================================================
# Scene
# ============================================================

def build_scene():
    scene = bpy.context.scene
    set_render(scene)

    mat_floor = make_mat("mat_floor_warm", (0.82, 0.80, 0.75), roughness=0.82)
    mat_track = make_mat("mat_track_gray", (0.47, 0.47, 0.47), roughness=0.62)
    mat_track_side = make_mat("mat_track_dark_side", (0.30, 0.30, 0.30), roughness=0.72)
    mat_container = make_mat("mat_container_gray", (0.30, 0.31, 0.33), roughness=0.82)
    mat_frame = make_mat("mat_container_frame_light", (0.62, 0.63, 0.64), roughness=0.70)
    mat_shadow = make_mat("mat_container_shadow", (0.30, 0.31, 0.33), roughness=0.92)
    mat_red = make_mat("mat_red_car_body", (0.95, 0.03, 0.02), roughness=0.32)
    mat_blue = make_mat("mat_blue_car_body", (0.05, 0.20, 0.95), roughness=0.32)
    mat_wheel = make_mat("mat_black_rubber_wheels", (0.02, 0.02, 0.025), roughness=0.75)
    mat_backdrop = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)

    floor = add_cube(
        "large_floor_base",
        (0.0, 0.0, -0.04),
        (9.8, 4.3, 0.10),
        material=mat_floor,
    )
    tag(floor, floor.name, "ground", "static_solid", "cube", "warm_beige", False, solid=True)

    backdrop = add_cube(
        "rear_backdrop_panel",
        (0.0, 2.34, 1.62),
        (10.2, 0.08, 3.24),
        material=mat_backdrop,
    )
    tag(backdrop, backdrop.name, "background", "static_solid", "cube", "off_white", False, solid=True)

    # Two parallel straight solid flat tracks
    red_track = add_cube(
        "near_red_track_flat_solid",
        (0.0, RED_TRACK_Y, TRACK_CENTER_Z),
        (TRACK_LENGTH, TRACK_WIDTH, TRACK_THICKNESS),
        material=mat_track,
    )
    tag(
        red_track,
        red_track.name,
        "near_track",
        "static_solid",
        "cube",
        "neutral_gray",
        False,
        solid=True,
        pb_track_kind="straight_flat_solid_track",
        pb_track_position="near_camera",
    )

    blue_track = add_cube(
        "far_blue_track_flat_solid",
        (0.0, BLUE_TRACK_Y, TRACK_CENTER_Z),
        (TRACK_LENGTH, TRACK_WIDTH, TRACK_THICKNESS),
        material=mat_track,
    )
    tag(
        blue_track,
        blue_track.name,
        "far_track",
        "static_solid",
        "cube",
        "neutral_gray",
        False,
        solid=True,
        pb_track_kind="straight_flat_solid_track",
        pb_track_position="far_from_camera",
    )

    # Slight dark side strips make the flat tracks read as solid but low.
    for y, name in [(RED_TRACK_Y, "near_track_dark_side"), (BLUE_TRACK_Y, "far_track_dark_side")]:
        side = add_cube(
            name,
            (0.0, y, TRACK_CENTER_Z - 0.035),
            (TRACK_LENGTH, TRACK_WIDTH + 0.06, 0.035),
            material=mat_track_side,
        )
        tag(side, side.name, "track_side_shadow", "static_solid", "cube", "dark_gray", False, solid=True)

    container_parts = build_container_with_side_window(mat_container, mat_frame, mat_shadow)

    red_body, red_parts = build_car(
        prefix="near_red_low_car",
        color_name="red",
        mat_body=mat_red,
        mat_wheel=mat_wheel,
        x=X_START,
        y=RED_TRACK_Y,
        body_height=RED_BODY_HEIGHT,
        vehicle_id="red_near_car",
        track_position="near_camera",
        height_ratio=1.0,
    )

    blue_body, blue_parts = build_car(
        prefix="far_blue_tall_car",
        color_name="blue",
        mat_body=mat_blue,
        mat_wheel=mat_wheel,
        x=X_START,
        y=BLUE_TRACK_Y,
        body_height=BLUE_BODY_HEIGHT,
        vehicle_id="blue_far_tall_car",
        track_position="far_from_camera",
        height_ratio=3.0,
    )

    bpy.ops.object.light_add(type="AREA", location=(-3.5, -4.8, 6.2))
    key_light = bpy.context.object
    key_light.name = "large_softbox_light"
    key_light.data.energy = 930
    key_light.data.size = 6.2

    bpy.ops.object.light_add(type="POINT", location=(4.1, -2.4, 3.7))
    fill_light = bpy.context.object
    fill_light.name = "right_fill_light"
    fill_light.data.energy = 145

    # Camera:
    # Flatter than the previous overly high view.
    # Slightly from the right/front, so the right tail / exit side is visible.
    # Still high enough to see the roof and side window.
    bpy.ops.object.camera_add(location=(2.35, -8.85, 2.45))
    camera = bpy.context.object
    camera.name = "camera_flatter_right_front_view_sees_tail_window_roof"
    camera.data.lens = 31
    look_at(camera, (0.36, 0.02, 0.96))
    camera.data.dof.use_dof = False
    scene.camera = camera

    return {
        "scene": scene,
        "red_body": red_body,
        "blue_body": blue_body,
        "red_parts": red_parts,
        "blue_parts": blue_parts,
        "container_parts": container_parts,
        "red_track": red_track,
        "blue_track": blue_track,
    }


# ============================================================
# Animation / semantic states
# ============================================================

def set_red_state(red_body, x):
    if x < COVER_X_MIN:
        phase = "visible_before_container"
        visibility = "visible"
        loc_state = "outside_left_near_track"
    elif x <= COVER_X_MAX:
        if WINDOW_X_MIN <= x <= WINDOW_X_MAX:
            phase = "inside_container_below_high_window_sill"
            visibility = "fully_occluded_below_window"
            loc_state = "inside_window_region_near_track"
        else:
            phase = "inside_container_hidden"
            visibility = "occluded_inside_container"
            loc_state = "inside_container_near_track"
    else:
        phase = "visible_after_container"
        visibility = "visible"
        loc_state = "outside_right_near_track"

    red_body["pb_state"] = phase
    red_body["pb_visibility_state"] = visibility
    red_body["pb_location_state"] = loc_state
    red_body["pb_expected_window_visibility"] = "not_visible_because_window_bottom_above_red_car"
    red_body["pb_track_position"] = "near_camera"
    red_body["pb_identity_preserved"] = True


def set_blue_state(blue_body, x):
    if x < COVER_X_MIN:
        phase = "visible_before_container"
        visibility = "visible"
        loc_state = "outside_left_far_track"
    elif x <= COVER_X_MAX:
        if WINDOW_X_MIN <= x <= WINDOW_X_MAX:
            phase = "inside_container_partially_visible_at_window"
            visibility = "upper_part_visible_through_window"
            loc_state = "inside_window_region_far_track"
        else:
            phase = "inside_container_hidden"
            visibility = "occluded_inside_container_except_window_region"
            loc_state = "inside_container_far_track"
    else:
        phase = "visible_after_container"
        visibility = "visible"
        loc_state = "outside_right_far_track"

    blue_body["pb_state"] = phase
    blue_body["pb_visibility_state"] = visibility
    blue_body["pb_location_state"] = loc_state
    blue_body["pb_expected_window_visibility"] = "upper_part_visible"
    blue_body["pb_track_position"] = "far_from_camera"
    blue_body["pb_identity_preserved"] = True


def animate_scene(scene, red_body, blue_body, red_parts, blue_parts, container_parts, red_track, blue_track):
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        x = x_at_frame(frame)

        set_car_parts(red_parts, x, RED_TRACK_Y, frame)
        set_car_parts(blue_parts, x, BLUE_TRACK_Y, frame)

        set_red_state(red_body, x)
        set_blue_state(blue_body, x)

        cover_phase = (
            "cars_at_side_window_region"
            if WINDOW_X_MIN <= x <= WINDOW_X_MAX
            else ("cars_inside_container" if COVER_X_MIN <= x <= COVER_X_MAX else "cars_outside_container")
        )

        for obj in container_parts:
            obj["pb_state"] = "static_container_with_high_side_window"
            obj["pb_cover_phase"] = cover_phase
            obj["pb_has_side_window"] = True
            obj["pb_window_bottom_z"] = WINDOW_Z_MIN
            obj["pb_window_top_z"] = WINDOW_Z_MAX
            obj["pb_red_car_top_z"] = RED_CAR_TOP_Z
            obj["pb_blue_car_top_z"] = BLUE_CAR_TOP_Z
            obj["pb_tail_exit_visible_required"] = True

        red_track["pb_state"] = "static_low_flat_solid_near_track"
        blue_track["pb_state"] = "static_low_flat_solid_far_track"

    # Blender 5.x compatibility: do not access obj.animation_data.action.fcurves.
    scene.frame_set(FRAME_START)


# ============================================================
# Output
# ============================================================

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
                "Two wheeled cars move from left to right on two parallel straight flat solid tracks. "
                "The near track, closer to the camera, carries a low red car with visible wheels. "
                "The far track carries a tall blue car with visible wheels. "
                "The blue car is three times as tall as the red car when measured from the track surface to the top of the car. "
                "Both cars enter a gray opaque container. "
                "The camera-facing side of the container has a high side window. "
                "The bottom edge of the window is higher than the top of the red car, so the red car should not be visible through the window. "
                "The top edge of the window is higher than the top of the blue car, so only the upper part of the tall blue car should be visible through the window. "
                "The two cars must keep their identities, colors, sizes, tracks, wheels, and count throughout the sequence. "
                "The view should show the container roof and the right-side tail / exit of the container."
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

    animate_scene(
        scene=scene,
        red_body=objs["red_body"],
        blue_body=objs["blue_body"],
        red_parts=objs["red_parts"],
        blue_parts=objs["blue_parts"],
        container_parts=objs["container_parts"],
        red_track=objs["red_track"],
        blue_track=objs["blue_track"],
    )

    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, OPTIONAL_WINDOW_FRAME, OPTIONAL_FRAME_PATH)
    render_png(scene, OPTIONAL_AFTER_EXIT_FRAME, OPTIONAL_FRAME_02B_PATH)

    render_animation(scene)
    write_task_json()
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("Output:", OUT_DIR)
    print("FIXED:")
    print(" - cars now have visible wheels")
    print(" - flat tracks are low; car height comes from wheel height + body height")
    print(" - blue total height above track = 3x red total height above track")
    print(" - window bottom raised above red car top")
    print(" - flatter camera sees roof and right tail/exit")
    print("=" * 100)


if __name__ == "__main__":
    main()
