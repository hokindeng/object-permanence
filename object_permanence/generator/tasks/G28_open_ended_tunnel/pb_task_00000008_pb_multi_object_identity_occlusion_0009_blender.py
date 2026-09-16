# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

ITEM_ID = "PB_MULTI_OBJECT_IDENTITY_OCCLUSION_0009"

FPS = 24
FRAME_START = 1
FRAME_END = 120

BALL_RADIUS = 0.22

# Two balls move in opposite directions on two neutral gray lanes.
RED_START_X = -3.35
RED_END_X = 3.35

BLUE_START_X = 3.35
BLUE_END_X = -3.35

RED_LANE_Y = -0.28
BLUE_LANE_Y = 0.28

TRACK_Z = 0.74
BALL_Z = TRACK_Z + BALL_RADIUS + 0.018

# Real tunnel / occlusion cover.
# Important: open along X direction.
# Balls enter the left/right openings and pass through the tunnel volume.
TUNNEL_CENTER_X = 0.0
TUNNEL_CENTER_Y = 0.0
TUNNEL_FLOOR_Z = TRACK_Z
TUNNEL_LENGTH_X = 2.05
TUNNEL_WIDTH_Y = 1.50
TUNNEL_HEIGHT_Z = 1.35
TUNNEL_WALL_THICKNESS = 0.12

TUNNEL_X_MIN = TUNNEL_CENTER_X - TUNNEL_LENGTH_X / 2.0
TUNNEL_X_MAX = TUNNEL_CENTER_X + TUNNEL_LENGTH_X / 2.0

OCCLUSION_START_FRAME = 40
OCCLUSION_END_FRAME = 82

INPUT_FRAME_1 = 1
OPTIONAL_BEFORE_OCCLUSION_FRAME = 34
OPTIONAL_AFTER_OCCLUSION_FRAME = 94

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

OUT_DIR = os.path.join(PROJECT_ROOT, "permanence_blender_outputs", ITEM_ID)
FRAMES_DIR = os.path.join(OUT_DIR, f"{ITEM_ID}_reference_frames")
SCENE_FILE = os.path.join(OUT_DIR, f"{ITEM_ID}_scene.blend")
TASK_JSON_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_task.json")

INPUT_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_input_frame_01.png")
OPTIONAL_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_before_tunnel_frame_02.png")
OPTIONAL_FRAME_02B_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_after_tunnel_frame_02B.png")


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


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def smooth01(t):
    t = max(0.0, min(1.0, float(t)))
    return 0.5 - 0.5 * math.cos(math.pi * t)


def lerp(a, b, t):
    return a + (b - a) * t


def progress_at_frame(frame):
    t = (frame - FRAME_START) / max(1, FRAME_END - FRAME_START)
    return smooth01(t)


def red_x_at_frame(frame):
    return lerp(RED_START_X, RED_END_X, progress_at_frame(frame))


def blue_x_at_frame(frame):
    return lerp(BLUE_START_X, BLUE_END_X, progress_at_frame(frame))


def make_mat(
    name,
    color,
    roughness=0.55,
    metallic=0.0,
    alpha=1.0,
    blend=None,
):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (color[0], color[1], color[2], alpha)

    try:
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            def set_input(socket_name, value):
                if socket_name in bsdf.inputs:
                    bsdf.inputs[socket_name].default_value = value

            set_input("Base Color", (color[0], color[1], color[2], alpha))
            set_input("Alpha", alpha)
            set_input("Roughness", roughness)
            set_input("Metallic", metallic)
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


