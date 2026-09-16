# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r'''{
  "item_id": "PB_CAR_BLOCKED_CLOSED_GATE_0028",
  "scene_kind": "closed_gate_block",
  "prompt": "A red wheeled car drives from left to right on a low flat straight track. A closed gate blocks the track. The car must stop at the closed gate and must not pass through or overlap it."
}''')
ITEM_ID = CASE["item_id"]

FPS = 24
FRAME_START = 1
FRAME_END = 120

# ============================================================
# Shared geometry
# ============================================================

TRACK_LENGTH = 9.0
TRACK_WIDTH = 0.42
TRACK_THICKNESS = 0.07
TRACK_TOP_Z = 0.07
TRACK_CENTER_Z = TRACK_TOP_Z - TRACK_THICKNESS / 2.0

TRACK_Y = 0.0
NEAR_TRACK_Y = -0.56
FAR_TRACK_Y = 0.56

WHEEL_RADIUS = 0.080
WHEEL_THICKNESS = 0.065
WHEEL_CENTER_Z = TRACK_TOP_Z + WHEEL_RADIUS
WHEEL_DIAMETER = WHEEL_RADIUS * 2.0

CAR_LENGTH = 0.60
CAR_WIDTH = 0.34
LOW_BODY_HEIGHT = 0.24
TALL_BODY_HEIGHT = (WHEEL_DIAMETER + LOW_BODY_HEIGHT) * 3.0 - WHEEL_DIAMETER

BODY_BOTTOM_Z = TRACK_TOP_Z + WHEEL_DIAMETER

BALL_RADIUS = 0.22
BALL_Z = TRACK_TOP_Z + BALL_RADIUS + 0.025

WALL_X = 1.55
WALL_THICKNESS = 0.18
WALL_LEFT_FACE_X = WALL_X - WALL_THICKNESS / 2.0
WALL_WIDTH_Y = 1.28
WALL_HEIGHT = 1.24

X_START = -3.15
X_FINAL = 3.35
IMPACT_FRAME = 70

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

OUT_DIR = os.path.join(PROJECT_ROOT, "permanence_blender_outputs", ITEM_ID)
FRAMES_DIR = os.path.join(OUT_DIR, "frames")
SCENE_FILE = os.path.join(OUT_DIR, f"{ITEM_ID}_scene.blend")
TASK_JSON_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_task.json")

INPUT_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_input_frame_01.png")
OPTIONAL_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_event_frame_02.png")
OPTIONAL_FRAME_02B_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_final_frame_02B.png")


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


def ease_out(t):
    # Decelerating ease-out: fast right after impact, slowing to a stop.
    t = clamp01(t)
    return 1.0 - (1.0 - t) * (1.0 - t)


def lerp(a, b, t):
    return a + (b - a) * t


def progress_at_frame(frame):
    return smooth01((frame - FRAME_START) / max(1, FRAME_END - FRAME_START))


def progress_to_impact(frame):
    return smooth01((frame - FRAME_START) / max(1, IMPACT_FRAME - FRAME_START))


def x_pass(frame):
    return lerp(X_START, X_FINAL, progress_at_frame(frame))


# Slight elastic rebound on barrier contact. On flat ground there is no restoring
# force, so the car recoils backward and comes to REST away from the wall.
REBOUND_BACK = 0.18
REBOUND_FRAME = IMPACT_FRAME + 8


def x_blocked(frame, car_length=CAR_LENGTH):
    x_contact = WALL_LEFT_FACE_X - car_length / 2.0 - 0.006
    x_rest = x_contact - REBOUND_BACK
    if frame <= IMPACT_FRAME:
        return lerp(X_START, x_contact, progress_to_impact(frame))
    if frame <= REBOUND_FRAME:
        return lerp(x_contact, x_rest, ease_out((frame - IMPACT_FRAME) / max(1, REBOUND_FRAME - IMPACT_FRAME)))
    return x_rest


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
        mat.use_screen_refraction = True
        mat.show_transparent_back = True
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


def add_cube(name, location, dimensions, material=None, solid=True, role="static_solid", color_name="gray"):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    if material is not None:
        obj.data.materials.append(material)

    tag(obj, name, role, "static_solid" if solid else "non_solid_marker", "cube", color_name, False, solid=solid)
    return obj


def add_wheel(name, location, material, vehicle_id, side_name):
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
# Objects
# ============================================================

def add_track(y=TRACK_Y, name="straight_flat_solid_track", mat=None):
    track = add_cube(
        name,
        (0.0, y, TRACK_CENTER_Z),
        (TRACK_LENGTH, TRACK_WIDTH, TRACK_THICKNESS),
        material=mat,
        solid=True,
        role="track",
        color_name="neutral_gray",
    )
    track["pb_track_kind"] = "straight_flat_solid_track"
    side = add_cube(
        name + "_dark_side",
        (0.0, y, TRACK_CENTER_Z - 0.035),
        (TRACK_LENGTH, TRACK_WIDTH + 0.06, 0.035),
        material=MATS["track_dark"],
        solid=True,
        role="track_side_shadow",
        color_name="dark_gray",
    )
    return track


def build_car(prefix, color_name, mat_body, x, y, body_height, vehicle_id):
    parts = []
    body_center_z = BODY_BOTTOM_Z + body_height / 2.0

    body = add_cube(
        f"{prefix}_body",
        (x, y, body_center_z),
        (CAR_LENGTH, CAR_WIDTH, body_height),
        material=mat_body,
        solid=True,
        role="target",
        color_name=color_name,
    )
    body["pb_is_dynamic"] = True
    body["pb_category"] = "dynamic_object"
    body["pb_vehicle_type"] = "wheeled_car"
    body["pb_vehicle_id"] = vehicle_id
    body["pb_total_height_above_track"] = WHEEL_DIAMETER + body_height
    body["pb_rel_x"] = 0.0
    body["pb_rel_y"] = 0.0
    body["pb_rel_z"] = body_center_z
    parts.append(body)

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
            MATS["wheel"],
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


def build_full_wall(name="solid_wall_blocker"):
    wall = add_cube(
        name,
        (WALL_X, TRACK_Y, WALL_HEIGHT / 2.0),
        (WALL_THICKNESS, WALL_WIDTH_Y, WALL_HEIGHT),
        material=MATS["wall"],
        solid=True,
        role="obstacle",
        color_name="gray",
    )
    wall["pb_blocks_motion"] = True

    rim = add_cube(
        "wall_left_impact_face_rim",
        (WALL_LEFT_FACE_X - 0.012, TRACK_Y, WALL_HEIGHT / 2.0),
        (0.024, WALL_WIDTH_Y + 0.02, WALL_HEIGHT + 0.02),
        material=MATS["wall_edge"],
        solid=True,
        role="impact_face_marker",
        color_name="light_gray",
    )
    return [wall, rim]


def build_wall_hole(kind):
    if kind == "large":
        hole_width = CAR_WIDTH + 0.48
        hole_height = WHEEL_DIAMETER + LOW_BODY_HEIGHT + 0.42
        hole_bottom = TRACK_TOP_Z - 0.015
        marker_name = "large_wall_hole_opening_marker"
    else:
        hole_width = CAR_WIDTH * 0.55
        hole_height = (WHEEL_DIAMETER + LOW_BODY_HEIGHT) * 0.55
        hole_bottom = TRACK_TOP_Z + 0.10
        marker_name = "small_wall_hole_opening_marker"

    hole_top = hole_bottom + hole_height
    hole_y_min = -hole_width / 2.0
    hole_y_max = hole_width / 2.0

    parts = []

    bottom_h = max(0.001, hole_bottom)
    parts.append(add_cube(
        f"wall_bottom_sill_{kind}_hole",
        (WALL_X, TRACK_Y, bottom_h / 2.0),
        (WALL_THICKNESS, WALL_WIDTH_Y, bottom_h),
        material=MATS["wall"],
        solid=True,
        role="wall_solid_part",
        color_name="gray",
    ))

    top_h = WALL_HEIGHT - hole_top
    parts.append(add_cube(
        f"wall_top_lintel_{kind}_hole",
        (WALL_X, TRACK_Y, hole_top + top_h / 2.0),
        (WALL_THICKNESS, WALL_WIDTH_Y, top_h),
        material=MATS["wall"],
        solid=True,
        role="wall_solid_part",
        color_name="gray",
    ))

    near_w = hole_y_min - (-WALL_WIDTH_Y / 2.0)
    near_y = -WALL_WIDTH_Y / 2.0 + near_w / 2.0
    parts.append(add_cube(
        f"wall_near_jamb_{kind}_hole",
        (WALL_X, near_y, hole_bottom + hole_height / 2.0),
        (WALL_THICKNESS, near_w, hole_height),
        material=MATS["wall"],
        solid=True,
        role="wall_solid_part",
        color_name="gray",
    ))

    far_w = WALL_WIDTH_Y / 2.0 - hole_y_max
    far_y = hole_y_max + far_w / 2.0
    parts.append(add_cube(
        f"wall_far_jamb_{kind}_hole",
        (WALL_X, far_y, hole_bottom + hole_height / 2.0),
        (WALL_THICKNESS, far_w, hole_height),
        material=MATS["wall"],
        solid=True,
        role="wall_solid_part",
        color_name="gray",
    ))

    rim_t = 0.035
    parts.append(add_cube(
        f"{kind}_hole_bottom_rim",
        (WALL_LEFT_FACE_X - 0.012, TRACK_Y, hole_bottom),
        (0.024, hole_width, rim_t),
        material=MATS["wall_edge"],
        solid=True,
        role="hole_rim",
        color_name="light_gray",
    ))
    parts.append(add_cube(
        f"{kind}_hole_top_rim",
        (WALL_LEFT_FACE_X - 0.012, TRACK_Y, hole_top),
        (0.024, hole_width, rim_t),
        material=MATS["wall_edge"],
        solid=True,
        role="hole_rim",
        color_name="light_gray",
    ))
    parts.append(add_cube(
        f"{kind}_hole_near_vertical_rim",
        (WALL_LEFT_FACE_X - 0.012, hole_y_min, hole_bottom + hole_height / 2.0),
        (0.024, rim_t, hole_height),
        material=MATS["wall_edge"],
        solid=True,
        role="hole_rim",
        color_name="light_gray",
    ))
    parts.append(add_cube(
        f"{kind}_hole_far_vertical_rim",
        (WALL_LEFT_FACE_X - 0.012, hole_y_max, hole_bottom + hole_height / 2.0),
        (0.024, rim_t, hole_height),
        material=MATS["wall_edge"],
        solid=True,
        role="hole_rim",
        color_name="light_gray",
    ))

    marker = add_cube(
        marker_name,
        (WALL_X, TRACK_Y, hole_bottom + hole_height / 2.0),
        (WALL_THICKNESS * 0.5, hole_width * 0.9, hole_height * 0.9),
        material=None,
        solid=False,
        role="opening_volume",
        color_name="none",
    )
    marker.hide_render = True
    marker.hide_viewport = True
    marker["pb_hole_kind"] = kind
    marker["pb_hole_width_y"] = hole_width
    marker["pb_hole_height_z"] = hole_height
    marker["pb_hole_larger_than_car"] = bool(kind == "large")
    marker["pb_hole_smaller_than_car"] = bool(kind == "small")
    parts.append(marker)

    return parts


def build_container_window(two_cars=False, low_only=False, tall_only=False):
    parts = []
    cover_x_min = -0.85
    cover_x_max = 1.05
    cover_y_min = -1.00
    cover_y_max = 1.00
    cover_z_min = 0.04
    cover_z_max = 1.58
    wall_t = 0.10

    red_top = TRACK_TOP_Z + WHEEL_DIAMETER + LOW_BODY_HEIGHT
    blue_top = TRACK_TOP_Z + WHEEL_DIAMETER + TALL_BODY_HEIGHT

    window_x_min = -0.12
    window_x_max = 0.62
    window_z_min = red_top + 0.24
    window_z_max = blue_top + 0.18

    x_mid = 0.5 * (cover_x_min + cover_x_max)
    y_mid = 0.5 * (cover_y_min + cover_y_max)
    z_mid = 0.5 * (cover_z_min + cover_z_max)

    parts.append(add_cube(
        "window_container_floor",
        (x_mid, y_mid, cover_z_min + wall_t / 2.0),
        (cover_x_max - cover_x_min, cover_y_max - cover_y_min, wall_t),
        material=MATS["wall"],
        solid=True,
        role="container_floor",
        color_name="gray",
    ))
    parts.append(add_cube(
        "window_container_far_wall",
        (x_mid, cover_y_max - wall_t / 2.0, z_mid),
        (cover_x_max - cover_x_min, wall_t, cover_z_max - cover_z_min),
        material=MATS["wall"],
        solid=True,
        role="container_far_wall",
        color_name="gray",
    ))

    lower_h = window_z_min - cover_z_min
    parts.append(add_cube(
        "window_container_near_wall_lower_high_sill",
        (x_mid, cover_y_min + wall_t / 2.0, cover_z_min + lower_h / 2.0),
        (cover_x_max - cover_x_min, wall_t, lower_h),
        material=MATS["wall"],
        solid=True,
        role="container_near_wall_lower_high_sill",
        color_name="gray",
    ))

    upper_h = cover_z_max - window_z_max
    parts.append(add_cube(
        "window_container_near_wall_upper",
        (x_mid, cover_y_min + wall_t / 2.0, window_z_max + upper_h / 2.0),
        (cover_x_max - cover_x_min, wall_t, upper_h),
        material=MATS["wall"],
        solid=True,
        role="container_near_wall_upper",
        color_name="gray",
    ))

    left_w = window_x_min - cover_x_min
    parts.append(add_cube(
        "window_container_left_jamb",
        (cover_x_min + left_w / 2.0, cover_y_min + wall_t / 2.0, 0.5 * (window_z_min + window_z_max)),
        (left_w, wall_t, window_z_max - window_z_min),
        material=MATS["wall"],
        solid=True,
        role="window_jamb",
        color_name="gray",
    ))

    right_w = cover_x_max - window_x_max
    parts.append(add_cube(
        "window_container_right_jamb",
        (window_x_max + right_w / 2.0, cover_y_min + wall_t / 2.0, 0.5 * (window_z_min + window_z_max)),
        (right_w, wall_t, window_z_max - window_z_min),
        material=MATS["wall"],
        solid=True,
        role="window_jamb",
        color_name="gray",
    ))

    parts.append(add_cube(
        "window_container_roof",
        (x_mid, y_mid, cover_z_max - wall_t / 2.0),
        (cover_x_max - cover_x_min, cover_y_max - cover_y_min, wall_t),
        material=MATS["wall"],
        solid=True,
        role="container_roof",
        color_name="gray",
    ))

    parts.append(add_cube(
        "raised_window_sill_frame",
        (0.5 * (window_x_min + window_x_max), cover_y_min - 0.025, window_z_min - 0.020),
        (window_x_max - window_x_min, 0.050, 0.045),
        material=MATS["wall_edge"],
        solid=True,
        role="window_sill_frame",
        color_name="light_gray",
    ))
    parts.append(add_cube(
        "window_top_frame",
        (0.5 * (window_x_min + window_x_max), cover_y_min - 0.025, window_z_max + 0.020),
        (window_x_max - window_x_min, 0.050, 0.045),
        material=MATS["wall_edge"],
        solid=True,
        role="window_top_frame",
        color_name="light_gray",
    ))

    for obj in parts:
        obj["pb_window_bottom_above_low_car"] = True
        obj["pb_window_top_above_tall_car"] = True
        obj["pb_has_side_window"] = True

    return parts


def build_gate(open_gate):
    parts = []
    if open_gate:
        parts.append(add_cube(
            "open_gate_left_post",
            (WALL_X, -0.48, 0.55),
            (0.16, 0.12, 1.10),
            material=MATS["wall"],
            solid=True,
            role="gate_post",
            color_name="gray",
        ))
        parts.append(add_cube(
            "open_gate_right_post",
            (WALL_X, 0.48, 0.55),
            (0.16, 0.12, 1.10),
            material=MATS["wall"],
            solid=True,
            role="gate_post",
            color_name="gray",
        ))
        parts.append(add_cube(
            "open_gate_raised_panel",
            (WALL_X, TRACK_Y, 1.18),
            (0.16, 0.86, 0.16),
            material=MATS["wall_edge"],
            solid=True,
            role="raised_gate_panel",
            color_name="light_gray",
        ))
        for p in parts:
            p["pb_gate_open"] = True
            p["pb_clear_passage"] = True
    else:
        parts.append(add_cube(
            "closed_gate_panel",
            (WALL_X, TRACK_Y, 0.55),
            (0.16, 0.92, 1.10),
            material=MATS["wall"],
            solid=True,
            role="closed_gate",
            color_name="gray",
        ))
        parts.append(add_cube(
            "closed_gate_left_impact_face_rim",
            (WALL_LEFT_FACE_X - 0.012, TRACK_Y, 0.55),
            (0.024, 0.96, 1.14),
            material=MATS["wall_edge"],
            solid=True,
            role="impact_face_marker",
            color_name="light_gray",
        ))
        for p in parts:
            p["pb_gate_closed"] = True
            p["pb_blocks_motion"] = True
    return parts


# ============================================================
# Scene build
# ============================================================

MATS = {}


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)

    MATS["floor"] = make_mat("mat_floor_warm", (0.82, 0.80, 0.75), roughness=0.82)
    MATS["track"] = make_mat("mat_track_gray", (0.46, 0.46, 0.46), roughness=0.62)
    MATS["track_dark"] = make_mat("mat_track_dark_side", (0.30, 0.30, 0.30), roughness=0.72)
    MATS["wall"] = make_mat("mat_wall_gray", (0.38, 0.40, 0.42), roughness=0.78)
    MATS["wall_edge"] = make_mat("mat_wall_edge_light", (0.60, 0.61, 0.62), roughness=0.68)
    MATS["red"] = make_mat("mat_red_body", (0.95, 0.03, 0.02), roughness=0.32)
    MATS["blue"] = make_mat("mat_blue_body", (0.05, 0.20, 0.95), roughness=0.32)
    MATS["orange"] = make_mat("mat_orange_ball", (1.0, 0.38, 0.06), roughness=0.30)
    MATS["wheel"] = make_mat("mat_black_rubber_wheels", (0.02, 0.02, 0.025), roughness=0.75)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)
    MATS["glass"] = make_mat("mat_transparent_glass_wall", (0.55, 0.85, 1.0), roughness=0.08, alpha=0.35, blend="BLEND")

    floor = add_cube(
        "large_floor_base",
        (0.0, 0.0, -0.04),
        (9.4, 4.2, 0.10),
        material=MATS["floor"],
        solid=True,
        role="ground",
        color_name="warm_beige",
    )

    backdrop = add_cube(
        "rear_backdrop_panel",
        (0.0, 2.25, 1.45),
        (9.6, 0.08, 2.9),
        material=MATS["backdrop"],
        solid=True,
        role="background",
        color_name="off_white",
    )

    return scene


def build_scene():
    scene = build_base_scene()
    kind = CASE["scene_kind"]
    objs = {"scene": scene, "dynamic_groups": [], "static_objects": []}

    if kind in ["solid_wall_block", "large_hole_pass", "small_hole_block", "open_gate_pass", "closed_gate_block"]:
        track = add_track(TRACK_Y, mat=MATS["track"])
        objs["track"] = track

        body, parts = build_car("red_wheeled_car", "red", MATS["red"], X_START, TRACK_Y, LOW_BODY_HEIGHT, "red_car")
        objs["red_body"] = body
        objs["red_parts"] = parts

        if kind == "solid_wall_block":
            objs["static_objects"] = build_full_wall()
        elif kind == "large_hole_pass":
            objs["static_objects"] = build_wall_hole("large")
        elif kind == "small_hole_block":
            objs["static_objects"] = build_wall_hole("small")
        elif kind == "open_gate_pass":
            objs["static_objects"] = build_gate(True)
        elif kind == "closed_gate_block":
            objs["static_objects"] = build_gate(False)

        bpy.ops.object.camera_add(location=(-0.45, -8.35, 1.42))
        camera = bpy.context.object
        camera.name = "camera_level_view_wall_or_gate"
        camera.data.lens = 31
        look_at(camera, (1.05, 0.02, 0.58))
        camera.data.dof.use_dof = False
        scene.camera = camera

    elif kind in ["single_tall_window", "single_low_window", "two_cars_window"]:
        add_track(NEAR_TRACK_Y, "near_flat_solid_track", MATS["track"])
        add_track(FAR_TRACK_Y, "far_flat_solid_track", MATS["track"])
        objs["static_objects"] = build_container_window()

        if kind == "single_tall_window":
            blue_body, blue_parts = build_car("far_blue_tall_car", "blue", MATS["blue"], X_START, FAR_TRACK_Y, TALL_BODY_HEIGHT, "blue_tall_car")
            objs["blue_body"] = blue_body
            objs["blue_parts"] = blue_parts
        elif kind == "single_low_window":
            red_body, red_parts = build_car("near_red_low_car", "red", MATS["red"], X_START, NEAR_TRACK_Y, LOW_BODY_HEIGHT, "red_low_car")
            objs["red_body"] = red_body
            objs["red_parts"] = red_parts
        else:
            red_body, red_parts = build_car("near_red_low_car", "red", MATS["red"], X_START, NEAR_TRACK_Y, LOW_BODY_HEIGHT, "red_low_car")
            blue_body, blue_parts = build_car("far_blue_tall_car", "blue", MATS["blue"], X_START, FAR_TRACK_Y, TALL_BODY_HEIGHT, "blue_tall_car")
            objs["red_body"] = red_body
            objs["red_parts"] = red_parts
            objs["blue_body"] = blue_body
            objs["blue_parts"] = blue_parts

        bpy.ops.object.camera_add(location=(2.25, -8.70, 2.35))
        camera = bpy.context.object
        camera.name = "camera_window_view_roof_tail_visible"
        camera.data.lens = 31
        look_at(camera, (0.38, 0.02, 0.98))
        camera.data.dof.use_dof = False
        scene.camera = camera

    elif kind == "transparent_wall_ball_block":
        track = add_track(TRACK_Y, mat=MATS["track"])
        objs["track"] = track

        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=48,
            ring_count=24,
            radius=BALL_RADIUS,
            location=(X_START, TRACK_Y, BALL_Z),
        )
        ball = bpy.context.object
        ball.name = "orange_ball"
        ball.data.materials.append(MATS["orange"])
        tag(
            ball,
            "orange_ball",
            "target",
            "dynamic_object",
            "sphere",
            "orange",
            True,
            solid=True,
            pb_radius=BALL_RADIUS,
        )
        objs["ball"] = ball

        wall = add_cube(
            "transparent_solid_wall",
            (WALL_X, TRACK_Y, 0.60),
            (0.12, 1.10, 1.20),
            material=MATS["glass"],
            solid=True,
            role="transparent_wall",
            color_name="transparent_blue",
        )
        wall["pb_transparent"] = True
        wall["pb_solid"] = True
        wall["pb_blocks_motion"] = True
        objs["static_objects"] = [wall]

        bpy.ops.object.camera_add(location=(-0.25, -7.90, 1.38))
        camera = bpy.context.object
        camera.name = "camera_level_view_transparent_wall"
        camera.data.lens = 31
        look_at(camera, (1.10, 0.02, 0.55))
        camera.data.dof.use_dof = False
        scene.camera = camera

    elif kind == "rear_car_stops_behind_front":
        track = add_track(TRACK_Y, mat=MATS["track"])
        objs["track"] = track
        objs["static_objects"] = build_full_wall("front_car_blocking_wall")

        red_body, red_parts = build_car("front_red_car", "red", MATS["red"], -1.45, TRACK_Y, LOW_BODY_HEIGHT, "front_red_car")
        blue_body, blue_parts = build_car("rear_blue_car", "blue", MATS["blue"], -3.25, TRACK_Y, LOW_BODY_HEIGHT, "rear_blue_car")
        objs["red_body"] = red_body
        objs["red_parts"] = red_parts
        objs["blue_body"] = blue_body
        objs["blue_parts"] = blue_parts

        bpy.ops.object.camera_add(location=(-0.45, -8.40, 1.45))
        camera = bpy.context.object
        camera.name = "camera_level_view_two_cars_no_penetration"
        camera.data.lens = 31
        look_at(camera, (0.60, 0.02, 0.55))
        camera.data.dof.use_dof = False
        scene.camera = camera

    else:
        raise RuntimeError(f"Unknown scene_kind: {kind}")

    bpy.ops.object.light_add(type="AREA", location=(-3.8, -4.2, 5.2))
    key_light = bpy.context.object
    key_light.name = "large_softbox_light"
    key_light.data.energy = 910
    key_light.data.size = 5.8

    bpy.ops.object.light_add(type="POINT", location=(3.7, -2.8, 3.0))
    fill_light = bpy.context.object
    fill_light.name = "right_fill_light"
    fill_light.data.energy = 135

    return objs


# ============================================================
# Animation
# ============================================================

def set_target_state(obj, state, **kwargs):
    obj["pb_state"] = state
    for k, v in kwargs.items():
        obj[k] = v


def animate_scene(objs):
    scene = objs["scene"]
    kind = CASE["scene_kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if kind in ["solid_wall_block", "small_hole_block", "closed_gate_block"]:
            x = x_blocked(frame)
            set_car_parts(objs["red_parts"], x, TRACK_Y, frame)

            moving = frame < IMPACT_FRAME
            state = "moving_toward_blocker" if moving else "stopped_by_blocker"
            set_target_state(
                objs["red_body"],
                state,
                pb_motion_state="moving" if moving else "stopped",
                pb_no_penetration=True,
                pb_expected_behavior="blocked_and_stopped",
            )

        elif kind in ["large_hole_pass", "open_gate_pass"]:
            x = x_pass(frame)
            set_car_parts(objs["red_parts"], x, TRACK_Y, frame)

            if x < WALL_LEFT_FACE_X - CAR_LENGTH / 2.0:
                phase = "approaching_opening"
            elif x < WALL_X + WALL_THICKNESS / 2.0 + CAR_LENGTH / 2.0:
                phase = "passing_through_opening"
            else:
                phase = "passed_opening"

            set_target_state(
                objs["red_body"],
                phase,
                pb_motion_state="moving",
                pb_expected_behavior="pass_through_clear_opening",
                pb_no_solid_wall_penetration=True,
            )

        elif kind in ["single_tall_window", "single_low_window", "two_cars_window"]:
            x = x_pass(frame)
            if "red_parts" in objs:
                set_car_parts(objs["red_parts"], x, NEAR_TRACK_Y, frame)
                if -0.12 <= x <= 0.62:
                    red_state = "hidden_below_high_window"
                    red_vis = "not_visible_through_window"
                elif x < -0.85:
                    red_state = "visible_before_container"
                    red_vis = "visible"
                elif x > 1.05:
                    red_state = "visible_after_container"
                    red_vis = "visible"
                else:
                    red_state = "inside_container_occluded"
                    red_vis = "occluded"
                set_target_state(
                    objs["red_body"],
                    red_state,
                    pb_visibility_state=red_vis,
                    pb_expected_window_visibility="hidden_below_window",
                )

            if "blue_parts" in objs:
                set_car_parts(objs["blue_parts"], x, FAR_TRACK_Y, frame)
                if -0.12 <= x <= 0.62:
                    blue_state = "upper_part_visible_through_window"
                    blue_vis = "upper_part_visible"
                elif x < -0.85:
                    blue_state = "visible_before_container"
                    blue_vis = "visible"
                elif x > 1.05:
                    blue_state = "visible_after_container"
                    blue_vis = "visible"
                else:
                    blue_state = "inside_container_occluded"
                    blue_vis = "occluded"
                set_target_state(
                    objs["blue_body"],
                    blue_state,
                    pb_visibility_state=blue_vis,
                    pb_expected_window_visibility="upper_part_visible",
                )

        elif kind == "transparent_wall_ball_block":
            x_contact = WALL_LEFT_FACE_X - BALL_RADIUS - 0.006
            if frame <= IMPACT_FRAME:
                x = lerp(X_START, x_contact, progress_to_impact(frame))
            else:
                x = x_contact

            ball = objs["ball"]
            ball.location = (x, TRACK_Y, BALL_Z)
            ball.rotation_euler = (0.0, -(x - X_START) / BALL_RADIUS, 0.0)
            ball.keyframe_insert(data_path="location", frame=frame)
            ball.keyframe_insert(data_path="rotation_euler", frame=frame)

            set_target_state(
                ball,
                "rolling_toward_transparent_wall" if frame < IMPACT_FRAME else "stopped_by_transparent_wall",
                pb_motion_state="moving" if frame < IMPACT_FRAME else "stopped",
                pb_transparent_wall_is_solid=True,
                pb_no_penetration=True,
            )

        elif kind == "rear_car_stops_behind_front":
            wall_contact_x = WALL_LEFT_FACE_X - CAR_LENGTH / 2.0 - 0.006
            red_start = -1.45
            red_x = lerp(red_start, wall_contact_x, smooth01(min(1.0, frame / 62.0)))
            if frame > 62:
                red_x = wall_contact_x

            safe_gap = 0.20
            blue_stop_x = red_x - CAR_LENGTH - safe_gap
            blue_start = -3.25
            blue_x_candidate = lerp(blue_start, blue_stop_x, smooth01(min(1.0, frame / 86.0)))
            blue_x = min(blue_x_candidate, blue_stop_x)

            set_car_parts(objs["red_parts"], red_x, TRACK_Y, frame)
            set_car_parts(objs["blue_parts"], blue_x, TRACK_Y, frame)

            set_target_state(
                objs["red_body"],
                "front_car_stopped_at_wall" if frame > 62 else "front_car_moving_toward_wall",
                pb_motion_state="stopped" if frame > 62 else "moving",
                pb_no_wall_penetration=True,
            )
            set_target_state(
                objs["blue_body"],
                "rear_car_stopped_behind_front_car" if frame > 86 else "rear_car_following_front_car",
                pb_motion_state="stopped" if frame > 86 else "moving",
                pb_no_penetration_of_front_car=True,
                pb_stays_behind_front_car=True,
            )

        for obj in objs.get("static_objects", []):
            obj["pb_state"] = "static_scene_constraint"
            obj["pb_scene_kind"] = kind

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
            "text_prompt": CASE["prompt"],
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
    print("scene_kind:", CASE["scene_kind"])
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
