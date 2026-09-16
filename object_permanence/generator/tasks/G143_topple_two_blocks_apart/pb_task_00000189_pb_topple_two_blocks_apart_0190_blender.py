# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_TOPPLE_TWO_BLOCKS_APART_0190",
  "scene_kind": "topple_two_blocks_apart",
  "prompt": "Two tall blocks stand upright side by side on the table with a small gap between them. A ball rolls straight into the gap and knocks the blocks apart: each block topples over in the opposite outward direction, the left block falling to the left and the right block falling to the right, so they never touch each other. Each comes to rest lying flat on the floor. The ball rolls on through and slows to a stop past the blocks. Nothing appears or vanishes."
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
    MATS["gray"] = make_mat("mat_neutral_gray", (0.46, 0.46, 0.46), roughness=0.62)
    MATS["dark_gray"] = make_mat("mat_dark_gray", (0.18, 0.18, 0.20), roughness=0.72)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)
    MATS["ball"] = make_mat("mat_ball", (0.86, 0.20, 0.16), roughness=0.24)
    MATS["block_l"] = make_mat("mat_block_l", (0.13, 0.42, 0.78), roughness=0.32)
    MATS["block_r"] = make_mat("mat_block_r", (0.20, 0.62, 0.28), roughness=0.32)


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
# Topple-two-blocks-apart scene  (TWO-BODY COLLISION, symmetric split)
# ============================================================
#
# Two tall UPRIGHT BLOCKS stand side by side on the table, offset in +/-Y with a
# small central gap (just the ball's diameter). A BALL rolls straight down the
# gap along +X at constant speed. When it reaches the blocks it is touching both
# inner (Y-facing) faces (faces sit exactly at |Y| = BALL_RADIUS, so gap = 0, NO
# clip). At that contact frame both blocks begin to TOPPLE OUTWARD, each about
# its OUTER bottom edge (rotation about the X axis): the LEFT block (-Y) falls
# further to -Y, the RIGHT block (+Y) falls to +Y, so their tops swing APART and
# they never touch or interpenetrate. Each ends lying FLAT on the floor
# (tilt 90 deg, resting z = BLOCK_W/2). During the topple every part of a block
# moves OUTWARD (away from the centre line) so neither block ever reaches the
# ball's Y=0 path. The ball rolls on through the gap and decelerates to rest
# past the blocks. Two struck bodies, clean symmetric split, no interpenetration.

BALL_RADIUS = 0.28
BALL_Z = BALL_RADIUS

BLOCK_LEN_X = 0.50    # block extent along X (ball travel direction)
BLOCK_W = 0.40        # block width along Y (becomes horizontal extent when flat)
BLOCK_H = 1.10        # block height along Z (tall, upright)
BLOCK_X0 = 0.0        # both blocks share this X (standing side by side)

# Inner faces sit exactly at |Y| = BALL_RADIUS so the ball just touches both
# (gap = 0). Block centre Y = inner_face + BLOCK_W/2.
_INNER_FACE_Y = BALL_RADIUS
BLOCK_YC = _INNER_FACE_Y + BLOCK_W / 2.0     # right block +YC, left block -YC

# Topple pivots: each block's OUTER bottom edge (z = 0).
_PIVOT_Y_R = BLOCK_YC + BLOCK_W / 2.0        # right outer bottom edge (+Y)
_PIVOT_Y_L = -(BLOCK_YC + BLOCK_W / 2.0)     # left  outer bottom edge (-Y)
# Centre offset from the (right) pivot when standing upright.
_OY_R = -BLOCK_W / 2.0   # centre is inward (-Y) of the right pivot
_OY_L = +BLOCK_W / 2.0   # centre is inward (+Y) of the left pivot
_OZ = BLOCK_H / 2.0

BLOCK_FINAL_DEG = 90.0        # ends lying flat on the floor

# Ball first laterally contacts the blocks when its centre reaches their near
# (-X) edge; that is the impact frame.
_BLOCK_NEAR_FACE_X = BLOCK_X0 - BLOCK_LEN_X / 2.0
_CONTACT_X = _BLOCK_NEAR_FACE_X          # ball CENTRE at first contact

CUE_START_X = -3.60
IMPACT_FRAME = 40             # ball reaches the blocks
TOPPLE_DUR = 44              # frames for a block to fall flat (0 -> 90 deg)
BALL_STOP_X = 1.30           # ball comes to rest here, past the blocks
BALL_STOP_FRAME = 96         # ball finished decelerating


def _ball_position(frame):
    """Constant speed into the gap, then eased (decelerating) to rest past the
    blocks. Never reverses; always moves +X."""
    if frame <= IMPACT_FRAME:
        t = clamp01((frame - FRAME_START) / float(IMPACT_FRAME - FRAME_START))
        x = lerp(CUE_START_X, _CONTACT_X, t)     # linear -> constant speed in
        return Vector((x, 0.0, BALL_Z))
    if frame <= BALL_STOP_FRAME:
        t = clamp01((frame - IMPACT_FRAME) / float(BALL_STOP_FRAME - IMPACT_FRAME))
        x = lerp(_CONTACT_X, BALL_STOP_X, ease_out_quad(t))   # decelerate to rest
        return Vector((x, 0.0, BALL_Z))
    return Vector((BALL_STOP_X, 0.0, BALL_Z))


