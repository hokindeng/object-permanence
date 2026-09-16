# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_BALL_TOPPLES_BLOCK_0180",
  "scene_kind": "ball_topples_block",
  "prompt": "A ball rolls across the flat floor and strikes a single standing block. On impact the block tips over away from the ball, rotating about its far bottom edge, and falls flat onto the floor with a small settling bounce. The ball rebounds slightly off the block and eases to a stop near where it struck. Exactly one ball and one block; nothing appears or vanishes."
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
    MATS["ball"] = make_mat("mat_ball_blue", (0.15, 0.55, 0.85), roughness=0.24)
    MATS["block"] = make_mat("mat_block_red", (0.85, 0.12, 0.10), roughness=0.42)


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
        (0.0, 2.42, 1.60),
        (10.0, 0.08, 3.20),
        material=MATS["backdrop"],
        role="background",
        color_name="off_white",
    )

    bpy.ops.object.light_add(type="AREA", location=(-3.8, -4.4, 5.5))
    key = bpy.context.object
    key.name = "large_softbox_light"
    key.data.energy = 950
    key.data.size = 6.0

    bpy.ops.object.light_add(type="POINT", location=(3.7, -2.8, 3.2))
    fill = bpy.context.object
    fill.data.energy = 145
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
# Ball-topples-block scene  (SIMPLE TWO-BODY COLLISION)
# ============================================================
#
# One blue ball rolls in along +X at constant speed and strikes one standing
# red block low on its near (-X) face. Momentum along +X from the contact:
# the block tips over AWAY from the ball, rotating about its FAR bottom edge
# (a hinge-like topple), accelerating under gravity torque (ease-in), slams
# flat on the floor and does two small decaying rotational rebounds before
# resting. The heavier block sends the ball into a small backward rebound
# (reaction along -X) that decays smoothly to rest. Exactly two bodies, NO
# chain/cascade. Contact is exact: at the strike frame the ball surface
# touches the block face with zero gap and zero overlap, and the block
# rotates away afterwards so they never re-touch.

_DIVERSITY = globals().get("DIVERSITY", {})

R_BALL = float(_DIVERSITY.get("ball_radius", 0.24))

BLOCK_TX = float(_DIVERSITY.get("block_thickness", 0.26))
BLOCK_W = 0.50           # block width along Y
BLOCK_H = float(_DIVERSITY.get("block_height", 1.00))
BLOCK_CX = float(_DIVERSITY.get("block_center_x", 0.60))

PIVOT_X = BLOCK_CX + BLOCK_TX / 2.0        # 0.73 : far bottom edge (topple pivot)
FACE_X = BLOCK_CX - BLOCK_TX / 2.0         # 0.47 : near face the ball strikes

BALL_START_X = float(_DIVERSITY.get("ball_start_x", -3.60))
CONTACT_X = FACE_X - R_BALL                # 0.23 : ball CENTER at exact touch
CONTACT_FRAME = 40                         # strike frame

# Ball rebound (reaction off the much heavier block): small backward speed
# decaying exponentially -> smooth ease to rest, never re-entering the block.
REBOUND_V0 = float(_DIVERSITY.get("rebound_velocity", -0.028))
REBOUND_DECAY = float(_DIVERSITY.get("rebound_decay", 0.88))
REBOUND_STOP_V = 0.001   # below this speed the ball is at rest

# Block topple: gravity-torque fall (ease-in quadratic) to 90 deg, then two
# decaying rotational rebounds on the floor before resting flat.
TOPPLE_START = CONTACT_FRAME
TOPPLE_LAND = int(_DIVERSITY.get("topple_land_frame", 68))
REBOUND_1_DEG = 5.0                        # first rebound amplitude
REBOUND_1_UP_END = 72
REBOUND_1_DOWN_END = 76
REBOUND_2_DEG = 1.2                        # second, smaller rebound
REBOUND_2_UP_END = 79
REBOUND_2_DOWN_END = 82

_BALL_TRAJ = None


def _compute_ball_traj():
    """Deterministic per-frame ball X: constant-speed roll-in to exact contact,
    then decaying backward rebound to rest. Returns {frame: x}."""
    traj = {}
    for f in range(FRAME_START, CONTACT_FRAME + 1):
        t = (f - FRAME_START) / float(CONTACT_FRAME - FRAME_START)
        traj[f] = lerp(BALL_START_X, CONTACT_X, t)      # linear -> constant speed
    x = CONTACT_X
    v = REBOUND_V0
    for f in range(CONTACT_FRAME + 1, FRAME_END + 1):
        if abs(v) >= REBOUND_STOP_V:
            x += v
            v *= REBOUND_DECAY
        traj[f] = x
    return traj


def ball_x_at(frame):
    global _BALL_TRAJ
    if _BALL_TRAJ is None:
        _BALL_TRAJ = _compute_ball_traj()
    return _BALL_TRAJ[frame]


