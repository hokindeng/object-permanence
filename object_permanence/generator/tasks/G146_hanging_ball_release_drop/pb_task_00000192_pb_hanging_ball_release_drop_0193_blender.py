# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector
import bmesh

CASE = json.loads(r"""{
  "item_id": "PB_HANGING_BALL_RELEASE_DROP_0193",
  "scene_kind": "hanging_ball_release_drop",
  "prompt": "A ball hangs at rest in the air on a thin string beneath an overhead beam, held by a small hook. The hook releases and the string goes slack, so the ball drops straight down to the floor, bounces once, and settles. Its horizontal position never changes and nothing remains suspended."
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


def ease_in_quad(t):
    t = clamp01(t)
    return t * t


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
        mat.use_screen_refraction = alpha < 1.0
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


def add_sphere(name, radius, location, material, color_name, role="target"):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object", "sphere", color_name, True, solid=True, pb_radius=radius)
    return obj


def add_cylinder(name, location, radius, depth, material=None, role="static_solid", color_name="gray", is_dynamic=False, solid=True, rotation=(0.0, 0.0, 0.0), vertices=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    if material is not None:
        obj.data.materials.append(material)
    tag(
        obj,
        name,
        role,
        "dynamic_object" if is_dynamic else ("static_solid" if solid else "non_solid_marker"),
        "cylinder",
        color_name,
        is_dynamic,
        solid=solid,
    )
    return obj


def _translation_matrix(v):
    from mathutils import Matrix
    return Matrix.Translation(v)


def _set_origin(obj, world_point):
    # Move an object's origin to a given world point without moving the mesh.
    delta = obj.location - world_point
    obj.data.transform(_translation_matrix(delta))
    obj.location = world_point.copy()


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


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor_warm", (0.82, 0.80, 0.75), roughness=0.82)
    MATS["gray"] = make_mat("mat_neutral_gray", (0.66, 0.66, 0.68), roughness=0.62)
    MATS["dark"] = make_mat("mat_dark_gray", (0.04, 0.04, 0.05), roughness=0.92)
    MATS["box"] = make_mat("mat_box_gray", (0.38, 0.39, 0.40), roughness=0.78)
    MATS["beam"] = make_mat("mat_beam_gray", (0.50, 0.51, 0.54), roughness=0.60)
    MATS["string"] = make_mat("mat_string_gray", (0.30, 0.30, 0.32), roughness=0.70)
    MATS["hook"] = make_mat("mat_hook", (0.20, 0.20, 0.22), roughness=0.45, metallic=0.6)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.38, 0.06), roughness=0.30)
    MATS["red"] = make_mat("mat_red", (0.85, 0.12, 0.10), roughness=0.32)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (9.8, 4.8, 0.10), MATS["floor"], role="ground", color_name="warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 2.42, 2.30), (10.0, 0.08, 5.00), MATS["backdrop"], role="background", color_name="off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.8, -4.4, 6.2))
    key = bpy.context.object
    key.name = "large_softbox_light"
    key.data.energy = 1050
    key.data.size = 6.0

    bpy.ops.object.light_add(type="POINT", location=(3.7, -2.8, 3.6))
    fill = bpy.context.object
    fill.name = "right_fill_light"
    fill.data.energy = 165

    return scene


def setup_camera(scene, location=(-0.65, -8.5, 1.75), target=(0.4, 0.0, 0.65), lens=31):
    bpy.ops.object.camera_add(location=location)
    camera = bpy.context.object
    camera.name = "camera_main"
    camera.data.lens = lens
    look_at(camera, target)
    camera.data.dof.use_dof = False
    scene.camera = camera


# ============================================================
# 0193 hanging ball release drop
#
# A BALL hangs at rest in the air beneath an overhead horizontal BEAM. The
# beam is carried by a vertical POST that stands on a base on the floor
# (post + beam + base = apparatus, gray). A thin vertical STRING drops from
# the beam and a small HOOK at its lower end holds the ball. The ball hangs
# still for the first ~30 frames; then the HOOK RELEASES and the STRING goes
# slack / retracts, removing the support, so the ball free-falls STRAIGHT
# DOWN (x, y held constant) to the floor, BOUNCING (restitution ~0.5) with
# decaying hops before it settles. Nothing is left suspended.
# ============================================================

def build_hanging_ball_release_drop_scene():
    scene = build_base_scene()
    # 3/4 front view framing the overhead beam, the hanging ball, and the whole
    # straight-down drop to the floor so the bounce stays in view.
    setup_camera(scene, location=(-4.6, -7.2, 3.15), target=(0.1, 0.0, 1.45), lens=33)

    FLOOR_Z = 0.0
    BALL_R = 0.26

    HANG_Z = 1.90                       # ball center while hanging at rest
    BEAM_Z = 3.05                       # beam centerline height
    BEAM_THICK = 0.16
    beam_bottom_z = BEAM_Z - BEAM_THICK / 2.0   # 2.97

    POST_X = -1.65                      # vertical post at the -x side
    BALL_X = 0.0                        # ball hangs at x = 0

    # ---- Vertical post (apparatus support) from floor up to the beam ----
    post_h = BEAM_Z + BEAM_THICK / 2.0 - FLOOR_Z
    add_cube(
        "hanger_post",
        (POST_X, 0.0, FLOOR_Z + post_h / 2.0),
        (0.22, 0.22, post_h),
        MATS["box"], role="hanger_post", color_name="gray",
    )
    # ---- Base plate under the post so the stand reads as free-standing ----
    add_cube(
        "post_base_support",
        (POST_X, 0.0, FLOOR_Z + 0.05),
        (0.90, 0.90, 0.10),
        MATS["box"], role="post_base_support", color_name="dark_gray",
    )

    # ---- Overhead horizontal beam from the post out over the ball ----
    beam_x_lo = POST_X
    beam_x_hi = BALL_X + 0.25
    beam_len = beam_x_hi - beam_x_lo
    beam_cx = 0.5 * (beam_x_lo + beam_x_hi)
    add_cube(
        "support_beam",
        (beam_cx, 0.0, BEAM_Z),
        (beam_len, 0.24, BEAM_THICK),
        MATS["beam"], role="support_beam", color_name="gray",
    )

    # ---- Thin vertical string from the beam bottom down to the ball top ----
    ball_top_z = HANG_Z + BALL_R                 # 2.16
    string_top_z = beam_bottom_z                 # 2.97
    string_len = string_top_z - ball_top_z       # 0.81
    string_cz = 0.5 * (string_top_z + ball_top_z)
    string = add_cylinder(
        "string_rod",
        (BALL_X, 0.0, string_cz),
        0.022, string_len,
        MATS["string"], role="string_rod", color_name="dark_gray",
    )
    # Origin at the TOP (beam side) so scaling z toward 0 makes the string
    # retract up into the beam at release (the support goes away cleanly).
    _set_origin(string, Vector((BALL_X, 0.0, string_top_z)))
    string["pb_is_string"] = True

    # ---- Small hook holding the ball at the lower end of the string ----
    hook = add_cylinder(
        "release_hook_support",
        (BALL_X, 0.0, ball_top_z + 0.03),
        0.05, 0.10,
        MATS["hook"], role="release_hook_support", color_name="dark_metal",
        rotation=(math.radians(90.0), 0.0, 0.0),
    )
    hook["pb_is_hook"] = True

    # ---- Ball: the TARGET. Hangs at rest, role has NO apparatus keyword. ----
    ball = add_sphere(
        "hanging_ball",
        BALL_R,
        (BALL_X, 0.0, HANG_Z),
        MATS["orange"],
        "orange",
        role="hanging_ball",
    )
    ball["pb_expected_behavior"] = "hook_releases_then_ball_free_falls_and_bounces_to_floor"

    return {
        "scene": scene,
        "kind": "hanging_ball_release_drop",
        "ball": ball,
        "string": string,
        "hook": hook,
        "floor_z": FLOOR_Z,
        "ball_r": BALL_R,
        "ball_x": BALL_X,
        "hang_z": HANG_Z,
        "string_top_z": string_top_z,
    }


def _sim_vertical_bounce(elapsed, z0, vz0, floor_z, g=0.011, rest=0.5):
    """Deterministic per-frame integration of a straight-down bouncing drop.
    Returns z after `elapsed` frames from release. Bounces off floor_z with the
    given restitution; hops decay until the ball settles."""
    z, vz = float(z0), float(vz0)
    n = int(round(elapsed))
    for _ in range(n):
        vz -= g
        z += vz
        if z <= floor_z:
            z = floor_z
            if vz < 0.0:
                vz = -vz * rest
            if abs(vz) < 0.6 * g:       # hops too small to see -> settle
                vz = 0.0
    return z


def animate_hanging_ball_release_drop(objs, frame):
    ball = objs["ball"]
    string = objs["string"]
    hook = objs["hook"]
    floor_z = objs["floor_z"]
    ball_r = objs["ball_r"]
    ball_x = objs["ball_x"]
    hang_z = objs["hang_z"]

    # ---- Timeline ----
    # 1..30   : ball hangs at rest on the string+hook (support present).
    # 30      : hook RELEASES; string retracts (scale z -> 0) over 30..38.
    # 30..    : ball free-falls straight down under gravity, BOUNCING off the
    #           floor (restitution 0.5) with decaying hops, settling by ~110.
    release_frame = 30
    retract_end = 38
    GRAVITY = 0.011
    REST = 0.5

    floor_rest_z = floor_z + ball_r

    # ---- String retract (support removal visual) ----
    if frame <= release_frame:
        s_scale = 1.0
    elif frame >= retract_end:
        s_scale = 0.0
    else:
        s_scale = 1.0 - smooth01((frame - release_frame) / float(retract_end - release_frame))
    string.scale = (1.0, 1.0, max(s_scale, 1e-4))
    string.keyframe_insert(data_path="scale", frame=frame)
    string["pb_state"] = "taut" if frame <= release_frame else "slack_retracting"

    # ---- Hook: stays with the string top after release (rides up as it opens) ----
    if frame <= release_frame:
        hook.location = (ball_x, 0.0, (hang_z + ball_r) + 0.03)
        hook["pb_state"] = "holding_ball"
    else:
        hook_open = smooth01(clamp01((frame - release_frame) / float(retract_end - release_frame)))
        hook.location = (ball_x, 0.0, (hang_z + ball_r) + 0.03 + hook_open * 0.55)
        hook["pb_state"] = "released_open"
    hook.keyframe_insert(data_path="location", frame=frame)

    # ---- Ball ----
    if frame <= release_frame:
        bz = hang_z
        state = "hanging_at_rest"
        spin = 0.0
    else:
        elapsed = frame - release_frame
        bz = _sim_vertical_bounce(elapsed, hang_z, 0.0, floor_rest_z, g=GRAVITY, rest=REST)
        if bz <= floor_rest_z + 1e-4:
            state = "settled_on_floor"
        else:
            state = "free_falling_with_bounce"
        spin = -0.03 * elapsed

    ball.location = (ball_x, 0.0, bz)      # x, y held CONSTANT -> straight-down drop
    ball.rotation_euler = (0.0, spin, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball["pb_state"] = state
    ball["pb_never_suspended"] = True


# ============================================================
# Build / animate dispatch
# ============================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "hanging_ball_release_drop":
        return build_hanging_ball_release_drop_scene()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "hanging_ball_release_drop":
            animate_hanging_ball_release_drop(objs, frame)
        else:
            raise RuntimeError("Unknown kind: " + str(kind))

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
    objs = build_scene_by_kind()
    scene = objs["scene"]
    animate_scene(objs)

    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, 60, OPTIONAL_FRAME_PATH)
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
