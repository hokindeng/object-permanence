# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

ITEM_ID = "PB_CAR_BLOCKED_BY_SMALL_WALL_HOLE_0019"

FPS = 24
FRAME_START = 1
FRAME_END = 120

# ============================================================
# Geometry
# ============================================================

# Low flat solid track
TRACK_LENGTH = 8.8
TRACK_WIDTH = 0.42
TRACK_THICKNESS = 0.07
TRACK_TOP_Z = 0.07
TRACK_CENTER_Z = TRACK_TOP_Z - TRACK_THICKNESS / 2.0
TRACK_Y = 0.0

# Wheeled red car
WHEEL_RADIUS = 0.080
WHEEL_THICKNESS = 0.065
WHEEL_CENTER_Z = TRACK_TOP_Z + WHEEL_RADIUS
WHEEL_DIAMETER = WHEEL_RADIUS * 2.0

CAR_LENGTH = 0.60
CAR_WIDTH = 0.34
CAR_BODY_HEIGHT = 0.24
CAR_BODY_BOTTOM_Z = TRACK_TOP_Z + WHEEL_DIAMETER
CAR_BODY_CENTER_Z = CAR_BODY_BOTTOM_Z + CAR_BODY_HEIGHT / 2.0
CAR_TOTAL_HEIGHT_ABOVE_TRACK = WHEEL_DIAMETER + CAR_BODY_HEIGHT
CAR_TOP_Z = TRACK_TOP_Z + CAR_TOTAL_HEIGHT_ABOVE_TRACK

# Wall with a small hole / small door.
WALL_X = 1.55
WALL_THICKNESS = 0.18
WALL_LEFT_FACE_X = WALL_X - WALL_THICKNESS / 2.0
WALL_WIDTH_Y = 1.28
WALL_HEIGHT = 1.22

# IMPORTANT:
# This opening is intentionally SMALLER than the car.
# It is aligned with the track, but the car cannot fit through it.
SMALL_HOLE_WIDTH_Y = CAR_WIDTH * 0.55
SMALL_HOLE_HEIGHT_Z = CAR_TOTAL_HEIGHT_ABOVE_TRACK * 0.55
SMALL_HOLE_CENTER_Y = TRACK_Y
SMALL_HOLE_BOTTOM_Z = TRACK_TOP_Z + 0.10
SMALL_HOLE_TOP_Z = SMALL_HOLE_BOTTOM_Z + SMALL_HOLE_HEIGHT_Z

SMALL_HOLE_Y_MIN = SMALL_HOLE_CENTER_Y - SMALL_HOLE_WIDTH_Y / 2.0
SMALL_HOLE_Y_MAX = SMALL_HOLE_CENTER_Y + SMALL_HOLE_WIDTH_Y / 2.0

# Motion: car approaches the small hole, contacts the wall face, and stops.
X_START = -3.10
X_CONTACT = WALL_LEFT_FACE_X - CAR_LENGTH / 2.0 - 0.006
IMPACT_FRAME = 70

OPTIONAL_IMPACT_FRAME = 72
OPTIONAL_STOPPED_FRAME = 120

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

OUT_DIR = os.path.join(PROJECT_ROOT, "permanence_blender_outputs", ITEM_ID)
FRAMES_DIR = os.path.join(OUT_DIR, "frames")
SCENE_FILE = os.path.join(OUT_DIR, f"{ITEM_ID}_scene.blend")
TASK_JSON_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_task.json")

INPUT_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_input_frame_01.png")
OPTIONAL_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_impact_small_hole_frame_02.png")
OPTIONAL_FRAME_02B_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_stopped_frame_02B.png")


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


def progress_to_impact(frame):
    return smooth01((frame - FRAME_START) / max(1, IMPACT_FRAME - FRAME_START))


# Slight elastic rebound on wall contact (like G03): impact -> recoil back -> settle.
REBOUND_BACK = 0.18
REBOUND_FRAME = IMPACT_FRAME + 8
SETTLE_FRAME = REBOUND_FRAME + 10
X_REBOUND = X_CONTACT - REBOUND_BACK
X_FINAL = X_REBOUND  # flat ground: rest at rebound, do NOT return to wall

def car_x_at_frame(frame):
    if frame <= IMPACT_FRAME:
        return lerp(X_START, X_CONTACT, progress_to_impact(frame))
    if frame <= REBOUND_FRAME:
        return lerp(X_CONTACT, X_REBOUND, smooth01((frame - IMPACT_FRAME) / max(1, REBOUND_FRAME - IMPACT_FRAME)))
    if frame <= SETTLE_FRAME:
        return lerp(X_REBOUND, X_FINAL, smooth01((frame - REBOUND_FRAME) / max(1, SETTLE_FRAME - REBOUND_FRAME)))
    return X_FINAL


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
# Car
# ============================================================