def block_angle_at(frame):
    """Topple angle (radians about +Y at the far bottom edge). 0 = standing,
    pi/2 = flat on the floor. Gravity-accelerated fall, then two decaying
    rebounds (decelerating up, accelerating back down), then rest."""
    if frame <= TOPPLE_START:
        return 0.0
    if frame <= TOPPLE_LAND:
        t = (frame - TOPPLE_START) / float(TOPPLE_LAND - TOPPLE_START)
        return math.radians(90.0) * ease_in_quad(t)
    if frame <= REBOUND_1_UP_END:
        t = (frame - TOPPLE_LAND) / float(REBOUND_1_UP_END - TOPPLE_LAND)
        return math.radians(90.0 - REBOUND_1_DEG * ease_out_quad(t))
    if frame <= REBOUND_1_DOWN_END:
        t = (frame - REBOUND_1_UP_END) / float(REBOUND_1_DOWN_END - REBOUND_1_UP_END)
        return math.radians(90.0 - REBOUND_1_DEG + REBOUND_1_DEG * ease_in_quad(t))
    if frame <= REBOUND_2_UP_END:
        t = (frame - REBOUND_1_DOWN_END) / float(REBOUND_2_UP_END - REBOUND_1_DOWN_END)
        return math.radians(90.0 - REBOUND_2_DEG * ease_out_quad(t))
    if frame <= REBOUND_2_DOWN_END:
        t = (frame - REBOUND_2_UP_END) / float(REBOUND_2_DOWN_END - REBOUND_2_UP_END)
        return math.radians(90.0 - REBOUND_2_DEG + REBOUND_2_DEG * ease_in_quad(t))
    return math.radians(90.0)


def build_ball_topples_block_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(-1.8, -8.6, 3.0), target=(0.5, 0.0, 0.5), lens=40)

    block = add_cube(
        "standing_block",
        (BLOCK_CX, 0.0, BLOCK_H / 2.0),
        (BLOCK_TX, BLOCK_W, BLOCK_H),
        MATS["block"],
        role="topple_block",
        color_name="red",
        is_dynamic=True,
    )
    block["pb_count_conserved"] = True
    block["pb_motion_constraint"] = "topples_about_far_bottom_edge"

    # Topple pivot at the block's FAR bottom edge: +Y rotation tips the block
    # away from the incoming ball and lays it flat extending +X.
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(PIVOT_X, 0.0, 0.0))
    pivot = bpy.context.object
    pivot.name = "block_topple_pivot"
    block.parent = pivot
    block.matrix_parent_inverse = pivot.matrix_world.inverted()

    ball = add_sphere(
        "striker_ball",
        R_BALL,
        (BALL_START_X, 0.0, R_BALL),
        MATS["ball"],
        "blue",
        role="striker_ball",
    )
    ball["pb_count_conserved"] = True
    ball["pb_motion_constraint"] = "rolls_on_flat_floor"

    return {
        "scene": scene,
        "kind": "ball_topples_block",
        "ball": ball,
        "block": block,
        "pivot": pivot,
    }


# ============================================================
# Animation
# ============================================================

def animate_ball_topples_block(objs, frame):
    ball = objs["ball"]
    pivot = objs["pivot"]
    block = objs["block"]

    # Ball: rolls in, exact-touch contact, small decaying backward rebound.
    bx = ball_x_at(frame)
    ball.location = (bx, 0.0, R_BALL)
    # Rolling without slipping: rotation tracks signed travel (reverses on
    # the rebound, freezes when the ball is at rest -> no spin at rest).
    ball.rotation_euler = (0.0, -(bx - BALL_START_X) / R_BALL, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    if frame < CONTACT_FRAME:
        ball["pb_state"] = "rolling_in"
        ball["pb_is_moving"] = True
    elif frame < CONTACT_FRAME + 26:
        ball["pb_state"] = "rebounding_after_strike"
        ball["pb_is_moving"] = True
    else:
        ball["pb_state"] = "at_rest_near_block"
        ball["pb_is_moving"] = False

    # Block: hinge-like topple about the far bottom edge.
    ang = block_angle_at(frame)
    pivot.rotation_euler = (0.0, ang, 0.0)
    pivot.keyframe_insert(data_path="rotation_euler", frame=frame)
    if frame <= TOPPLE_START:
        block["pb_state"] = "standing_upright"
        block["pb_is_moving"] = False
    elif frame <= REBOUND_2_DOWN_END:
        block["pb_state"] = "toppling_over"
        block["pb_is_moving"] = True
    else:
        block["pb_state"] = "resting_flat_on_floor"
        block["pb_is_moving"] = False


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "ball_topples_block":
            animate_ball_topples_block(objs, frame)
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

    if kind == "ball_topples_block":
        return build_ball_topples_block_scene()

    raise RuntimeError("Unknown scene_kind: " + str(kind))


def main():
    ensure_dirs()
    clear_scene()

    objs = build_scene_by_kind()
    scene = objs["scene"]

    animate_scene(objs)

    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, 54, OPTIONAL_FRAME_PATH)
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
