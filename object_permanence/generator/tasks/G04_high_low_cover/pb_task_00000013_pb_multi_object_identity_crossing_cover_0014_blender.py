# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

ITEM_ID = "PB_MULTI_OBJECT_IDENTITY_CROSSING_COVER_0014"

FPS = 24
FRAME_START = 1
FRAME_END = 120

# ============================================================
# Core geometry
# ============================================================

BALL_RADIUS = 0.22
RAIL_TUBE_RADIUS = 0.040
BALL_CLEARANCE = 0.020

TRACK_HALF_WIDTH = 0.145

X_START = -3.55
X_FINAL = 3.55

# Front/back layout.
FRONT_Y = -0.55
BACK_Y = 0.55

# Red starts front-left and exits back-right.
RED_START_Y = FRONT_Y
RED_FINAL_Y = BACK_Y

# Blue starts back-left and exits front-right.
BLUE_START_Y = BACK_Y
BLUE_FINAL_Y = FRONT_Y

# The two tracks are one high and one low.
# They cross in x-y projection inside the cover, but are separated in height.
HIGH_TRACK_Z = 1.42
LOW_TRACK_Z = 0.66

def ball_center_z_for_track(track_center_z):
    return track_center_z + RAIL_TUBE_RADIUS + BALL_RADIUS + BALL_CLEARANCE

RED_BALL_Z = ball_center_z_for_track(HIGH_TRACK_Z)
BLUE_BALL_Z = ball_center_z_for_track(LOW_TRACK_Z)

# Opaque crossing cover.
COVER_X_MIN = -0.82
COVER_X_MAX = 0.82
COVER_Y_MIN = -1.20
COVER_Y_MAX = 1.20
COVER_Z_MIN = 0.38
COVER_Z_MAX = 2.36
COVER_T = 0.12

INPUT_FRAME_1 = 1
OPTIONAL_HIDDEN_FRAME = 64
OPTIONAL_AFTER_EXIT_FRAME = 98

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

OUT_DIR = os.path.join(PROJECT_ROOT, "permanence_blender_outputs", ITEM_ID)
FRAMES_DIR = os.path.join(OUT_DIR, f"{ITEM_ID}_reference_frames")
SCENE_FILE = os.path.join(OUT_DIR, f"{ITEM_ID}_scene.blend")
TASK_JSON_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_task.json")

INPUT_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_input_frame_01.png")
OPTIONAL_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_hidden_high_low_crossing_frame_02.png")
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


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def progress_at_frame(frame):
    return smooth01((frame - FRAME_START) / max(1, FRAME_END - FRAME_START))


def x_at_frame(frame):
    return lerp(X_START, X_FINAL, progress_at_frame(frame))


def path_y_at_x(x, y_start, y_final):
    t = clamp01((x - X_START) / max(1e-6, X_FINAL - X_START))
    return lerp(y_start, y_final, smooth01(t))


def red_y_at_x(x):
    return path_y_at_x(x, RED_START_Y, RED_FINAL_Y)


def blue_y_at_x(x):
    return path_y_at_x(x, BLUE_START_Y, BLUE_FINAL_Y)


def red_track_z_at_x(x):
    return HIGH_TRACK_Z


def blue_track_z_at_x(x):
    return LOW_TRACK_Z


def red_ball_z_at_x(x):
    return RED_BALL_Z


def blue_ball_z_at_x(x):
    return BLUE_BALL_Z


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
# Track construction
# ============================================================

def make_curve_object(name, points, bevel_depth, material, role, rail_kind, height_role):
    curve = bpy.data.curves.new(name + "_curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 20
    curve.bevel_depth = bevel_depth
    curve.bevel_resolution = 4

    spl = curve.splines.new("POLY")
    spl.points.add(len(points) - 1)

    for p, co in zip(spl.points, points):
        p.co = (co[0], co[1], co[2], 1.0)

    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)

    if material is not None:
        obj.data.materials.append(material)

    tag(
        obj,
        name,
        role,
        "static_solid",
        "curve_tube",
        "neutral_gray",
        False,
        solid=True,
        pb_rail_kind=rail_kind,
        pb_track_height_role=height_role,
        pb_identity_cue=False,
        pb_ball_should_ride_above_track=True,
    )
    return obj


