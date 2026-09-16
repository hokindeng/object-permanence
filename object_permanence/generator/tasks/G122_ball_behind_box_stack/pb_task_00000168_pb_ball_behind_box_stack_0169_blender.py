# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_BALL_BEHIND_BOX_STACK_0169",
  "scene_kind": "ball_behind_box_stack",
  "kind": "ball_behind_box_stack",
  "prompt": "A ball rolls horizontally across the table at a steady speed and passes behind a tall opaque stack of two boxes standing between it and the camera. The ball is hidden for a stretch of frames, then emerges from the far side of the stack, still rolling -- the same ball, same size, continuing straight on."
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


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def make_mat(name, color, roughness=0.55, metallic=0.0, alpha=1.0, transparent=False):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (color[0], color[1], color[2], alpha)

    try:
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            if "Base Color" in bsdf.inputs:
                bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], alpha)
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = roughness
            if "Metallic" in bsdf.inputs:
                bsdf.inputs["Metallic"].default_value = metallic
            if "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = alpha
    except Exception:
        pass

    return mat


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), roughness=0.85)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.92)

    MATS["gray"] = make_mat("mat_gray", (0.62, 0.63, 0.66), roughness=0.75)
    MATS["housing"] = make_mat("mat_housing", (0.32, 0.33, 0.37), roughness=0.85)
    MATS["dark"] = make_mat("mat_dark", (0.18, 0.20, 0.24), roughness=0.55)
    MATS["support"] = make_mat("mat_support", (0.16, 0.18, 0.22), roughness=0.60)

    MATS["red"] = make_mat("mat_red", (0.92, 0.18, 0.18), roughness=0.28)
    MATS["blue"] = make_mat("mat_blue", (0.16, 0.36, 0.95), roughness=0.28)
    MATS["yellow"] = make_mat("mat_yellow", (0.98, 0.78, 0.15), roughness=0.28)
    MATS["orange"] = make_mat("mat_orange", (0.97, 0.45, 0.10), roughness=0.28)


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


def add_cube(name, location, dimensions, material, role, color_name, is_dynamic=False, solid=True, rotation=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=rotation)
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
        "dynamic_object" if is_dynamic else "static_solid",
        "cube",
        color_name,
        is_dynamic,
        solid=solid,
    )
    return obj


def add_sphere(name, radius, location, material, color_name, role="target", is_dynamic=True):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=48, ring_count=24)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)

    tag(
        obj,
        name,
        role,
        "dynamic_object" if is_dynamic else "static_solid",
        "sphere",
        color_name,
        is_dynamic,
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
        scene.eevee.gtao_distance = 3.0
        scene.eevee.gtao_factor = 1.2
    except Exception:
        pass

    if scene.world is None:
        scene.world = bpy.data.worlds.new("clean_world")
    scene.world.color = (1.0, 1.0, 1.0)

    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Base Contrast"
    except Exception:
        try:
            scene.view_settings.view_transform = "Standard"
            scene.view_settings.look = "None"
        except Exception:
            pass


def setup_base(camera_loc, target, ortho_scale):
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (14.0, 8.0, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.55, 2.05), (14.0, 0.08, 4.1), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-2.8, -4.5, 6.4))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 600
    key.data.size = 7.0

    bpy.ops.object.light_add(type="POINT", location=(3.0, 1.8, 3.6))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 140

    bpy.ops.object.camera_add(location=camera_loc)
    cam = bpy.context.object
    cam.name = "camera_main"
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = ortho_scale
    look_at(cam, target)
    scene.camera = cam

    return scene


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