def build_car(prefix, x, y, mat_body, mat_wheel):
    parts = []

    body = add_cube(
        f"{prefix}_body",
        (x, y, CAR_BODY_CENTER_Z),
        (CAR_LENGTH, CAR_WIDTH, CAR_BODY_HEIGHT),
        material=mat_body,
    )
    tag(
        body,
        body.name,
        "target",
        "dynamic_object",
        "car_body",
        "red",
        True,
        solid=True,
        pb_vehicle_type="wheeled_car",
        pb_total_height_above_track=CAR_TOTAL_HEIGHT_ABOVE_TRACK,
        pb_expected_motion="left_to_right_until_blocked_by_small_hole_wall",
    )
    body["pb_rel_x"] = 0.0
    body["pb_rel_y"] = 0.0
    body["pb_rel_z"] = CAR_BODY_CENTER_Z
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
            mat_wheel,
            "red_car",
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
# Wall with small hole
# ============================================================

def build_wall_with_small_hole(mat_wall, mat_edge):
    parts = []

    # Bottom sill below the small hole.
    bottom_h = max(0.001, SMALL_HOLE_BOTTOM_Z)
    bottom = add_cube(
        "wall_bottom_sill_below_small_hole",
        (WALL_X, TRACK_Y, bottom_h / 2.0),
        (WALL_THICKNESS, WALL_WIDTH_Y, bottom_h),
        material=mat_wall,
    )
    tag(
        bottom,
        bottom.name,
        "wall_solid_part",
        "static_solid",
        "cube",
        "gray",
        False,
        solid=True,
        pb_wall_part="bottom_sill",
        pb_small_hole_id="too_small_car_opening",
    )
    parts.append(bottom)

    # Top lintel above the small hole.
    top_h = WALL_HEIGHT - SMALL_HOLE_TOP_Z
    top = add_cube(
        "wall_top_lintel_above_small_hole",
        (WALL_X, TRACK_Y, SMALL_HOLE_TOP_Z + top_h / 2.0),
        (WALL_THICKNESS, WALL_WIDTH_Y, top_h),
        material=mat_wall,
    )
    tag(
        top,
        top.name,
        "wall_solid_part",
        "static_solid",
        "cube",
        "gray",
        False,
        solid=True,
        pb_wall_part="top_lintel",
        pb_small_hole_id="too_small_car_opening",
    )
    parts.append(top)

    # Near jamb.
    near_jamb_w = SMALL_HOLE_Y_MIN - (-WALL_WIDTH_Y / 2.0)
    near_jamb_y = -WALL_WIDTH_Y / 2.0 + near_jamb_w / 2.0
    near_jamb = add_cube(
        "wall_near_side_jamb_small_hole",
        (WALL_X, near_jamb_y, SMALL_HOLE_BOTTOM_Z + SMALL_HOLE_HEIGHT_Z / 2.0),
        (WALL_THICKNESS, near_jamb_w, SMALL_HOLE_HEIGHT_Z),
        material=mat_wall,
    )
    tag(
        near_jamb,
        near_jamb.name,
        "wall_solid_part",
        "static_solid",
        "cube",
        "gray",
        False,
        solid=True,
        pb_wall_part="near_side_jamb",
        pb_small_hole_id="too_small_car_opening",
    )
    parts.append(near_jamb)

    # Far jamb.
    far_jamb_w = WALL_WIDTH_Y / 2.0 - SMALL_HOLE_Y_MAX
    far_jamb_y = SMALL_HOLE_Y_MAX + far_jamb_w / 2.0
    far_jamb = add_cube(
        "wall_far_side_jamb_small_hole",
        (WALL_X, far_jamb_y, SMALL_HOLE_BOTTOM_Z + SMALL_HOLE_HEIGHT_Z / 2.0),
        (WALL_THICKNESS, far_jamb_w, SMALL_HOLE_HEIGHT_Z),
        material=mat_wall,
    )
    tag(
        far_jamb,
        far_jamb.name,
        "wall_solid_part",
        "static_solid",
        "cube",
        "gray",
        False,
        solid=True,
        pb_wall_part="far_side_jamb",
        pb_small_hole_id="too_small_car_opening",
    )
    parts.append(far_jamb)

    # Bright rim around the small opening.
    rim_t = 0.035

    rim_bottom = add_cube(
        "small_hole_bottom_rim",
        (WALL_LEFT_FACE_X - 0.012, TRACK_Y, SMALL_HOLE_BOTTOM_Z),
        (0.024, SMALL_HOLE_WIDTH_Y, rim_t),
        material=mat_edge,
    )
    tag(
        rim_bottom,
        rim_bottom.name,
        "small_hole_rim",
        "static_solid",
        "cube",
        "light_gray",
        False,
        solid=True,
        pb_small_hole_width_y=SMALL_HOLE_WIDTH_Y,
        pb_car_width=CAR_WIDTH,
    )
    parts.append(rim_bottom)

    rim_top = add_cube(
        "small_hole_top_rim",
        (WALL_LEFT_FACE_X - 0.012, TRACK_Y, SMALL_HOLE_TOP_Z),
        (0.024, SMALL_HOLE_WIDTH_Y, rim_t),
        material=mat_edge,
    )
    tag(
        rim_top,
        rim_top.name,
        "small_hole_rim",
        "static_solid",
        "cube",
        "light_gray",
        False,
        solid=True,
        pb_small_hole_height_z=SMALL_HOLE_HEIGHT_Z,
        pb_car_height=CAR_TOTAL_HEIGHT_ABOVE_TRACK,
    )
    parts.append(rim_top)

    rim_near = add_cube(
        "small_hole_near_vertical_rim",
        (WALL_LEFT_FACE_X - 0.012, SMALL_HOLE_Y_MIN, SMALL_HOLE_BOTTOM_Z + SMALL_HOLE_HEIGHT_Z / 2.0),
        (0.024, rim_t, SMALL_HOLE_HEIGHT_Z),
        material=mat_edge,
    )
    tag(rim_near, rim_near.name, "small_hole_rim", "static_solid", "cube", "light_gray", False, solid=True)
    parts.append(rim_near)

    rim_far = add_cube(
        "small_hole_far_vertical_rim",
        (WALL_LEFT_FACE_X - 0.012, SMALL_HOLE_Y_MAX, SMALL_HOLE_BOTTOM_Z + SMALL_HOLE_HEIGHT_Z / 2.0),
        (0.024, rim_t, SMALL_HOLE_HEIGHT_Z),
        material=mat_edge,
    )
    tag(rim_far, rim_far.name, "small_hole_rim", "static_solid", "cube", "light_gray", False, solid=True)
    parts.append(rim_far)

    return parts


