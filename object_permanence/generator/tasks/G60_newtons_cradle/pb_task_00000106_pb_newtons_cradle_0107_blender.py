# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_NEWTONS_CRADLE_0107",
  "scene_kind": "newtons_cradle",
  "prompt": "Five identical metal balls hang in a row as a Newton's cradle, just touching. The leftmost ball is raised and released; it strikes the row and the rightmost ball swings out by an equal amount while the middle balls stay still. Momentum transfers through the stationary balls; the ball count is conserved."
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


def add_cylinder_between(name, p1, p2, radius, material, role="static_solid", color_name="gray", is_dynamic=False, solid=True, vertices=32):
    p1 = Vector(p1)
    p2 = Vector(p2)
    mid = (p1 + p2) * 0.5
    direction = p2 - p1
    length = direction.length
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=length, location=mid)
    obj = bpy.context.object
    obj.name = name
    if length > 1e-8:
        obj.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    if material is not None:
        obj.data.materials.append(material)
    tag(
        obj,
        name,
        role,
        "dynamic_object" if is_dynamic else ("static_solid" if solid else "non_solid_marker"),
        "cylinder",
        color_name,
        is_dynamic,
        solid=solid,
    )
    return obj


def set_cylinder_between(obj, p1, p2):
    p1 = Vector(p1)
    p2 = Vector(p2)
    mid = (p1 + p2) * 0.5
    direction = p2 - p1
    length = direction.length
    obj.location = mid
    if length > 1e-8:
        obj.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
        obj.dimensions = (obj.dimensions.x, obj.dimensions.y, length)
        try:
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
            obj.select_set(False)
        except Exception:
            pass


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
    MATS["metal"] = make_mat("mat_metal_ball", (0.62, 0.63, 0.66), roughness=0.18, metallic=1.0)
    MATS["frame"] = make_mat("mat_metal_frame", (0.30, 0.31, 0.34), roughness=0.40, metallic=0.85)
    MATS["black"] = make_mat("mat_black", (0.02, 0.02, 0.025), roughness=0.75)
    MATS["rope"] = make_mat("mat_rope_dark", (0.05, 0.05, 0.055), roughness=0.65)
    MATS["edge"] = make_mat("mat_light_edge", (0.62, 0.63, 0.64), roughness=0.68)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube(
        "large_floor_base",
        (0.0, 0.0, -0.05),
        (9.8, 4.8, 0.10),
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
# Newton's cradle scene
# ============================================================

NUM_BALLS = 5
BALL_RADIUS = 0.22
BAR_Z = 2.18          # support bar height (top pivot height)
STRING_LENGTH = 1.20  # pendulum arc length L (pivot -> ball center)
SWING_ANGLE = math.radians(42.0)  # amplitude of end-ball swing
IMPACT_FRAME = 30     # left ball reaches the row (theta back to 0) at ~frame 30


def build_newtons_cradle_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(0.0, -9.2, 1.45), target=(0.0, 0.0, 1.15), lens=34)

    # Balls just touch -> centers spaced by one diameter.
    spacing = 2.0 * BALL_RADIUS
    centers_x = [(i - (NUM_BALLS - 1) / 2.0) * spacing for i in range(NUM_BALLS)]

    # Each ball hangs from a fixed pivot directly above its rest position, on the bar.
    pivots = [(cx, 0.0, BAR_Z) for cx in centers_x]
    rest_z = BAR_Z - STRING_LENGTH  # ball center z at theta = 0

    # Size the frame for the full end-ball swing envelope, not just the resting row.
    # Otherwise the raised ball's strings cross the support posts near peak swing.
    max_swing_x = abs(centers_x[0]) + STRING_LENGTH * math.sin(SWING_ANGLE)
    half_span = max_swing_x + BALL_RADIUS + 0.30
    bar_len = 2.0 * half_span

    # Top horizontal support bar.
    add_cube(
        "top_support_bar",
        (0.0, 0.0, BAR_Z + 0.06),
        (bar_len, 0.14, 0.12),
        material=MATS["frame"],
        role="support_bar",
        color_name="dark_gray",
    )

    # Two vertical posts at the ends of the bar.
    post_h = BAR_Z + 0.12
    for side, sx in (("left", -half_span + 0.06), ("right", half_span - 0.06)):
        post = add_cube(
            f"{side}_support_post",
            (sx, 0.0, post_h / 2.0),
            (0.12, 0.14, post_h),
            material=MATS["frame"],
            role="support_post",
            color_name="dark_gray",
        )
        post["pb_outside_full_swing_envelope"] = True

    # Bifilar V string anchors: two points on the bar offset in +/- Y from the pivot x.
    string_y = 0.18  # half the bifilar separation along Y

    balls = []
    strings = []  # list of (ball_index, cyl_obj, anchor_local_y)
    for i in range(NUM_BALLS):
        pivot = pivots[i]
        bob_pos = (
            pivot[0] + STRING_LENGTH * math.sin(0.0),
            0.0,
            pivot[2] - STRING_LENGTH * math.cos(0.0),
        )
        ball = add_sphere(
            f"metal_ball_{i}",
            BALL_RADIUS,
            bob_pos,
            MATS["metal"],
            "metallic_gray",
            role="target",
        )
        ball["pb_motion_constraint"] = "fixed_length_pendulum_arc"
        ball["pb_ball_index"] = i
        ball["pb_count_conserved"] = True
        balls.append(ball)

        for sgn in (-1.0, 1.0):
            anchor = (pivot[0], sgn * string_y, pivot[2])
            cyl = add_cylinder_between(
                f"string_{i}_{'pos' if sgn > 0 else 'neg'}",
                anchor,
                bob_pos,
                0.012,
                MATS["rope"],
                role="string",
                color_name="dark_gray",
                is_dynamic=True,
                solid=True,
                vertices=12,
            )
            cyl["pb_string_length_constant"] = True
            strings.append((i, cyl, sgn * string_y))

    return {
        "scene": scene,
        "kind": "newtons_cradle",
        "pivots": pivots,
        "length": STRING_LENGTH,
        "swing_angle": SWING_ANGLE,
        "rest_z": rest_z,
        "balls": balls,
        "strings": strings,
        "string_y": string_y,
    }


