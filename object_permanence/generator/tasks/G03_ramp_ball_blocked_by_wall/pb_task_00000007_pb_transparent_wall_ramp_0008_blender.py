# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

ITEM_ID = "PB_TRANSPARENT_WALL_RAMP_0008"

FPS = 24
FRAME_START = 1
FRAME_END = 120

RAMP_LENGTH = 8.0
RAMP_WIDTH = 1.8
RAMP_THICKNESS = 0.18
RAMP_ANGLE_DEG = 12.0
RAMP_ANGLE = math.radians(RAMP_ANGLE_DEG)
RAMP_CENTER = Vector((0.0, 0.0, 1.45))

BALL_RADIUS = 0.23
BALL_X_START = -3.35

WALL_X = 0.55
WALL_THICKNESS_X = 0.16
WALL_WIDTH_Y = 1.24
WALL_HEIGHT_Z = 1.28

BALL_CONTACT_X = WALL_X - WALL_THICKNESS_X / 2.0 - BALL_RADIUS - 0.008
BALL_REBOUND_X = BALL_CONTACT_X - 0.28
BALL_FINAL_X = BALL_CONTACT_X - 0.055

CONTACT_FRAME = 74
REBOUND_FRAME = 92

INPUT_FRAME_1 = 1
OPTIONAL_FRAME_2 = 48
OPTIONAL_CONTACT_FRAME_02B = 84

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
OUT_DIR = os.path.join(PROJECT_ROOT, "permanence_blender_outputs", ITEM_ID)
FRAMES_DIR = os.path.join(OUT_DIR, f"{ITEM_ID}_reference_frames")
SCENE_FILE = os.path.join(OUT_DIR, f"{ITEM_ID}_scene.blend")
TASK_JSON_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_task.json")

INPUT_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_input_frame_01.png")
OPTIONAL_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_frame_02.png")
OPTIONAL_CONTACT_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_contact_frame_02B.png")


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


def ramp_basis():
    u = Vector((math.cos(RAMP_ANGLE), 0.0, -math.sin(RAMP_ANGLE)))
    v = Vector((0.0, 1.0, 0.0))
    n = Vector((math.sin(RAMP_ANGLE), 0.0, math.cos(RAMP_ANGLE)))
    return u, v, n


U, V, N = ramp_basis()


def local_to_world(x, y, z):
    return RAMP_CENTER + U * x + V * y + N * z


def smooth01(t):
    t = max(0.0, min(1.0, float(t)))
    return 0.5 - 0.5 * math.cos(math.pi * t)

def accel01(t):
    # gravity-driven roll from rest: displacement ~ t**2 (ease-in / accelerating).
    # Velocity rises monotonically and peaks at wall contact, matching s = 1/2 a t**2.
    t = max(0.0, min(1.0, t))
    return t * t


def lerp(a, b, t):
    return a + (b - a) * t


