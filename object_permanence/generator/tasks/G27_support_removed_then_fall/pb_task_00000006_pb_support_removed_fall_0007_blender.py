# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
from mathutils import Vector

ITEM_ID = "PB_SUPPORT_REMOVED_FALL_0007"
FPS = 24
FRAME_START = 1
FRAME_END = 120

SUPPORT_MOVE_START = 45
SUPPORT_MOVE_END = 75
BALL_RELEASE_FRAME = 61

BALL_RADIUS = 0.23
FLOOR_TOP_Z = 0.0
SUPPORT_TOP_Z = 0.88

BALL_ON_SUPPORT_Z = SUPPORT_TOP_Z + BALL_RADIUS + 0.004
BALL_ON_FLOOR_Z = FLOOR_TOP_Z + BALL_RADIUS + 0.004

# The fall easing (ease_in_quad below) is the physically-correct convex shape for a
# constant-gravity drop (distance fallen grows as t^2). The land frame is derived from g
# rather than hardcoded, so the GT shows a true accelerating free fall (~10 frames).
_FALL_DISTANCE = BALL_ON_SUPPORT_Z - BALL_ON_FLOOR_Z
_GRAVITY = 9.8
BALL_LAND_FRAME = BALL_RELEASE_FRAME + max(1, round(FPS * math.sqrt(2.0 * _FALL_DISTANCE / _GRAVITY)))

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_DIR = os.path.join(PROJECT_ROOT, "permanence_blender_outputs", ITEM_ID)
FRAMES_DIR = os.path.join(OUT_DIR, f"{ITEM_ID}_reference_frames")
SCENE_FILE = os.path.join(OUT_DIR, f"{ITEM_ID}_scene.blend")
TASK_JSON_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_task.json")

INPUT_FRAME_01 = os.path.join(OUT_DIR, f"{ITEM_ID}_input_frame_01.png")
OPTIONAL_FRAME_02 = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_support_removed_frame_02.png")
OPTIONAL_FRAME_02B = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_landed_frame_02B.png")


def ensure_dirs():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(FRAMES_DIR, exist_ok=True)


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for block in bpy.data.meshes:
        if block.users == 0:
            bpy.data.meshes.remove(block)
    for block in bpy.data.materials:
        if block.users == 0:
            bpy.data.materials.remove(block)
    for block in bpy.data.cameras:
        if block.users == 0:
            bpy.data.cameras.remove(block)
    for block in bpy.data.lights:
        if block.users == 0:
            bpy.data.lights.remove(block)


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()


def set_render(scene):
    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    scene.render.fps = FPS
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'

    for engine in ["BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"]:
        try:
            scene.render.engine = engine
            break
        except Exception:
            pass

    scene.render.film_transparent = False
    scene.world.color = (1.0, 1.0, 1.0)

    try:
        scene.view_settings.view_transform = 'Filmic'
        scene.view_settings.look = 'Medium High Contrast'
        scene.view_settings.exposure = 0.0
        scene.view_settings.gamma = 1.0
    except Exception:
        pass


def make_principled_material(name, base_color=(0.8, 0.8, 0.8, 1.0), roughness=0.5, metallic=0.0, alpha=1.0, blend='OPAQUE'):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = base_color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = alpha
    mat.diffuse_color = base_color
    try:
        mat.blend_method = blend
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


