# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

ITEM_ID = "PB_MULTI_OBJECT_IDENTITY_TUNNEL_0012"

FPS = 24
FRAME_START = 1
FRAME_END = 120

BALL_RADIUS = 0.22
RAIL_RADIUS = 0.035
RAIL_HALF_GAUGE = 0.10
BALL_RAIL_CLEARANCE = 0.008

# Motion layout
X_START = -3.65
X_EXIT = 1.45
X_FINAL = 3.55

FRONT_Y = -0.42
BACK_Y = 0.42

TRACK_Z = 0.72
BALL_RAIL_CENTER_DISTANCE = BALL_RADIUS + RAIL_RADIUS + BALL_RAIL_CLEARANCE
BALL_SUPPORT_OFFSET_Z = math.sqrt(
    BALL_RAIL_CENTER_DISTANCE ** 2 - RAIL_HALF_GAUGE ** 2
)
BALL_Z = TRACK_Z + BALL_SUPPORT_OFFSET_Z

# Opaque tunnel
TUNNEL_X_MIN = -0.95
TUNNEL_X_MAX = 1.25
TUNNEL_CENTER_X = 0.5 * (TUNNEL_X_MIN + TUNNEL_X_MAX)
TUNNEL_Y_MIN = -1.05
TUNNEL_Y_MAX = 1.05
TUNNEL_CENTER_Y = 0.0
TUNNEL_Z_MIN = TRACK_Z - 0.05
TUNNEL_Z_MAX = 1.90

TUNNEL_WALL_T = 0.12

ENTER_TUNNEL_FRAME = 46
EXIT_TUNNEL_FRAME = 82

INPUT_FRAME_1 = 1
OPTIONAL_HIDDEN_FRAME = 62
OPTIONAL_AFTER_EXIT_FRAME = 98

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

OUT_DIR = os.path.join(PROJECT_ROOT, "permanence_blender_outputs", ITEM_ID)
FRAMES_DIR = os.path.join(OUT_DIR, f"{ITEM_ID}_reference_frames")
SCENE_FILE = os.path.join(OUT_DIR, f"{ITEM_ID}_scene.blend")
TASK_JSON_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_task.json")

INPUT_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_input_frame_01.png")
OPTIONAL_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_hidden_inside_tunnel_frame_02.png")
OPTIONAL_FRAME_02B_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_after_exit_frame_02B.png")


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


def ball_x_at_frame(frame):
    t = (frame - FRAME_START) / max(1, FRAME_END - FRAME_START)
    return lerp(X_START, X_FINAL, smooth01(t))


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


def make_curve_object(name, points, bevel_depth, material, role, rail_kind):
    curve = bpy.data.curves.new(name + "_curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 16
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
        pb_identity_cue=False,
    )
    return obj


def build_straight_two_tube_track(name_prefix, y, x0, x1, mat_rail, mat_tie, rail_kind):
    parts = []

    z = TRACK_Z

    front_tube = make_curve_object(
        f"{name_prefix}_front_tube",
        [(x0, y - RAIL_HALF_GAUGE, z), (x1, y - RAIL_HALF_GAUGE, z)],
        RAIL_RADIUS,
        mat_rail,
        "neutral_gray_track_tube",
        rail_kind,
    )
    parts.append(front_tube)

    back_tube = make_curve_object(
        f"{name_prefix}_back_tube",
        [(x0, y + RAIL_HALF_GAUGE, z), (x1, y + RAIL_HALF_GAUGE, z)],
        RAIL_RADIUS,
        mat_rail,
        "neutral_gray_track_tube",
        rail_kind,
    )
    parts.append(back_tube)

    for idx, frac in enumerate([0.05, 0.14, 0.23, 0.32, 0.41, 0.50, 0.59, 0.68, 0.77, 0.86, 0.95]):
        x = lerp(x0, x1, frac)
        tie = add_cube(
            f"{name_prefix}_cross_tie_{idx:02d}",
            (x, y, z - 0.045),
            (0.055, 0.40, 0.045),
            material=mat_tie,
        )
        tag(
            tie,
            tie.name,
            "neutral_gray_track_cross_tie",
            "static_solid",
            "cube",
            "dark_gray",
            False,
            solid=True,
            pb_rail_kind=rail_kind,
            pb_identity_cue=False,
        )
        parts.append(tie)

    return parts