def path_points(y_func, z_func, x0, x1, n=150):
    pts = []
    for i in range(n + 1):
        t = i / n
        x = lerp(x0, x1, t)
        y = y_func(x)
        z = z_func(x)
        pts.append((x, y, z))
    return pts


def offset_y_func(y_func, offset):
    def f(x):
        return y_func(x) + offset
    return f


def build_high_low_crossing_track(name_prefix, y_func, z_func, mat_rail, mat_tie, rail_kind, height_role):
    parts = []

    # Two tube rails. The ball moves along the center between them,
    # with ball center placed ABOVE the rails.
    front_tube = make_curve_object(
        f"{name_prefix}_front_tube_rail",
        path_points(offset_y_func(y_func, -TRACK_HALF_WIDTH), z_func, X_START - 0.20, X_FINAL + 0.20, 150),
        RAIL_TUBE_RADIUS,
        mat_rail,
        "neutral_gray_crossing_track_tube",
        rail_kind,
        height_role,
    )
    parts.append(front_tube)

    back_tube = make_curve_object(
        f"{name_prefix}_back_tube_rail",
        path_points(offset_y_func(y_func, TRACK_HALF_WIDTH), z_func, X_START - 0.20, X_FINAL + 0.20, 150),
        RAIL_TUBE_RADIUS,
        mat_rail,
        "neutral_gray_crossing_track_tube",
        rail_kind,
        height_role,
    )
    parts.append(back_tube)

    for idx, frac in enumerate([0.05, 0.13, 0.21, 0.29, 0.37, 0.45, 0.55, 0.63, 0.71, 0.79, 0.87, 0.95]):
        x = lerp(X_START - 0.20, X_FINAL + 0.20, frac)
        y = y_func(x)
        z = z_func(x) - RAIL_TUBE_RADIUS - 0.035
        tie = add_cube(
            f"{name_prefix}_cross_tie_{idx:02d}",
            (x, y, z),
            (0.060, TRACK_HALF_WIDTH * 2.0 + 0.18, 0.045),
            rotation=(0.0, 0.0, 0.0),
            material=mat_tie,
        )
        tag(
            tie,
            tie.name,
            "neutral_gray_crossing_track_tie",
            "static_solid",
            "cube",
            "dark_gray",
            False,
            solid=True,
            pb_rail_kind=rail_kind,
            pb_track_height_role=height_role,
            pb_identity_cue=False,
        )
        parts.append(tie)

    return parts


# ============================================================
# Opaque cover
# ============================================================

