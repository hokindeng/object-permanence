# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

ITEM_ID = "PB_DOUBLE_DOOR_OPENS_CAR_PASSES_0025"

FPS = 24
FRAME_START = 1
FRAME_END = 120

# ============================================================
# Geometry / timing
# ============================================================

TRACK_TOP_Z = 0.08
TRACK_THICKNESS = 0.08
TRACK_CENTER_Z = TRACK_TOP_Z - TRACK_THICKNESS / 2.0
TRACK_LENGTH = 8.8
TRACK_WIDTH = 0.44
TRACK_Y = 0.0

CAR_LENGTH = 0.62
CAR_WIDTH = 0.34
CAR_BODY_HEIGHT = 0.24
WHEEL_RADIUS = 0.080
WHEEL_THICKNESS = 0.065
WHEEL_DIAMETER = WHEEL_RADIUS * 2.0

WHEEL_CENTER_Z = TRACK_TOP_Z + WHEEL_RADIUS
BODY_BOTTOM_Z = TRACK_TOP_Z + WHEEL_DIAMETER
CAR_BODY_CENTER_Z = BODY_BOTTOM_Z + CAR_BODY_HEIGHT / 2.0
CAR_TOP_Z = TRACK_TOP_Z + WHEEL_DIAMETER + CAR_BODY_HEIGHT

# Constant car motion: no easing, no waiting.
X_START = -3.20
SPEED_X = 0.052

# Double door in the middle of the track.
GATE_X = 0.92
DOOR_THICKNESS_X = 0.10
DOOR_TOTAL_WIDTH_Y = 1.08
DOOR_HALF_WIDTH_Y = DOOR_TOTAL_WIDTH_Y / 2.0
DOOR_PANEL_WIDTH_Y = DOOR_HALF_WIDTH_Y
DOOR_HEIGHT = 0.88
DOOR_CENTER_Z = TRACK_TOP_Z + DOOR_HEIGHT / 2.0

GATE_FRAME_HEIGHT = 1.16
GATE_POST_WIDTH = 0.10

# Doors start closed, then open before the car arrives.
DOOR_OPEN_START_FRAME = 20
DOOR_OPEN_END_FRAME = 60
DOOR_OPEN_ANGLE_DEG = 82.0

OPTIONAL_DOOR_OPENING_FRAME = 42
OPTIONAL_CAR_PASSING_FRAME = 82

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

OUT_DIR = os.path.join(PROJECT_ROOT, "permanence_blender_outputs", ITEM_ID)
FRAMES_DIR = os.path.join(OUT_DIR, "frames")
SCENE_FILE = os.path.join(OUT_DIR, f"{ITEM_ID}_scene.blend")
TASK_JSON_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_task.json")

INPUT_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_input_frame_01.png")
OPTIONAL_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_doors_opening_frame_02.png")
OPTIONAL_FRAME_02B_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_car_passing_frame_02B.png")


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


def add_cube(name, location, dimensions, material=None, role="static_solid", color_name="gray", is_dynamic=False, solid=True):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
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
        "dynamic_object" if is_dynamic else ("static_solid" if solid else "non_solid_marker"),
        "cube",
        color_name,
        is_dynamic,
        solid=solid,
    )
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
# Materials
# ============================================================

MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor_warm", (0.82, 0.80, 0.75), roughness=0.82)
    MATS["track"] = make_mat("mat_track_gray", (0.46, 0.46, 0.46), roughness=0.62)
    MATS["track_dark"] = make_mat("mat_track_dark_side", (0.30, 0.30, 0.30), roughness=0.72)
    MATS["door"] = make_mat("mat_double_door_gray", (0.36, 0.38, 0.40), roughness=0.76)
    MATS["door_edge"] = make_mat("mat_double_door_edge_light", (0.62, 0.63, 0.64), roughness=0.68)
    MATS["red"] = make_mat("mat_red_car_body", (0.95, 0.03, 0.02), roughness=0.32)
    MATS["wheel"] = make_mat("mat_black_wheels", (0.02, 0.02, 0.025), roughness=0.75)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)


# ============================================================
# Object builders
# ============================================================