def build_scene():
    scene = bpy.context.scene
    set_render(scene)

    # Materials
    floor_mat = make_principled_material(
        "mat_floor_warm",
        base_color=(0.83, 0.81, 0.76, 1.0),
        roughness=0.85
    )
    support_mat = make_principled_material(
        "mat_support_blue",
        base_color=(0.32, 0.60, 0.92, 1.0),
        roughness=0.35
    )
    support_post_mat = make_principled_material(
        "mat_support_post_dark",
        base_color=(0.24, 0.27, 0.31, 1.0),
        roughness=0.45
    )
    ball_mat = make_principled_material(
        "mat_ball_orange",
        base_color=(1.0, 0.38, 0.06, 1.0),
        roughness=0.25
    )
    backdrop_mat = make_principled_material(
        "mat_backdrop",
        base_color=(0.96, 0.97, 0.98, 1.0),
        roughness=0.95
    )

    # Floor
    bpy.ops.mesh.primitive_cube_add(location=(0.0, 0.0, -0.05), scale=(3.2, 2.4, 0.05))
    floor = bpy.context.active_object
    floor.name = "large_floor_base"
    floor.data.materials.append(floor_mat)
    tag(floor, "large_floor_base", "ground", "static_solid", "cube", "warm_beige", False, solid=True)

    # Backdrop wall
    bpy.ops.mesh.primitive_cube_add(location=(0.0, 2.15, 1.5), scale=(3.2, 0.04, 1.5))
    backdrop = bpy.context.active_object
    backdrop.name = "rear_backdrop_panel"
    backdrop.data.materials.append(backdrop_mat)
    tag(backdrop, "rear_backdrop_panel", "background", "static_solid", "cube", "off_white", False, solid=True)

    # Support posts
    bpy.ops.mesh.primitive_cube_add(location=(-0.42, 0.0, 0.38), scale=(0.08, 0.22, 0.38))
    left_post = bpy.context.active_object
    left_post.name = "support_left_post"
    left_post.data.materials.append(support_post_mat)
    tag(left_post, "support_left_post", "support_frame", "static_solid", "cube", "dark_gray", False, solid=True)

    bpy.ops.mesh.primitive_cube_add(location=(0.42, 0.0, 0.38), scale=(0.08, 0.22, 0.38))
    right_post = bpy.context.active_object
    right_post.name = "support_right_post"
    right_post.data.materials.append(support_post_mat)
    tag(right_post, "support_right_post", "support_frame", "static_solid", "cube", "dark_gray", False, solid=True)

    # Support plate (movable)
    bpy.ops.mesh.primitive_cube_add(location=(0.0, 0.0, 0.84), scale=(0.65, 0.45, 0.04))
    support_plate = bpy.context.active_object
    support_plate.name = "support_plate"
    support_plate.data.materials.append(support_mat)
    tag(
        support_plate,
        "support_plate",
        "support",
        "dynamic_solid",
        "cube",
        "blue",
        True,
        solid=True,
        pb_width=1.30,
        pb_height=0.08
    )

    # Ball
    bpy.ops.mesh.primitive_uv_sphere_add(radius=BALL_RADIUS, location=(0.0, 0.0, BALL_ON_SUPPORT_Z))
    ball = bpy.context.active_object
    ball.name = "target_orange_ball"
    ball.data.materials.append(ball_mat)
    tag(
        ball,
        "target_orange_ball",
        "target",
        "dynamic_object",
        "sphere",
        "orange",
        True,
        solid=True,
        pb_radius=BALL_RADIUS
    )

    # Camera
    bpy.ops.object.camera_add(location=(4.6, -5.2, 3.2))
    cam = bpy.context.active_object
    cam.name = "camera_support_removed_fall"
    cam.data.lens = 45
    look_at(cam, (0.0, 0.0, 0.9))
    scene.camera = cam

    # Lights
    bpy.ops.object.light_add(type='AREA', location=(-2.6, -3.8, 5.8))
    area = bpy.context.active_object
    area.name = "key_area_light"
    area.data.energy = 800
    area.data.size = 4.8

    bpy.ops.object.light_add(type='POINT', location=(2.8, 2.5, 3.6))
    fill = bpy.context.active_object
    fill.name = "fill_point_light"
    fill.data.energy = 110

    return {
        "floor": floor,
        "backdrop": backdrop,
        "left_post": left_post,
        "right_post": right_post,
        "support_plate": support_plate,
        "ball": ball,
        "camera": cam,
    }


def ease_in_quad(t):
    t = max(0.0, min(1.0, float(t)))
    return t * t


def ease_in_out(t):
    t = max(0.0, min(1.0, float(t)))
    return 3.0 * t * t - 2.0 * t * t * t


def support_x_at_frame(frame):
    x0 = 0.0
    x1 = -1.75
    if frame <= SUPPORT_MOVE_START:
        return x0
    if frame >= SUPPORT_MOVE_END:
        return x1
    t = (frame - SUPPORT_MOVE_START) / float(SUPPORT_MOVE_END - SUPPORT_MOVE_START)
    return x0 + (x1 - x0) * ease_in_out(t)


def ball_z_at_frame(frame):
    if frame <= BALL_RELEASE_FRAME - 1:
        return BALL_ON_SUPPORT_Z
    if frame <= BALL_LAND_FRAME:
        t = (frame - BALL_RELEASE_FRAME) / float(BALL_LAND_FRAME - BALL_RELEASE_FRAME)
        return BALL_ON_SUPPORT_Z + (BALL_ON_FLOOR_Z - BALL_ON_SUPPORT_Z) * ease_in_quad(t)

    tau = (frame - BALL_LAND_FRAME) / float(max(1, FRAME_END - BALL_LAND_FRAME))
    bounce = 0.085 * math.exp(-6.0 * tau) * abs(math.sin(3.2 * math.pi * tau))
    return BALL_ON_FLOOR_Z + bounce