def build_tunnel(mat_tunnel, mat_edge, mat_shadow):
    parts = []

    x_mid = TUNNEL_CENTER_X
    y_mid = TUNNEL_CENTER_Y
    z_mid = 0.5 * (TUNNEL_Z_MIN + TUNNEL_Z_MAX)

    # Bottom floor inside tunnel
    bottom = add_cube(
        "gray_two_lane_tunnel_bottom_floor",
        (x_mid, y_mid, TUNNEL_Z_MIN + TUNNEL_WALL_T / 2.0),
        (TUNNEL_X_MAX - TUNNEL_X_MIN, TUNNEL_Y_MAX - TUNNEL_Y_MIN, TUNNEL_WALL_T),
        material=mat_tunnel,
    )
    tag(
        bottom,
        bottom.name,
        "tunnel_floor",
        "static_solid",
        "cube",
        "gray",
        False,
        solid=True,
        pb_tunnel_id="two_lane_identity_tunnel",
    )
    parts.append(bottom)

    # Front wall: camera-side occluder.
    front_wall = add_cube(
        "gray_two_lane_tunnel_front_wall_camera_side",
        (x_mid, TUNNEL_Y_MIN + TUNNEL_WALL_T / 2.0, z_mid),
        (TUNNEL_X_MAX - TUNNEL_X_MIN, TUNNEL_WALL_T, TUNNEL_Z_MAX - TUNNEL_Z_MIN),
        material=mat_tunnel,
    )
    tag(
        front_wall,
        front_wall.name,
        "tunnel_occluder",
        "static_solid",
        "cube",
        "gray",
        False,
        solid=True,
        pb_occludes=True,
        pb_tunnel_id="two_lane_identity_tunnel",
    )
    parts.append(front_wall)

    # Back wall.
    back_wall = add_cube(
        "gray_two_lane_tunnel_back_wall",
        (x_mid, TUNNEL_Y_MAX - TUNNEL_WALL_T / 2.0, z_mid),
        (TUNNEL_X_MAX - TUNNEL_X_MIN, TUNNEL_WALL_T, TUNNEL_Z_MAX - TUNNEL_Z_MIN),
        material=mat_tunnel,
    )
    tag(
        back_wall,
        back_wall.name,
        "tunnel_wall",
        "static_solid",
        "cube",
        "gray",
        False,
        solid=True,
        pb_tunnel_id="two_lane_identity_tunnel",
    )
    parts.append(back_wall)

    # Roof.
    roof = add_cube(
        "gray_two_lane_tunnel_roof",
        (x_mid, y_mid, TUNNEL_Z_MAX - TUNNEL_WALL_T / 2.0),
        (TUNNEL_X_MAX - TUNNEL_X_MIN, TUNNEL_Y_MAX - TUNNEL_Y_MIN, TUNNEL_WALL_T),
        material=mat_tunnel,
    )
    tag(
        roof,
        roof.name,
        "tunnel_roof",
        "static_solid",
        "cube",
        "gray",
        False,
        solid=True,
        pb_occludes=True,
        pb_tunnel_id="two_lane_identity_tunnel",
    )
    parts.append(roof)

    # Dark interior floor strip to make the tunnel read as hollow.
    shadow = add_cube(
        "dark_visible_two_lane_tunnel_interior_shadow",
        (x_mid, y_mid, TRACK_Z - 0.035),
        ((TUNNEL_X_MAX - TUNNEL_X_MIN) * 0.86, (TUNNEL_Y_MAX - TUNNEL_Y_MIN) * 0.72, 0.035),
        material=mat_shadow,
    )
    tag(
        shadow,
        shadow.name,
        "tunnel_interior_shadow",
        "static_visual_marker",
        "cube",
        "dark_gray",
        False,
        solid=False,
        pb_tunnel_id="two_lane_identity_tunnel",
    )
    parts.append(shadow)

    # Opening rims: left and right sides, both lanes visible as one wide open mouth.
    for side_name, x in [("left", TUNNEL_X_MIN), ("right", TUNNEL_X_MAX)]:
        top = add_cube(
            f"{side_name}_tunnel_opening_top_rim",
            (x, y_mid, TUNNEL_Z_MAX + 0.035),
            (TUNNEL_WALL_T * 1.25, TUNNEL_Y_MAX - TUNNEL_Y_MIN + 0.10, 0.070),
            material=mat_edge,
        )
        tag(
            top,
            top.name,
            "tunnel_opening_rim",
            "static_solid",
            "cube",
            "medium_gray",
            False,
            solid=True,
            pb_opening_side=side_name,
            pb_tunnel_opening=True,
        )
        parts.append(top)

        bottom = add_cube(
            f"{side_name}_tunnel_opening_bottom_lip",
            (x, y_mid, TUNNEL_Z_MIN + 0.060),
            (TUNNEL_WALL_T * 1.25, TUNNEL_Y_MAX - TUNNEL_Y_MIN + 0.10, 0.080),
            material=mat_edge,
        )
        tag(
            bottom,
            bottom.name,
            "tunnel_opening_rim",
            "static_solid",
            "cube",
            "medium_gray",
            False,
            solid=True,
            pb_opening_side=side_name,
            pb_tunnel_opening=True,
        )
        parts.append(bottom)

        front = add_cube(
            f"{side_name}_tunnel_opening_front_vertical_rim",
            (x, TUNNEL_Y_MIN - 0.035, z_mid),
            (TUNNEL_WALL_T * 1.25, 0.070, TUNNEL_Z_MAX - TUNNEL_Z_MIN + 0.10),
            material=mat_edge,
        )
        tag(
            front,
            front.name,
            "tunnel_opening_rim",
            "static_solid",
            "cube",
            "medium_gray",
            False,
            solid=True,
            pb_opening_side=side_name,
            pb_tunnel_opening=True,
        )
        parts.append(front)

        back = add_cube(
            f"{side_name}_tunnel_opening_back_vertical_rim",
            (x, TUNNEL_Y_MAX + 0.035, z_mid),
            (TUNNEL_WALL_T * 1.25, 0.070, TUNNEL_Z_MAX - TUNNEL_Z_MIN + 0.10),
            material=mat_edge,
        )
        tag(
            back,
            back.name,
            "tunnel_opening_rim",
            "static_solid",
            "cube",
            "medium_gray",
            False,
            solid=True,
            pb_opening_side=side_name,
            pb_tunnel_opening=True,
        )
        parts.append(back)

    return parts