# ============================================================
# Scene
# ============================================================

def build_scene():
    scene = bpy.context.scene
    set_render(scene)

    mat_floor = make_mat("mat_floor_warm", (0.82, 0.80, 0.75), roughness=0.82)
    mat_track = make_mat("mat_track_gray", (0.46, 0.46, 0.46), roughness=0.62)
    mat_track_side = make_mat("mat_track_dark_side", (0.30, 0.30, 0.30), roughness=0.72)
    mat_wall = make_mat("mat_wall_gray", (0.38, 0.40, 0.42), roughness=0.78)
    mat_wall_edge = make_mat("mat_wall_edge_light", (0.60, 0.61, 0.62), roughness=0.68)
    mat_red = make_mat("mat_red_car_body", (0.95, 0.03, 0.02), roughness=0.32)
    mat_wheel = make_mat("mat_black_rubber_wheels", (0.02, 0.02, 0.025), roughness=0.75)
    mat_backdrop = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)

    floor = add_cube(
        "large_floor_base",
        (0.0, 0.0, -0.04),
        (9.2, 4.2, 0.10),
        material=mat_floor,
    )
    tag(floor, floor.name, "ground", "static_solid", "cube", "warm_beige", False, solid=True)

    backdrop = add_cube(
        "rear_backdrop_panel",
        (0.0, 2.25, 1.45),
        (9.4, 0.08, 2.9),
        material=mat_backdrop,
    )
    tag(backdrop, backdrop.name, "background", "static_solid", "cube", "off_white", False, solid=True)

    track = add_cube(
        "straight_flat_solid_track",
        (0.0, TRACK_Y, TRACK_CENTER_Z),
        (TRACK_LENGTH, TRACK_WIDTH, TRACK_THICKNESS),
        material=mat_track,
    )
    tag(
        track,
        track.name,
        "track",
        "static_solid",
        "cube",
        "neutral_gray",
        False,
        solid=True,
        pb_track_kind="straight_flat_solid_track",
        pb_aligned_with_small_hole=True,
    )

    track_side = add_cube(
        "straight_flat_solid_track_dark_side",
        (0.0, TRACK_Y, TRACK_CENTER_Z - 0.035),
        (TRACK_LENGTH, TRACK_WIDTH + 0.06, 0.035),
        material=mat_track_side,
    )
    tag(track_side, track_side.name, "track_side_shadow", "static_solid", "cube", "dark_gray", False, solid=True)

    wall_parts = build_wall_with_small_hole(mat_wall, mat_wall_edge)

    body, car_parts = build_car(
        prefix="red_wheeled_car",
        x=X_START,
        y=TRACK_Y,
        mat_body=mat_red,
        mat_wheel=mat_wheel,
    )

    bpy.ops.object.light_add(type="AREA", location=(-3.8, -4.2, 5.2))
    key_light = bpy.context.object
    key_light.name = "large_softbox_light"
    key_light.data.energy = 910
    key_light.data.size = 5.8

    bpy.ops.object.light_add(type="POINT", location=(3.7, -2.8, 3.0))
    fill_light = bpy.context.object
    fill_light.name = "right_fill_light"
    fill_light.data.energy = 135

    # Camera:
    # Same family as 0017/0018: level view, left face of the wall visible.
    # The small opening is visible, but obviously too small for the car.
    bpy.ops.object.camera_add(location=(-0.45, -8.35, 1.42))
    camera = bpy.context.object
    camera.name = "camera_level_view_small_hole_left_face_visible"
    camera.data.lens = 31
    look_at(camera, (1.05, 0.02, 0.58))
    camera.data.dof.use_dof = False
    scene.camera = camera

    return {
        "scene": scene,
        "track": track,
        "wall_parts": wall_parts,
        "car_body": body,
        "car_parts": car_parts,
    }


