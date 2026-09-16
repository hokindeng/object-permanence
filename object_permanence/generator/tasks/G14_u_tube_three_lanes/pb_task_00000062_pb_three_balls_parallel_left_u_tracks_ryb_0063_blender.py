# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_THREE_BALLS_PARALLEL_LEFT_U_TRACKS_RYB_0063",
  "track_color_order": [
    "red",
    "yellow",
    "blue"
  ],
  "prompt": "Three parallel lanes are shown. Each lane has one opaque left-half U-shaped tube that smoothly connects at the bottom to a rightward open double-rail straight track. The near, middle, and far track balls are red, yellow, and blue. Each ball starts just outside the top mouth of its U tube, enters the opaque U tube, continues to exist while hidden, and emerges onto the same rightward double-rail track. The balls must preserve color, identity, size, count, and lane assignment. After emerging, all three balls should gradually lose speed along their open rails and come to rest without stopping abruptly by the end of the video."
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


# =============================================================================
# GEOMETRY FIRST
# =============================================================================

TRACK_NAMES = ["near", "middle", "far"]
TRACK_YS = [-1.10, 0.0, 1.10]

BALL_RADIUS = 0.17
RAIL_RADIUS = 0.045
RAIL_GAP = 0.24

# U tube centerline is the ball-center path while inside the opaque tube.
U_CENTER_X = -1.65
U_CENTER_Z = 1.78
U_RADIUS = 1.22

ANGLE_START = math.pi          # top-left mouth of left-half U
ANGLE_END = 1.5 * math.pi      # bottom, tangent to rightward horizontal straight

ARC_LEN = U_RADIUS * abs(ANGLE_END - ANGLE_START)
BOTTOM_X = U_CENTER_X
BOTTOM_BALL_CENTER_Z = U_CENTER_Z - U_RADIUS
STRAIGHT_END_X = 2.95
STRAIGHT_LEN = STRAIGHT_END_X - BOTTOM_X
TOTAL_LEN = ARC_LEN + STRAIGHT_LEN

# The U tube begins slightly after the mouth so frame 1 ball is outside, not inserted.
TUBE_START_S = 0.13

# Correct two-rail contact geometry for straight track.
# Ball touches both rails: distance from ball center to rail cylinder center = BALL_RADIUS + RAIL_RADIUS.
RAIL_DY = RAIL_GAP / 2.0
RAIL_Z_DROP = math.sqrt((BALL_RADIUS + RAIL_RADIUS) ** 2 - RAIL_DY ** 2)
STRAIGHT_RAIL_CENTER_Z = BOTTOM_BALL_CENTER_Z - RAIL_Z_DROP

# Motion.
REST_END = 8
DT = 1.0 / FPS
G_SCALE = 1.00
INITIAL_SPEED = 0.035
ROLLING_FRICTION_DECELERATION = 0.0014


# =============================================================================
# BASIC HELPERS
# =============================================================================

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
    except Exception:
        pass

    return mat


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), roughness=0.85)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.92)

    MATS["tube"] = make_mat("mat_single_opaque_u_tube", (0.56, 0.57, 0.60), roughness=0.78)
    MATS["rail"] = make_mat("mat_open_double_rail", (0.72, 0.73, 0.76), roughness=0.55, metallic=0.08)
    MATS["support"] = make_mat("mat_support", (0.18, 0.20, 0.24), roughness=0.60)

    MATS["red"] = make_mat("mat_red_ball", (0.92, 0.18, 0.18), roughness=0.25)
    MATS["blue"] = make_mat("mat_blue_ball", (0.16, 0.36, 0.95), roughness=0.25)
    MATS["yellow"] = make_mat("mat_yellow_ball", (0.98, 0.78, 0.15), roughness=0.25)


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


def add_cube(name, location, dimensions, material, role, color_name, is_dynamic=False, solid=True):
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
    )
    return obj


def add_cylinder_between(name, p1, p2, radius, material, role, color_name):
    p1 = Vector(p1)
    p2 = Vector(p2)
    diff = p2 - p1
    length = diff.length
    mid = (p1 + p2) / 2.0

    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=length, vertices=32, location=mid)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = diff.to_track_quat("Z", "Y").to_euler()

    if material is not None:
        obj.data.materials.append(material)

    tag(obj, name, role, "static_solid", "cylinder", color_name, False, solid=True)
    return obj


