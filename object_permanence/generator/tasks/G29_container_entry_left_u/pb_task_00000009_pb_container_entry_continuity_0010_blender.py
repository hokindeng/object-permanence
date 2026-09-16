# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

ITEM_ID = "PB_CONTAINER_ENTRY_CONTINUITY_0010"

FPS = 24
FRAME_START = 1
FRAME_END = 120

BALL_RADIUS = 0.22
PRIMARY_LANE = 0
SECOND_BALL_PRESENT = 0

# ============================================================
# Correct track geometry:
# left U-shaped downhill section, then straight rail
# ============================================================

RAIL_X_START = -3.90
U_LOWEST_X = -2.35

CONTAINER_X_MIN = -1.18
CONTAINER_X_MAX = 1.30

EMPTY_EXIT_X_END = 3.20

FRONT_Y = -0.46
BACK_Y = 0.46
OCCUPIED_Y = FRONT_Y if PRIMARY_LANE == 0 else BACK_Y
EMPTY_Y = BACK_Y if PRIMARY_LANE == 0 else FRONT_Y

U_HIGH_Z = 1.66
STRAIGHT_Z = 0.74

# The ball rests nestled in the valley between the two parallel tube rails.
# Each rail tube (bevel radius RAIL_BEVEL) centerline is RAIL_HALF_GAUGE to either side
# of the ball center in y. Contact requires sqrt(dy^2 + dz^2) = R + r, so the ball
# center sits dz = sqrt((R+r)^2 - dy^2) above the rail centerline (track_z).
RAIL_BEVEL = 0.035
RAIL_HALF_GAUGE = 0.135
BALL_Z_OFFSET = math.sqrt((BALL_RADIUS + RAIL_BEVEL) ** 2 - RAIL_HALF_GAUGE ** 2) + 0.004

CONTAINER_Y_MIN = -1.12
CONTAINER_Y_MAX = 1.12
CONTAINER_Z_MIN = 0.34
CONTAINER_Z_MAX = 2.30
WALL_T = 0.12

BALL_START_X = RAIL_X_START + 0.13
BALL_ENTRY_X = CONTAINER_X_MIN - 0.04
BALL_FINAL_X = 0.06

ENTER_FRAME = 54
SETTLE_FRAME = 98

INPUT_FRAME_1 = 1
OPTIONAL_BEFORE_ENTRY_FRAME = 42
OPTIONAL_HIDDEN_INSIDE_FRAME = 82

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

OUT_DIR = os.path.join(PROJECT_ROOT, "permanence_blender_outputs", ITEM_ID)
FRAMES_DIR = os.path.join(OUT_DIR, f"{ITEM_ID}_reference_frames")
SCENE_FILE = os.path.join(OUT_DIR, f"{ITEM_ID}_scene.blend")
TASK_JSON_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_task.json")

INPUT_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_input_frame_01.png")
OPTIONAL_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_before_entry_frame_02.png")
OPTIONAL_FRAME_02B_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_hidden_inside_frame_02B.png")


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
    t = clamp01(t)
    return 1.0 - (1.0 - t) * (1.0 - t)


def lerp(a, b, t):
    return a + (b - a) * t


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
        scene.eevee.gtao_factor = 1.25
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
# Track math: only left section is U-shaped. After lowest point, straight.
# ============================================================

def track_z_at_x(x):
    """
    Correct shape:
    - From RAIL_X_START to U_LOWEST_X: U-like curved downhill section.
    - From U_LOWEST_X onward: straight horizontal rail at STRAIGHT_Z.
    """
    if x <= U_LOWEST_X:
        t = clamp01((x - RAIL_X_START) / max(1e-6, U_LOWEST_X - RAIL_X_START))

        # Starts high, curves down to the lowest point.
        # This is the left half of a U/half-pipe, not a whole left-to-right U.
        return STRAIGHT_Z + (U_HIGH_Z - STRAIGHT_Z) * (math.cos(0.5 * math.pi * t) ** 2)

    return STRAIGHT_Z


