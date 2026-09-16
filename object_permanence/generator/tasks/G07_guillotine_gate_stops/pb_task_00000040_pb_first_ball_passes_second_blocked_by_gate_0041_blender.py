# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

ITEM_ID = "PB_FIRST_BALL_PASSES_SECOND_BLOCKED_BY_GATE_0041"

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
OPTIONAL_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_gate_closed_frame_02.png")
OPTIONAL_FRAME_02B_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_second_ball_blocked_frame_02B.png")


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


def lerp(a, b, t):
    return a + (b - a) * t


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def make_mat(name, color, roughness=0.55):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (color[0], color[1], color[2], 1.0)

    try:
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            if "Base Color" in bsdf.inputs:
                bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = roughness
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


def add_cube(name, location, dimensions, material, role, color_name, is_dynamic=False, solid=True):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
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


def add_sphere(name, radius, location, material, color_name):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, "target", "dynamic_object", "sphere", color_name, True, solid=True, pb_radius=radius)
    return obj


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor_warm", (0.82, 0.80, 0.75), roughness=0.82)
    MATS["track"] = make_mat("mat_track_gray", (0.46, 0.46, 0.46), roughness=0.62)
    MATS["frame"] = make_mat("mat_guillotine_frame_light", (0.66, 0.67, 0.69), roughness=0.70)
    MATS["slot"] = make_mat("mat_dark_slot", (0.10, 0.10, 0.12), roughness=0.78)
    MATS["blade"] = make_mat("mat_dark_gate_blade", (0.20, 0.20, 0.22), roughness=0.74)
    MATS["orange"] = make_mat("mat_orange_ball", (1.0, 0.38, 0.06), roughness=0.30)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)


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


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0, 0, -0.05), (10.0, 5.0, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0, 2.48, 1.62), (10.2, 0.08, 3.24), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.6, -4.3, 5.5))
    key = bpy.context.object
    key.name = "large_softbox_light"
    key.data.energy = 960
    key.data.size = 6.2

    bpy.ops.object.light_add(type="POINT", location=(3.6, -3.0, 3.0))
    fill = bpy.context.object
    fill.name = "fill_light"
    fill.data.energy = 145

    return scene


def setup_camera(scene):
    # Rotated to the left-front side.
    # Car moves left -> right along X. This camera sees the left blocking face of the guillotine.
    bpy.ops.object.camera_add(location=(-2.55, -7.15, 2.05))
    cam = bpy.context.object
    cam.name = "camera_left_front_view_guillotine_gate"
    cam.data.lens = 32
    cam.data.dof.use_dof = False
    look_at(cam, (0.78, 0.0, 0.62))
    scene.camera = cam


def build_scene():
    scene = build_base_scene()
    setup_camera(scene)

    gate_x = 0.92

    add_cube(
        "straight_gate_track",
        (0.0, 0.0, 0.06),
        (9.6, 0.34, 0.08),
        MATS["track"],
        "gate_track",
        "gray",
    )

    # Guillotine frame. Posts are on front/back sides; the blade slides vertically between them.
    add_cube(
        "guillotine_near_side_post",
        (gate_x, -0.50, 1.05),
        (0.18, 0.13, 2.10),
        MATS["frame"],
        "guillotine_side_post",
        "light_gray",
        is_dynamic=False,
        solid=True,
    )
    add_cube(
        "guillotine_far_side_post",
        (gate_x, 0.50, 1.05),
        (0.18, 0.13, 2.10),
        MATS["frame"],
        "guillotine_side_post",
        "light_gray",
        is_dynamic=False,
        solid=True,
    )
    add_cube(
        "guillotine_top_crossbeam",
        (gate_x, 0.0, 2.12),
        (0.22, 1.15, 0.16),
        MATS["frame"],
        "guillotine_top_crossbeam",
        "light_gray",
        is_dynamic=False,
        solid=True,
    )

    # Dark vertical slots make the structure read as a guided sliding gate.
    add_cube(
        "guillotine_near_inner_guide_slot",
        (gate_x - 0.012, -0.39, 0.96),
        (0.055, 0.055, 1.72),
        MATS["slot"],
        "guillotine_guide_slot",
        "dark_gray",
        is_dynamic=False,
        solid=True,
    )
    add_cube(
        "guillotine_far_inner_guide_slot",
        (gate_x - 0.012, 0.39, 0.96),
        (0.055, 0.055, 1.72),
        MATS["slot"],
        "guillotine_guide_slot",
        "dark_gray",
        is_dynamic=False,
        solid=True,
    )

    blade = add_cube(
        "guillotine_sliding_gate_blade",
        (gate_x, 0.0, 1.58),
        (0.16, 0.76, 0.92),
        MATS["blade"],
        "guillotine_sliding_gate_blade",
        "dark_gray",
        is_dynamic=True,
        solid=True,
    )
    blade["pb_slides_vertically_between_posts"] = True
    blade["pb_drops_only_after_first_ball_clears"] = True

    first = add_sphere("first_orange_ball", 0.14, (-1.80, 0.0, 0.22), MATS["orange"], "orange")
    second = add_sphere("second_orange_ball", 0.14, (-4.20, 0.0, 0.22), MATS["orange"], "orange")
    first["pb_order"] = 1
    second["pb_order"] = 2

    return {
        "scene": scene,
        "gate": blade,
        "first": first,
        "second": second,
    }


