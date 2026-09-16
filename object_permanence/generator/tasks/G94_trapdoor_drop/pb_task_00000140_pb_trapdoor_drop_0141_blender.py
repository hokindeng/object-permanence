# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_TRAPDOOR_DROP_0141",
  "scene_kind": "trapdoor_drop",
  "prompt": "A ball rests on a trapdoor set into a raised platform. The trapdoor swings open downward on its hinge, removing the support; the ball falls straight down through the hole in the platform, lands on the floor below, bounces briefly, and settles. Nothing remains suspended and nothing appears or vanishes."
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


# ============================================================
# General helpers
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


def ease_in_quad(t):
    t = clamp01(t)
    return t * t


def ease_out_quad(t):
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
    tag(
        obj,
        name,
        role,
        "dynamic_object",
        "sphere",
        color_name,
        True,
        solid=True,
        pb_radius=radius,
    )
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
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)
    MATS["deck"] = make_mat("mat_deck_gray", (0.44, 0.45, 0.47), roughness=0.72)
    MATS["leg"] = make_mat("mat_leg_light", (0.62, 0.63, 0.64), roughness=0.68)
    MATS["door"] = make_mat("mat_door_wood", (0.62, 0.45, 0.28), roughness=0.62)
    MATS["hinge"] = make_mat("mat_hinge", (0.20, 0.20, 0.22), roughness=0.45, metallic=0.6)
    MATS["ball"] = make_mat("mat_ball_orange", (1.0, 0.38, 0.06), roughness=0.30)


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube(
        "large_floor_base",
        (0.0, 0.6, -0.05),
        (13.0, 9.0, 0.10),
        material=MATS["floor"],
        role="ground",
        color_name="warm_beige",
    )

    add_cube(
        "rear_backdrop_panel",
        (0.0, 2.42, 1.90),
        (10.0, 0.08, 4.20),
        material=MATS["backdrop"],
        role="background",
        color_name="off_white",
    )

    bpy.ops.object.light_add(type="AREA", location=(-3.8, -4.4, 6.0))
    key = bpy.context.object
    key.name = "large_softbox_light"
    key.data.energy = 1000
    key.data.size = 6.0

    bpy.ops.object.light_add(type="POINT", location=(3.7, -2.8, 3.4))
    fill = bpy.context.object
    fill.data.energy = 155
    fill.name = "right_fill_light"

    return scene


def setup_camera(scene, location=(0.0, -9.2, 1.45), target=(0.0, 0.0, 1.15), lens=34):
    bpy.ops.object.camera_add(location=location)
    camera = bpy.context.object
    camera.name = "camera_main"
    camera.data.lens = lens
    look_at(camera, target)
    camera.data.dof.use_dof = False
    scene.camera = camera
    return camera


# ============================================================
# Trapdoor drop scene  (SUPPORT REMOVAL -> GRAVITY DROP)
# ============================================================
#
# A raised platform (deck) has a rectangular hole in the middle. A flat
# trapdoor slab fills the hole (2 cm visible seam on each side) and a ball
# rests on top of it. The trapdoor is hinged along its TOP edge on the -X
# side of the hole: rotating the hinge by +Y swings the free (+X) edge
# downward INTO the hole, so no part of the door ever sweeps into the deck
# slabs on either side. Once the support starts to swing away, the ball
# free-falls from rest under gravity (quadratic), passes through the hole,
# lands on the floor, does three small decaying bounces and settles. The ball
# height each frame is max(free-fall, door-support) so it can never sink
# into the still-supporting door (no clip) and never hovers once the
# support is gone.

_DIVERSITY = globals().get("DIVERSITY", {})

DECK_TOP_Z = float(_DIVERSITY.get("platform_height", 1.55))
CAMERA_PRESET = str(_DIVERSITY.get("camera_preset", "left_low"))
THICK = 0.12             # deck slab / trapdoor thickness
HOLE_W = float(_DIVERSITY.get("hole_width", 1.10))
DOOR_CLEAR = 0.02        # visible seam between door and each hole edge
WIDTH_Y = 1.60           # platform / door depth along Y

HINGE_X = -HOLE_W / 2.0 + DOOR_CLEAR          # -0.53 : hinge edge X
DOOR_LEN = HOLE_W - 2.0 * DOOR_CLEAR          # 1.06 : hinge edge -> free edge
HINGE_Z = DECK_TOP_Z                          # pivot on the door's TOP hinge edge

