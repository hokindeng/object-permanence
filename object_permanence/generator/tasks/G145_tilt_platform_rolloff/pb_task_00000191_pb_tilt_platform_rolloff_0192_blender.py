# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_TILT_PLATFORM_ROLLOFF_0192",
  "scene_kind": "tilt_platform_rolloff",
  "prompt": "A ball rests on a flat platform held level on a pivot. The platform tilts down on one side; the ball rolls to the low edge, rolls off, and falls to the floor, bouncing before it settles. Nothing remains suspended."
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
    MATS["slab"] = make_mat("mat_slab_gray", (0.58, 0.60, 0.64), roughness=0.58)
    MATS["pivot"] = make_mat("mat_pivot_gray", (0.34, 0.35, 0.38), roughness=0.60)
    MATS["box"] = make_mat("mat_box_gray", (0.38, 0.39, 0.40), roughness=0.78)
    MATS["red"] = make_mat("mat_red", (0.85, 0.12, 0.10), roughness=0.32)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (9.8, 4.8, 0.10), MATS["floor"], role="ground", color_name="warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 2.42, 1.60), (10.0, 0.08, 3.20), MATS["backdrop"], role="background", color_name="off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.8, -4.4, 5.5))
    key = bpy.context.object
    key.name = "large_softbox_light"
    key.data.energy = 950
    key.data.size = 6.0

    bpy.ops.object.light_add(type="POINT", location=(3.7, -2.8, 3.2))
    fill = bpy.context.object
    fill.name = "right_fill_light"
    fill.data.energy = 145

    return scene


def setup_camera(scene, location=(-0.65, -8.5, 1.75), target=(0.4, 0.0, 0.65), lens=31):
    bpy.ops.object.camera_add(location=location)
    camera = bpy.context.object
    camera.name = "camera_main"
    camera.data.lens = lens
    look_at(camera, target)
    camera.data.dof.use_dof = False
    scene.camera = camera


def _translation_matrix(v):
    from mathutils import Matrix
    return Matrix.Translation(v)


def _set_origin(obj, world_point):
    # Move an object's origin to a given world point without moving the mesh.
    delta = obj.location - world_point
    obj.data.transform(_translation_matrix(delta))
    obj.location = world_point.copy()


# ============================================================
# 0192 tilt platform rolloff
#
# A ball rests on a flat PLATFORM (apparatus) that is level on a pivot at
# its -x edge. The platform TILTS down on the +x side about that pivot edge.
# The ball rolls down the incline to the low (+x) edge, rolls OFF, and then
# free-falls to the floor, BOUNCING (restitution ~0.5) before it settles.
# ============================================================