def add_cube(name, location, dimensions, rotation=(0, 0, 0), material=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material is not None:
        obj.data.materials.append(material)
    return obj


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


def build_tunnel(mat_tunnel, mat_edge, mat_shadow):
    """
    Build a real rectangular tunnel:
    - open on left and right ends along X
    - front wall, back wall, and roof hide the balls from camera
    - no wall closes the X openings
    """
    z_mid = TUNNEL_FLOOR_Z + TUNNEL_HEIGHT_Z / 2.0
    y_front = TUNNEL_CENTER_Y - TUNNEL_WIDTH_Y / 2.0 + TUNNEL_WALL_THICKNESS / 2.0
    y_back = TUNNEL_CENTER_Y + TUNNEL_WIDTH_Y / 2.0 - TUNNEL_WALL_THICKNESS / 2.0
    z_roof = TUNNEL_FLOOR_Z + TUNNEL_HEIGHT_Z - TUNNEL_WALL_THICKNESS / 2.0

    parts = []

    front_wall = add_cube(
        "gray_tunnel_front_wall_camera_side",
        (TUNNEL_CENTER_X, y_front, z_mid),
        (TUNNEL_LENGTH_X, TUNNEL_WALL_THICKNESS, TUNNEL_HEIGHT_Z),
        material=mat_tunnel,
    )
    tag(
        front_wall,
        "gray_tunnel_front_wall_camera_side",
        "tunnel_occluder",
        "static_solid",
        "cube",
        "gray",
        False,
        solid=True,
        pb_occludes=True,
        pb_tunnel_part="front_wall",
    )
    parts.append(front_wall)

    back_wall = add_cube(
        "gray_tunnel_back_wall",
        (TUNNEL_CENTER_X, y_back, z_mid),
        (TUNNEL_LENGTH_X, TUNNEL_WALL_THICKNESS, TUNNEL_HEIGHT_Z),
        material=mat_tunnel,
    )
    tag(
        back_wall,
        "gray_tunnel_back_wall",
        "tunnel_occluder",
        "static_solid",
        "cube",
        "gray",
        False,
        solid=True,
        pb_occludes=True,
        pb_tunnel_part="back_wall",
    )
    parts.append(back_wall)

    roof = add_cube(
        "gray_tunnel_roof",
        (TUNNEL_CENTER_X, TUNNEL_CENTER_Y, z_roof),
        (TUNNEL_LENGTH_X, TUNNEL_WIDTH_Y, TUNNEL_WALL_THICKNESS),
        material=mat_tunnel,
    )
    tag(
        roof,
        "gray_tunnel_roof",
        "tunnel_occluder",
        "static_solid",
        "cube",
        "gray",
        False,
        solid=True,
        pb_occludes=True,
        pb_tunnel_part="roof",
    )
    parts.append(roof)

    # Dark inner shadow strip to make the tunnel interior read as an opening.
    inner_shadow = add_cube(
        "dark_visible_tunnel_interior_shadow",
        (TUNNEL_CENTER_X, TUNNEL_CENTER_Y, TRACK_Z + 0.018),
        (TUNNEL_LENGTH_X * 0.92, TUNNEL_WIDTH_Y * 0.72, 0.026),
        material=mat_shadow,
    )
    tag(
        inner_shadow,
        "dark_visible_tunnel_interior_shadow",
        "tunnel_interior",
        "static_visual_marker",
        "cube",
        "dark_gray",
        False,
        solid=False,
    )
    parts.append(inner_shadow)

    # Neutral gray opening rims. These indicate open tunnel mouths, not walls.
    rim_specs = [
        ("left_tunnel_opening_top_rim", TUNNEL_X_MIN, TUNNEL_CENTER_Y, z_roof + TUNNEL_WALL_THICKNESS * 0.55,
         (TUNNEL_WALL_THICKNESS, TUNNEL_WIDTH_Y + 0.12, TUNNEL_WALL_THICKNESS * 0.75)),
        ("right_tunnel_opening_top_rim", TUNNEL_X_MAX, TUNNEL_CENTER_Y, z_roof + TUNNEL_WALL_THICKNESS * 0.55,
         (TUNNEL_WALL_THICKNESS, TUNNEL_WIDTH_Y + 0.12, TUNNEL_WALL_THICKNESS * 0.75)),
        ("left_tunnel_front_vertical_rim", TUNNEL_X_MIN, y_front, z_mid,
         (TUNNEL_WALL_THICKNESS, TUNNEL_WALL_THICKNESS * 1.25, TUNNEL_HEIGHT_Z + 0.08)),
        ("right_tunnel_front_vertical_rim", TUNNEL_X_MAX, y_front, z_mid,
         (TUNNEL_WALL_THICKNESS, TUNNEL_WALL_THICKNESS * 1.25, TUNNEL_HEIGHT_Z + 0.08)),
        ("left_tunnel_back_vertical_rim", TUNNEL_X_MIN, y_back, z_mid,
         (TUNNEL_WALL_THICKNESS, TUNNEL_WALL_THICKNESS * 1.25, TUNNEL_HEIGHT_Z + 0.08)),
        ("right_tunnel_back_vertical_rim", TUNNEL_X_MAX, y_back, z_mid,
         (TUNNEL_WALL_THICKNESS, TUNNEL_WALL_THICKNESS * 1.25, TUNNEL_HEIGHT_Z + 0.08)),
    ]

    for name, x, y, z, dims in rim_specs:
        rim = add_cube(name, (x, y, z), dims, material=mat_edge)
        tag(
            rim,
            name,
            "tunnel_opening_rim",
            "static_solid",
            "cube",
            "medium_gray",
            False,
            solid=True,
            pb_tunnel_opening=True,
        )
        parts.append(rim)

    return parts


def build_scene():
    scene = bpy.context.scene
    set_render(scene)

    mat_floor = make_mat("mat_floor_warm", (0.82, 0.80, 0.75), roughness=0.82)

    # All track / lane cue materials are neutral gray.
    mat_track = make_mat("mat_track_neutral_gray", (0.58, 0.58, 0.58), roughness=0.72)
    mat_lane = make_mat("mat_lane_marker_neutral_gray", (0.40, 0.40, 0.40), roughness=0.68)
    mat_endpoint = make_mat("mat_endpoint_neutral_gray", (0.34, 0.34, 0.34), roughness=0.64)

    mat_red_ball = make_mat("mat_red_ball_identity_A", (0.95, 0.03, 0.02), roughness=0.30)
    mat_blue_ball = make_mat("mat_blue_ball_identity_B", (0.05, 0.20, 0.95), roughness=0.30)

    mat_tunnel = make_mat("mat_gray_tunnel_solid", (0.30, 0.31, 0.33), roughness=0.78)
    mat_tunnel_edge = make_mat("mat_tunnel_edge_medium_gray", (0.50, 0.51, 0.53), roughness=0.70)
    mat_tunnel_shadow = make_mat("mat_tunnel_interior_shadow", (0.055, 0.058, 0.065), roughness=0.90)

    mat_backdrop = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)

    floor = add_cube(
        "large_floor_base",
        (0.0, 0.0, 0.0),
        (8.8, 3.4, 0.12),
        material=mat_floor,
    )
    tag(floor, "large_floor_base", "ground", "static_solid", "cube", "warm_beige", False, solid=True)

    backdrop = add_cube(
        "rear_backdrop_panel",
        (0.0, 1.95, 1.65),
        (8.8, 0.08, 3.3),
        material=mat_backdrop,
    )
    tag(backdrop, "rear_backdrop_panel", "background", "static_solid", "cube", "off_white", False, solid=True)

    track = add_cube(
        "shared_neutral_gray_two_lane_track",
        (0.0, 0.0, TRACK_Z - 0.045),
        (7.7, 1.22, 0.09),
        material=mat_track,
    )
    tag(track, "shared_neutral_gray_two_lane_track", "support_surface", "static_solid", "cube", "gray", False, solid=True)

    # Neutral gray lane lines only. They do not reveal red/blue identity.
    lane_1 = add_cube(
        "neutral_gray_lane_marker_front",
        (0.0, RED_LANE_Y, TRACK_Z + 0.014),
        (7.5, 0.052, 0.018),
        material=mat_lane,
    )
    tag(lane_1, "neutral_gray_lane_marker_front", "lane_marker", "static_visual_marker", "cube", "gray", False, solid=False)

    lane_2 = add_cube(
        "neutral_gray_lane_marker_back",
        (0.0, BLUE_LANE_Y, TRACK_Z + 0.014),
        (7.5, 0.052, 0.018),
        material=mat_lane,
    )
    tag(lane_2, "neutral_gray_lane_marker_back", "lane_marker", "static_visual_marker", "cube", "gray", False, solid=False)

    # Neutral endpoint pads. These show start/end zones but not identity colors.
    endpoint_specs = [
        ("neutral_left_front_endpoint_pad", RED_START_X, RED_LANE_Y),
        ("neutral_right_front_endpoint_pad", RED_END_X, RED_LANE_Y),
        ("neutral_right_back_endpoint_pad", BLUE_START_X, BLUE_LANE_Y),
        ("neutral_left_back_endpoint_pad", BLUE_END_X, BLUE_LANE_Y),
    ]
    for name, x, y in endpoint_specs:
        pad = add_cube(
            name,
            (x, y, TRACK_Z + 0.028),
            (0.28, 0.15, 0.026),
            material=mat_endpoint,
        )
        tag(pad, name, "neutral_endpoint_marker", "static_visual_marker", "cube", "gray", False, solid=False)

    tunnel_parts = build_tunnel(mat_tunnel, mat_tunnel_edge, mat_tunnel_shadow)

    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=48,
        ring_count=24,
        radius=BALL_RADIUS,
        location=(RED_START_X, RED_LANE_Y, BALL_Z),
    )
    red_ball = bpy.context.object
    red_ball.name = "identity_A_red_ball"
    red_ball.data.materials.append(mat_red_ball)
    tag(
        red_ball,
        "identity_A_red_ball",
        "target",
        "dynamic_object",
        "sphere",
        "red",
        True,
        solid=True,
        pb_identity_id="A",
        pb_expected_start_side="left",
        pb_expected_end_side="right",
        pb_expected_lane_y=RED_LANE_Y,
        pb_radius=BALL_RADIUS,
    )

    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=48,
        ring_count=24,
        radius=BALL_RADIUS,
        location=(BLUE_START_X, BLUE_LANE_Y, BALL_Z),
    )
    blue_ball = bpy.context.object
    blue_ball.name = "identity_B_blue_ball"
    blue_ball.data.materials.append(mat_blue_ball)
    tag(
        blue_ball,
        "identity_B_blue_ball",
        "target",
        "dynamic_object",
        "sphere",
        "blue",
        True,
        solid=True,
        pb_identity_id="B",
        pb_expected_start_side="right",
        pb_expected_end_side="left",
        pb_expected_lane_y=BLUE_LANE_Y,
        pb_radius=BALL_RADIUS,
    )

    bpy.ops.object.light_add(type="AREA", location=(-2.8, -3.8, 5.9))
    key_light = bpy.context.object
    key_light.name = "large_softbox_light"
    key_light.data.energy = 780
    key_light.data.size = 5.4

    bpy.ops.object.light_add(type="POINT", location=(3.2, -2.8, 3.4))
    fill_light = bpy.context.object
    fill_light.name = "fill_point_light"
    fill_light.data.energy = 120

    bpy.ops.object.camera_add(location=(4.9, -6.6, 3.25))
    camera = bpy.context.object
    camera.name = "camera_identity_tunnel_occlusion_view"
    camera.data.lens = 38
    look_at(camera, (0.0, 0.0, 1.12))
    camera.data.dof.use_dof = False
    scene.camera = camera

    return {
        "scene": scene,
        "red_ball": red_ball,
        "blue_ball": blue_ball,
        "tunnel_parts": tunnel_parts,
    }


