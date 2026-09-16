# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

ITEM_ID = "PB_RAMP_OPEN_RIGHT_GATED_BOX_BALL_ROLLS_TO_CATCH_BOX_0089"

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


# ============================================================
# Geometry constants
# ============================================================

RAMP_X0 = -2.50
RAMP_X1 = 1.60
RAMP_Z0 = 1.28
RAMP_Z1 = 0.16
RAMP_WIDTH = 0.90

BALL_RADIUS = 0.12
BALL_START_X = -2.12
BALL_RAMP_END_X = 1.60
BALL_FINAL_X = 2.25
BALL_Y = 0.0

BOX_LEFT_X = -2.42
BOX_RIGHT_OPEN_X = -0.98
BOX_CENTER_X = (BOX_LEFT_X + BOX_RIGHT_OPEN_X) / 2.0
BOX_FRONT_Y = -0.62
BOX_BACK_Y = 0.58
BOX_DOOR_WIDTH = (BOX_RIGHT_OPEN_X - BOX_LEFT_X) / 2.0
BOX_DOOR_HEIGHT = 0.96
BOX_DOOR_CENTER_Z = 1.22

CATCH_BOX_LEFT_X = RAMP_X1
CATCH_BOX_CENTER_X = 2.25
CATCH_BOX_LENGTH = 1.30
CATCH_BOX_WIDTH = 1.10
CATCH_FLOOR_TOP_Z = 0.16
CATCH_BALL_Z = CATCH_FLOOR_TOP_Z + BALL_RADIUS

RAMP_THETA = math.atan2(RAMP_Z0 - RAMP_Z1, RAMP_X1 - RAMP_X0)
BALL_VERTICAL_OFFSET_ON_RAMP = BALL_RADIUS / math.cos(RAMP_THETA)


def ramp_surface_z(x: float) -> float:
    t = (x - RAMP_X0) / (RAMP_X1 - RAMP_X0)
    return RAMP_Z0 + (RAMP_Z1 - RAMP_Z0) * t


def ball_z_on_ramp(x: float) -> float:
    return ramp_surface_z(x) + BALL_VERTICAL_OFFSET_ON_RAMP


# ============================================================
# Blender helpers
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
    MATS["ramp"] = make_mat("mat_ramp", (0.62, 0.64, 0.68), 0.76)
    MATS["box"] = make_mat("mat_box", (0.70, 0.71, 0.74), 0.76)
    MATS["door"] = make_mat("mat_door", (0.45, 0.48, 0.54), 0.82)
    MATS["support"] = make_mat("mat_support", (0.15, 0.17, 0.20), 0.60)
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
    tag(
        obj,
        name,
        role,
        "dynamic_object" if is_dynamic else "static_solid",
        "cube",
        color_name,
        is_dynamic,
        solid=solid,
    )
    return obj


def add_ball(name, radius, location, material, color_name):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=48, ring_count=24)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(
        obj,
        name,
        "target_ball",
        "dynamic_object",
        "sphere",
        color_name,
        True,
        solid=True,
        pb_radius=radius,
        pb_expected_track="starts_inside_open_right_gated_box_on_ramp_then_rolls_to_open_catch_box",
        pb_identity_preserved=True,
    )
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


def make_root(name, loc, role):
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=loc)
    obj = bpy.context.object
    obj.name = name
    tag(obj, name, role, "dynamic_object", "empty", "none", True, solid=False)
    return obj


def parent_to_local(obj, parent, local_location):
    obj.parent = parent
    obj.location = local_location
    return obj


# ============================================================
# Component-first scene construction
# ============================================================