def ball_x_at_frame(frame):
    if frame <= ENTER_FRAME:
        t = (frame - FRAME_START) / max(1, ENTER_FRAME - FRAME_START)
        return lerp(BALL_START_X, BALL_ENTRY_X, smooth01(t))

    if frame <= SETTLE_FRAME:
        t = (frame - ENTER_FRAME) / max(1, SETTLE_FRAME - ENTER_FRAME)
        return lerp(BALL_ENTRY_X, BALL_FINAL_X, ease_out(t))

    tau = (frame - SETTLE_FRAME) / max(1, FRAME_END - SETTLE_FRAME)
    return BALL_FINAL_X + 0.018 * math.exp(-5.0 * tau) * math.sin(3.0 * math.pi * tau)


def ball_location_at_x(x, lane_y=OCCUPIED_Y):
    return (x, lane_y, track_z_at_x(x) + BALL_Z_OFFSET)


def exit_ball_x_at_frame(frame):
    """Second ball traverses the other lane and exits instead of teleporting."""
    t = clamp01((frame - FRAME_START) / float(FRAME_END - FRAME_START))
    return lerp(BALL_START_X, EMPTY_EXIT_X_END - 0.20, smooth01(t))


def inside_container_x(x):
    return CONTAINER_X_MIN <= x <= CONTAINER_X_MAX


# ============================================================
# Curve rails
# ============================================================

def make_curve_object(name, points, bevel_depth, material, role, rail_kind, color_name="neutral_gray"):
    curve = bpy.data.curves.new(name + "_curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 20
    curve.bevel_depth = bevel_depth
    curve.bevel_resolution = 5

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
        color_name,
        False,
        solid=True,
        pb_rail_kind=rail_kind,
        pb_left_u_then_straight=True,
        pb_identity_cue=False,
    )
    return obj


def rail_points(y, x_start, x_end, n=120):
    pts = []
    for i in range(n + 1):
        t = i / n
        x = lerp(x_start, x_end, t)
        z = track_z_at_x(x)
        pts.append((x, y, z))
    return pts


def build_left_u_then_straight_track(name_prefix, y, x_end, mat_rail, mat_tie, rail_kind):
    """
    A track is two parallel tube rails plus cross ties.
    Shape:
      left high U-like downhill curve -> lowest point -> straight horizontal rail.
    """
    parts = []

    front = make_curve_object(
        f"{name_prefix}_front_tube_rail",
        rail_points(y - 0.135, RAIL_X_START, x_end, 125),
        0.035,
        mat_rail,
        "left_u_then_straight_rail_tube",
        rail_kind,
    )
    parts.append(front)

    back = make_curve_object(
        f"{name_prefix}_back_tube_rail",
        rail_points(y + 0.135, RAIL_X_START, x_end, 125),
        0.035,
        mat_rail,
        "left_u_then_straight_rail_tube",
        rail_kind,
    )
    parts.append(back)

    # Cross ties: denser on left curve + straight part.
    for idx, frac in enumerate([0.04, 0.10, 0.16, 0.22, 0.28, 0.34, 0.40, 0.48, 0.58, 0.68, 0.78, 0.88, 0.96]):
        x = lerp(RAIL_X_START, x_end, frac)
        z = track_z_at_x(x) - 0.045
        tie = add_cube(
            f"{name_prefix}_cross_tie_{idx:02d}",
            (x, y, z),
            (0.055, 0.40, 0.045),
            material=mat_tie,
        )
        tag(
            tie,
            tie.name,
            "rail_cross_tie",
            "static_solid",
            "cube",
            "dark_gray",
            False,
            solid=True,
            pb_rail_kind=rail_kind,
            pb_left_u_then_straight=True,
            pb_identity_cue=False,
        )
        parts.append(tie)

    return parts