def add_open_curve_tube(name, points, radius, material, role, color_name):
    curve = bpy.data.curves.new(name + "_curve", type="CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 24
    curve.bevel_depth = radius
    curve.bevel_resolution = 8
    curve.fill_mode = "FULL"
    curve.use_fill_caps = False

    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)

    for i, p in enumerate(points):
        spline.points[i].co = (p[0], p[1], p[2], 1.0)

    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)

    if material is not None:
        obj.data.materials.append(material)

    tag(obj, name, role, "static_solid", "open_curve_tube", color_name, False, solid=True)
    obj["pb_open_ended"] = True
    obj["pb_single_u_tube"] = True
    return obj


# =============================================================================
# PATH AND MOTION
# =============================================================================

def arc_centerline(track_y, s):
    theta = ANGLE_START + s / U_RADIUS
    x = U_CENTER_X + U_RADIUS * math.cos(theta)
    z = U_CENTER_Z + U_RADIUS * math.sin(theta)
    return Vector((x, track_y, z))


def ball_center_by_s(track_y, s):
    s = max(0.0, min(float(s), TOTAL_LEN))

    if s <= ARC_LEN:
        return arc_centerline(track_y, s)

    straight_s = s - ARC_LEN
    x = BOTTOM_X + straight_s
    return Vector((x, track_y, BOTTOM_BALL_CENTER_Z))


def z_by_s(s):
    return ball_center_by_s(0.0, s).z


def compute_s_by_frame():
    s_by_frame = {}
    s = 0.0
    start_z = z_by_s(0.0)
    bottom_z = BOTTOM_BALL_CENTER_Z

    exit_speed = math.sqrt(INITIAL_SPEED * INITIAL_SPEED + 2.0 * G_SCALE * max(0.0, start_z - bottom_z))

    exit_step = exit_speed * DT
    straight_speed = exit_step

    for frame in range(FRAME_START, FRAME_END + 1):
        if frame <= REST_END:
            s_by_frame[frame] = 0.0
            continue

        if s < ARC_LEN:
            current_z = z_by_s(s)
            drop = max(0.0, start_z - current_z)
            speed = math.sqrt(INITIAL_SPEED * INITIAL_SPEED + 2.0 * G_SCALE * drop)
            s = min(ARC_LEN, s + speed * DT)
        else:
            # Constant rolling resistance opposes motion on the level rails.
            # Integrate velocity every frame instead of switching to a scripted
            # terminal ease-out or clamping the position at an endpoint.
            s = min(TOTAL_LEN, s + straight_speed)
            straight_speed = max(0.0, straight_speed - ROLLING_FRICTION_DECELERATION)
        s_by_frame[frame] = s

    return s_by_frame


# =============================================================================
# SCENE
# =============================================================================

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


def build_one_lane(track_name, track_y):
    # One clean opaque U tube. It starts slightly after the top mouth so the ball is visible outside at frame 1.
    tube_points = []
    n = 56
    for i in range(n + 1):
        s = TUBE_START_S + (ARC_LEN - TUBE_START_S) * i / float(n)
        p = arc_centerline(track_y, s)
        tube_points.append((p.x, p.y, p.z))

    tube = add_open_curve_tube(
        f"{track_name}_single_opaque_left_u_tube",
        tube_points,
        0.31,
        MATS["tube"],
        "single_opaque_left_u_tube",
        "gray",
    )
    tube["pb_track_name"] = track_name

    # Straight double rails: correct contact height.
    x0 = BOTTOM_X + 0.08
    x1 = STRAIGHT_END_X

    for side, dy in [("left", -RAIL_DY), ("right", RAIL_DY)]:
        add_cylinder_between(
            f"{track_name}_straight_{side}_rail",
            (x0, track_y + dy, STRAIGHT_RAIL_CENTER_Z),
            (x1, track_y + dy, STRAIGHT_RAIL_CENTER_Z),
            RAIL_RADIUS,
            MATS["rail"],
            "straight_open_rail_contact_correct",
            "light_gray",
        )

    # Straight ties and supports.
    for i in range(9):
        t = i / 8.0
        x = x0 + (x1 - x0) * t
        add_cube(
            f"{track_name}_straight_tie_{i:02d}",
            (x, track_y, STRAIGHT_RAIL_CENTER_Z - 0.08),
            (0.11, 0.48, 0.055),
            MATS["support"],
            "straight_track_tie",
            "dark_gray",
            is_dynamic=False,
        )

    add_cube(
        f"{track_name}_u_tube_support",
        (BOTTOM_X - 0.10, track_y, BOTTOM_BALL_CENTER_Z - BALL_RADIUS - 0.28),
        (0.20, 0.52, 0.32),
        MATS["support"],
        "u_tube_support",
        "dark_gray",
        is_dynamic=False,
    )