BALL_R = float(_DIVERSITY.get("ball_radius", 0.30))
BALL_X = float(_DIVERSITY.get("ball_x", 0.0))
Z_ON_DOOR = DECK_TOP_Z + BALL_R               # ball resting on the closed door
Z_ON_FLOOR = BALL_R

OPEN_START = 24          # trapdoor starts to swing
OPEN_END = int(_DIVERSITY.get("open_end_frame", 36))
MAX_ANGLE = math.radians(float(_DIVERSITY.get("max_angle_degrees", 88.0)))

GRAVITY = float(_DIVERSITY.get("gravity", 0.016))
RESTITUTION = float(_DIVERSITY.get("restitution", 0.5))
MIN_BOUNCE_V = 0.02      # below this rebound speed -> settled


def door_angle_at(frame):
    if frame <= OPEN_START:
        return 0.0
    if frame >= OPEN_END:
        return MAX_ANGLE
    return MAX_ANGLE * smooth01((frame - OPEN_START) / float(OPEN_END - OPEN_START))


def door_support_zc(frame):
    """Highest z at which the swinging door can still support the ball center
    (ball at x = BALL_X = 0). Face support while the contact foot lies on the
    door; then edge support on the free-edge top corner; None once the corner
    has swung further than BALL_R from the ball's vertical line."""
    ang = door_angle_at(frame)
    s, c = math.sin(ang), math.cos(ang)

    # Top surface plane: through pivot P=(HINGE_X, HINGE_Z), direction
    # (c, -s), upward normal (s, c). Ball center on the plane at distance R:
    #   s*(0 - HINGE_X) + c*(zc - HINGE_Z) = BALL_R
    if c > 1e-6:
        zc_face = HINGE_Z + (BALL_R - s * (BALL_X - HINGE_X)) / c
        u_foot = c * (BALL_X - HINGE_X) - s * (zc_face - HINGE_Z)
        if 0.0 <= u_foot <= DOOR_LEN:
            return zc_face

    # Free-edge top corner
    ex = HINGE_X + DOOR_LEN * c
    ez = HINGE_Z - DOOR_LEN * s
    dx = BALL_X - ex
    if abs(dx) < BALL_R:
        return ez + math.sqrt(BALL_R * BALL_R - dx * dx)
    return None


# Free-fall + bounce chain (pure quadratic gravity, decaying restitution).
_FALL_DIST = Z_ON_DOOR - Z_ON_FLOOR
_T_IMPACT = math.sqrt(2.0 * _FALL_DIST / GRAVITY)
_V_IMPACT = GRAVITY * _T_IMPACT


def freefall_z(frame):
    """Gravity free-fall from rest at OPEN_START, then decaying bounces."""
    if frame <= OPEN_START:
        return Z_ON_DOOR
    t = frame - OPEN_START
    if t <= _T_IMPACT:
        return Z_ON_DOOR - 0.5 * GRAVITY * t * t
    tt = t - _T_IMPACT
    v = _V_IMPACT
    for _ in range(16):
        v_up = RESTITUTION * v
        if v_up < MIN_BOUNCE_V:
            return Z_ON_FLOOR
        hop_T = 2.0 * v_up / GRAVITY
        if tt <= hop_T:
            return Z_ON_FLOOR + v_up * tt - 0.5 * GRAVITY * tt * tt
        tt -= hop_T
        v = v_up
    return Z_ON_FLOOR


def ball_z_at(frame):
    ff = freefall_z(frame)
    sup = door_support_zc(frame)
    z = ff if sup is None else max(ff, sup)
    return max(Z_ON_FLOOR, z)