def write_task_json(task):
    with open(TASK_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(task, f, indent=2, ensure_ascii=False)


def save_scene():
    bpy.ops.wm.save_as_mainfile(filepath=SCENE_FILE)


# =============================================================================
# 00000168  ball_behind_box_stack  (Cluster: Baillargeonian Occlusion)
#
# A vivid ball rolls in a straight line across the table (x increases at a
# constant rate; y and z are held constant so it is a pure horizontal roll). A
# tall opaque STACK of TWO boxes stands between the ball's path and the camera
# (nearer the camera, at smaller y). As the ball's silhouette slides fully behind
# the stack, the STACK GEOMETRY occludes it -- the ball is never removed from
# the render, so the disappearance is honest image-space cover -- then it
# emerges from the far side and keeps rolling -- the same ball, same radius.
# Its true location keeps advancing while hidden so the reappearance is
# physically continuous.
#
# The lower box alone is taller than the ball, so the ball's full height is
# occluded whenever its center is within (lower_box_half_x - ball_radius) of the
# stack center in x. The camera is a front ortho view so screen-x ~= world-x.
# =============================================================================

# --- geometry -----------------------------------------------------------------
FLOOR_TOP_Z = 0.0
_DIVERSITY = globals().get("DIVERSITY", {})

BALL_RADIUS = float(_DIVERSITY.get("ball_radius", 0.30))
BALL_Y = float(_DIVERSITY.get("ball_y", 0.70))
BALL_Z = FLOOR_TOP_Z + BALL_RADIUS
PATH_HALF_LENGTH = float(_DIVERSITY.get("path_half_length", 3.2))
TRAVEL_DIRECTION = str(_DIVERSITY.get("travel_direction", "left_to_right"))
TRAVEL_SIGN = 1.0 if TRAVEL_DIRECTION == "left_to_right" else -1.0
BALL_X_START = -TRAVEL_SIGN * PATH_HALF_LENGTH
BALL_X_END = TRAVEL_SIGN * PATH_HALF_LENGTH

STACK_X = float(_DIVERSITY.get("stack_x", 0.0))
STACK_Y = 0.0                # camera side (smaller y than the ball) -> occludes

LOWER_BOX_W = float(_DIVERSITY.get("lower_box_width", 1.8))
LOWER_BOX_D = 0.60          # y depth
LOWER_BOX_H = float(_DIVERSITY.get("lower_box_height", 0.90))
UPPER_BOX_W = float(_DIVERSITY.get("upper_box_width", 1.5))
UPPER_BOX_D = 0.55
UPPER_BOX_H = 0.70

LOWER_HALF_X = LOWER_BOX_W / 2.0            # 0.9
HIDE_HALF_X = LOWER_HALF_X - BALL_RADIUS    # ball fully behind -> hidden (0.6)


def build_ball_behind_box_stack():
    scene = setup_base(
        camera_loc=(1.35 * TRAVEL_SIGN, -10.0, 1.75),
        target=(0.25 * TRAVEL_SIGN, 0.45, 0.58),
        ortho_scale=8.4,
    )

    # --- the rolling ball (the TARGET, vivid) ------------------------------
    ball = add_sphere(
        "rolling_ball",
        BALL_RADIUS,
        (BALL_X_START, BALL_Y, BALL_Z),
        MATS["orange"],
        "orange",
        role="rolling_ball",
        is_dynamic=True,
    )
    ball["pb_path"] = "straight_horizontal_roll_behind_static_box_stack"
    ball["pb_can_disappear"] = False

    # --- opaque STACK of two boxes (apparatus occluder, gray) --------------
    lower_z = FLOOR_TOP_Z + LOWER_BOX_H / 2.0
    add_cube("occluder_box_lower", (STACK_X, STACK_Y, lower_z),
             (LOWER_BOX_W, LOWER_BOX_D, LOWER_BOX_H), MATS["housing"], "occluder_box", "gray")
    upper_z = FLOOR_TOP_Z + LOWER_BOX_H + UPPER_BOX_H / 2.0
    add_cube("occluder_box_upper", (STACK_X, STACK_Y, upper_z),
             (UPPER_BOX_W, UPPER_BOX_D, UPPER_BOX_H), MATS["gray"], "occluder_box", "gray")

    return scene, {
        "kind": "ball_behind_box_stack",
        "ball": ball,
        "ball_y": BALL_Y,
        "ball_z": BALL_Z,
        "stack_x": STACK_X,
        "stack_y": STACK_Y,
        "lower_half_x": LOWER_HALF_X,
        "hide_half_x": HIDE_HALF_X,
    }


def animate_ball_behind_box_stack(scene, meta):
    ball = meta["ball"]
    ball_y = meta["ball_y"]
    ball_z = meta["ball_z"]
    stack_x = meta["stack_x"]
    hide_half_x = meta["hide_half_x"]

    span = BALL_X_END - BALL_X_START
    n = float(FRAME_END - FRAME_START)

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        # constant-velocity straight roll: x monotonic increasing, y/z constant.
        u = (frame - FRAME_START) / n
        x = BALL_X_START + span * u
        ball.location = (x, ball_y, ball_z)

        # rolling spin about the Y axis (rolls along +x).
        roll = (x - BALL_X_START) / BALL_RADIUS
        ball.rotation_euler = (0.0, -roll, 0.0)

        # Documentary-only flag: silhouette fully behind the lower box footprint
        # (frontal camera; the stack geometry does the actual occluding).
        inside = abs(x - stack_x) <= hide_half_x

        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)

        if inside:
            ball["pb_state"] = "hidden_behind_box_stack"
        elif TRAVEL_SIGN * (x - stack_x) < 0.0:
            ball["pb_state"] = "rolling_approaching_stack"
        else:
            ball["pb_state"] = "emerged_rolling_on_far_side"
        ball["pb_occluded"] = bool(inside)

    scene.frame_set(FRAME_START)


# =============================================================================
# Dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE.get("scene_kind", CASE.get("kind"))
    if kind == "ball_behind_box_stack":
        return build_ball_behind_box_stack()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(scene, meta):
    kind = CASE.get("scene_kind", CASE.get("kind"))
    if kind == "ball_behind_box_stack":
        return animate_ball_behind_box_stack(scene, meta)
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def main():
    ensure_dirs()
    clear_scene()

    scene, meta = build_scene_by_kind()
    animate_scene_by_kind(scene, meta)

    task = {
        "item_id": ITEM_ID,
        "visual_regime": "3D_procedural_control",
        "fps": FPS,
        "inputs": {
            "text_prompt": CASE["prompt"],
        },
        "reference_completion_frames_dir": "frames",
        "scene_file": f"{ITEM_ID}_scene.blend",
    }

    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, 60, OPTIONAL_FRAME_PATH)
    render_png(scene, 120, OPTIONAL_FRAME_02B_PATH)
    render_animation(scene)
    write_task_json(task)
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("scene_kind:", CASE.get("scene_kind"))
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