def _block_angle(frame):
    """Topple magnitude (rad) about the outer bottom edge (same schedule for
    both blocks; the direction is applied per side in _block_transform)."""
    if frame <= IMPACT_FRAME:
        return 0.0
    t = clamp01((frame - IMPACT_FRAME) / float(TOPPLE_DUR))
    return math.radians(BLOCK_FINAL_DEG) * smooth01(t)


def _block_transform(pivot_y, oy, phi):
    """Location + rotation_euler of a block toppled by |phi| about its outer
    bottom edge. Rotation is about the X axis; the sign of phi is chosen per
    side so the top swings OUTWARD. Rx(phi) on the centre offset (0, oy, oz):
        y' = oy*cos - oz*sin ; z' = oy*sin + oz*cos
    Right block uses phi<0 (falls +Y), left block uses phi>0 (falls -Y); each
    ends flat with loc_z = BLOCK_W/2."""
    c = math.cos(phi)
    s = math.sin(phi)
    loc_y = pivot_y + (oy * c - _OZ * s)
    loc_z = (oy * s + _OZ * c)
    return Vector((BLOCK_X0, loc_y, loc_z)), Vector((phi, 0.0, 0.0))


def build_topple_two_blocks_apart_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(-1.2, -8.8, 3.4), target=(0.3, 0.0, 0.5), lens=36)

    ball = add_sphere(
        "moving_ball",
        BALL_RADIUS,
        (CUE_START_X, 0.0, BALL_Z),
        MATS["ball"],
        "red",
        role="moving_ball",
    )
    ball["pb_count_conserved"] = True
    ball["pb_motion_constraint"] = "rolls_on_flat_floor"

    block_l = add_cube(
        "struck_block_left",
        (BLOCK_X0, -BLOCK_YC, BLOCK_H / 2.0),
        (BLOCK_LEN_X, BLOCK_W, BLOCK_H),
        material=MATS["block_l"],
        role="struck_block_left",
        color_name="blue",
        is_dynamic=True,
    )
    block_l["pb_count_conserved"] = True
    block_l["pb_motion_constraint"] = "topples_outward_about_left_base_edge"

    block_r = add_cube(
        "struck_block_right",
        (BLOCK_X0, BLOCK_YC, BLOCK_H / 2.0),
        (BLOCK_LEN_X, BLOCK_W, BLOCK_H),
        material=MATS["block_r"],
        role="struck_block_right",
        color_name="green",
        is_dynamic=True,
    )
    block_r["pb_count_conserved"] = True
    block_r["pb_motion_constraint"] = "topples_outward_about_right_base_edge"

    return {
        "scene": scene,
        "kind": "topple_two_blocks_apart",
        "ball": ball,
        "block_l": block_l,
        "block_r": block_r,
    }


# ============================================================
# Animation
# ============================================================

def _apply_block(block, pivot_y, oy, phi, frame):
    loc, rot = _block_transform(pivot_y, oy, phi)
    block.location = loc
    block.rotation_euler = rot
    block.keyframe_insert(data_path="location", frame=frame)
    block.keyframe_insert(data_path="rotation_euler", frame=frame)
    if frame <= IMPACT_FRAME:
        block["pb_state"] = "standing"
        block["pb_is_moving"] = False
    elif abs(phi) < math.radians(BLOCK_FINAL_DEG) - 1e-3:
        block["pb_state"] = "toppling_outward"
        block["pb_is_moving"] = True
    else:
        block["pb_state"] = "fallen_flat"
        block["pb_is_moving"] = False


def animate_topple_two_blocks_apart(objs, frame):
    ball = objs["ball"]
    block_l = objs["block_l"]
    block_r = objs["block_r"]

    bpos = _ball_position(frame)
    ball.location = bpos
    ball.rotation_euler = (0.0, -(bpos.x - CUE_START_X) / BALL_RADIUS, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    moving = frame < BALL_STOP_FRAME
    ball["pb_state"] = "rolling_through" if moving else "stopped_past_blocks"
    ball["pb_is_moving"] = bool(moving)

    mag = _block_angle(frame)
    # Left block topples to -Y (phi > 0), right block to +Y (phi < 0).
    _apply_block(block_l, _PIVOT_Y_L, _OY_L, +mag, frame)
    _apply_block(block_r, _PIVOT_Y_R, _OY_R, -mag, frame)


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "topple_two_blocks_apart":
            animate_topple_two_blocks_apart(objs, frame)
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

    if kind == "topple_two_blocks_apart":
        return build_topple_two_blocks_apart_scene()

    raise RuntimeError("Unknown scene_kind: " + str(kind))


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
