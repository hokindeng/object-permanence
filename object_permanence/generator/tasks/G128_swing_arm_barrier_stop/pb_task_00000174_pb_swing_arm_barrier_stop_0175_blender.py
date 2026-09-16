# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_SWING_ARM_BARRIER_STOP_0175",
  "kind": "swing_arm_barrier_stop",
  "prompt": "A horizontal parking-gate barrier arm, hinged at one end on a post, is down across a flat track, blocking it. A ball rolls up to the closed arm and is stopped -- it decelerates to rest against the arm, unable to pass. The arm stays down the whole time (the blocked case): the ball cannot get through."
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


def lerp(a, b, t):
    return a + (b - a) * t


def smooth01(t):
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


def make_mat(name, color, roughness=0.55, metallic=0.0, alpha=1.0):
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
    MATS["dark"] = make_mat("mat_dark", (0.18, 0.20, 0.24), roughness=0.55)
    MATS["screen"] = make_mat("mat_screen", (0.46, 0.48, 0.53), roughness=0.88)
    MATS["stripe"] = make_mat("mat_stripe", (0.86, 0.30, 0.14), roughness=0.60)

    MATS["red"] = make_mat("mat_red", (0.92, 0.18, 0.18), roughness=0.28)
    MATS["blue"] = make_mat("mat_blue", (0.16, 0.36, 0.95), roughness=0.28)
    MATS["yellow"] = make_mat("mat_yellow", (0.98, 0.78, 0.15), roughness=0.28)
    MATS["orange"] = make_mat("mat_orange", (0.97, 0.45, 0.10), roughness=0.28)
    MATS["pink"] = make_mat("mat_pink", (0.95, 0.35, 0.62), roughness=0.28)
    MATS["teal"] = make_mat("mat_teal", (0.10, 0.72, 0.62), roughness=0.28)


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


def add_ball(name, radius, location, material, color_name, role="moving_ball"):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=48, ring_count=24)
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


def add_vertical_cylinder(name, location, radius, height, material, role, color_name):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=height, vertices=32, location=location)
    obj = bpy.context.object
    obj.name = name

    if material is not None:
        obj.data.materials.append(material)

    tag(obj, name, role, "static_solid", "cylinder", color_name, False, solid=True)
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
        scene.view_settings.view_transform = "Filmic"
        scene.view_settings.look = "Medium High Contrast"
    except Exception:
        pass


def setup_base(camera_loc, target, ortho_scale):
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (11.0, 7.0, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.05, 1.65), (11.0, 0.08, 3.3), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-2.8, -4.5, 5.8))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 950
    key.data.size = 5.5

    bpy.ops.object.light_add(type="POINT", location=(3.0, 1.8, 3.3))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 120

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
# 00000174  swing_arm_barrier_stop
#
# A parking-gate barrier ARM (apparatus -> gray), hinged at one end on a vertical
# post, is DOWN (horizontal, across the track) the whole time. A BALL (target ->
# vivid) rolls up to the closed arm at constant speed until it actually CONTACTS
# the arm's near surface (the warning-stripe face, the first surface in its path),
# then a small damped rebound (restitution 0.25) eases it to rest just in front
# of the arm. It cannot pass. No penetration; the arm never lifts or moves, so
# the static arm never intersects the ball either.
# =============================================================================

BALL_R = 0.24
FLOOR_Z = BALL_R                 # ball-centre height rolling on the floor (top z = 0)
BALL_START_X = -3.0

BLOCK_X = 0.6                    # x of the down barrier arm across the track
ARM_THICK_X = 0.10              # arm thickness along X
ARM_HEIGHT_Z = 0.16             # arm cross-section height
ARM_Z = 0.28                    # arm centre height (intercepts the rolling ball)
ARM_POST_Y = 0.85               # post (hinge) at the +Y side of the track
ARM_FREE_Y = -0.75             # arm free end reaches the -Y side
ARM_NEAR_FACE_X = BLOCK_X - ARM_THICK_X / 2.0   # 0.55 -- the arm body's -X face

# The red warning stripe sits half-proud of the arm's near face, so ITS front
# face (x = 0.54) is the first solid surface the rolling ball meets.
STRIPE_THICK_X = 0.02
STRIPE_FRONT_X = ARM_NEAR_FACE_X - STRIPE_THICK_X / 2.0     # 0.54
CONTACT_FACE_X = STRIPE_FRONT_X                             # first surface in the path
CONTACT_X = CONTACT_FACE_X - BALL_R                         # 0.30 ball centre at contact

# contact kinematics: constant speed until actual contact (zero gap, zero
# penetration at the contact frame), then a short damped impact response:
# reversed exit speed (restitution) with uniform decel to rest near the arm.
BALL_V = 0.06                                # units/frame, constant approach speed
BALL_T0 = 1                                  # hold frame before motion starts
F_CONTACT = BALL_T0 + (CONTACT_X - BALL_START_X) / BALL_V   # = 56.0 (exact frame)

RESTITUTION = 0.25                           # damped impact: exit/impact speed ratio
REBOUND_V = BALL_V * RESTITUTION             # 0.015 units/frame, direction reversed
REBOUND_T = 16                               # frames of uniform decel until rest
REBOUND_DIST = REBOUND_V * REBOUND_T / 2.0   # 0.12 total rollback
REST_X = CONTACT_X - REBOUND_DIST            # 0.18 -- final resting centre x
F_REST = F_CONTACT + REBOUND_T               # 72.0