def build_trapdoor_drop_scene():
    scene = build_base_scene()
    if CAMERA_PRESET == "right_high":
        camera_location = (2.0, -7.6, 3.15)
        camera_target = (0.0, 0.0, 0.90 * DECK_TOP_Z)
    else:
        camera_location = (-2.0, -7.6, 1.95)
        camera_target = (0.0, 0.0, 0.56 * DECK_TOP_Z)
    setup_camera(scene, location=camera_location, target=camera_target, lens=35)

    # Deck: two slabs left/right of the hole, top surface at DECK_TOP_Z.
    slab_len = 1.60
    left_slab = add_cube(
        "deck_slab_left",
        (-HOLE_W / 2.0 - slab_len / 2.0, 0.0, DECK_TOP_Z - THICK / 2.0),
        (slab_len, WIDTH_Y, THICK),
        MATS["deck"],
        role="platform_deck",
        color_name="gray",
    )
    right_slab = add_cube(
        "deck_slab_right",
        (HOLE_W / 2.0 + slab_len / 2.0, 0.0, DECK_TOP_Z - THICK / 2.0),
        (slab_len, WIDTH_Y, THICK),
        MATS["deck"],
        role="platform_deck",
        color_name="gray",
    )
    left_slab["pb_count_conserved"] = True
    right_slab["pb_count_conserved"] = True

    # Support legs under the outer ends of the deck (never under the hole).
    leg_h = DECK_TOP_Z - THICK
    for name, lx in (("deck_leg_left", -1.85), ("deck_leg_right", 1.85)):
        add_cube(
            name,
            (lx, 0.0, leg_h / 2.0),
            (0.30, 1.50, leg_h),
            MATS["leg"],
            role="platform_leg",
            color_name="light_gray",
        )

    # Trapdoor slab. Its TOP hinge edge sits at (HINGE_X, DECK_TOP_Z); built
    # closed, it exactly fills the hole minus the 2 cm seams, top flush with
    # the deck. Parented to a hinge empty at the top hinge edge so a +Y
    # rotation swings the free (+X) edge down INTO the hole.
    door = add_cube(
        "trapdoor_slab",
        (HINGE_X + DOOR_LEN / 2.0, 0.0, DECK_TOP_Z - THICK / 2.0),
        (DOOR_LEN, WIDTH_Y, THICK),
        MATS["door"],
        role="trapdoor",
        color_name="wood_tan",
        is_dynamic=True,
    )
    door["pb_count_conserved"] = True

    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(HINGE_X, 0.0, HINGE_Z))
    pivot = bpy.context.object
    pivot.name = "trapdoor_hinge_pivot"
    door.parent = pivot
    door.matrix_parent_inverse = pivot.matrix_world.inverted()

    # Dark hinge bar along the hinge edge (depth cue), resting on the deck top.
    hinge_bar = add_cube(
        "trapdoor_hinge_bar",
        (HINGE_X, 0.0, DECK_TOP_Z + 0.025),
        (0.06, WIDTH_Y * 1.02, 0.05),
        MATS["hinge"],
        role="hinge_bar",
        color_name="dark_metal",
    )
    hinge_bar["pb_is_hinge"] = True

    ball = add_sphere(
        "trapdoor_ball",
        BALL_R,
        (BALL_X, 0.0, Z_ON_DOOR),
        MATS["ball"],
        "orange",
        # Keep "door" out of this ball's role: render.py's is_target() matches
        # apparatus keywords by substring, so a role containing it would class
        # the task's sole target ball as rig apparatus and repaint it muted.
        role="ball_released_through_hatch",
    )
    ball["pb_count_conserved"] = True
    ball["pb_expected_behavior"] = "trapdoor_opens_then_ball_free_falls_to_floor"

    return {
        "scene": scene,
        "kind": "trapdoor_drop",
        "ball": ball,
        "pivot": pivot,
        "door": door,
    }


# ============================================================
# Animation
# ============================================================

def animate_trapdoor_drop(objs, frame):
    ball = objs["ball"]
    pivot = objs["pivot"]

    # Trapdoor swing (hinge empty; door follows rigidly).
    ang = door_angle_at(frame)
    pivot.rotation_euler = (0.0, ang, 0.0)
    pivot.keyframe_insert(data_path="rotation_euler", frame=frame)

    # Ball: rest -> gravity free-fall (never below remaining support) ->
    # floor bounces -> settled. X/Y stay fixed; it falls straight down.
    bz = ball_z_at(frame)
    ball.location = (BALL_X, 0.0, bz)
    ball.rotation_euler = (0.0, 0.0, 0.0)     # resting ball never spins
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)

    if frame <= OPEN_START:
        ball["pb_state"] = "resting_on_trapdoor"
        ball["pb_is_moving"] = False
    elif bz > Z_ON_FLOOR + 1e-4:
        ball["pb_state"] = "falling_through_hole"
        ball["pb_is_moving"] = True
    else:
        ball["pb_state"] = "settled_on_floor"
        ball["pb_is_moving"] = False
    ball["pb_never_suspended"] = True


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "trapdoor_drop":
            animate_trapdoor_drop(objs, frame)
        else:
            raise RuntimeError("Unknown kind: " + str(kind))

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


def build_scene_by_kind():
    kind = CASE["scene_kind"]

    if kind == "trapdoor_drop":
        return build_trapdoor_drop_scene()

    raise RuntimeError("Unknown scene_kind: " + str(kind))


def main():
    ensure_dirs()
    clear_scene()

    objs = build_scene_by_kind()
    scene = objs["scene"]

    animate_scene(objs)

    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, 32, OPTIONAL_FRAME_PATH)
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