# --- G07 second-ball elastic rebound at closed gate (FLAT ground) ---
# On flat ground there is no restoring force, so after bouncing off the gate the
# ball recoils backward and comes to REST at the rebound position (away from the
# gate). The recoil is a decelerating ease-out: fast right after impact, slowing
# to a stop. Ball radius 0.14; REBOUND_BACK ~ 0.85 * radius.
SECOND_REBOUND_BACK = 0.12
SECOND_CONTACT_FRAME = 90
SECOND_REBOUND_FRAME = 102

# The first ball keeps its horizontal momentum after clearing the gate, but the
# track no longer supports it once its centre passes the right edge. It then
# follows a downward ballistic arc instead of continuing at a fixed height.
FIRST_START_X = -1.80
FIRST_SPEED_X = 0.074
TRACK_RIGHT_X = 4.80
FIRST_FALL_START_FRAME = int(math.ceil(
    FRAME_START + (TRACK_RIGHT_X - FIRST_START_X) / FIRST_SPEED_X
))
FIRST_FALL_ACCEL = 0.006

def ease_out01(t):
    # decelerating: fast at start, slowing to a stop (derivative -> 0 at t=1).
    t = clamp01(t)
    return 1.0 - (1.0 - t) * (1.0 - t)

def second_ball_x_at_frame(frame, contact_x, raw_x_at):
    """approach -> contact gate -> recoil backward and come to rest (no settle forward)."""
    if frame <= SECOND_CONTACT_FRAME:
        return min(raw_x_at(frame), contact_x)
    rebound_x = contact_x - SECOND_REBOUND_BACK
    if frame <= SECOND_REBOUND_FRAME:
        t = (frame - SECOND_CONTACT_FRAME) / max(1, (SECOND_REBOUND_FRAME - SECOND_CONTACT_FRAME))
        return lerp(contact_x, rebound_x, ease_out01(t))
    return rebound_x


def animate_scene(objs):
    scene = objs["scene"]
    gate = objs["gate"]
    first = objs["first"]
    second = objs["second"]

    gate_x = 0.92
    gate_half_x = 0.08
    ball_r = 0.14

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        # Blade remains raised while first ball passes.
        # It only slides down after the first ball is long gone.
        if frame <= 55:
            gate_z = 1.58
            gate_state = "open_blade_raised_between_posts"
        elif frame <= 78:
            gate_z = lerp(1.58, 0.55, smooth01((frame - 55) / 23.0))
            gate_state = "sliding_down_after_first_ball_cleared"
        else:
            gate_z = 0.55
            gate_state = "closed_blocking_track"

        gate.location = (gate_x, 0.0, gate_z)
        gate.keyframe_insert(data_path="location", frame=frame)
        gate["pb_state"] = gate_state

        # First ball clears the gate before blade begins dropping.
        first_x = FIRST_START_X + FIRST_SPEED_X * (frame - FRAME_START)
        if frame < FIRST_FALL_START_FRAME:
            first_z = 0.22
        else:
            fall_dt = frame - FIRST_FALL_START_FRAME
            first_z = 0.22 - FIRST_FALL_ACCEL * fall_dt * fall_dt
        first.location = (first_x, 0.0, first_z)
        first.rotation_euler = (0.0, -0.12 * frame, 0.0)
        first.keyframe_insert(data_path="location", frame=frame)
        first.keyframe_insert(data_path="rotation_euler", frame=frame)

        first_rear_x = first_x - ball_r
        gate_right_face = gate_x + gate_half_x
        if frame >= FIRST_FALL_START_FRAME:
            first["pb_state"] = "falling_after_leaving_track"
        else:
            first["pb_state"] = "fully_cleared_gate_before_blade_drops" if first_rear_x > gate_right_face else "passing_open_guillotine_gate"
        first["pb_gate_does_not_hit_first_ball"] = True
        first["pb_falls_after_leaving_track"] = True
        first["pb_track_exit_frame"] = FIRST_FALL_START_FRAME

        # Second ball arrives after gate is closed and stops at the left face,
        # with a slight elastic rebound on contact (recoil then settle).
        stop_x = gate_x - gate_half_x - ball_r - 0.012
        second_raw_x = -4.20 + 0.055 * (frame - 1)
        second_x = second_ball_x_at_frame(
            frame, stop_x, lambda fr: -4.20 + 0.055 * (fr - 1)
        )

        second.location = (second_x, 0.0, 0.22)
        second.rotation_euler = (0.0, -0.10 * frame, 0.0)
        second.keyframe_insert(data_path="location", frame=frame)
        second.keyframe_insert(data_path="rotation_euler", frame=frame)

        if second_raw_x >= stop_x and frame >= 78:
            second["pb_state"] = "stopped_at_left_face_of_closed_guillotine_gate"
        else:
            second["pb_state"] = "approaching_after_first_ball"
        second["pb_must_not_pass_closed_gate"] = True
        second["pb_no_gate_penetration"] = True

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
            "text_prompt": (
                "Two orange balls move one after the other from left to right on the same gray straight track. "
                "A guillotine-style gate with two side posts and a top crossbeam is open at first, with the gate blade raised above the track. "
                "The first ball completely passes through the gate while it is open. "
                "Only after the first ball has fully cleared the gate, the blade slides down along the side posts and closes. "
                "The second ball arrives later and stops at the closed gate. "
                "The second ball must not pass through the closed gate, and the gate must not hit or clip through the first ball."
            ),
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
    objs = build_scene()
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
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