def build_tilt_platform_rolloff_scene():
    scene = build_base_scene()
    # Side/front view: the platform spans along x, pivot at the LEFT (-x) edge on a
    # short pivot post; the +x side tilts down. Camera low and to -y front so the
    # level hold, the tilt, the roll to the low edge, the roll-off, and the bouncing
    # fall are all clearly visible with no clipping.
    setup_camera(scene, location=(0.4, -8.8, 2.05), target=(0.6, 0.0, 1.05), lens=34)

    FLOOR_TOP_Z = 0.0

    # ---- Platform geometry (a flat slab that pivots about its -x edge) ----
    PLAT_LEN_X = 3.00       # length along x
    PLAT_LEN_Y = 1.30       # depth along y
    PLAT_THICK = 0.18       # thickness in z
    PLAT_LEVEL_Z = FLOOR_TOP_Z + 1.55   # z of the platform centerline while level

    PIVOT_X = -PLAT_LEN_X / 2.0
    # Use the platform's lower-left corner as the hinge. This keeps the entire
    # rotating slab on the +X/+Z side of the support instead of sweeping through it.
    PIVOT_Z = PLAT_LEVEL_Z - PLAT_THICK / 2.0
    HALF_LEN = PLAT_LEN_X / 2.0

    platform = add_cube(
        "tilting_platform",
        (0.0, 0.0, PLAT_LEVEL_Z),
        (PLAT_LEN_X, PLAT_LEN_Y, PLAT_THICK),
        MATS["slab"],
        role="tilting_platform",
        color_name="gray",
        solid=True,
    )
    platform["pb_pivots_about_left_edge"] = True
    # Move the object origin to the lower-left hinge corner.
    _set_origin(platform, Vector((PIVOT_X, 0.0, PIVOT_Z)))

    # ---- Pivot post/fulcrum under the -x edge (apparatus support) ----
    POST_W = 0.46
    POST_H = PIVOT_Z - FLOOR_TOP_Z
    if POST_H < 0.1:
        POST_H = 0.1
    post_center_z = FLOOR_TOP_Z + POST_H / 2.0
    pivot_post = add_cube(
        "pivot_support_post",
        (PIVOT_X - POST_W / 2.0, 0.0, post_center_z),
        (POST_W, POST_W, POST_H),
        MATS["pivot"],
        role="pivot_support_post",
        color_name="gray",
        solid=True,
    )
    pivot_post["pb_is_support"] = True

    # ---- Ball resting on the platform, a bit toward the +x side so it has room to
    #      roll down to the low edge. Role has NO apparatus keyword -> vivid target. ----
    BALL_R = 0.32
    BALL_S0 = 0.20 * HALF_LEN   # signed distance from the platform CENTER (+x side)
    PLAT_TOP_LOCAL_Z = PLAT_THICK
    ball_x0 = BALL_S0
    ball_z0 = PIVOT_Z + PLAT_TOP_LOCAL_Z + BALL_R
    ball = add_sphere(
        "rolling_ball",
        BALL_R,
        (ball_x0, 0.0, ball_z0),
        MATS["red"],
        "red",
        role="rolling_ball",
    )
    ball["pb_rests_on_platform"] = True

    return {
        "scene": scene,
        "kind": "tilt_platform_rolloff",
        "platform": platform,
        "pivot_post": pivot_post,
        "ball": ball,
        "floor_top_z": FLOOR_TOP_Z,
        "plat_thick": PLAT_THICK,
        "plat_level_z": PLAT_LEVEL_Z,
        "pivot_x": PIVOT_X,
        "pivot_z": PIVOT_Z,
        "half_len": HALF_LEN,
        "ball_r": BALL_R,
        "ball_s0": BALL_S0,
        "plat_top_local_z": PLAT_TOP_LOCAL_Z,
    }


def _sim_projectile(elapsed, x0, z0, vx0, vz0, floor_z, g=0.011, rest=0.5, mu=0.12):
    """Deterministic per-frame integration of a bouncing projectile.
    Returns (x, z) after `elapsed` frames from launch. Bounces off floor_z with the
    given restitution; horizontal speed decays a little on each bounce and rolls to a
    stop once the vertical hops die out."""
    x, z, vx, vz = float(x0), float(z0), float(vx0), float(vz0)
    n = int(round(elapsed))
    for _ in range(n):
        vz -= g
        z += vz
        x += vx
        if z <= floor_z:
            z = floor_z
            if vz < 0.0:
                vz = -vz * rest
                vx *= (1.0 - mu)
            if abs(vz) < 0.5 * g:      # hops too small to see -> settle vertically
                vz = 0.0
        if z <= floor_z + 1e-6 and abs(vz) < 1e-6:
            vx *= 0.82                 # rolling friction to a stop on the floor
            if abs(vx) < 0.002:
                vx = 0.0
    return x, z