# ============================================================
# Animation
# ============================================================

# Frames at which an end ball strikes the row and momentum jolts through the
# middle balls. (Phase A impact ~30; right ball returns ~57; left ball ~88.)
MID_IMPACT_FRAMES = (IMPACT_FRAME, 57, 88)
# Small subtle wobble of the three middle balls. The end balls swing ~42 deg;
# the middle balls only barely jiggle (a couple of degrees) at each impact and
# damp back to rest within a few frames.
MID_WOBBLE_AMP = math.radians(5.0)   # nominal amplitude; realized peak ~3.0 deg
MID_WOBBLE_OMEGA = 1.15              # angular freq of the damped wobble (rad/frame)
MID_WOBBLE_DECAY = 0.42              # exponential damping (per frame)
MID_WOBBLE_WINDOW = 12               # frames the wobble is active after an impact


def _mid_wobble(frame, ball_index):
    """Small damped oscillation for a middle ball at the given frame.

    Returns a tiny theta (radians) that is non-zero only in a short window
    after each impact and decays back toward 0. The innermost balls (1, 3)
    that are directly struck wobble a hair more than the centre ball (2).
    """
    best = 0.0
    for k, imp in enumerate(MID_IMPACT_FRAMES):
        df = frame - imp
        if df < 0 or df > MID_WOBBLE_WINDOW:
            continue
        # The centre ball (index 2) wobbles slightly less than the inner
        # balls (1, 3); never let the middle wobble approach the end swing.
        amp = MID_WOBBLE_AMP * (0.7 if ball_index == 2 else 1.0)
        # Direction of the strike: impact k=0 (left ball in), k>0 alternate.
        # Even impacts come from the LEFT (push toward +X), odd from the RIGHT.
        push = 1.0 if (k % 2 == 0) else -1.0
        val = (
            push
            * amp
            * math.sin(MID_WOBBLE_OMEGA * df)
            * math.exp(-MID_WOBBLE_DECAY * df)
        )
        if abs(val) > abs(best):
            best = val
    return best


def _apply_mid_wobble(thetas, frame):
    """Overlay the subtle middle-ball jiggle onto theta = 0 for balls 1,2,3."""
    for i in range(1, NUM_BALLS - 1):
        thetas[i] = _mid_wobble(frame, i)
    return thetas