def build_empty_right_straight_exit(mat_rail, mat_tie):
    parts = []
    y = EMPTY_Y
    z = STRAIGHT_Z

    for suffix, yy in [("front", y - 0.135), ("back", y + 0.135)]:
        obj = make_curve_object(
            f"empty_rail_right_exit_straight_{suffix}_tube",
            [(CONTAINER_X_MAX + 0.03, yy, z), (EMPTY_EXIT_X_END, yy, z)],
            0.035,
            mat_rail,
            "empty_rail_right_straight_exit_tube",
            "empty_rail_with_right_exit",
        )
        obj["pb_is_wrong_exit_lure"] = True
        parts.append(obj)

    for idx, x in enumerate([CONTAINER_X_MAX + 0.35, CONTAINER_X_MAX + 0.75, CONTAINER_X_MAX + 1.15, CONTAINER_X_MAX + 1.55]):
        tie = add_cube(
            f"empty_rail_right_exit_straight_cross_tie_{idx:02d}",
            (x, y, z - 0.045),
            (0.055, 0.40, 0.045),
            material=mat_tie,
        )
        tag(
            tie,
            tie.name,
            "empty_rail_right_straight_exit_cross_tie",
            "static_solid",
            "cube",
            "dark_gray",
            False,
            solid=True,
            pb_rail_kind="empty_rail_with_right_exit",
            pb_is_wrong_exit_lure=True,
        )
        parts.append(tie)

    return parts


def build_occupied_blocked_wall_stub(mat_rail, mat_tie, mat_stop):
    """
    Occupied rail has no right hole, but it still visibly reaches the sealed wall.
    This adds a short rail stub and stopper on the sealed wall.
    """
    parts = []
    y = OCCUPIED_Y
    z = STRAIGHT_Z

    # Seat the stopper FLUSH against the wall's outer face so it directly caps the sealed
    # occupied track (zero gap -- otherwise you can see background through the gap), and
    # make the visible rail stub protrude OUTWARD from the stopper as the "stub + stopper
    # attached to the sealed wall" cue the prompt asks for.
    WALL_OUTER_FACE = CONTAINER_X_MAX + WALL_T / 2          # 1.36
    STOP_DEPTH = 0.17
    STOP_CX = WALL_OUTER_FACE + STOP_DEPTH / 2              # flush: inner face == wall face
    STOP_OUTER_FACE = WALL_OUTER_FACE + STOP_DEPTH          # 1.53
    STUB_X0 = STOP_OUTER_FACE
    STUB_X1 = STOP_OUTER_FACE + 0.21

    for suffix, yy in [("front", y - 0.135), ("back", y + 0.135)]:
        obj = make_curve_object(
            f"occupied_rail_stub_on_sealed_right_wall_{suffix}_tube",
            [(STUB_X0, yy, z), (STUB_X1, yy, z)],
            0.035,
            mat_rail,
            "occupied_rail_blocked_wall_stub",
            "occupied_rail_blocked_right",
        )
        obj["pb_no_opening_here"] = True
        obj["pb_closed_wall"] = True
        parts.append(obj)

    tie = add_cube(
        "occupied_rail_stub_cross_tie_against_sealed_wall",
        (0.5 * (STUB_X0 + STUB_X1), y, z - 0.045),
        (0.055, 0.40, 0.045),
        material=mat_tie,
    )
    tag(
        tie,
        tie.name,
        "occupied_rail_blocked_wall_stub_cross_tie",
        "static_solid",
        "cube",
        "dark_gray",
        False,
        solid=True,
        pb_rail_kind="occupied_rail_blocked_right",
        pb_no_opening_here=True,
    )
    parts.append(tie)

    stopper = add_cube(
        "occupied_rail_sealed_right_wall_stop_block",
        (STOP_CX, y, z + 0.20),
        (STOP_DEPTH, 0.70, 0.58),
        material=mat_stop,
    )
    tag(
        stopper,
        stopper.name,
        "closed_end_stop_block",
        "static_solid",
        "cube",
        "medium_gray",
        False,
        solid=True,
        pb_blocks_exit=True,
        pb_rail_kind="occupied_rail_blocked_right",
        pb_no_exit=True,
        pb_not_an_opening=True,
    )
    parts.append(stopper)

    return parts


