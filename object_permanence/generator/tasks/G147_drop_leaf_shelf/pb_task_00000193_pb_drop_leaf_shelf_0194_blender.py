# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_DROP_LEAF_SHELF_0194",
  "scene_kind": "drop_leaf_shelf",
  "prompt": "A ball rests on a shelf hinged at the back wall, held out horizontally like a drop-leaf table. The shelf swings down about its wall hinge, removing the support; the ball slides off the front edge and falls to the floor, bouncing before it settles. Nothing remains suspended."
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
    MATS["wall"] = make_mat("mat_wall_gray", (0.50, 0.51, 0.54), roughness=0.72)
    MATS["hinge"] = make_mat("mat_hinge", (0.20, 0.20, 0.22), roughness=0.45, metallic=0.6)
    MATS["red"] = make_mat("mat_red", (0.85, 0.12, 0.10), roughness=0.32)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (9.8, 4.8, 0.10), MATS["floor"], role="ground", color_name="warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 2.42, 1.90), (10.0, 0.08, 4.20), MATS["backdrop"], role="background", color_name="off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.8, -4.4, 6.0))
    key = bpy.context.object
    key.name = "large_softbox_light"
    key.data.energy = 1000
    key.data.size = 6.0

    bpy.ops.object.light_add(type="POINT", location=(3.7, -2.8, 3.4))
    fill = bpy.context.object
    fill.name = "right_fill_light"
    fill.data.energy = 155

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
# 0194 drop-leaf shelf
#
# A shelf (apparatus) is hinged at the BACK WALL like a drop-leaf table,
# held out horizontally with a ball resting on it. The shelf swings DOWN
# ~90 degrees about its wall hinge (rotation about the x axis at the wall),
# removing the support. The ball slides off the front edge and free-falls
# to the floor, BOUNCING (restitution ~0.5) before it settles.
# ============================================================

def build_drop_leaf_shelf_scene():
    scene = build_base_scene()
    # 3/4 view: the back wall is at +y; the shelf leaf reaches FORWARD toward -y
    # (toward the camera) and swings straight down. Camera offset in -x and -y so
    # the horizontal hold, the downward swing, the slide off the front edge, and the
    # bouncing fall are all clearly visible with no clipping.
    setup_camera(scene, location=(-3.9, -7.4, 2.75), target=(0.0, -0.25, 0.75), lens=36)

    FLOOR_Z = 0.0

    # ---- Back wall the shelf hinges from (apparatus) ----
    WALL_Y = 0.70          # y of the wall face the leaf hinges at
    WALL_THICK = 0.22
    WALL_W = 2.6
    WALL_H = 3.0
    add_cube(
        "back_wall_support",
        (0.0, WALL_Y + WALL_THICK / 2.0, FLOOR_Z + WALL_H / 2.0),
        (WALL_W, WALL_THICK, WALL_H),
        MATS["wall"],
        role="back_wall_support",
        color_name="gray",
        solid=True,
    )

    # ---- Shelf leaf: hinged at the wall face, reaching forward (-y), held level ----
    SHELF_W = 1.40         # x extent
    SHELF_LEN_Y = 1.50     # length of the leaf (forward reach along -y)
    SHELF_THICK = 0.16
    SHELF_Z = FLOOR_Z + 1.75          # centerline height while level (> LEN_Y so the
    #                                    hanging leaf clears the floor)
    HINGE_Y = WALL_Y                   # hinge axis (along x) at the wall face
    SHELF_TOP_LOCAL_Z = SHELF_THICK / 2.0

    # Build the leaf centered between the hinge (y=HINGE_Y) and its free front edge
    # (y=HINGE_Y - SHELF_LEN_Y). Its geometric center y:
    shelf_center_y = HINGE_Y - SHELF_LEN_Y / 2.0
    shelf = add_cube(
        "drop_leaf_shelf_panel",
        (0.0, shelf_center_y, SHELF_Z),
        (SHELF_W, SHELF_LEN_Y, SHELF_THICK),
        MATS["slab"],
        role="drop_leaf_shelf_panel",
        color_name="gray",
        solid=True,
    )
    shelf["pb_is_drop_leaf"] = True
    # Move origin to the hinge point (wall face, at shelf centerline height) so a
    # rotation about x swings the leaf down about the wall.
    _set_origin(shelf, Vector((0.0, HINGE_Y, SHELF_Z)))

    # ---- Hinge bar along the wall (apparatus depth cue) ----
    hinge_bar = add_cube(
        "shelf_hinge_bar",
        (0.0, HINGE_Y, SHELF_Z),
        (SHELF_W * 1.02, 0.08, 0.08),
        MATS["hinge"],
        role="shelf_hinge_bar",
        color_name="dark_metal",
        solid=True,
    )
    hinge_bar["pb_is_hinge"] = True

    # ---- Ball on the shelf, a bit forward of the hinge (vivid target) ----
    BALL_R = 0.30
    ball_y0 = HINGE_Y - 0.55           # rests partway out along the leaf
    ball_z0 = SHELF_Z + SHELF_TOP_LOCAL_Z + BALL_R
    ball = add_sphere(
        "falling_ball",
        BALL_R,
        (0.0, ball_y0, ball_z0),
        MATS["red"],
        "red",
        role="falling_ball",
    )
    ball["pb_rests_on_shelf_leaf"] = True

    return {
        "scene": scene,
        "kind": "drop_leaf_shelf",
        "shelf": shelf,
        "ball": ball,
        "floor_z": FLOOR_Z,
        "shelf_thick": SHELF_THICK,
        "shelf_z": SHELF_Z,
        "shelf_len_y": SHELF_LEN_Y,
        "hinge_y": HINGE_Y,
        "shelf_top_local_z": SHELF_TOP_LOCAL_Z,
        "ball_r": BALL_R,
        "ball_y0": ball_y0,
    }