def build_scene():
    scene = bpy.context.scene
    set_render(scene)

    mat_floor = make_mat("mat_floor_warm", (0.82, 0.80, 0.75), roughness=0.82)
    mat_rail = make_mat("mat_neutral_gray_track_tubes", (0.46, 0.46, 0.46), roughness=0.58)
    mat_tie = make_mat("mat_dark_gray_track_ties", (0.28, 0.28, 0.28), roughness=0.74)
    mat_tunnel = make_mat("mat_opaque_gray_tunnel", (0.30, 0.31, 0.33), roughness=0.82)
    mat_tunnel_edge = make_mat("mat_tunnel_edge_medium_gray", (0.55, 0.56, 0.58), roughness=0.70)
    mat_shadow = make_mat("mat_tunnel_interior_shadow", (0.05, 0.052, 0.058), roughness=0.92)
    mat_red = make_mat("mat_red_identity_A_ball", (0.95, 0.03, 0.02), roughness=0.30)
    mat_blue = make_mat("mat_blue_identity_B_ball", (0.05, 0.20, 0.95), roughness=0.30)
    mat_backdrop = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)

    floor = add_cube(
        "large_floor_base",
        (0.0, 0.0, -0.04),
        (8.6, 3.8, 0.10),
        material=mat_floor,
    )
    tag(floor, floor.name, "ground", "static_solid", "cube", "warm_beige", False, solid=True)

    backdrop = add_cube(
        "rear_backdrop_panel",
        (0.0, 2.05, 1.55),
        (8.6, 0.08, 3.1),
        material=mat_backdrop,
    )
    tag(backdrop, backdrop.name, "background", "static_solid", "cube", "off_white", False, solid=True)

    # Two neutral gray tracks. No red/blue lane colors.
    front_track = build_straight_two_tube_track(
        "front_neutral_gray_track",
        FRONT_Y,
        X_START - 0.20,
        X_FINAL + 0.20,
        mat_rail,
        mat_tie,
        "front_track_identity_A_path",
    )

    back_track = build_straight_two_tube_track(
        "back_neutral_gray_track",
        BACK_Y,
        X_START - 0.20,
        X_FINAL + 0.20,
        mat_rail,
        mat_tie,
        "back_track_identity_B_path",
    )

    tunnel_parts = build_tunnel(mat_tunnel, mat_tunnel_edge, mat_shadow)

    # Red ball on front track.
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=48,
        ring_count=24,
        radius=BALL_RADIUS,
        location=(X_START, FRONT_Y, BALL_Z),
    )
    red_ball = bpy.context.object
    red_ball.name = "identity_A_red_ball_front_track"
    red_ball.data.materials.append(mat_red)
    tag(
        red_ball,
        "identity_A_red_ball_front_track",
        "target",
        "dynamic_object",
        "sphere",
        "red",
        True,
        solid=True,
        pb_identity_id="A",
        pb_expected_track="front",
        pb_expected_final_track="front",
        pb_radius=BALL_RADIUS,
        pb_centered_between_rails=True,
        pb_rail_clearance=BALL_RAIL_CLEARANCE,
    )

    # Blue ball on back track.
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=48,
        ring_count=24,
        radius=BALL_RADIUS,
        location=(X_START, BACK_Y, BALL_Z),
    )
    blue_ball = bpy.context.object
    blue_ball.name = "identity_B_blue_ball_back_track"
    blue_ball.data.materials.append(mat_blue)
    tag(
        blue_ball,
        "identity_B_blue_ball_back_track",
        "target",
        "dynamic_object",
        "sphere",
        "blue",
        True,
        solid=True,
        pb_identity_id="B",
        pb_expected_track="back",
        pb_expected_final_track="back",
        pb_radius=BALL_RADIUS,
        pb_centered_between_rails=True,
        pb_rail_clearance=BALL_RAIL_CLEARANCE,
    )

    # Lights
    bpy.ops.object.light_add(type="AREA", location=(-2.8, -3.9, 5.8))
    key_light = bpy.context.object
    key_light.name = "large_softbox_light"
    key_light.data.energy = 850
    key_light.data.size = 5.8

    bpy.ops.object.light_add(type="POINT", location=(3.7, -2.8, 3.4))
    fill_light = bpy.context.object
    fill_light.name = "right_fill_light"
    fill_light.data.energy = 135

    # Camera: front-right view shows both tracks, both balls, and tunnel openings.
    bpy.ops.object.camera_add(location=(5.1, -6.7, 3.1))
    camera = bpy.context.object
    camera.name = "camera_multi_object_identity_tunnel"
    camera.data.lens = 34
    look_at(camera, (0.0, 0.0, 0.95))
    camera.data.dof.use_dof = False
    scene.camera = camera

    return {
        "scene": scene,
        "red_ball": red_ball,
        "blue_ball": blue_ball,
        "front_track": front_track,
        "back_track": back_track,
        "tunnel_parts": tunnel_parts,
    }