# ============================================================
# Container with wall holes
# ============================================================

def add_wall_blocks_with_holes(prefix, x, y_min, y_max, z_min, z_max, openings, mat, role, side):
    y_breaks = [y_min, y_max]
    z_breaks = [z_min, z_max]

    for op in openings:
        y_breaks.extend([op["y0"], op["y1"]])
        z_breaks.extend([op["z0"], op["z1"]])

    y_breaks = sorted(set([round(v, 5) for v in y_breaks if y_min <= v <= y_max]))
    z_breaks = sorted(set([round(v, 5) for v in z_breaks if z_min <= v <= z_max]))

    parts = []
    idx = 0

    for yi in range(len(y_breaks) - 1):
        ya, yb = y_breaks[yi], y_breaks[yi + 1]
        if yb - ya < 0.03:
            continue

        for zi in range(len(z_breaks) - 1):
            za, zb = z_breaks[zi], z_breaks[zi + 1]
            if zb - za < 0.03:
                continue

            cy = 0.5 * (ya + yb)
            cz = 0.5 * (za + zb)

            in_hole = False
            for op in openings:
                if op["y0"] <= cy <= op["y1"] and op["z0"] <= cz <= op["z1"]:
                    in_hole = True
                    break

            if in_hole:
                continue

            block = add_cube(
                f"{prefix}_sealed_block_{idx:02d}",
                (x, cy, cz),
                (WALL_T, yb - ya, zb - za),
                material=mat,
            )
            tag(
                block,
                block.name,
                role,
                "static_solid",
                "cube",
                "gray",
                False,
                solid=True,
                pb_wall_side=side,
                pb_wall_is_sealed_except_declared_openings=True,
            )
            parts.append(block)
            idx += 1

    return parts


def add_opening_rim(prefix, x, y, z, y_width, z_height, mat, side, rail_kind):
    parts = []

    specs = [
        ("top", y, z + z_height / 2 + 0.04, (WALL_T * 1.35, y_width + 0.12, 0.08)),
        ("bottom", y, z - z_height / 2 - 0.04, (WALL_T * 1.35, y_width + 0.12, 0.08)),
        ("front", y - y_width / 2 - 0.04, z, (WALL_T * 1.35, 0.08, z_height + 0.12)),
        ("back", y + y_width / 2 + 0.04, z, (WALL_T * 1.35, 0.08, z_height + 0.12)),
    ]

    for suffix, yy, zz, dims in specs:
        obj = add_cube(
            f"{prefix}_{suffix}_rim",
            (x, yy, zz),
            dims,
            material=mat,
        )
        tag(
            obj,
            obj.name,
            "opening_rim",
            "static_solid",
            "cube",
            "medium_gray",
            False,
            solid=True,
            pb_opening_side=side,
            pb_rail_kind=rail_kind,
            pb_actual_opening=True,
        )
        parts.append(obj)

    return parts