def build_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (10.5, 8.0, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.45, 1.9), (10.5, 0.08, 3.8), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.0, -5.0, 6.5))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 1150
    key.data.size = 6.0

    bpy.ops.object.light_add(type="POINT", location=(3.6, -2.0, 4.4))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 150

    bpy.ops.object.camera_add(location=(7.4, -8.4, 5.4))
    cam = bpy.context.object
    cam.name = "camera_clean_single_u_tube_three_tracks"
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 7.4
    cam["pb_camera_fix"] = "farther_view_ortho_scale_7_4"
    look_at(cam, (-0.25, 0.0, 0.85))
    scene.camera = cam

    for name, y in zip(TRACK_NAMES, TRACK_YS):
        build_one_lane(name, y)

    color_order = CASE["track_color_order"]
    color_mat = {
        "red": MATS["red"],
        "blue": MATS["blue"],
        "yellow": MATS["yellow"],
    }

    balls = {}

    for name, y, color in zip(TRACK_NAMES, TRACK_YS, color_order):
        start = ball_center_by_s(y, 0.0)
        ball = add_ball(
            f"{name}_{color}_ball",
            BALL_RADIUS,
            start,
            color_mat[color],
            color,
        )
        ball["pb_track_name"] = name
        ball["pb_expected_track"] = name
        ball["pb_starts_at_tube_mouth_not_on_extra_rail"] = True
        ball["pb_not_inserted_into_tube_at_frame_1"] = True
        balls[name] = ball

    return {
        "scene": scene,
        "balls": balls,
        "color_order": color_order,
    }


# =============================================================================
# ANIMATION
# =============================================================================

def animate_scene(objs):
    scene = objs["scene"]
    balls = objs["balls"]
    s_by_frame = compute_s_by_frame()

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        s = s_by_frame[frame]

        for name, y in zip(TRACK_NAMES, TRACK_YS):
            ball = balls[name]
            p = ball_center_by_s(y, s)

            ball.location = p
            ball.rotation_euler = (0.0, s / BALL_RADIUS, 0.0)

            if s < TUBE_START_S:
                ball["pb_state"] = "visible_at_u_tube_top_mouth"
                ball["pb_visibility_region"] = "outside_tube_mouth"
            elif s <= ARC_LEN:
                ball["pb_state"] = "inside_single_opaque_left_u_tube"
                ball["pb_visibility_region"] = "hidden_inside_opaque_tube"
            elif s < TOTAL_LEN:
                ball["pb_state"] = "visible_on_contact_correct_open_double_rail"
                ball["pb_visibility_region"] = "open_straight_track"
            else:
                ball["pb_state"] = "final_on_open_double_rail"
                ball["pb_visibility_region"] = "open_straight_track"

            ball["pb_path_s"] = float(s)
            ball["pb_track_identity_preserved"] = True
            ball.keyframe_insert(data_path="location", frame=frame)
            ball.keyframe_insert(data_path="rotation_euler", frame=frame)

    scene.frame_set(FRAME_START)


# =============================================================================
# OUTPUT
# =============================================================================

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
    near_color, middle_color, far_color = CASE["track_color_order"]

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

    with open(TASK_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(task, f, indent=2, ensure_ascii=False)


def save_scene():
    bpy.ops.wm.save_as_mainfile(filepath=SCENE_FILE)


def main():
    ensure_dirs()
    clear_scene()

    objs = build_scene()
    animate_scene(objs)

    scene = objs["scene"]
    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, 60, OPTIONAL_FRAME_PATH)
    render_png(scene, 120, OPTIONAL_FRAME_02B_PATH)

    render_animation(scene)
    write_task_json()
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("track_color_order near/middle/far:", CASE["track_color_order"])
    print("No extra upper rail. Single U tube. Correct straight double-rail contact height.")
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