def build_opaque_crossing_cover(mat_cover, mat_edge, mat_shadow):
    parts = []

    x_mid = 0.5 * (COVER_X_MIN + COVER_X_MAX)
    y_mid = 0.5 * (COVER_Y_MIN + COVER_Y_MAX)
    z_mid = 0.5 * (COVER_Z_MIN + COVER_Z_MAX)

    floor = add_cube(
        "gray_high_low_crossing_cover_bottom_floor",
        (x_mid, y_mid, COVER_Z_MIN + COVER_T / 2.0),
        (COVER_X_MAX - COVER_X_MIN - COVER_T, COVER_Y_MAX - COVER_Y_MIN - 2.0 * COVER_T, COVER_T),
        material=mat_cover,
    )
    tag(
        floor,
        floor.name,
        "cover_floor",
        "static_solid",
        "cube",
        "gray",
        False,
        solid=True,
        pb_cover_id="opaque_high_low_crossing_cover",
    )
    parts.append(floor)

    front = add_cube(
        "gray_high_low_crossing_cover_front_wall_camera_side",
        (x_mid, COVER_Y_MIN + COVER_T / 2.0, z_mid),
        (COVER_X_MAX - COVER_X_MIN, COVER_T, COVER_Z_MAX - COVER_Z_MIN),
        material=mat_cover,
    )
    tag(
        front,
        front.name,
        "cover_occluder",
        "static_solid",
        "cube",
        "gray",
        False,
        solid=True,
        pb_occludes=True,
        pb_cover_id="opaque_high_low_crossing_cover",
    )
    parts.append(front)

    back = add_cube(
        "gray_high_low_crossing_cover_back_wall",
        (x_mid, COVER_Y_MAX - COVER_T / 2.0, z_mid),
        (COVER_X_MAX - COVER_X_MIN, COVER_T, COVER_Z_MAX - COVER_Z_MIN),
        material=mat_cover,
    )
    tag(
        back,
        back.name,
        "cover_wall",
        "static_solid",
        "cube",
        "gray",
        False,
        solid=True,
        pb_cover_id="opaque_high_low_crossing_cover",
    )
    parts.append(back)

    roof = add_cube(
        "gray_high_low_crossing_cover_roof",
        (x_mid, y_mid, COVER_Z_MAX - COVER_T / 2.0),
        (COVER_X_MAX - COVER_X_MIN - COVER_T, COVER_Y_MAX - COVER_Y_MIN - 2.0 * COVER_T, COVER_T),
        material=mat_cover,
    )
    tag(
        roof,
        roof.name,
        "cover_roof",
        "static_solid",
        "cube",
        "gray",
        False,
        solid=True,
        pb_occludes=True,
        pb_cover_id="opaque_high_low_crossing_cover",
    )
    parts.append(roof)

    shadow = add_cube(
        "dark_visible_high_low_crossing_cover_interior_shadow",
        (x_mid, y_mid, COVER_Z_MIN + 0.035),
        ((COVER_X_MAX - COVER_X_MIN) * 0.80, (COVER_Y_MAX - COVER_Y_MIN) * 0.74, 0.035),
        material=mat_shadow,
    )
    tag(
        shadow,
        shadow.name,
        "cover_interior_shadow",
        "static_visual_marker",
        "cube",
        "dark_gray",
        False,
        solid=False,
        pb_cover_id="opaque_high_low_crossing_cover",
    )
    parts.append(shadow)

    # Left/right opening rims. One wide opening per side, because both tracks enter/exit the cover.
    for side_name, x in [("left", COVER_X_MIN), ("right", COVER_X_MAX)]:
        top = add_cube(
            f"{side_name}_high_low_crossing_cover_opening_top_rim",
            (x, y_mid, COVER_Z_MAX + 0.035),
            (COVER_T * 1.25, COVER_Y_MAX - COVER_Y_MIN + 0.12, 0.070),
            material=mat_edge,
        )
        tag(
            top,
            top.name,
            "cover_opening_rim",
            "static_solid",
            "cube",
            "medium_gray",
            False,
            solid=True,
            pb_opening_side=side_name,
            pb_cover_opening=True,
        )
        parts.append(top)

        bottom = add_cube(
            f"{side_name}_high_low_crossing_cover_opening_bottom_lip",
            (x, y_mid, COVER_Z_MIN + 0.060),
            (COVER_T * 1.25, COVER_Y_MAX - COVER_Y_MIN + 0.12, 0.080),
            material=mat_edge,
        )
        tag(
            bottom,
            bottom.name,
            "cover_opening_rim",
            "static_solid",
            "cube",
            "medium_gray",
            False,
            solid=True,
            pb_opening_side=side_name,
            pb_cover_opening=True,
        )
        parts.append(bottom)

        front_rim = add_cube(
            f"{side_name}_high_low_crossing_cover_front_vertical_rim",
            (x, COVER_Y_MIN - 0.035, z_mid),
            (COVER_T * 1.25, 0.070, COVER_Z_MAX - COVER_Z_MIN + 0.10),
            material=mat_edge,
        )
        tag(
            front_rim,
            front_rim.name,
            "cover_opening_rim",
            "static_solid",
            "cube",
            "medium_gray",
            False,
            solid=True,
            pb_opening_side=side_name,
            pb_cover_opening=True,
        )
        parts.append(front_rim)

        back_rim = add_cube(
            f"{side_name}_high_low_crossing_cover_back_vertical_rim",
            (x, COVER_Y_MAX + 0.035, z_mid),
            (COVER_T * 1.25, 0.070, COVER_Z_MAX - COVER_Z_MIN + 0.10),
            material=mat_edge,
        )
        tag(
            back_rim,
            back_rim.name,
            "cover_opening_rim",
            "static_solid",
            "cube",
            "medium_gray",
            False,
            solid=True,
            pb_opening_side=side_name,
            pb_cover_opening=True,
        )
        parts.append(back_rim)

    return parts