def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube(
        "large_floor_base",
        (0.0, 0.0, -0.05),
        (9.6, 4.4, 0.10),
        material=MATS["floor"],
        role="ground",
        color_name="warm_beige",
    )

    add_cube(
        "rear_backdrop_panel",
        (0.0, 2.32, 1.45),
        (9.8, 0.08, 2.90),
        material=MATS["backdrop"],
        role="background",
        color_name="off_white",
    )

    bpy.ops.object.light_add(type="AREA", location=(-3.8, -4.4, 5.4))
    key = bpy.context.object
    key.name = "large_softbox_light"
    key.data.energy = 930
    key.data.size = 5.8

    bpy.ops.object.light_add(type="POINT", location=(3.7, -2.8, 3.0))
    fill = bpy.context.object
    fill.name = "right_fill_light"
    fill.data.energy = 140

    return scene


def build_track():
    track = add_cube(
        "straight_flat_solid_track",
        (0.0, TRACK_Y, TRACK_CENTER_Z),
        (TRACK_LENGTH, TRACK_WIDTH, TRACK_THICKNESS),
        material=MATS["track"],
        role="track",
        color_name="neutral_gray",
    )
    track["pb_track_kind"] = "straight_flat_solid_track"
    track["pb_supports_car"] = True

    side = add_cube(
        "straight_flat_solid_track_dark_side",
        (0.0, TRACK_Y, TRACK_CENTER_Z - 0.035),
        (TRACK_LENGTH, TRACK_WIDTH + 0.06, 0.035),
        material=MATS["track_dark"],
        role="track_side_shadow",
        color_name="dark_gray",
    )

    return [track, side]


def build_car():
    parts = []

    body = add_cube(
        "red_wheeled_car_body",
        (X_START, TRACK_Y, CAR_BODY_CENTER_Z),
        (CAR_LENGTH, CAR_WIDTH, CAR_BODY_HEIGHT),
        material=MATS["red"],
        role="target",
        color_name="red",
        is_dynamic=True,
        solid=True,
    )
    body["pb_vehicle_type"] = "wheeled_car"
    body["pb_vehicle_id"] = "red_car"
    body["pb_rel_x"] = 0.0
    body["pb_rel_y"] = 0.0
    body["pb_rel_z"] = CAR_BODY_CENTER_Z
    body["pb_constant_speed_x"] = SPEED_X
    parts.append(body)

    wheel_offsets = [
        (-CAR_LENGTH * 0.33, -CAR_WIDTH * 0.58, WHEEL_CENTER_Z, "front_near"),
        ( CAR_LENGTH * 0.33, -CAR_WIDTH * 0.58, WHEEL_CENTER_Z, "rear_near"),
        (-CAR_LENGTH * 0.33,  CAR_WIDTH * 0.58, WHEEL_CENTER_Z, "front_far"),
        ( CAR_LENGTH * 0.33,  CAR_WIDTH * 0.58, WHEEL_CENTER_Z, "rear_far"),
    ]

    for dx, dy, dz, side in wheel_offsets:
        wheel = add_wheel(
            f"red_wheeled_car_wheel_{side}",
            (X_START + dx, TRACK_Y + dy, dz),
            MATS["wheel"],
            "red_car",
            side,
        )
        wheel["pb_rel_x"] = dx
        wheel["pb_rel_y"] = dy
        wheel["pb_rel_z"] = dz
        parts.append(wheel)

    return body, parts