def build_container(mat_container, mat_edge, mat_shadow):
    parts = []

    x_mid = 0.5 * (CONTAINER_X_MIN + CONTAINER_X_MAX)
    y_mid = 0.5 * (CONTAINER_Y_MIN + CONTAINER_Y_MAX)
    z_mid = 0.5 * (CONTAINER_Z_MIN + CONTAINER_Z_MAX)

    floor = add_cube(
        "gray_container_bottom_floor",
        (x_mid, y_mid, CONTAINER_Z_MIN + WALL_T / 2),
        (CONTAINER_X_MAX - CONTAINER_X_MIN - WALL_T, CONTAINER_Y_MAX - CONTAINER_Y_MIN - 2 * WALL_T, WALL_T),
        material=mat_container,
    )
    tag(floor, floor.name, "container_floor", "static_solid", "cube", "gray", False, solid=True)
    parts.append(floor)

    front = add_cube(
        "gray_container_front_wall_camera_side",
        (x_mid, CONTAINER_Y_MIN + WALL_T / 2, z_mid),
        (CONTAINER_X_MAX - CONTAINER_X_MIN, WALL_T, CONTAINER_Z_MAX - CONTAINER_Z_MIN),
        material=mat_container,
    )
    tag(front, front.name, "container_occluder", "static_solid", "cube", "gray", False, solid=True, pb_occludes=True)
    parts.append(front)

    back = add_cube(
        "gray_container_back_wall",
        (x_mid, CONTAINER_Y_MAX - WALL_T / 2, z_mid),
        (CONTAINER_X_MAX - CONTAINER_X_MIN, WALL_T, CONTAINER_Z_MAX - CONTAINER_Z_MIN),
        material=mat_container,
    )
    tag(back, back.name, "container_wall", "static_solid", "cube", "gray", False, solid=True)
    parts.append(back)

    roof = add_cube(
        "gray_container_roof",
        (x_mid, y_mid, CONTAINER_Z_MAX - WALL_T / 2),
        (CONTAINER_X_MAX - CONTAINER_X_MIN - WALL_T, CONTAINER_Y_MAX - CONTAINER_Y_MIN - 2 * WALL_T, WALL_T),
        material=mat_container,
    )
    tag(roof, roof.name, "container_roof", "static_solid", "cube", "gray", False, solid=True, pb_occludes=True)
    parts.append(roof)

    interior_shadow = add_cube(
        "dark_visible_container_interior_shadow",
        (x_mid, y_mid, CONTAINER_Z_MIN + 0.035),
        ((CONTAINER_X_MAX - CONTAINER_X_MIN) * 0.86, (CONTAINER_Y_MAX - CONTAINER_Y_MIN) * 0.72, 0.035),
        material=mat_shadow,
    )
    tag(interior_shadow, interior_shadow.name, "container_interior", "static_visual_marker", "cube", "dark_gray", False, solid=False)
    parts.append(interior_shadow)

    y_width = 0.66
    z_height = 0.92
    hole_z = STRAIGHT_Z + 0.42

    # Left wall: both tracks enter container.
    left_openings = [
        {
            "name": "occupied_left_entry",
            "y0": OCCUPIED_Y - y_width / 2,
            "y1": OCCUPIED_Y + y_width / 2,
            "z0": hole_z - z_height / 2,
            "z1": hole_z + z_height / 2,
        },
        {
            "name": "empty_left_entry",
            "y0": EMPTY_Y - y_width / 2,
            "y1": EMPTY_Y + y_width / 2,
            "z0": hole_z - z_height / 2,
            "z1": hole_z + z_height / 2,
        },
    ]

    parts.extend(add_wall_blocks_with_holes(
        "left_container_wall_two_entry_holes",
        CONTAINER_X_MIN,
        CONTAINER_Y_MIN + WALL_T,
        CONTAINER_Y_MAX - WALL_T,
        CONTAINER_Z_MIN,
        CONTAINER_Z_MAX,
        left_openings,
        mat_container,
        "container_left_wall",
        "left_two_entry_holes",
    ))

    for prefix, y, rail_kind in [
        ("occupied_left_entry_opening", OCCUPIED_Y, "occupied_rail_blocked_right"),
        ("empty_left_entry_opening", EMPTY_Y, "empty_rail_with_right_exit"),
    ]:
        parts.extend(add_opening_rim(prefix, CONTAINER_X_MIN - (WALL_T / 2 + WALL_T * 1.35 / 2 + 0.015), y, hole_z, y_width, z_height, mat_edge, "left", rail_kind))

    # Right wall: ONLY empty track has exit hole.
    right_openings = [
        {
            "name": "empty_right_exit_only",
            "y0": EMPTY_Y - y_width / 2,
            "y1": EMPTY_Y + y_width / 2,
            "z0": hole_z - z_height / 2,
            "z1": hole_z + z_height / 2,
        }
    ]

    parts.extend(add_wall_blocks_with_holes(
        "right_wall_only_empty_exit",
        CONTAINER_X_MAX,
        CONTAINER_Y_MIN + WALL_T,
        CONTAINER_Y_MAX - WALL_T,
        CONTAINER_Z_MIN,
        CONTAINER_Z_MAX,
        right_openings,
        mat_container,
        "container_right_wall",
        "right_only_empty_track_exit",
    ))

    parts.extend(add_opening_rim(
        "empty_right_exit_opening_only",
        CONTAINER_X_MAX + (WALL_T / 2 + WALL_T * 1.35 / 2 + 0.015),
        EMPTY_Y,
        hole_z,
        y_width,
        z_height,
        mat_edge,
        "right",
        "empty_rail_with_right_exit",
    ))

    return parts