# ============================================================
# Scene
# ============================================================

def build_scene():
    scene = bpy.context.scene
    set_render(scene)

    mat_floor = make_mat("mat_floor_warm", (0.82, 0.80, 0.75), roughness=0.82)
    mat_rail = make_mat("mat_neutral_gray_high_low_crossing_tracks", (0.46, 0.46, 0.46), roughness=0.58)
    mat_tie = make_mat("mat_dark_gray_high_low_track_ties", (0.28, 0.28, 0.28), roughness=0.74)
    mat_cover = make_mat("mat_opaque_gray_high_low_crossing_cover", (0.30, 0.31, 0.33), roughness=0.82)
    mat_cover_edge = make_mat("mat_high_low_cover_edge_medium_gray", (0.55, 0.56, 0.58), roughness=0.70)
    mat_shadow = make_mat("mat_high_low_cover_interior_shadow", (0.30, 0.31, 0.33), roughness=0.92)  # solid: interior same as cover (no dark flicker bar)
    mat_red = make_mat("mat_red_identity_A_ball", (0.95, 0.03, 0.02), roughness=0.30)
    mat_blue = make_mat("mat_blue_identity_B_ball", (0.05, 0.20, 0.95), roughness=0.30)
    mat_backdrop = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)

    floor = add_cube(
        "large_floor_base",
        (0.0, 0.0, -0.04),
        (8.8, 4.0, 0.10),
        material=mat_floor,
    )
    tag(floor, floor.name, "ground", "static_solid", "cube", "warm_beige", False, solid=True)

    backdrop = add_cube(
        "rear_backdrop_panel",
        (0.0, 2.18, 1.55),
        (8.8, 0.08, 3.1),
        material=mat_backdrop,
    )
    tag(backdrop, backdrop.name, "background", "static_solid", "cube", "off_white", False, solid=True)

    # Tracks are created before the cover so the cover hides the crossing region.
    red_track_parts = build_high_low_crossing_track(
        "red_high_track_front_left_to_back_right",
        red_y_at_x,
        red_track_z_at_x,
        mat_rail,
        mat_tie,
        "red_identity_high_path_front_left_to_back_right",
        "high_track",
    )

    blue_track_parts = build_high_low_crossing_track(
        "blue_low_track_back_left_to_front_right",
        blue_y_at_x,
        blue_track_z_at_x,
        mat_rail,
        mat_tie,
        "blue_identity_low_path_back_left_to_front_right",
        "low_track",
    )

    cover_parts = build_opaque_crossing_cover(mat_cover, mat_cover_edge, mat_shadow)

    # Red ball starts on the HIGH track, above the rails, not intersecting them.
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=48,
        ring_count=24,
        radius=BALL_RADIUS,
        location=(X_START, red_y_at_x(X_START), red_ball_z_at_x(X_START)),
    )
    red_ball = bpy.context.object
    red_ball.name = "identity_A_red_ball_on_high_track"
    red_ball.data.materials.append(mat_red)
    tag(
        red_ball,
        "identity_A_red_ball_on_high_track",
        "target",
        "dynamic_object",
        "sphere",
        "red",
        True,
        solid=True,
        pb_identity_id="A",
        pb_track_height_role="high_track",
        pb_expected_start_side="front_left",
        pb_expected_final_side="back_right",
        pb_expected_path="front_left_to_back_right_high_track",
        pb_radius=BALL_RADIUS,
        pb_rail_tube_radius=RAIL_TUBE_RADIUS,
        pb_ball_center_z_rule="track_z + rail_tube_radius + ball_radius + clearance",
    )

    # Blue ball starts on the LOW track, above the rails, not intersecting them.
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=48,
        ring_count=24,
        radius=BALL_RADIUS,
        location=(X_START, blue_y_at_x(X_START), blue_ball_z_at_x(X_START)),
    )
    blue_ball = bpy.context.object
    blue_ball.name = "identity_B_blue_ball_on_low_track"
    blue_ball.data.materials.append(mat_blue)
    tag(
        blue_ball,
        "identity_B_blue_ball_on_low_track",
        "target",
        "dynamic_object",
        "sphere",
        "blue",
        True,
        solid=True,
        pb_identity_id="B",
        pb_track_height_role="low_track",
        pb_expected_start_side="back_left",
        pb_expected_final_side="front_right",
        pb_expected_path="back_left_to_front_right_low_track",
        pb_radius=BALL_RADIUS,
        pb_rail_tube_radius=RAIL_TUBE_RADIUS,
        pb_ball_center_z_rule="track_z + rail_tube_radius + ball_radius + clearance",
    )

    bpy.ops.object.light_add(type="AREA", location=(-2.8, -3.9, 5.8))
    key_light = bpy.context.object
    key_light.name = "large_softbox_light"
    key_light.data.energy = 850
    key_light.data.size = 5.8

    bpy.ops.object.light_add(type="POINT", location=(3.7, -2.8, 3.4))
    fill_light = bpy.context.object
    fill_light.name = "right_fill_light"
    fill_light.data.energy = 135

    # More level / front-facing view, but still slightly above the scene.
    # This makes the cover top and both left/right openings easier to see.
    bpy.ops.object.camera_add(location=(5.85, -7.55, 2.45))
    camera = bpy.context.object
    camera.name = "camera_level_view_high_low_crossing_cover"
    camera.data.lens = 36
    look_at(camera, (0.0, 0.0, 1.08))
    camera.data.dof.use_dof = False
    scene.camera = camera

    return {
        "scene": scene,
        "red_ball": red_ball,
        "blue_ball": blue_ball,
        "red_track_parts": red_track_parts,
        "blue_track_parts": blue_track_parts,
        "cover_parts": cover_parts,
    }