def build_double_door():
    objs = []

    # Side posts.
    for y, side_name in [(-DOOR_HALF_WIDTH_Y, "near"), (DOOR_HALF_WIDTH_Y, "far")]:
        post = add_cube(
            f"double_door_{side_name}_hinge_post",
            (GATE_X, y, GATE_FRAME_HEIGHT / 2.0),
            (DOOR_THICKNESS_X * 1.25, GATE_POST_WIDTH, GATE_FRAME_HEIGHT),
            material=MATS["door_edge"],
            role="door_hinge_post",
            color_name="light_gray",
            is_dynamic=False,
            solid=True,
        )
        post["pb_door_frame"] = True
        objs.append(post)

    # Top beam.
    top = add_cube(
        "double_door_top_beam",
        (GATE_X, TRACK_Y, GATE_FRAME_HEIGHT),
        (DOOR_THICKNESS_X * 1.25, DOOR_TOTAL_WIDTH_Y + 0.18, 0.10),
        material=MATS["door_edge"],
        role="door_top_frame",
        color_name="light_gray",
        is_dynamic=False,
        solid=True,
    )
    top["pb_door_frame"] = True
    objs.append(top)

    # Two dynamic door panels.
    near_panel = add_cube(
        "double_door_near_panel",
        (GATE_X, -DOOR_PANEL_WIDTH_Y / 2.0, DOOR_CENTER_Z),
        (DOOR_THICKNESS_X, DOOR_PANEL_WIDTH_Y, DOOR_HEIGHT),
        material=MATS["door"],
        role="double_door_panel",
        color_name="gray",
        is_dynamic=True,
        solid=True,
    )
    near_panel["pb_panel_side"] = "near"
    near_panel["pb_hinge_y"] = -DOOR_HALF_WIDTH_Y
    near_panel["pb_closed_state_blocks_path"] = True
    near_panel["pb_opens_before_car_arrives"] = True
    objs.append(near_panel)

    far_panel = add_cube(
        "double_door_far_panel",
        (GATE_X, DOOR_PANEL_WIDTH_Y / 2.0, DOOR_CENTER_Z),
        (DOOR_THICKNESS_X, DOOR_PANEL_WIDTH_Y, DOOR_HEIGHT),
        material=MATS["door"],
        role="double_door_panel",
        color_name="gray",
        is_dynamic=True,
        solid=True,
    )
    far_panel["pb_panel_side"] = "far"
    far_panel["pb_hinge_y"] = DOOR_HALF_WIDTH_Y
    far_panel["pb_closed_state_blocks_path"] = True
    far_panel["pb_opens_before_car_arrives"] = True
    objs.append(far_panel)

    # Light center seam marker at first frame; it also opens with panels.
    seam = add_cube(
        "double_door_center_seam_marker",
        (GATE_X - 0.012, TRACK_Y, DOOR_CENTER_Z),
        (0.024, 0.035, DOOR_HEIGHT),
        material=MATS["door_edge"],
        role="door_center_seam_marker",
        color_name="light_gray",
        is_dynamic=True,
        solid=True,
    )
    seam["pb_center_seam"] = True
    objs.append(seam)

    return near_panel, far_panel, seam, objs


def setup_camera(scene):
    # Level-ish view, slightly raised to read the door opening and the car wheels.
    bpy.ops.object.camera_add(location=(-0.55, -8.45, 1.58))
    camera = bpy.context.object
    camera.name = "camera_level_view_double_door"
    camera.data.lens = 31
    look_at(camera, (0.60, 0.0, 0.58))
    camera.data.dof.use_dof = False
    scene.camera = camera


# ============================================================
# Motion
# ============================================================

def car_x_at_frame(frame):
    return X_START + SPEED_X * (frame - FRAME_START)


def door_open_fraction(frame):
    if frame <= DOOR_OPEN_START_FRAME:
        return 0.0
    if frame >= DOOR_OPEN_END_FRAME:
        return 1.0
    t = (frame - DOOR_OPEN_START_FRAME) / float(DOOR_OPEN_END_FRAME - DOOR_OPEN_START_FRAME)
    return smooth01(t)


def door_angle(frame):
    return math.radians(DOOR_OPEN_ANGLE_DEG) * door_open_fraction(frame)


def set_car_parts(parts, base_x, frame):
    dist = base_x - X_START
    roll = -dist / max(1e-6, WHEEL_RADIUS)

    for obj in parts:
        rx = obj.get("pb_rel_x", 0.0)
        ry = obj.get("pb_rel_y", 0.0)
        rz = obj.get("pb_rel_z", obj.location.z)

        obj.location = (base_x + rx, TRACK_Y + ry, rz)

        if obj.get("pb_role") == "vehicle_wheel":
            obj.rotation_euler = (math.pi / 2.0, roll, 0.0)
            obj.keyframe_insert(data_path="rotation_euler", frame=frame)

        obj.keyframe_insert(data_path="location", frame=frame)


def set_door_panel(panel, side, frame):
    a = door_angle(frame)
    half = DOOR_PANEL_WIDTH_Y / 2.0

    if side == "near":
        hinge_y = -DOOR_HALF_WIDTH_Y
        # Closed center offset is +half in Y. Rotate toward negative X.
        center_x = GATE_X - math.sin(a) * half
        center_y = hinge_y + math.cos(a) * half
        zrot = a
    else:
        hinge_y = DOOR_HALF_WIDTH_Y
        # Closed center offset is -half in Y. Rotate toward negative X.
        center_x = GATE_X - math.sin(a) * half
        center_y = hinge_y - math.cos(a) * half
        zrot = -a

    panel.location = (center_x, center_y, DOOR_CENTER_Z)
    panel.rotation_euler = (0.0, 0.0, zrot)
    panel.keyframe_insert(data_path="location", frame=frame)
    panel.keyframe_insert(data_path="rotation_euler", frame=frame)

    if frame <= DOOR_OPEN_START_FRAME:
        state = "closed_blocking_path"
    elif frame < DOOR_OPEN_END_FRAME:
        state = "swinging_open_before_car_arrives"
    else:
        state = "open_clear_path"

    panel["pb_state"] = state
    panel["pb_open_fraction"] = float(door_open_fraction(frame))
    panel["pb_open_angle_degrees"] = float(math.degrees(a))
    panel["pb_allows_passage_when_open"] = bool(door_open_fraction(frame) >= 0.98)
    panel["pb_blocks_path_when_closed"] = True