def _cradle_angles(frame):
    """Return a list of theta (radians) for the 5 balls at the given frame.

    Sign convention: positive theta swings a ball toward +X (to the right).
    Ball 0 (LEFT) and ball 4 (RIGHT) carry essentially all the motion (full
    +/-amplitude pendulum swings). The middle three balls (1,2,3) only barely
    move: a small damped wobble triggered at each impact (see _mid_wobble),
    so momentum visibly transfers THROUGH them while they stay nearly still.

    Phases over 120 frames:
      A) frame 1..IMPACT : LEFT ball swings DOWN from its raised position
                           (negative theta) to impact (theta = 0) at ~frame 30.
      B) IMPACT..~57     : RIGHT ball swings OUT (positive theta) and back to 0.
      C) ~57..~88        : LEFT  ball swings OUT (negative theta) and back to 0.
      D) ~88..120        : RIGHT ball swings OUT (positive theta) and back to 0.
    """
    A = SWING_ANGLE
    thetas = [0.0] * NUM_BALLS
    left = 0
    right = NUM_BALLS - 1

    f = frame

    # Middle balls (1,2,3) get a small damped wobble overlaid at each impact.
    _apply_mid_wobble(thetas, f)

    # Phase A: left ball released from raised (-A) and swings down to impact.
    if f <= IMPACT_FRAME:
        t = clamp01((f - FRAME_START) / float(IMPACT_FRAME - FRAME_START))
        # Quarter cosine: starts at -A (raised left), ends at 0 (vertical/impact),
        # speeding up as it falls.
        thetas[left] = -A * math.cos(0.5 * math.pi * t)
        return thetas

    # Phase B: right ball swings out and back (one half-cosine bump, positive).
    b_start = IMPACT_FRAME
    b_end = 57
    if f <= b_end:
        t = clamp01((f - b_start) / float(b_end - b_start))
        thetas[right] = A * math.sin(math.pi * t)
        return thetas

    # Phase C: left ball swings out and back (negative bump).
    c_start = b_end
    c_end = 88
    if f <= c_end:
        t = clamp01((f - c_start) / float(c_end - c_start))
        thetas[left] = -A * math.sin(math.pi * t)
        return thetas

    # Phase D: right ball swings out and back (positive bump).
    d_start = c_end
    d_end = FRAME_END
    t = clamp01((f - d_start) / float(d_end - d_start))
    thetas[right] = A * math.sin(math.pi * t)
    return thetas


def animate_newtons_cradle(objs, frame):
    balls = objs["balls"]
    strings = objs["strings"]
    pivots = objs["pivots"]
    L = objs["length"]
    string_y = objs["string_y"]

    thetas = _cradle_angles(frame)

    ball_pos = []
    for i, ball in enumerate(balls):
        pivot = pivots[i]
        theta = thetas[i]
        pos = Vector((
            pivot[0] + L * math.sin(theta),
            0.0,
            pivot[2] - L * math.cos(theta),
        ))
        ball.location = pos
        ball.keyframe_insert(data_path="location", frame=frame)
        ball_pos.append(pos)

        if i == 0:
            role = "left_end_ball"
        elif i == NUM_BALLS - 1:
            role = "right_end_ball"
        else:
            role = "middle_stationary_ball"
        ball["pb_state"] = role
        ball["pb_is_moving"] = bool(abs(theta) > 1e-4)
        ball["pb_pendulum_length_constant"] = True

    # Strings follow their balls: redraw each string between its bar anchor
    # (offset in Y) and the current ball center every frame.
    for (i, cyl, anchor_y) in strings:
        pivot = pivots[i]
        anchor = (pivot[0], anchor_y, pivot[2])
        set_cylinder_between(cyl, anchor, ball_pos[i])
        cyl.keyframe_insert(data_path="location", frame=frame)
        cyl.keyframe_insert(data_path="rotation_euler", frame=frame)
        cyl["pb_state"] = "string_follows_ball"


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if kind == "newtons_cradle":
            animate_newtons_cradle(objs, frame)
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

    if kind == "newtons_cradle":
        return build_newtons_cradle_scene()

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