def is_inside_tunnel(x):
    return TUNNEL_X_MIN <= x <= TUNNEL_X_MAX


def set_ball_semantic_state(ball, color_name, identity_id, frame, x, start_x, end_x):
    if is_inside_tunnel(x):
        phase = "inside_gray_tunnel_occluded"
    elif frame < OCCLUSION_START_FRAME:
        phase = "visible_before_entering_tunnel"
    else:
        phase = "visible_after_exiting_tunnel"

    side = "left" if x < TUNNEL_X_MIN else "right" if x > TUNNEL_X_MAX else "inside_tunnel"

    ball["pb_state"] = f"{color_name}_{phase}"
    ball["pb_identity_id"] = identity_id
    ball["pb_identity_phase"] = phase
    ball["pb_current_side"] = side
    ball["pb_expected_color"] = color_name
    ball["pb_expected_identity_constant"] = True
    ball["pb_no_swap_allowed"] = True
    ball["pb_inside_tunnel"] = bool(is_inside_tunnel(x))

    if is_inside_tunnel(x):
        ball["pb_contact_state"] = "moving_inside_tunnel_occluded"
        ball["pb_visibility_state"] = "occluded_by_gray_tunnel"
    else:
        ball["pb_contact_state"] = "moving_on_track_visible"
        ball["pb_visibility_state"] = "visible"

    if frame == FRAME_END:
        ball["pb_final_side"] = "right" if end_x > start_x else "left"