# ============================================================
# Scene
# ============================================================

def build_scene():
    scene = bpy.context.scene
    set_render(scene)

    mat_floor = make_mat("mat_floor_warm", (0.82, 0.80, 0.75), roughness=0.82)
    mat_rail = make_mat("mat_rail_neutral_gray_tube", (0.46, 0.46, 0.46), roughness=0.55)
    mat_tie = make_mat("mat_track_ties_dark_gray", (0.28, 0.28, 0.28), roughness=0.72)
    mat_ball = make_mat("mat_orange_ball_target", (1.0, 0.38, 0.05), roughness=0.30)
    mat_second_ball = make_mat("mat_blue_ball_target", (0.10, 0.34, 0.96), roughness=0.30)

    mat_container = make_mat("mat_opaque_gray_container", (0.30, 0.31, 0.33), roughness=0.82)
    mat_container_edge = make_mat("mat_container_edge_medium_gray", (0.55, 0.56, 0.58), roughness=0.70)
    mat_shadow = make_mat("mat_container_interior_shadow", (0.30, 0.31, 0.33), roughness=0.92)  # solid: interior same as container (kill dark flicker bar)
    mat_backdrop = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)

    floor = add_cube(
        "large_floor_base",
        (0.0, 0.0, -0.02),
        (9.6, 4.2, 0.12),
        material=mat_floor,
    )
    tag(floor, floor.name, "ground", "static_solid", "cube", "warm_beige", False, solid=True)

    backdrop = add_cube(
        "rear_backdrop_panel",
        (0.0, 2.20, 1.70),
        (9.6, 0.08, 3.45),
        material=mat_backdrop,
    )
    tag(backdrop, backdrop.name, "background", "static_solid", "cube", "off_white", False, solid=True)

    # Two identical tracks:
    # left U-shaped downhill section -> straight rail into container.
    occupied_track = build_left_u_then_straight_track(
        "occupied_left_u_then_straight_track_blocked_right",
        OCCUPIED_Y,
        CONTAINER_X_MAX - 0.035,
        mat_rail,
        mat_tie,
        "occupied_rail_blocked_right",
    )

    empty_track = build_left_u_then_straight_track(
        "empty_left_u_then_straight_track_with_right_exit",
        EMPTY_Y,
        CONTAINER_X_MAX,
        mat_rail,
        mat_tie,
        "empty_rail_with_right_exit",
    )

    empty_exit_tail = build_empty_right_straight_exit(mat_rail, mat_tie)

    # Container drawn after rails so its opaque walls hide internal rail/ball portions.
    container_parts = build_container(mat_container, mat_container_edge, mat_shadow)

    # Crucial: occupied track has visible right-wall rail stub + stopper, but no hole.
    occupied_stub = build_occupied_blocked_wall_stub(mat_rail, mat_tie, mat_container_edge)

    # Ball.
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=48,
        ring_count=24,
        radius=BALL_RADIUS,
        location=ball_location_at_x(BALL_START_X),
    )
    ball = bpy.context.object
    ball.name = "target_orange_ball_on_occupied_left_u_then_straight_track"
    ball.data.materials.append(mat_ball)
    tag(
        ball,
        "target_orange_ball_on_occupied_left_u_then_straight_track",
        "target",
        "dynamic_object",
        "sphere",
        "orange",
        True,
        solid=True,
        pb_identity_id="target_ball",
        pb_expected_final_location="inside_container_on_blocked_occupied_track",
        pb_rail_kind="occupied_rail_blocked_right",
        pb_wrong_exit_is_empty_rail=True,
        pb_radius=BALL_RADIUS,
    )

    second_ball = None
    if SECOND_BALL_PRESENT:
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=48,
            ring_count=24,
            radius=BALL_RADIUS,
            location=ball_location_at_x(BALL_START_X, EMPTY_Y),
        )
        second_ball = bpy.context.object
        second_ball.name = "secondary_blue_ball_on_open_exit_track"
        second_ball.data.materials.append(mat_second_ball)
        tag(
            second_ball,
            "secondary_blue_ball_on_open_exit_track",
            "secondary_target",
            "dynamic_object",
            "sphere",
            "blue",
            True,
            solid=True,
            pb_identity_id="secondary_ball",
            pb_expected_final_location="visible_beyond_open_exit",
            pb_rail_kind="open_exit_track",
            pb_radius=BALL_RADIUS,
        )

    bpy.ops.object.light_add(type="AREA", location=(-3.0, -4.2, 6.4))
    key = bpy.context.object
    key.name = "large_softbox_light"
    key.data.energy = 880
    key.data.size = 5.8

    bpy.ops.object.light_add(type="POINT", location=(3.8, -3.2, 3.8))
    fill = bpy.context.object
    fill.name = "right_wall_fill_light"
    fill.data.energy = 170

    # Camera: show left U-section, straight rails, container right wall.
    bpy.ops.object.camera_add(location=(5.65, -7.35, 3.75))
    cam = bpy.context.object
    cam.name = "camera_left_u_then_straight_container_view"
    cam.data.lens = 30
    look_at(cam, (-0.35, -0.02, 1.25))
    cam.data.dof.use_dof = False
    scene.camera = cam

    return {
        "scene": scene,
        "ball": ball,
        "second_ball": second_ball,
        "container_parts": container_parts,
        "rail_parts": occupied_track + empty_track + empty_exit_tail + occupied_stub,
    }


