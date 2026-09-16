# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector
import bmesh

CASE = json.loads(r"""{
  "item_id": "PB_BOMB_BAY_DOORS_DROP_0177",
  "scene_kind": "bomb_bay_doors_drop",
  "prompt": "A ball rests centered on two small doors that meet in the middle, set flush into a raised platform with a hole beneath. The two doors swing downward and apart on their outer hinges (like bomb-bay doors), opening a gap; the ball loses its support and free-falls straight down through the gap to the floor below, where it bounces a few decaying times before coming to rest, with nothing left suspended."
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
    MATS["dark"] = make_mat("mat_dark_gray", (0.04, 0.04, 0.05), roughness=0.92)
    MATS["box"] = make_mat("mat_box_gray", (0.38, 0.39, 0.40), roughness=0.78)
    MATS["edge"] = make_mat("mat_light_edge", (0.62, 0.63, 0.64), roughness=0.68)
    MATS["panel"] = make_mat("mat_panel_gray", (0.44, 0.45, 0.47), roughness=0.70)
    MATS["hinge"] = make_mat("mat_hinge", (0.20, 0.20, 0.22), roughness=0.45, metallic=0.6)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.38, 0.06), roughness=0.30)
    MATS["red"] = make_mat("mat_red", (0.85, 0.12, 0.10), roughness=0.32)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (9.8, 4.8, 0.10), MATS["floor"], role="ground", color_name="warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 2.42, 1.90), (10.0, 0.08, 4.20), MATS["backdrop"], role="background", color_name="off_white")

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
# 0177 bomb bay doors drop
#
# A raised solid PLATFORM at table height is a square FRAME of four border
# slabs surrounding a genuine square HOLE. TWO small DOORS meet along the
# centre line and together fill the hole flush with the platform top. Each
# door is parented to a hinge EMPTY on its OUTER edge (at x = +/- HOLE_HALF).
# The two doors swing DOWNWARD and APART about their outer hinges (bomb-bay
# style), removing the support from a ball resting centred where they meet.
# The ball then free-falls straight down through the opened hole to the floor
# and BOUNCES a few decaying times before settling.
# ============================================================

def _simulate_bounce(z0, floor_z, g, restitution, n_steps):
    """Semi-implicit Euler free-fall with bouncing on the floor.

    Returns a list of n_steps z positions. Index 0 == z0 (the release height);
    each subsequent step integrates gravity and reflects velocity with the
    given restitution when the floor is contacted.
    """
    zs = [z0]
    z = z0
    v = 0.0
    for _ in range(1, n_steps):
        v -= g
        z += v
        if z <= floor_z:
            z = floor_z
            v = -v * restitution
            # Settle once the rebound speed is tiny.
            if abs(v) < 0.010:
                v = 0.0
                z = floor_z
        zs.append(z)
    return zs


def build_bomb_bay_doors_drop_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(-4.2, -6.8, 3.05), target=(0.0, 0.0, 0.72), lens=34)

    FLOOR_Z = 0.0
    PLATFORM_TOP_Z = 1.10
    PLATFORM_THICK = 0.16
    platform_center_z = PLATFORM_TOP_Z - PLATFORM_THICK / 2.0
    platform_bottom_z = platform_center_z - PLATFORM_THICK / 2.0

    BALL_R = 0.26

    # Square HOLE, comfortably wider than 2.4 * ball radius (0.624).
    HOLE = 1.00
    HOLE_HALF = HOLE / 2.0            # 0.50 -> gap when open = 1.00 >= 0.624
    BORDER = 0.80
    OUTER_HALF = HOLE_HALF + BORDER   # 1.30
    depth = 2.0 * OUTER_HALF          # 2.60

    # --- Platform frame: four border slabs forming the square opening --------
    add_cube("platform_frame_px", (HOLE_HALF + BORDER / 2.0, 0.0, platform_center_z),
             (BORDER, depth, PLATFORM_THICK), MATS["gray"], role="platform_frame", color_name="gray")
    add_cube("platform_frame_nx", (-(HOLE_HALF + BORDER / 2.0), 0.0, platform_center_z),
             (BORDER, depth, PLATFORM_THICK), MATS["gray"], role="platform_frame", color_name="gray")
    add_cube("platform_frame_py", (0.0, HOLE_HALF + BORDER / 2.0, platform_center_z),
             (HOLE, BORDER, PLATFORM_THICK), MATS["gray"], role="platform_frame", color_name="gray")
    add_cube("platform_frame_ny", (0.0, -(HOLE_HALF + BORDER / 2.0), platform_center_z),
             (HOLE, BORDER, PLATFORM_THICK), MATS["gray"], role="platform_frame", color_name="gray")

    # --- Four legs so the platform reads as a raised table (apparatus) -------
    leg_h = platform_bottom_z - FLOOR_Z
    leg_inset = OUTER_HALF - 0.16
    for sx in (-1, 1):
        for sy in (-1, 1):
            add_cube(
                f"platform_leg_{'p' if sx > 0 else 'n'}x_{'p' if sy > 0 else 'n'}y",
                (sx * leg_inset, sy * leg_inset, FLOOR_Z + leg_h / 2.0),
                (0.16, 0.16, leg_h),
                MATS["box"], role="platform_leg", color_name="dark_gray",
            )

    # --- Two bomb-bay DOORS, each hinged on its OUTER edge -------------------
    DOOR_THICK = 0.06
    door_center_z = PLATFORM_TOP_Z - DOOR_THICK / 2.0   # top flush with platform top
    DOOR_W = HOLE_HALF - 0.01           # x extent of each leaf (0.49)
    DOOR_L = HOLE - 0.02                # y extent (depth) of the leaves (0.98)

    doors = []
    # Right door: hinge at x = +HOLE_HALF, leaf centre at +HOLE_HALF - DOOR_W/2
    # (offset toward -x from the hinge). A NEGATIVE Y-rotation swings it DOWN
    # and outward toward +x.
    # Left door: hinge at x = -HOLE_HALF, leaf centre offset toward +x from the
    # hinge; a POSITIVE Y-rotation swings it DOWN and outward toward -x.
    for side, sgn in (("right", 1), ("left", -1)):
        hinge_x = sgn * HOLE_HALF
        bpy.ops.object.empty_add(type="PLAIN_AXES", location=(hinge_x, 0.0, door_center_z))
        hinge = bpy.context.object
        hinge.name = f"bay_door_hinge_{side}"
        tag(hinge, f"bay_door_hinge_{side}", "bay_door_hinge", "static_solid", "empty", "dark_metal", False, solid=True)

        leaf_center_x = sgn * (HOLE_HALF - DOOR_W / 2.0)
        door = add_cube(
            f"bay_door_{side}",
            (leaf_center_x, 0.0, door_center_z),
            (DOOR_W, DOOR_L, DOOR_THICK),
            MATS["panel"], role=f"bay_door_{side}", color_name="gray",
        )
        door.parent = hinge
        door.matrix_parent_inverse = hinge.matrix_world.inverted()
        door["pb_is_bay_door"] = True

        # Dark hinge bar along the outer edge (depth cue, apparatus).
        add_cube(
            f"bay_door_hinge_bar_{side}",
            (hinge_x, 0.0, PLATFORM_TOP_Z - 0.01),
            (0.06, DOOR_L * 1.02, 0.05),
            MATS["hinge"], role="bay_door_hinge_bar", color_name="dark_metal",
        )
        doors.append({"side": side, "sgn": sgn, "hinge": hinge})

    # --- Ball: the TARGET. Rests centred where the two doors meet. -----------
    ball = add_sphere(
        "dropping_ball",
        BALL_R,
        (0.0, 0.0, PLATFORM_TOP_Z + BALL_R),
        MATS["orange"],
        "orange",
        role="dropping_ball",
    )
    ball["pb_expected_behavior"] = "bay_doors_open_then_ball_free_falls_and_bounces_to_rest"

    # --- Precompute the bouncing free-fall trajectory ------------------------
    open_start = 26
    GRAVITY = 0.022   # ~10 frames from the platform down to the floor -- near-real free-fall -- while still landing after the doors are open.
    RESTITUTION = 0.5
    rest_z = PLATFORM_TOP_Z + BALL_R      # 1.36
    floor_rest_z = FLOOR_Z + BALL_R       # 0.26
    n_fall = FRAME_END - open_start + 1
    bounce_zs = _simulate_bounce(rest_z, floor_rest_z, GRAVITY, RESTITUTION, n_fall)

    return {
        "scene": scene,
        "kind": "bomb_bay_doors_drop",
        "ball": ball,
        "doors": doors,
        "platform_top_z": PLATFORM_TOP_Z,
        "floor_z": FLOOR_Z,
        "ball_r": BALL_R,
        "hole_half": HOLE_HALF,
        "open_start": open_start,
        "open_end": 31,  # doors open in ~5 frames (fully open by frame 31), staying ahead of the falling ball (its centre reaches the door plane ~frame 31), so no clipping.
        "max_angle": math.radians(76.0),  # Short of vertical, so the leaves keep sloping into the hole (free edge inside x=+/-0.4, ball still clears) instead of tucking under the platform frame out of the camera's view.
        "rest_z": rest_z,
        "floor_rest_z": floor_rest_z,
        "bounce_zs": bounce_zs,
    }


def animate_bomb_bay_doors_drop(objs, frame):
    ball = objs["ball"]
    doors = objs["doors"]
    open_start = objs["open_start"]
    open_end = objs["open_end"]
    max_angle = objs["max_angle"]
    rest_z = objs["rest_z"]
    floor_rest_z = objs["floor_rest_z"]
    bounce_zs = objs["bounce_zs"]

    # ---- Timeline ----
    # 1..26   : at rest, ball supported on the two closed doors.
    # 26..31  : doors swing DOWN and APART (ease-in) about their outer hinges.
    # 26..    : support removed as the leaves tilt away; the ball begins a real
    #           bouncing free-fall at 26. The doors swing down faster than the
    #           ball falls, so the leaves clear out from under it (no clipping),
    #           and the ball drops straight through (x,y held constant), then
    #           bounces on the floor with decaying hops before settling.
    if frame <= open_start:
        o_open = 0.0
    elif frame >= open_end:
        o_open = 1.0
    else:
        o_open = ease_in_quad((frame - open_start) / float(open_end - open_start))
    angle = max_angle * o_open

    for d in doors:
        hinge = d["hinge"]
        # Negative for the right door, positive for the left -> both swing DOWN
        # and APART (away from the central fall column).
        hinge.rotation_euler = (0.0, -d["sgn"] * angle, 0.0)
        hinge.keyframe_insert(data_path="rotation_euler", frame=frame)

    # ---- Ball ----
    if frame <= open_start:
        bz = rest_z
        state = "resting_on_closed_doors"
    else:
        bz = bounce_zs[frame - open_start]
        if bz <= floor_rest_z + 1e-6:
            state = "settled_on_floor"
        else:
            state = "free_falling_or_bouncing"

    ball.location = (0.0, 0.0, bz)        # x, y held CONSTANT -> straight-down drop
    ball.rotation_euler = (0.0, -0.08 * frame, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball["pb_state"] = state
    ball["pb_never_suspended"] = True


# ============================================================
# Build / animate dispatch
# ============================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "bomb_bay_doors_drop":
        return build_bomb_bay_doors_drop_scene()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "bomb_bay_doors_drop":
            animate_bomb_bay_doors_drop(objs, frame)
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