def animate_scene(scene, red_ball, blue_ball, tunnel_parts):
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        rx = red_x_at_frame(frame)
        bx = blue_x_at_frame(frame)

        red_ball.location = (rx, RED_LANE_Y, BALL_Z)
        blue_ball.location = (bx, BLUE_LANE_Y, BALL_Z)

        red_dist = rx - RED_START_X
        blue_dist = BLUE_START_X - bx

        red_ball.rotation_euler = (0.0, -red_dist / BALL_RADIUS, 0.0)
        blue_ball.rotation_euler = (0.0, blue_dist / BALL_RADIUS, 0.0)

        set_ball_semantic_state(
            red_ball,
            color_name="red",
            identity_id="A",
            frame=frame,
            x=rx,
            start_x=RED_START_X,
            end_x=RED_END_X,
        )
        set_ball_semantic_state(
            blue_ball,
            color_name="blue",
            identity_id="B",
            frame=frame,
            x=bx,
            start_x=BLUE_START_X,
            end_x=BLUE_END_X,
        )

        tunnel_phase = (
            "balls_inside_open_ended_tunnel"
            if is_inside_tunnel(rx) or is_inside_tunnel(bx)
            else "tunnel_openings_visible_no_ball_inside"
        )
        for obj in tunnel_parts:
            obj["pb_state"] = "static_gray_open_ended_tunnel"
            obj["pb_occlusion_phase"] = tunnel_phase
            obj["pb_open_ended_tunnel"] = True
            obj["pb_not_a_wall"] = True

        red_ball.keyframe_insert(data_path="location", frame=frame)
        red_ball.keyframe_insert(data_path="rotation_euler", frame=frame)
        blue_ball.keyframe_insert(data_path="location", frame=frame)
        blue_ball.keyframe_insert(data_path="rotation_euler", frame=frame)

    # Blender 5.x note:
    # Do NOT access obj.animation_data.action.fcurves.
    # We key every integer frame, so rendered frames are deterministic enough.

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
                "Two balls move at the same time on a neutral gray two-lane track. "
                "The red ball starts on the left lane and moves to the right. "
                "The blue ball starts on the right lane and moves to the left. "
                "Both balls enter an open-ended gray tunnel with visible left and right openings. "
                "The balls are briefly hidden while they pass inside the tunnel, then each ball exits from the opposite opening. "
                "The tunnel is not a wall: it has open ends that the balls pass through. "
                "After the occlusion, the red ball must still be the same red ball and continue to the right side, "
                "while the blue ball must still be the same blue ball and continue to the left side. "
                "The neutral gray track must not reveal identity by lane color. "
                "The two objects must not swap identities, colors, trajectories, sizes, or counts. "
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
        tunnel_parts=objs["tunnel_parts"],
    )

    render_png(scene, INPUT_FRAME_1, INPUT_FRAME_PATH)
    render_png(scene, OPTIONAL_BEFORE_OCCLUSION_FRAME, OPTIONAL_FRAME_PATH)
    render_png(scene, OPTIONAL_AFTER_OCCLUSION_FRAME, OPTIONAL_FRAME_02B_PATH)

    render_animation(scene)
    write_task_json()
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("Output:", OUT_DIR)
    print("FIXED:")
    print(" - central wall replaced by open-ended gray tunnel")
    print(" - balls enter and exit tunnel openings")
    print(" - track and lane markers are neutral gray")
    print(" - identity must be preserved through tunnel occlusion")
    print("=" * 100)


if __name__ == "__main__":
    main()