# ============================================================
# Animation
# ============================================================

def set_ball_semantic_state(ball, frame, x):
    if x < CONTAINER_X_MIN:
        phase = "visible_on_left_u_then_straight_occupied_track_before_entry"
        visibility = "visible"
        loc_state = "outside_container_on_occupied_track"
    elif x < BALL_FINAL_X - 0.05:
        phase = "entering_container_on_occupied_straight_track"
        visibility = "partially_occluded_by_container"
        loc_state = "passing_through_left_opening"
    else:
        phase = "inside_container_occluded_but_existing_on_blocked_track"
        visibility = "occluded_inside_container"
        loc_state = "inside_container_on_blocked_occupied_track"

    ball["pb_state"] = phase
    ball["pb_visibility_state"] = visibility
    ball["pb_location_state"] = loc_state
    ball["pb_inside_container"] = bool(inside_container_x(x))
    ball["pb_identity_preserved"] = True
    ball["pb_expected_color"] = "orange"
    ball["pb_expected_count"] = 2 if SECOND_BALL_PRESENT else 1
    ball["pb_rail_kind"] = "occupied_rail_blocked_right"
    ball["pb_must_not_use_empty_rail_exit"] = True
    ball["pb_must_continue_existing_when_hidden"] = True


def animate_scene(scene, ball, second_ball, container_parts, rail_parts):
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        x = ball_x_at_frame(frame)
        ball.location = ball_location_at_x(x)

        distance = x - BALL_START_X
        ball.rotation_euler = (0.0, -distance / BALL_RADIUS, 0.0)

        set_ball_semantic_state(ball, frame, x)

        for obj in container_parts:
            obj["pb_state"] = "opaque_container_right_wall_sealed_except_empty_track_exit"
            obj["pb_right_wall_rule"] = "only_empty_track_exit_hole_open"
            obj["pb_occupied_track_right_side"] = "sealed_but_visible_stub_and_stopper"
            obj["pb_empty_track_right_side"] = "open_exit_with_straight_tail"

        for obj in rail_parts:
            obj["pb_state"] = "neutral_gray_left_u_then_straight_track"
            obj["pb_no_color_identity_cue"] = True
            obj["pb_left_section_u_shaped"] = True
            obj["pb_after_lowest_point_straight"] = True

        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)

        if second_ball is not None:
            x2 = exit_ball_x_at_frame(frame)
            second_ball.location = ball_location_at_x(x2, EMPTY_Y)
            second_ball.rotation_euler = (0.0, -(x2 - BALL_START_X) / BALL_RADIUS, 0.0)
            second_ball["pb_state"] = "rolling_on_other_lane_and_exiting"
            second_ball["pb_identity_preserved"] = True
            second_ball.keyframe_insert(data_path="location", frame=frame)
            second_ball.keyframe_insert(data_path="rotation_euler", frame=frame)

    # Do NOT use obj.animation_data.action.fcurves in Blender 5.x.
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
    occupied_lane_name = "front" if PRIMARY_LANE == 0 else "back"
    other_lane_name = "back" if PRIMARY_LANE == 0 else "front"
    if SECOND_BALL_PRESENT:
        occupancy_text = (
            f"An orange ball starts on the {occupied_lane_name} track and a blue ball starts on the {other_lane_name} track. "
            f"Both roll simultaneously. The orange ball enters the sealed {occupied_lane_name} track and remains hidden inside, "
            f"while the blue ball follows the {other_lane_name} track through its real right-side exit and remains visible. "
        )
        primary_constraint = (
            "It must not disappear, teleport, duplicate, switch to the other ball's track, "
            "or emerge from the other ball's exit."
        )
    else:
        occupancy_text = (
            f"A single orange ball starts on the {occupied_lane_name} track; the {other_lane_name} track is empty. "
            f"The ball enters the opaque container on the occupied {occupied_lane_name} track and becomes hidden inside. "
        )
        primary_constraint = (
            "It must not disappear, teleport, duplicate, switch to the empty track, "
            "or emerge from the empty-track exit."
        )
    task = {
        "item_id": ITEM_ID,
        "visual_regime": "3D_procedural_control",
        "fps": FPS,
        "inputs": {
            "text_prompt": (
                occupancy_text +
                "Each track has a left-side U-shaped downhill section like a pirate-ship slide. "
                "Immediately after the U-shaped section reaches its lowest point, the track becomes a straight horizontal rail. "
                "Both straight rails enter an opaque gray container from the left. "
                f"On the right wall of the container, only the {other_lane_name} track has an open exit hole and a straight rail continuing outside. "
                f"The occupied {occupied_lane_name} track has no right-side hole; instead a visible rail stub and stopper are attached to the sealed wall. "
                "Every other part of the right wall is closed. "
                "The same orange ball must continue to exist inside the container on its original occupied blocked track. "
                + primary_constraint
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

    animate_scene(scene, objs["ball"], objs["second_ball"], objs["container_parts"], objs["rail_parts"])

    render_png(scene, INPUT_FRAME_1, INPUT_FRAME_PATH)
    render_png(scene, OPTIONAL_BEFORE_ENTRY_FRAME, OPTIONAL_FRAME_PATH)
    render_png(scene, OPTIONAL_HIDDEN_INSIDE_FRAME, OPTIONAL_FRAME_02B_PATH)

    render_animation(scene)
    write_task_json()
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("FIXED SHAPE:")
    print(" - left section is U-shaped downhill")
    print(" - after lowest point, rail becomes straight")
    print(" - empty track has only right exit + straight tail")
    print(" - occupied track has visible wall stub + stopper but no hole")
    print(" - right wall sealed everywhere except empty track hole")
    print("=" * 100)


if __name__ == "__main__":
    main()