def ball_rotation_x(frame):
    if frame <= BALL_RELEASE_FRAME - 1:
        return 0.0
    return (frame - BALL_RELEASE_FRAME + 1) * 0.13


def set_state(scene, support_plate, ball, frame):
    scene.frame_set(frame)

    # Support plate movement
    sx = support_x_at_frame(frame)
    support_plate.location = (sx, 0.0, 0.84)
    support_plate.rotation_euler = (0.0, 0.0, 0.0)

    # Ball movement
    z = ball_z_at_frame(frame)
    rx = ball_rotation_x(frame)
    ball.location = (0.0, 0.0, z)
    ball.rotation_euler = (rx, 0.0, rx * 0.35)

    # Semantic state tags for recorder
    if frame <= BALL_RELEASE_FRAME - 1:
        ball["pb_state"] = "supported_before_release"
        ball["pb_contact_state"] = "supported"
        ball["pb_allowed_region"] = "on_support_plate"
    elif frame <= BALL_LAND_FRAME:
        ball["pb_state"] = "falling_after_support_removed"
        ball["pb_contact_state"] = "free_fall"
        ball["pb_allowed_region"] = "between_support_and_floor"
    else:
        ball["pb_state"] = "landed_on_floor"
        ball["pb_contact_state"] = "supported_by_floor"
        ball["pb_allowed_region"] = "on_floor"

    if frame < SUPPORT_MOVE_START:
        support_plate["pb_state"] = "supporting_ball_stationary"
        support_plate["pb_contact_state"] = "supporting"
    elif frame <= SUPPORT_MOVE_END:
        support_plate["pb_state"] = "retracting_support"
        support_plate["pb_contact_state"] = "moving_away"
    else:
        support_plate["pb_state"] = "retracted"
        support_plate["pb_contact_state"] = "not_supporting"

    support_plate.keyframe_insert(data_path="location", frame=frame)
    support_plate.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)


def animate_scene(scene, support_plate, ball):
    for frame in range(FRAME_START, FRAME_END + 1):
        set_state(scene, support_plate, ball, frame)

    # Blender 5.x Action API changed. We key every frame, so integer-frame renders
    # are already deterministic and do not require forcing interpolation mode.

    scene.frame_set(FRAME_START)


def render_still(scene, frame, path):
    scene.frame_set(frame)
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def render_animation(scene):
    scene.frame_set(FRAME_START)
    scene.render.filepath = os.path.join(FRAMES_DIR, f"{ITEM_ID}_frame_")
    bpy.ops.render.render(animation=True)


def write_task_json():
    task = {
        "item_id": ITEM_ID,
        "visual_regime": "simple_clean_3d",
        "fps": FPS,
        "inputs": {
            "text_prompt": (
                "A single orange ball starts on a support plate above the floor. "
                "While the support plate is still underneath the ball, the ball must remain supported "
                "and must not begin falling. The support plate then slides away. "
                "Only after the support is removed should the same ball fall downward and land on the floor. "
                "The ball must keep its identity, color, size, and count throughout the sequence."
            )
        },
        "scene_file": f"{ITEM_ID}_scene.blend",
        "reference_completion_frames_dir": f"{ITEM_ID}_reference_frames"
    }
    with open(TASK_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(task, f, indent=2, ensure_ascii=False)


def save_scene():
    bpy.ops.wm.save_as_mainfile(filepath=SCENE_FILE)


def main():
    ensure_dirs()
    clear_scene()
    objs = build_scene()
    scene = bpy.context.scene
    animate_scene(scene, objs["support_plate"], objs["ball"])

    render_still(scene, 1, INPUT_FRAME_01)
    render_still(scene, 70, OPTIONAL_FRAME_02)
    render_still(scene, 120, OPTIONAL_FRAME_02B)

    render_animation(scene)
    write_task_json()
    save_scene()

    print("=" * 80)
    print("DONE.")
    print("Item:", ITEM_ID)
    print("Output root:", OUT_DIR)
    print("Files:")
    print(" -", os.path.basename(INPUT_FRAME_01))
    print(" -", os.path.basename(OPTIONAL_FRAME_02))
    print(" -", os.path.basename(OPTIONAL_FRAME_02B))
    print(" -", os.path.basename(TASK_JSON_PATH))
    print(" -", os.path.basename(SCENE_FILE))
    print(" -", os.path.basename(FRAMES_DIR))
    print("=" * 80)


if __name__ == "__main__":
    main()