# ============================================================
# Animation / semantic states
# ============================================================

def set_car_state(body, x):
    front_x = x + CAR_LENGTH / 2.0
    gap_to_wall = WALL_LEFT_FACE_X - front_x

    car_too_wide = CAR_WIDTH > SMALL_HOLE_WIDTH_Y
    car_too_tall = CAR_TOTAL_HEIGHT_ABOVE_TRACK > SMALL_HOLE_HEIGHT_Z

    if x < X_CONTACT - 1e-6:
        phase = "approaching_too_small_wall_hole"
        contact_state = "not_yet_in_contact"
        motion_state = "moving"
    else:
        phase = "blocked_by_wall_with_too_small_hole"
        contact_state = "contacting_wall_around_small_hole"
        motion_state = "stopped"

    body["pb_state"] = phase
    body["pb_contact_state"] = contact_state
    body["pb_motion_state"] = motion_state
    body["pb_gap_to_wall"] = float(gap_to_wall)
    body["pb_front_x"] = float(front_x)
    body["pb_small_hole_smaller_than_car_width"] = bool(car_too_wide)
    body["pb_small_hole_smaller_than_car_height"] = bool(car_too_tall)
    body["pb_should_not_pass_through_small_hole"] = True
    body["pb_no_shrinking_allowed"] = True
    body["pb_no_penetration"] = bool(front_x <= WALL_LEFT_FACE_X + 1e-6)
    body["pb_expected_final_behavior"] = "stop_at_wall_because_hole_too_small"


def animate_scene(scene, track, wall_parts, car_body, car_parts):
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        x = car_x_at_frame(frame)
        set_car_parts(car_parts, x, TRACK_Y, frame)
        set_car_state(car_body, x)

        for obj in wall_parts:
            obj["pb_state"] = "static_wall_with_too_small_hole"
            obj["pb_small_hole_width_y"] = SMALL_HOLE_WIDTH_Y
            obj["pb_small_hole_height_z"] = SMALL_HOLE_HEIGHT_Z
            obj["pb_car_width"] = CAR_WIDTH
            obj["pb_car_height"] = CAR_TOTAL_HEIGHT_ABOVE_TRACK
            obj["pb_hole_smaller_than_car"] = True
            obj["pb_solid_wall_parts_forbid_penetration"] = True

        track["pb_state"] = "static_low_flat_track_aligned_with_too_small_hole"

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
                "A single red wheeled car starts on the left and drives to the right along a low flat straight solid track. "
                "On the right side there is a gray wall with a small rectangular door or hole aligned with the track. "
                "The opening is clearly smaller than the car in both width and height. "
                "The view is level and shows the left face of the wall and the small opening. "
                "The car should approach the small opening but must not pass through it because it is too small. "
                "The car should be blocked by the solid wall around the opening and come to a stop. "
                "The car must not shrink, squeeze through, clip through, pass through any solid wall part, emerge on the far side, disappear, duplicate, or change size. "
                "The car must keep its identity, color, wheels, size, and count throughout the sequence."
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
        track=objs["track"],
        wall_parts=objs["wall_parts"],
        car_body=objs["car_body"],
        car_parts=objs["car_parts"],
    )

    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, OPTIONAL_IMPACT_FRAME, OPTIONAL_FRAME_PATH)
    render_png(scene, OPTIONAL_STOPPED_FRAME, OPTIONAL_FRAME_02B_PATH)

    render_animation(scene)
    write_task_json()
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("Output:", OUT_DIR)
    print("RULES:")
    print(" - red wheeled car drives left to right")
    print(" - wall has a small rectangular opening")
    print(" - opening is smaller than the car")
    print(" - car must stop and must not squeeze/pass through")
    print(" - no shrinking / no penetration / no tunneling")
    print(" - level view shows wall left face and small opening")
    print("=" * 100)


if __name__ == "__main__":
    main()