# ============================================================
# Animation
# ============================================================

def set_ball_state(ball, identity_id, color_name, frame, x, path_name, start_side, final_side, height_role):
    if x < COVER_X_MIN:
        phase = "visible_before_crossing_cover"
        visibility = "visible"
        loc_state = start_side
    elif x <= COVER_X_MAX:
        phase = "hidden_inside_opaque_crossing_cover"
        visibility = "occluded_inside_crossing_cover"
        loc_state = "inside_hidden_crossing_region"
    else:
        phase = "visible_after_crossing_cover"
        visibility = "visible"
        loc_state = final_side

    ball["pb_state"] = f"{color_name}_{phase}"
    ball["pb_identity_id"] = identity_id
    ball["pb_identity_phase"] = phase
    ball["pb_visibility_state"] = visibility
    ball["pb_location_state"] = loc_state
    ball["pb_expected_color"] = color_name
    ball["pb_expected_path"] = path_name
    ball["pb_expected_start_side"] = start_side
    ball["pb_expected_final_side"] = final_side
    ball["pb_track_height_role"] = height_role
    ball["pb_identity_preserved"] = True
    ball["pb_no_swap_allowed"] = True
    ball["pb_inside_cover"] = bool(COVER_X_MIN <= x <= COVER_X_MAX)
    ball["pb_ball_rides_above_track_not_intersecting"] = True