def add_ramp_wedge():
    y0 = -RAMP_WIDTH / 2.0
    y1 = RAMP_WIDTH / 2.0
    base_z = 0.02

    verts = [
        (RAMP_X0, y0, RAMP_Z0),
        (RAMP_X1, y0, RAMP_Z1),
        (RAMP_X1, y1, RAMP_Z1),
        (RAMP_X0, y1, RAMP_Z0),
        (RAMP_X0, y0, base_z),
        (RAMP_X1, y0, base_z),
        (RAMP_X1, y1, base_z),
        (RAMP_X0, y1, base_z),
    ]

    faces = [
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ]

    mesh = bpy.data.meshes.new("single_continuous_sloped_ramp_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    obj = bpy.data.objects.new("single_continuous_sloped_ramp", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(MATS["ramp"])

    tag(
        obj,
        "single_continuous_sloped_ramp",
        "sloped_ramp",
        "static_solid",
        "wedge_ramp",
        "gray",
        False,
        solid=True,
        pb_surface_start=(RAMP_X0, RAMP_Z0),
        pb_surface_end=(RAMP_X1, RAMP_Z1),
        pb_ball_contact_mode="ball_center_z_equals_ramp_surface_plus_radius_over_cos_theta",
    )
    return obj


def setup_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (10.4, 5.8, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 2.15, 1.55), (10.4, 0.08, 3.10), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.0, -3.8, 4.8))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 900
    key.data.size = 4.8

    bpy.ops.object.light_add(type="POINT", location=(2.9, -1.6, 2.6))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 100

    # Pulled farther back, slightly higher, and rotated toward the viewer-right side.
    bpy.ops.object.camera_add(location=(1.15, -8.80, 3.55))
    cam = bpy.context.object
    cam.name = "camera_main"
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 5.95
    look_at(cam, (0.20, 0.0, 0.68))
    scene.camera = cam
    return scene


def build_fixed_components_first():
    # 1. Ramp.
    add_ramp_wedge()

    # 2. Top gated enclosure. Right side is deliberately OPEN.
    # No right side wall exists. The ball exits to the right along the ramp.
    add_cube(
        "gated_box_back_wall",
        (BOX_CENTER_X, BOX_BACK_Y, 1.28),
        (BOX_RIGHT_OPEN_X - BOX_LEFT_X + 0.10, 0.08, 0.82),
        MATS["box"],
        "gated_box_back_wall",
        "gray",
    )

    add_cube(
        "gated_box_left_side_wall",
        (BOX_LEFT_X - 0.04, 0.0, 1.28),
        (0.08, 1.22, 0.82),
        MATS["box"],
        "gated_box_left_side_wall",
        "gray",
    )

    add_cube(
        "gated_box_front_lintel",
        (BOX_CENTER_X, BOX_FRONT_Y, 1.78),
        (BOX_RIGHT_OPEN_X - BOX_LEFT_X + 0.10, 0.12, 0.08),
        MATS["support"],
        "front_door_lintel",
        "dark_gray",
    )

    # Open right exit: only a small top marker, no wall.
    right_marker = add_cube(
        "open_right_exit_marker_not_a_wall",
        (BOX_RIGHT_OPEN_X + 0.03, 0.55, 1.78),
        (0.06, 0.14, 0.08),
        MATS["support"],
        "open_right_exit_marker",
        "dark_gray",
    )
    right_marker["pb_right_side_is_open_exit"] = True
    right_marker["pb_not_a_blocking_wall"] = True

    # 3. Door hinges at front plane.
    add_cylinder_between(
        "left_door_vertical_hinge",
        (BOX_LEFT_X, BOX_FRONT_Y, 0.70),
        (BOX_LEFT_X, BOX_FRONT_Y, 1.73),
        0.035,
        MATS["support"],
        "left_door_hinge",
        "dark_gray",
    )
    add_cylinder_between(
        "right_door_vertical_hinge",
        (BOX_RIGHT_OPEN_X, BOX_FRONT_Y, 0.70),
        (BOX_RIGHT_OPEN_X, BOX_FRONT_Y, 1.73),
        0.035,
        MATS["support"],
        "right_door_hinge",
        "dark_gray",
    )

    # 4. Lower open-top catch box. Left side is open for entry from ramp.
    wall_t = 0.08
    wall_h = 0.46
    floor_thick = 0.16
    floor_center_z = CATCH_FLOOR_TOP_Z - floor_thick / 2.0

    add_cube(
        "open_catch_box_floor",
        (CATCH_BOX_CENTER_X, 0.0, floor_center_z),
        (CATCH_BOX_LENGTH, CATCH_BOX_WIDTH, floor_thick),
        MATS["box"],
        "catch_box_floor",
        "gray",
    )
    add_cube(
        "open_catch_box_back_wall",
        (CATCH_BOX_CENTER_X, CATCH_BOX_WIDTH / 2.0 - wall_t / 2.0, CATCH_FLOOR_TOP_Z + wall_h / 2.0),
        (CATCH_BOX_LENGTH, wall_t, wall_h),
        MATS["box"],
        "catch_box_back_wall",
        "gray",
    )
    add_cube(
        "open_catch_box_front_low_wall",
        (CATCH_BOX_CENTER_X, -CATCH_BOX_WIDTH / 2.0 + wall_t / 2.0, CATCH_FLOOR_TOP_Z + 0.15),
        (CATCH_BOX_LENGTH, wall_t, 0.30),
        MATS["box"],
        "catch_box_front_low_wall",
        "gray",
    )
    add_cube(
        "open_catch_box_right_wall",
        (CATCH_BOX_CENTER_X + CATCH_BOX_LENGTH / 2.0 - wall_t / 2.0, 0.0, CATCH_FLOOR_TOP_Z + wall_h / 2.0),
        (wall_t, CATCH_BOX_WIDTH, wall_h),
        MATS["box"],
        "catch_box_right_wall",
        "gray",
    )

    # No left wall; ramp enters directly.
    entry = add_cube(
        "catch_box_left_open_entry_marker_not_a_wall",
        (CATCH_BOX_LEFT_X, CATCH_BOX_WIDTH / 2.0 - 0.05, CATCH_FLOOR_TOP_Z + 0.04),
        (0.08, 0.10, 0.08),
        MATS["support"],
        "open_entry_marker",
        "dark_gray",
    )
    entry["pb_left_side_open_for_ball_entry"] = True
    entry["pb_not_a_blocking_wall"] = True