def _sim_projectile(elapsed, h0, z0, vh0, vz0, floor_z, g=0.011, rest=0.5, mu=0.10):
    """Deterministic per-frame integration of a bouncing projectile in a vertical
    plane. `h` is the horizontal coordinate (here y). Returns (h, z) after `elapsed`
    frames from launch."""
    h, z, vh, vz = float(h0), float(z0), float(vh0), float(vz0)
    n = int(round(elapsed))
    for _ in range(n):
        vz -= g
        z += vz
        h += vh
        if z <= floor_z:
            z = floor_z
            if vz < 0.0:
                vz = -vz * rest
                vh *= (1.0 - mu)
            if abs(vz) < 0.5 * g:
                vz = 0.0
        if z <= floor_z + 1e-6 and abs(vz) < 1e-6:
            vh *= 0.82
            if abs(vh) < 0.002:
                vh = 0.0
    return h, z


def animate_drop_leaf_shelf(objs, frame):
    shelf = objs["shelf"]
    ball = objs["ball"]
    floor_z = objs["floor_z"]
    shelf_z = objs["shelf_z"]
    shelf_len_y = objs["shelf_len_y"]
    hinge_y = objs["hinge_y"]
    shelf_top_local_z = objs["shelf_top_local_z"]
    ball_r = objs["ball_r"]
    ball_y0 = objs["ball_y0"]

    # Timeline:
    #   1-20   : hold. Shelf level, ball resting.
    #   20-60  : shelf swings DOWN ~90 deg about the wall hinge (ease-in). The ball
    #            rides then slides forward toward the free front edge.
    #   ~52    : the ball reaches the front edge, slides off, and free-falls to the
    #            floor, BOUNCING (0.5), settling by ~105.
    swing_start = 20
    swing_end = 60
    max_angle = math.radians(90.0)

    if frame <= swing_start:
        ang = 0.0
        ang_t = 0.0
    elif frame <= swing_end:
        ang_t = ease_in_quad((frame - swing_start) / float(swing_end - swing_start))
        ang = ang_t * max_angle
    else:
        ang_t = 1.0
        ang = max_angle

    # Rotate about +x: a forward (-y) point's z goes negative -> the free edge swings
    # down. Origin is at the wall hinge.
    shelf.rotation_euler = (ang, 0.0, 0.0)
    shelf.keyframe_insert(data_path="rotation_euler", frame=frame)
    shelf["pb_state"] = "level" if frame <= swing_start else ("swinging_down" if frame < swing_end else "hanging_down")

    # Surface point (top face) at distance s forward of the hinge along the leaf.
    # Local (relative to hinge): (0, -s, +shelf_top_local_z). Rotate about x by ang:
    #   y' = -s*cos(ang) - top*sin(ang)
    #   z' = -s*sin(ang) + top*cos(ang)
    # normal (local +z) rotated: (0, -sin(ang), cos(ang)).
    def surface_point_and_normal(s, ang):
        c = math.cos(ang)
        sn = math.sin(ang)
        y_w = hinge_y + (-s * c - shelf_top_local_z * sn)
        z_w = shelf_z + (-s * sn + shelf_top_local_z * c)
        ny = -sn
        nz = c
        return y_w, z_w, ny, nz

    # Ball distance from hinge along the leaf. s0 from rest y; grows toward the free
    # front edge as the leaf tilts.
    s0 = hinge_y - ball_y0
    s_edge = shelf_len_y - ball_r * 0.6

    roll_launch_t = ease_in_quad(clamp01((ang_t - 0.06) / 0.55)) if swing_end > swing_start else 0.0
    s_ball = lerp(s0, s_edge, roll_launch_t)
    on_shelf = roll_launch_t < 0.999

    if on_shelf:
        cy, cz, ny, nz = surface_point_and_normal(s_ball, ang)
        ball_y = cy + ny * ball_r
        ball_z = cz + nz * ball_r
        ball["pb_state"] = "resting_on_shelf" if frame <= swing_start else "sliding_down_shelf"
        objs["_ball_launch"] = {"frame": frame, "y": ball_y, "z": ball_z}
    else:
        launch = objs.get("_ball_launch")
        if launch is None:
            cy, cz, ny, nz = surface_point_and_normal(s_edge, ang)
            launch = {"frame": frame, "y": cy + ny * ball_r, "z": cz + nz * ball_r}
            objs["_ball_launch"] = launch
        floor_rest_z = floor_z + ball_r
        elapsed = frame - launch["frame"]
        # Slides off the front edge with a little forward (-y) and downward velocity.
        ball_y, ball_z = _sim_projectile(
            elapsed, launch["y"], launch["z"], vh0=-0.03, vz0=-0.02,
            floor_z=floor_rest_z, g=0.011, rest=0.5, mu=0.14,
        )
        if ball_z <= floor_rest_z + 0.01:
            ball["pb_state"] = "settling_on_floor"
        else:
            ball["pb_state"] = "free_falling_with_bounce"

    ball.location = (0.0, ball_y, ball_z)
    # Rolling spin about +x as it moves in -y.
    roll_angle = (s_ball - s0) / max(ball_r, 1e-6)
    if not on_shelf:
        roll_angle += 0.05 * max(0, frame - objs.get("_ball_launch", {}).get("frame", frame))
    ball.rotation_euler = (roll_angle, 0.0, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball["pb_never_suspended"] = True


# ============================================================
# Build / animate dispatch
# ============================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "drop_leaf_shelf":
        return build_drop_leaf_shelf_scene()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "drop_leaf_shelf":
            animate_drop_leaf_shelf(objs, frame)
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