def animate_scene(scene, red_ball, blue_ball, red_track_parts, blue_track_parts, cover_parts):
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        x = x_at_frame(frame)

        red_y = red_y_at_x(x)
        blue_y = blue_y_at_x(x)

        red_ball.location = (x, red_y, red_ball_z_at_x(x))
        blue_ball.location = (x, blue_y, blue_ball_z_at_x(x))

        dist = x - X_START
        red_ball.rotation_euler = (0.0, -dist / BALL_RADIUS, 0.0)
        blue_ball.rotation_euler = (0.0, -dist / BALL_RADIUS, 0.0)

        set_ball_state(
            red_ball,
            "A",
            "red",
            frame,
            x,
            "front_left_to_back_right_high_track",
            "front_left",
            "back_right",
            "high_track",
        )
        set_ball_state(
            blue_ball,
            "B",
            "blue",
            frame,
            x,
            "back_left_to_front_right_low_track",
            "back_left",
            "front_right",
            "low_track",
        )

        cover_phase = (
            "balls_hidden_crossing_inside_high_low_cover"
            if COVER_X_MIN <= x <= COVER_X_MAX
            else "balls_visible_outside_cover"
        )

        for obj in cover_parts:
            obj["pb_state"] = "static_opaque_high_low_crossing_cover"
            obj["pb_cover_phase"] = cover_phase
            obj["pb_cover_id"] = "opaque_high_low_crossing_cover"
            obj["pb_hides_crossing_region"] = True
            obj["pb_open_ended_cover"] = True
            obj["pb_not_a_wall"] = True

        for obj in red_track_parts:
            obj["pb_state"] = "static_neutral_gray_high_identity_path"
            obj["pb_no_color_identity_cue"] = True
            obj["pb_track_color_does_not_encode_ball_identity"] = True
            obj["pb_track_height_role"] = "high_track"

        for obj in blue_track_parts:
            obj["pb_state"] = "static_neutral_gray_low_identity_path"
            obj["pb_no_color_identity_cue"] = True
            obj["pb_track_color_does_not_encode_ball_identity"] = True
            obj["pb_track_height_role"] = "low_track"

        red_ball.keyframe_insert(data_path="location", frame=frame)
        red_ball.keyframe_insert(data_path="rotation_euler", frame=frame)
        blue_ball.keyframe_insert(data_path="location", frame=frame)
        blue_ball.keyframe_insert(data_path="rotation_euler", frame=frame)

    # Blender 5.x: do not access obj.animation_data.action.fcurves.
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
                "Two colored balls move at the same time on two neutral gray tracks. "
                "In the first frame, the red ball is clearly visible on the front-left high track, "
                "and the blue ball is clearly visible on the back-left low track. "
                "The two tracks are at different heights: the red ball's track is higher, and the blue ball's track is lower. "
                "Both tracks enter an opaque gray crossing cover. "
                "Inside the cover, the paths cross in the horizontal view while the balls are hidden, "
                "but the tracks are vertically separated so the balls do not collide or pass through each other. "
                "Each ball should roll along and above its own track, not through the track. "
                "After the hidden crossing, the red ball should emerge on the back-right high path, "
                "and the blue ball should emerge on the front-right low path. "
                "The tracks are neutral gray and do not reveal identity by color. "
                "The red and blue balls must preserve their identities through the hidden crossing. "
                "They must not swap colors, swap identities, merge, disappear, teleport, duplicate, pass through the rails, or change size. "
                "After emerging, both balls should decelerate and come to rest by the end of the video."
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
        red_ball=objs["red_ball"],
        blue_ball=objs["blue_ball"],
        red_track_parts=objs["red_track_parts"],
        blue_track_parts=objs["blue_track_parts"],
        cover_parts=objs["cover_parts"],
    )

    render_png(scene, INPUT_FRAME_1, INPUT_FRAME_PATH)
    render_png(scene, OPTIONAL_HIDDEN_FRAME, OPTIONAL_FRAME_PATH)
    render_png(scene, OPTIONAL_AFTER_EXIT_FRAME, OPTIONAL_FRAME_02B_PATH)

    render_animation(scene)
    write_task_json()
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("Output:", OUT_DIR)
    print("FIXES:")
    print(" - red path is RAISED HIGH track")
    print(" - blue path is LOW track")
    print(" - ball center = track_z + rail_radius + ball_radius + clearance")
    print(" - balls move along their own track centerline above the rails")
    print(" - no track intersection / no ball-through-track bug")
    print("=" * 100)


if __name__ == "__main__":
    main()