def build_double_doors_after_fixed_components():
    left_root = make_root("left_outward_door_hinge_root", (BOX_LEFT_X, BOX_FRONT_Y, BOX_DOOR_CENTER_Z), "left_outward_door_hinge_root")
    right_root = make_root("right_outward_door_hinge_root", (BOX_RIGHT_OPEN_X, BOX_FRONT_Y, BOX_DOOR_CENTER_Z), "right_outward_door_hinge_root")

    left_leaf = add_cube(
        "left_outward_opening_door_leaf",
        (0.0, 0.0, 0.0),
        (BOX_DOOR_WIDTH, 0.06, BOX_DOOR_HEIGHT),
        MATS["door"],
        "left_outward_opening_door_leaf",
        "gray",
        is_dynamic=True,
    )

    right_leaf = add_cube(
        "right_outward_opening_door_leaf",
        (0.0, 0.0, 0.0),
        (BOX_DOOR_WIDTH, 0.06, BOX_DOOR_HEIGHT),
        MATS["door"],
        "right_outward_opening_door_leaf",
        "gray",
        is_dynamic=True,
    )

    # Closed state:
    # left door spans BOX_LEFT_X -> BOX_CENTER_X.
    # right door spans BOX_CENTER_X -> BOX_RIGHT_OPEN_X.
    parent_to_local(left_leaf, left_root, (BOX_DOOR_WIDTH / 2.0, 0.0, 0.0))
    parent_to_local(right_leaf, right_root, (-BOX_DOOR_WIDTH / 2.0, 0.0, 0.0))

    for obj in [left_leaf, right_leaf]:
        obj["pb_door_opens_outward_toward_camera"] = True
        obj["pb_door_hinged_not_floating"] = True
        obj["pb_door_front_plane_y"] = BOX_FRONT_Y
        obj["pb_ball_path_y"] = BALL_Y
        obj["pb_separated_from_ball_path_in_y"] = True

    return left_root, right_root


def place_ball_last():
    x = BALL_START_X
    z = ball_z_on_ramp(x)

    ball = add_ball(
        "orange_ball_inside_open_right_gated_box_on_ramp",
        BALL_RADIUS,
        (x, BALL_Y, z),
        MATS["orange"],
        "orange",
    )

    ball["pb_initial_container"] = "top_gated_box_with_open_right_exit"
    ball["pb_initial_state"] = "visible_first_frame_with_double_doors_open"
    ball["pb_final_container"] = "lower_open_top_catch_box"
    ball["pb_no_right_wall_blocking_exit"] = True
    ball["pb_starts_moving_after_frame_1"] = True
    ball["pb_motion_profile"] = "accelerated_down_ramp_x_proportional_to_t_squared"
    ball["pb_center_z_formula"] = "ramp_surface_z(x) + ball_radius / cos(ramp_angle)"

    return ball


# ============================================================
# Animation
# ============================================================