def set_seam_marker(seam, frame):
    # Seam is visible at closed state; once doors open, move it slightly upward and hide in render.
    # Keeping it animated avoids confusion in recorder.
    frac = door_open_fraction(frame)
    seam.location = (GATE_X - 0.014, TRACK_Y, DOOR_CENTER_Z + frac * 0.02)
    seam.scale = (1.0, max(0.05, 1.0 - frac), 1.0)
    seam.keyframe_insert(data_path="location", frame=frame)
    seam.keyframe_insert(data_path="scale", frame=frame)
    seam["pb_state"] = "center_seam_closed_visible" if frac < 0.2 else "center_seam_opening"


def animate_scene(scene, car_body, car_parts, near_panel, far_panel, seam, static_objs):
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        x = car_x_at_frame(frame)
        set_car_parts(car_parts, x, frame)

        set_door_panel(near_panel, "near", frame)
        set_door_panel(far_panel, "far", frame)
        set_seam_marker(seam, frame)

        car_front_x = x + CAR_LENGTH / 2.0
        car_rear_x = x - CAR_LENGTH / 2.0
        gate_left_face_x = GATE_X - DOOR_THICKNESS_X / 2.0
        gate_right_face_x = GATE_X + DOOR_THICKNESS_X / 2.0
        frac = door_open_fraction(frame)

        if car_front_x < gate_left_face_x:
            phase = "approaching_closed_then_opening_double_door"
        elif car_rear_x <= gate_right_face_x:
            phase = "passing_between_open_double_doors"
        else:
            phase = "passed_open_double_door"

        car_body["pb_state"] = phase
        car_body["pb_motion_state"] = "constant_speed_driving"
        car_body["pb_constant_speed_x"] = SPEED_X
        car_body["pb_doors_open_before_arrival"] = bool(frac >= 0.98)
        car_body["pb_passes_between_open_doors"] = bool(frac >= 0.98)
        car_body["pb_no_penetration_of_closed_doors"] = True
        car_body["pb_should_not_stop_and_wait"] = True

        for obj in static_objs:
            obj["pb_state"] = "static_track_or_door_frame"
            obj["pb_scene_kind"] = "double_door_opens_car_passes"
            obj["pb_gate_x"] = GATE_X
            obj["pb_car_top_z"] = CAR_TOP_Z

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
                "A single red wheeled car drives from left to right at a constant speed on a low flat straight solid track. "
                "In the middle of the track there is a gray double door. In the first frame the two door panels are closed and block the path. "
                "Before the car reaches the door, both door panels slowly swing open to the sides, creating a clear doorway. "
                "When the car reaches the doorway, it should pass between the opened door panels. "
                "The car must not pass through the closed door panels, overlap the panels, stop and wait unnaturally, teleport, disappear, duplicate, or change size. "
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

    scene = build_base_scene()
    static_objs = []
    static_objs.extend(build_track())

    car_body, car_parts = build_car()
    near_panel, far_panel, seam, door_objs = build_double_door()
    static_objs.extend(door_objs)

    setup_camera(scene)

    animate_scene(
        scene=scene,
        car_body=car_body,
        car_parts=car_parts,
        near_panel=near_panel,
        far_panel=far_panel,
        seam=seam,
        static_objs=static_objs,
    )

    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, OPTIONAL_DOOR_OPENING_FRAME, OPTIONAL_FRAME_PATH)
    render_png(scene, OPTIONAL_CAR_PASSING_FRAME, OPTIONAL_FRAME_02B_PATH)

    render_animation(scene)
    write_task_json()
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("Output:", OUT_DIR)
    print("RULES:")
    print(" - double door starts closed")
    print(" - both panels slowly swing open before the car arrives")
    print(" - car moves at constant speed")
    print(" - car passes between opened door panels, not through the solid panels")
    print("=" * 100)


if __name__ == "__main__":
    main()