def ball_x_at_frame(frame):
    if frame <= CONTACT_FRAME:
        t = (frame - FRAME_START) / max(1, CONTACT_FRAME - FRAME_START)
        return lerp(BALL_X_START, BALL_CONTACT_X, accel01(t))

    if frame <= REBOUND_FRAME:
        t = (frame - CONTACT_FRAME) / max(1, REBOUND_FRAME - CONTACT_FRAME)
        return lerp(BALL_CONTACT_X, BALL_REBOUND_X, smooth01(t))

    t = (frame - REBOUND_FRAME) / max(1, FRAME_END - REBOUND_FRAME)
    return lerp(BALL_REBOUND_X, BALL_FINAL_X, smooth01(t))


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def make_mat(
    name,
    color,
    roughness=0.55,
    metallic=0.0,
    alpha=1.0,
    transmission_like=False,
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

            if transmission_like:
                set_input("Transmission Weight", 0.18)
                set_input("Transmission", 0.18)
                set_input("IOR", 1.45)
    except Exception:
        pass

    if blend is None:
        blend = "BLEND" if alpha < 1.0 else "OPAQUE"

    try:
        mat.blend_method = blend
        mat.show_transparent_back = True
        mat.use_screen_refraction = True
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
        scene.eevee.gtao_factor = 1.2
    except Exception:
        pass

    try:
        scene.eevee.use_ssr = True
        scene.eevee.use_ssr_refraction = True
    except Exception:
        pass

    if scene.world is None:
        scene.world = bpy.data.worlds.new("clean_white_world")
    scene.world.color = (1.0, 1.0, 1.0)

    try:
        scene.view_settings.view_transform = "Filmic"
        scene.view_settings.look = "Medium High Contrast"
        scene.view_settings.exposure = 0.0
        scene.view_settings.gamma = 1.0
    except Exception:
        pass


def build_scene():
    scene = bpy.context.scene
    set_render(scene)

    mat_ramp = make_mat("warm_light_wood", (0.76, 0.57, 0.36), roughness=0.68)
    mat_track = make_mat("pale_track_surface", (0.86, 0.73, 0.55), roughness=0.72)
    mat_ball = make_mat("glossy_red_ball", (0.95, 0.03, 0.02), roughness=0.35)
    mat_floor = make_mat("matte_offwhite_floor", (0.83, 0.81, 0.76), roughness=0.75)

    mat_glass = make_mat(
        "transparent_cyan_glass_solid",
        (0.30, 0.88, 1.00),
        roughness=0.10,
        alpha=0.38,
        transmission_like=True,
        blend="BLEND",
    )
    mat_glass_contact_face = make_mat(
        "slightly_darker_transparent_contact_face",
        (0.08, 0.58, 0.80),
        roughness=0.14,
        alpha=0.28,
        transmission_like=True,
        blend="BLEND",
    )
    mat_glass_edge = make_mat(
        "dark_teal_glass_edge_frame",
        (0.02, 0.22, 0.30),
        roughness=0.44,
        alpha=1.0,
    )
    mat_glass_highlight = make_mat(
        "white_glass_highlight_strips",
        (1.0, 1.0, 1.0),
        roughness=0.18,
        alpha=0.55,
        blend="BLEND",
    )
    mat_contact_marker = make_mat(
        "small_contact_marker_yellow",
        (1.0, 0.84, 0.10),
        roughness=0.46,
    )

    ramp_body = add_cube(
        "ramp_body",
        RAMP_CENTER,
        (RAMP_LENGTH, RAMP_WIDTH, RAMP_THICKNESS),
        rotation=(0.0, RAMP_ANGLE, 0.0),
        material=mat_ramp,
    )
    tag(ramp_body, "ramp_body", "support_surface", "static_solid", "cube", "wood", False, solid=True)

    track_center = local_to_world(0.0, 0.0, RAMP_THICKNESS / 2 + 0.018)
    track_strip = add_cube(
        "track_strip_on_ramp",
        track_center,
        (RAMP_LENGTH * 0.96, 0.56, 0.035),
        rotation=(0.0, RAMP_ANGLE, 0.0),
        material=mat_track,
    )
    tag(track_strip, "track_strip_on_ramp", "track", "static_solid", "cube", "pale_wood", False, solid=True)

    table_floor = add_cube(
        "table_floor",
        (0.6, 0.0, 0.35),
        (9.2, 3.2, 0.18),
        rotation=(0, 0, 0),
        material=mat_floor,
    )
    tag(table_floor, "table_floor", "ground", "static_solid", "cube", "offwhite", False, solid=True)

    wall_center = local_to_world(
        WALL_X,
        0.0,
        RAMP_THICKNESS / 2.0 + WALL_HEIGHT_Z / 2.0,
    )
    wall = add_cube(
        "transparent_glass_wall_across_track",
        wall_center,
        (WALL_THICKNESS_X, WALL_WIDTH_Y, WALL_HEIGHT_Z),
        rotation=(0.0, RAMP_ANGLE, 0.0),
        material=mat_glass,
    )
    tag(
        wall,
        "transparent_glass_wall_across_track",
        "transparent_barrier",
        "static_solid_transparent",
        "cube",
        "cyan_transparent",
        False,
        solid=True,
        pb_transparent=True,
        pb_blocks_motion=True,
        pb_wall_x=WALL_X,
        pb_wall_thickness=WALL_THICKNESS_X,
    )

    contact_face_panel = add_cube(
        "transparent_wall_contact_face_panel",
        local_to_world(
            WALL_X - WALL_THICKNESS_X / 2.0 + 0.003,
            0.0,
            RAMP_THICKNESS / 2.0 + WALL_HEIGHT_Z / 2.0,
        ),
        (0.010, WALL_WIDTH_Y * 0.96, WALL_HEIGHT_Z * 0.96),
        rotation=(0.0, RAMP_ANGLE, 0.0),
        material=mat_glass_contact_face,
    )
    tag(
        contact_face_panel,
        "transparent_wall_contact_face_panel",
        "contact_face",
        "static_solid_transparent",
        "cube",
        "blue_transparent",
        False,
        solid=True,
        pb_transparent=True,
    )

    EDGE = 0.055

    edge_specs = [
        (
            "transparent_wall_left_vertical_edge",
            -WALL_WIDTH_Y / 2.0,
            RAMP_THICKNESS / 2.0 + WALL_HEIGHT_Z / 2.0,
            (WALL_THICKNESS_X * 1.20, EDGE, WALL_HEIGHT_Z + EDGE),
        ),
        (
            "transparent_wall_right_vertical_edge",
            WALL_WIDTH_Y / 2.0,
            RAMP_THICKNESS / 2.0 + WALL_HEIGHT_Z / 2.0,
            (WALL_THICKNESS_X * 1.20, EDGE, WALL_HEIGHT_Z + EDGE),
        ),
        (
            "transparent_wall_bottom_edge",
            0.0,
            RAMP_THICKNESS / 2.0 + EDGE / 2.0,
            (WALL_THICKNESS_X * 1.20, WALL_WIDTH_Y + EDGE, EDGE),
        ),
        (
            "transparent_wall_top_edge",
            0.0,
            RAMP_THICKNESS / 2.0 + WALL_HEIGHT_Z - EDGE / 2.0,
            (WALL_THICKNESS_X * 1.20, WALL_WIDTH_Y + EDGE, EDGE),
        ),
    ]

    for name, y, z, dims in edge_specs:
        edge_obj = add_cube(
            name,
            local_to_world(WALL_X, y, z),
            dims,
            rotation=(0.0, RAMP_ANGLE, 0.0),
            material=mat_glass_edge,
        )
        tag(
            edge_obj,
            name,
            "transparent_wall_edge_frame",
            "static_solid",
            "cube",
            "dark_teal",
            False,
            solid=True,
        )

    for idx, z_frac in enumerate([0.38, 0.62], start=1):
        highlight = add_cube(
            f"transparent_wall_white_highlight_strip_{idx:02d}",
            local_to_world(
                WALL_X - WALL_THICKNESS_X / 2.0 - 0.006,
                0.0,
                RAMP_THICKNESS / 2.0 + WALL_HEIGHT_Z * z_frac,
            ),
            (0.008, WALL_WIDTH_Y * 0.64, 0.020),
            rotation=(0.0, RAMP_ANGLE, 0.0),
            material=mat_glass_highlight,
        )
        tag(
            highlight,
            highlight.name,
            "glass_visual_highlight",
            "static_visual_marker",
            "cube",
            "white",
            False,
            solid=False,
            pb_transparent=True,
        )

    contact_marker = add_cube(
        "small_contact_marker_on_track_before_transparent_wall",
        local_to_world(BALL_CONTACT_X, 0.0, RAMP_THICKNESS / 2.0 + 0.033),
        (0.14, 0.34, 0.018),
        rotation=(0.0, RAMP_ANGLE, 0.0),
        material=mat_contact_marker,
    )
    tag(
        contact_marker,
        "small_contact_marker_on_track_before_transparent_wall",
        "contact_marker",
        "static_visual_marker",
        "cube",
        "yellow",
        False,
        solid=False,
    )

    ball_z = RAMP_THICKNESS / 2.0 + BALL_RADIUS + 0.025
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=48,
        ring_count=24,
        radius=BALL_RADIUS,
        location=local_to_world(BALL_X_START, 0.0, ball_z),
    )
    ball = bpy.context.object
    ball.name = "target_red_ball_blocked_by_transparent_wall"
    ball.data.materials.append(mat_ball)
    tag(
        ball,
        "target_red_ball_blocked_by_transparent_wall",
        "target",
        "dynamic_object",
        "sphere",
        "red",
        True,
        solid=True,
        pb_radius=BALL_RADIUS,
    )

    bpy.ops.object.light_add(type="AREA", location=(-1.7, -3.8, 6.0))
    key_light = bpy.context.object
    key_light.name = "large_softbox_light"
    key_light.data.energy = 720
    key_light.data.size = 5.8

    bpy.ops.object.light_add(type="POINT", location=(-3.2, -2.1, 3.1))
    fill_light = bpy.context.object
    fill_light.name = "contact_face_fill_light"
    fill_light.data.energy = 95

    bpy.ops.object.light_add(type="POINT", location=(1.0, -2.8, 2.2))
    glass_light = bpy.context.object
    glass_light.name = "small_glass_highlight_light"
    glass_light.data.energy = 60

    bpy.ops.object.camera_add(location=(-4.2, -9.5, 4.7))
    camera = bpy.context.object
    camera.name = "camera_transparent_wall_contact_face_view"
    look_at(camera, (-0.75, 0.0, 1.32))
    camera.data.lens = 30
    camera.data.dof.use_dof = False
    scene.camera = camera

    return {
        "scene": scene,
        "wall": wall,
        "ball": ball,
        "ball_z": ball_z,
    }