def animate_tilt_platform_rolloff(objs, frame):
    platform = objs["platform"]
    pivot_post = objs["pivot_post"]
    ball = objs["ball"]
    floor_top_z = objs["floor_top_z"]
    plat_thick = objs["plat_thick"]
    pivot_x = objs["pivot_x"]
    pivot_z = objs["pivot_z"]
    half_len = objs["half_len"]
    ball_r = objs["ball_r"]
    ball_s0 = objs["ball_s0"]
    plat_top_local_z = objs["plat_top_local_z"]

    # Timeline:
    #   1-20   : hold. Platform level on the pivot, ball resting.
    #   20-64  : platform tilts DOWN on +x about the -x pivot edge (ease-in). The
    #            ball rides then rolls toward the low (+x) edge.
    #   ~52    : the ball reaches the low edge, rolls OFF, and free-falls with a
    #            BOUNCE (restitution 0.5) to the floor, settling by ~110.
    tip_start = 20
    tip_end = 64

    # Final tilt angle: enough for a clear incline / roll-off; the +x end does NOT
    # reach the floor (ball leaves before that), so pick a fixed moderate angle. The
    # ball leaves the edge while the tilt is still moderate (see roll mapping) so it
    # launches from a good height and gets a clearly visible bounce.
    max_tilt = math.radians(30.0)

    if frame <= tip_start:
        tilt = 0.0
        tip_t = 0.0
    elif frame <= tip_end:
        tip_t = ease_in_quad((frame - tip_start) / float(tip_end - tip_start))
        tilt = tip_t * max_tilt
    else:
        tip_t = 1.0
        tilt = max_tilt

    # Rotating about +y by a POSITIVE angle drops the +x end. Origin is at the pivot.
    platform.rotation_euler = (0.0, tilt, 0.0)
    platform.keyframe_insert(data_path="rotation_euler", frame=frame)
    platform["pb_state"] = "level" if frame <= tip_start else ("tilting" if frame < tip_end else "tilted_down")

    # Pivot post stays fixed.
    pivot_post.keyframe_insert(data_path="location", frame=frame)
    pivot_post["pb_state"] = "static_support"

    def surface_point_and_normal(s, tilt):
        c = math.cos(tilt)
        sn = math.sin(tilt)
        x_w = pivot_x + (s * c + plat_top_local_z * sn)
        z_w = pivot_z + (-s * sn + plat_top_local_z * c)
        nx = sn
        nz = c
        return x_w, z_w, nx, nz

    # Ball's signed distance from pivot along the platform top. s0 = ball_s0 + half_len
    # (ball_s0 was from platform CENTER; pivot is half_len to the -x).
    s0 = ball_s0 + half_len
    s_edge = (2.0 * half_len) - ball_r * 0.6

    # Roll fraction: begins shortly after tilt starts, accelerates with tilt. It
    # reaches the edge while the tilt is still ~15 deg (edge still fairly high) so the
    # ensuing free-fall is tall enough for a clearly visible bounce.
    roll_launch_t = ease_in_quad(clamp01((tip_t - 0.05) / 0.45)) if tip_end > tip_start else 0.0
    s_ball = lerp(s0, s_edge, roll_launch_t)
    on_shelf = roll_launch_t < 0.999

    if on_shelf:
        cx, cz, nx, nz = surface_point_and_normal(s_ball, tilt)
        ball_x = cx + nx * ball_r
        ball_z = cz + nz * ball_r
        ball["pb_state"] = "resting_on_platform" if frame <= tip_start else "rolling_down_platform"
        objs["_ball_launch"] = {"frame": frame, "x": ball_x, "z": ball_z}
    else:
        launch = objs.get("_ball_launch")
        if launch is None:
            cx, cz, nx, nz = surface_point_and_normal(s_edge, tilt)
            launch = {"frame": frame, "x": cx + nx * ball_r, "z": cz + nz * ball_r}
            objs["_ball_launch"] = launch
        floor_rest_z = floor_top_z + ball_r
        elapsed = frame - launch["frame"]
        # Launch with a little forward+down velocity (it rolled off the low edge).
        ball_x, ball_z = _sim_projectile(
            elapsed, launch["x"], launch["z"], vx0=0.025, vz0=-0.02,
            floor_z=floor_rest_z, g=0.011, rest=0.5, mu=0.16,
        )
        if ball_z <= floor_rest_z + 0.01:
            ball["pb_state"] = "settling_on_floor"
        else:
            ball["pb_state"] = "free_falling_with_bounce"

    ball.location = (ball_x, 0.0, ball_z)
    roll_angle = -(s_ball - s0) / max(ball_r, 1e-6)
    if not on_shelf:
        roll_angle -= 0.05 * max(0, frame - objs.get("_ball_launch", {}).get("frame", frame))
    ball.rotation_euler = (0.0, roll_angle, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball["pb_never_suspended"] = True


# ============================================================
# Build / animate dispatch
# ============================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "tilt_platform_rolloff":
        return build_tilt_platform_rolloff_scene()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "tilt_platform_rolloff":
            animate_tilt_platform_rolloff(objs, frame)
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
    render_png(scene, 72, OPTIONAL_FRAME_PATH)
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
