# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_BALL_SHOVES_BLOCK_SLIDE_0186",
  "scene_kind": "ball_shoves_block_slide",
  "prompt": "A ball rolls across a flat surface toward a block resting upright on the table. The ball reaches the block's near face and, on contact, the block slides forward across the table, staying upright, and decelerates to rest a short distance ahead. The ball slows and stops near the block's starting position after the strike. Nothing appears or vanishes."
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
    MATS["block"] = make_mat("mat_block", (0.13, 0.42, 0.78), roughness=0.32)


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
# Ball-shoves-block-slide scene  (SINGLE-BODY COLLISION)
# ============================================================
#
# A BLOCK (a cuboid) rests upright on the table (the struck target). A BALL
# rolls in along +X at constant speed and just touches the block's NEAR (-X)
# face (gap >= 0, NO clip). At that contact frame the block begins to SLIDE
# forward in +X, staying perfectly UPRIGHT (no rotation / no topple), and it
# DECELERATES (ease-out, as if by friction) to rest a short distance ahead.
# The block leaves at a speed <= the ball's incoming speed, then its per-frame
# speed is non-increasing. The ball decelerates to rest at the contact point
# and never crosses the block's near face (the block only ever moves away in
# +X). One struck body, no cascade. Nothing appears or vanishes.

BALL_RADIUS = 0.28
BALL_Z = BALL_RADIUS

BLOCK_T = 0.50      # block extent along X (slide direction)
BLOCK_W = 0.55      # block extent along Y
BLOCK_H = 0.50      # block extent along Z (upright, stays upright)
BLOCK_X0 = 0.0      # resting base-center X of the block
BLOCK_Z = BLOCK_H / 2.0

# Ball just touches the block's near (-X) face with a tiny positive standoff.
_BALL_GAP = 0.01
_BLOCK_NEAR_FACE_X = BLOCK_X0 - BLOCK_T / 2.0
_CONTACT_X = _BLOCK_NEAR_FACE_X - BALL_RADIUS - _BALL_GAP   # ball CENTER at contact

CUE_START_X = -4.0
IMPACT_FRAME = 40             # ball reaches block near face
SLIDE_DUR = 55               # frames for the block to slide to rest
SLIDE_DIST = 1.40            # how far the block slides forward (+X)


def _ball_position(frame):
    """Constant speed in, then parked at the contact point (never past it)."""
    if frame <= IMPACT_FRAME:
        t = clamp01((frame - FRAME_START) / float(IMPACT_FRAME - FRAME_START))
        x = lerp(CUE_START_X, _CONTACT_X, t)     # linear -> constant incoming speed
        return Vector((x, 0.0, BALL_Z))
    return Vector((_CONTACT_X, 0.0, BALL_Z))


def _block_offset(frame):
    """Forward (+X) slide offset of the block, eased-out (decelerating) to rest."""
    if frame <= IMPACT_FRAME:
        return 0.0
    t = clamp01((frame - IMPACT_FRAME) / float(SLIDE_DUR))
    return SLIDE_DIST * ease_out_quad(t)


def _block_position(frame):
    return Vector((BLOCK_X0 + _block_offset(frame), 0.0, BLOCK_Z))


def build_ball_shoves_block_slide_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(-1.6, -8.4, 3.0), target=(0.4, 0.0, 0.5), lens=40)

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

    block = add_cube(
        "shoved_block",
        (BLOCK_X0, 0.0, BLOCK_Z),
        (BLOCK_T, BLOCK_W, BLOCK_H),
        material=MATS["block"],
        role="shoved_block",
        color_name="blue",
        is_dynamic=True,
    )
    block["pb_count_conserved"] = True
    block["pb_motion_constraint"] = "slides_forward_upright"

    return {
        "scene": scene,
        "kind": "ball_shoves_block_slide",
        "ball": ball,
        "block": block,
    }


# ============================================================
# Animation
# ============================================================

def animate_ball_shoves_block_slide(objs, frame):
    ball = objs["ball"]
    block = objs["block"]

    bpos = _ball_position(frame)
    ball.location = bpos
    ball.rotation_euler = (0.0, -(bpos.x - CUE_START_X) / BALL_RADIUS, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball["pb_state"] = "rolling_in" if frame < IMPACT_FRAME else "stopped_at_block"
    ball["pb_is_moving"] = bool(frame < IMPACT_FRAME)

    block.location = _block_position(frame)
    block.rotation_euler = (0.0, 0.0, 0.0)          # stays upright: never rotates
    block.keyframe_insert(data_path="location", frame=frame)
    block.keyframe_insert(data_path="rotation_euler", frame=frame)
    off = _block_offset(frame)
    if frame <= IMPACT_FRAME:
        block["pb_state"] = "resting"
        block["pb_is_moving"] = False
    elif off < SLIDE_DIST - 1e-4:
        block["pb_state"] = "sliding"
        block["pb_is_moving"] = True
    else:
        block["pb_state"] = "stopped"
        block["pb_is_moving"] = False


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "ball_shoves_block_slide":
            animate_ball_shoves_block_slide(objs, frame)
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

    if kind == "ball_shoves_block_slide":
        return build_ball_shoves_block_slide_scene()

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