def animate_scene(scene, wall, ball, ball_z):
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        x = ball_x_at_frame(frame)
        ball.location = local_to_world(x, 0.0, ball_z)

        distance = x - BALL_X_START
        ball.rotation_euler = (0.0, -distance / BALL_RADIUS, 0.0)

        if frame < CONTACT_FRAME:
            ball["pb_state"] = "rolling_toward_transparent_wall"
            ball["pb_contact_state"] = "not_in_contact"
            ball["pb_allowed_region"] = "uphill_side_before_wall"
        elif frame <= REBOUND_FRAME:
            ball["pb_state"] = "contacting_transparent_wall_and_rebounding"
            ball["pb_contact_state"] = "blocked_by_transparent_wall"
            ball["pb_allowed_region"] = "uphill_side_touching_wall"
        else:
            ball["pb_state"] = "settled_in_front_of_transparent_wall"
            ball["pb_contact_state"] = "blocked_settled"
            ball["pb_allowed_region"] = "uphill_side_in_front_of_wall"

        wall["pb_state"] = "static_transparent_solid_barrier"
        wall["pb_contact_state"] = "blocks_ball_motion"

        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)

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
                "A small red ball rolls downhill along a wooden ramp. "
                "A transparent glass wall stands across the track. "
                "The wall is see-through but it is a real solid barrier. "
                "The ball should roll into the transparent wall, make visible contact with the glass face, "
                "bounce slightly, and remain in front of the wall. "
                "The ball must not pass through the transparent wall, must not teleport to the other side, "
                "and must preserve its identity, color, size, count, and continuous trajectory."
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
        wall=objs["wall"],
        ball=objs["ball"],
        ball_z=objs["ball_z"],
    )

    render_png(scene, INPUT_FRAME_1, INPUT_FRAME_PATH)
    render_png(scene, OPTIONAL_FRAME_2, OPTIONAL_FRAME_PATH)
    render_png(scene, OPTIONAL_CONTACT_FRAME_02B, OPTIONAL_CONTACT_FRAME_PATH)

    render_animation(scene)
    write_task_json()
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("Output:", OUT_DIR)
    print("Rule: transparent glass wall is visible but solid.")
    print("Rule: ball contacts the wall, rebounds slightly, and remains in front.")
    print("=" * 100)


if __name__ == "__main__":
    main()