def door_open_angle_for_frame(frame: int) -> float:
    open_angle = math.radians(110.0)
    closed_angle = 0.0

    # Frame 1 is open.
    if frame <= 1:
        return open_angle

    # Doors close quickly while ball already begins rolling.
    if frame <= 18:
        t = (frame - 1) / 17.0
        return open_angle + (closed_angle - open_angle) * t

    # Hidden interval.
    if frame <= 108:
        return closed_angle

    # Reopen at the end.
    if frame <= 120:
        t = (frame - 108) / 12.0
        return closed_angle + (open_angle - closed_angle) * t

    return open_angle


def ball_position_for_frame(frame: int):
    if frame <= 1:
        x = BALL_START_X
        z = ball_z_on_ramp(x)
        return x, BALL_Y, z

    # Accelerated ramp rolling from frame 2.
    if frame <= 88:
        t = (frame - 1) / (88 - 1)
        t = max(0.0, min(1.0, t))

        # x ∝ t^2: starts slow, then accelerates.
        x = BALL_START_X + (BALL_RAMP_END_X - BALL_START_X) * (t * t)
        z = ball_z_on_ramp(x)
        return x, BALL_Y, z

    # Settles into the open-top catch box.
    if frame <= 104:
        t = (frame - 88) / (104 - 88)
        t = max(0.0, min(1.0, t))
        smooth = t * (2.0 - t)

        x = BALL_RAMP_END_X + (BALL_FINAL_X - BALL_RAMP_END_X) * smooth
        z = CATCH_BALL_Z
        return x, BALL_Y, z

    return BALL_FINAL_X, BALL_Y, CATCH_BALL_Z


def animate_scene(scene, left_root, right_root, ball):
    travelled = 0.0
    last_x = BALL_START_X

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        # Doors open outward toward camera:
        # left door rotates negative; right door rotates positive.
        a = door_open_angle_for_frame(frame)
        left_root.rotation_euler = (0.0, 0.0, -a)
        right_root.rotation_euler = (0.0, 0.0, a)
        left_root.keyframe_insert(data_path="rotation_euler", frame=frame)
        right_root.keyframe_insert(data_path="rotation_euler", frame=frame)

        x, y, z = ball_position_for_frame(frame)

        if frame == FRAME_START:
            travelled = 0.0
        else:
            travelled += abs(x - last_x)

        ball.location = (x, y, z)
        ball.rotation_euler = (0.0, -travelled / BALL_RADIUS, 0.0)
        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)

        if frame <= 1:
            ball["pb_state"] = "visible_inside_top_gated_box_doors_open"
        elif frame <= 88:
            ball["pb_state"] = "accelerating_down_slope_after_first_frame"
        elif frame <= 104:
            ball["pb_state"] = "entering_lower_open_top_catch_box"
        else:
            ball["pb_state"] = "resting_inside_lower_open_top_catch_box"

        last_x = x

    scene.frame_set(FRAME_START)


def build_scene():
    scene = setup_base_scene()

    # Required order:
    # fixed scene -> doors -> ball -> animation
    build_fixed_components_first()
    left_root, right_root = build_double_doors_after_fixed_components()
    ball = place_ball_last()
    animate_scene(scene, left_root, right_root, ball)

    scene["pb_animation_type"] = "keyframed_geometric_motion_with_gravity_like_acceleration"
    scene["pb_not_rigidbody_bake"] = True
    scene["pb_component_order"] = "fixed_scene_components_then_doors_then_ball"
    scene["pb_right_side_of_top_box_is_open"] = True
    return scene


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

    scene = build_scene()

    task = {
        "item_id": ITEM_ID,
        "visual_regime": "3D_procedural_control",
        "fps": FPS,
        "inputs": {
            "text_prompt": (
                "A sloped ramp has a gated enclosure at the top. "
                "The enclosure has double doors at the front and an open right exit, so the ball can roll out to the right. "
                "The first frame shows the double doors open outward and an orange ball visible inside the enclosure on the sloped ramp. "
                "Immediately after the first frame, the ball starts rolling down the ramp with gravity-like acceleration. "
                "The doors close while the ball moves, then reopen at the end. "
                "The ball finishes inside a lower open-top catch box. "
                "The ball must not pass through any wall, door, ramp, floor, or catch box."
            ),
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
    print("Output:", OUT_DIR)
    print("Design: open-right gated box, outward double doors, ball accelerates after frame 1.")
    print("=" * 100)


if __name__ == "__main__":
    main()