def set_ball_state(ball, identity_id, color_name, track_name, frame, x):
    if x < TUNNEL_X_MIN:
        phase = "visible_before_tunnel"
        visibility = "visible"
        loc_state = f"outside_left_on_{track_name}_track"
    elif x <= TUNNEL_X_MAX:
        phase = "inside_opaque_tunnel_occluded"
        visibility = "occluded_inside_tunnel"
        loc_state = f"inside_tunnel_on_{track_name}_track"
    else:
        phase = "visible_after_tunnel"
        visibility = "visible"
        loc_state = f"outside_right_on_{track_name}_track"

    ball["pb_state"] = f"{color_name}_{phase}"
    ball["pb_identity_id"] = identity_id
    ball["pb_identity_phase"] = phase
    ball["pb_visibility_state"] = visibility
    ball["pb_location_state"] = loc_state
    ball["pb_expected_color"] = color_name
    ball["pb_expected_track"] = track_name
    ball["pb_identity_preserved"] = True
    ball["pb_no_swap_allowed"] = True
    ball["pb_must_not_change_track"] = True
    ball["pb_inside_tunnel"] = bool(TUNNEL_X_MIN <= x <= TUNNEL_X_MAX)


def animate_scene(scene, red_ball, blue_ball, front_track, back_track, tunnel_parts):
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        x = ball_x_at_frame(frame)

        red_ball.location = (x, FRONT_Y, BALL_Z)
        blue_ball.location = (x, BACK_Y, BALL_Z)

        dist = x - X_START
        red_ball.rotation_euler = (0.0, -dist / BALL_RADIUS, 0.0)
        blue_ball.rotation_euler = (0.0, -dist / BALL_RADIUS, 0.0)

        set_ball_state(red_ball, "A", "red", "front", frame, x)
        set_ball_state(blue_ball, "B", "blue", "back", frame, x)

        tunnel_phase = (
            "balls_inside_tunnel_occluded"
            if TUNNEL_X_MIN <= x <= TUNNEL_X_MAX
            else "balls_visible_outside_tunnel"
        )

        for obj in tunnel_parts:
            obj["pb_state"] = "static_opaque_open_ended_two_lane_tunnel"
            obj["pb_tunnel_phase"] = tunnel_phase
            obj["pb_tunnel_id"] = "two_lane_identity_tunnel"
            obj["pb_open_ended_tunnel"] = True
            obj["pb_not_a_wall"] = True
            obj["pb_hides_balls_inside"] = True

        for obj in front_track + back_track:
            obj["pb_state"] = "static_neutral_gray_identity_track"
            obj["pb_no_color_identity_cue"] = True
            obj["pb_track_color_does_not_encode_ball_identity"] = True

        red_ball.keyframe_insert(data_path="location", frame=frame)
        red_ball.keyframe_insert(data_path="rotation_euler", frame=frame)
        blue_ball.keyframe_insert(data_path="location", frame=frame)
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
                "Two colored balls move at the same time on two identical neutral gray parallel tracks. "
                "In the first frame, the red ball is clearly visible on the front track and the blue ball is clearly visible on the back track. "
                "Both tracks enter the same opaque gray two-lane tunnel with open left and right ends. "
                "The tracks are neutral gray and do not reveal identity by color. "
                "The red ball and blue ball enter the tunnel and are briefly hidden inside. "
                "When they exit the tunnel on the right side, the red ball must still be the red ball on the front track, "
                "and the blue ball must still be the blue ball on the back track. "
                "The two balls must not swap identities, swap colors, change tracks, merge, disappear, teleport, duplicate, or change size."
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
        front_track=objs["front_track"],
        back_track=objs["back_track"],
        tunnel_parts=objs["tunnel_parts"],
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
    print("RULES:")
    print(" - first frame: red front track, blue back track")
    print(" - tracks are neutral gray")
    print(" - both balls enter open-ended opaque tunnel")
    print(" - red exits front, blue exits back")
    print(" - no identity swap / color swap / track swap / merge / disappearance")
    print("=" * 100)


if __name__ == "__main__":
    main()