def build_swing_arm_barrier_stop():
    scene = setup_base(
        camera_loc=(-3.4, -7.7, 4.3),
        target=(0.3, 0.0, 0.35),
        ortho_scale=7.6,
    )

    # ----- Flat track the ball rolls along (apparatus -> gray). Flush with floor. -----
    add_cube(
        "straight_roll_track",
        (0.0, 0.0, 0.005),
        (9.0, 1.1, 0.02),
        MATS["screen"], "roll_track", "gray",
    )

    # ----- Barrier post (apparatus -> gray): the vertical hinge post at +Y side. -----
    post_h = ARM_Z + 0.35
    add_vertical_cylinder(
        "barrier_hinge_post",
        (BLOCK_X, ARM_POST_Y, post_h / 2.0),
        0.06, post_h, MATS["dark"], "barrier_post", "dark_gray",
    )

    # ----- Barrier arm pivot (empty) at the post top, at arm height. -----
    piv = bpy.data.objects.new("barrier_arm_pivot", None)
    piv.location = (BLOCK_X, ARM_POST_Y, ARM_Z)
    bpy.context.scene.collection.objects.link(piv)
    piv["pb_object_id"] = "barrier_arm_pivot"
    piv["pb_role"] = "barrier_gate_hinge"
    piv["pb_is_dynamic"] = True

    # ----- Horizontal barrier ARM (apparatus -> gray). Spans across the track in Y. --
    # DOWN = horizontal (blocking). Parented to the pivot; the pivot stays at angle 0
    # (fully down) the whole time -> the closed arm blocks the ball.
    arm_len_y = ARM_POST_Y - ARM_FREE_Y            # 1.60
    arm_cy = (ARM_POST_Y + ARM_FREE_Y) / 2.0       # 0.05
    arm = add_cube(
        "swing_barrier_arm",
        (BLOCK_X, arm_cy, ARM_Z),
        (ARM_THICK_X, arm_len_y, ARM_HEIGHT_Z),
        MATS["gray"], "barrier_arm_gate", "gray",
        is_dynamic=False,
    )
    arm.parent = piv
    arm.matrix_parent_inverse = piv.matrix_world.inverted()
    arm["pb_stays_down_blocking_track"] = True

    # A red warning stripe strip on the arm's near (-X) face (apparatus -> gray).
    # Half-sunk into the face so its own front plane is CONTACT_FACE_X (0.54):
    # this stripe face is the exact surface the ball's contact math uses.
    stripe = add_cube(
        "barrier_arm_stripe",
        (STRIPE_FRONT_X + STRIPE_THICK_X / 2.0, arm_cy, ARM_Z),
        (STRIPE_THICK_X, arm_len_y * 0.96, ARM_HEIGHT_Z * 0.7),
        MATS["stripe"], "barrier_arm_gate_stripe", "red",
        is_dynamic=False,
    )
    stripe.parent = piv
    stripe.matrix_parent_inverse = piv.matrix_world.inverted()

    # ----- The BALL: target (vivid). Rolls in +X toward the down arm and is stopped. --
    ball = add_ball(
        "rolling_ball", BALL_R, (BALL_START_X, arm_cy, FLOOR_Z),
        MATS["teal"], "teal",
    )
    ball["pb_path"] = "rolls_up_to_down_arm_and_is_halted_resting_against_it"

    return scene, {
        "ball": ball,
        "piv": piv,
        "arm": arm,
        "ball_y": arm_cy,
    }


def animate_swing_arm_barrier_stop(scene, meta):
    ball = meta["ball"]
    piv = meta["piv"]
    ball_y = meta["ball_y"]

    def ball_x(frame):
        if frame <= BALL_T0:
            return BALL_START_X
        if frame <= F_CONTACT:
            # constant speed all the way to actual contact -- no anticipatory braking
            return BALL_START_X + BALL_V * (frame - BALL_T0)
        if frame <= F_REST:
            # damped rebound: leaves contact at REBOUND_V in -X, uniform decel to rest
            tau = frame - F_CONTACT
            return CONTACT_X - REBOUND_V * tau + (REBOUND_V / (2.0 * REBOUND_T)) * tau * tau
        return REST_X

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        # The barrier arm stays DOWN (angle 0 = horizontal, closed) the whole time.
        piv.rotation_euler = (0.0, 0.0, 0.0)
        piv.keyframe_insert(data_path="rotation_euler", frame=frame)

        # Constant speed until the ball actually CONTACTS the arm's near surface
        # (frame 56: centre x = 0.30, leading edge exactly at the stripe face
        # x = 0.54, zero penetration), then a small damped rebound (restitution
        # 0.25) eases it to rest 0.12 in front of the arm. Rotation follows
        # rolling contact in both directions and stops with the ball.
        xb = ball_x(frame)
        ball.location = (xb, ball_y, FLOOR_Z)
        ball.rotation_euler = (0.0, -(xb - BALL_START_X) / BALL_R, 0.0)
        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)

        if frame < F_CONTACT:
            ball["pb_state"] = "rolling_toward_down_barrier_arm"
        elif frame < F_REST:
            ball["pb_state"] = "impact_and_damped_rebound_off_closed_arm"
        else:
            ball["pb_state"] = "halted_at_rest_blocked_by_down_barrier_arm"
        ball["pb_must_not_pass_closed_arm"] = True

    scene.frame_set(FRAME_START)


# =============================================================================
# Dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["kind"]

    if kind == "swing_arm_barrier_stop":
        return build_swing_arm_barrier_stop()

    raise RuntimeError("Unknown kind: " + str(kind))


def animate_scene_by_kind(scene, meta):
    kind = CASE["kind"]

    if kind == "swing_arm_barrier_stop":
        return animate_swing_arm_barrier_stop(scene, meta)

    raise RuntimeError("Unknown kind: " + str(kind))


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
    print("kind:", CASE["kind"])
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
