# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_GLANCING_OBLIQUE_COLLISION_0121",
  "scene_kind": "glancing_oblique_collision",
  "prompt": "A moving ball rolls across a flat surface and strikes a stationary ball off-centre (a glancing hit). After the collision the two balls separate along different diagonal directions - the struck ball moves off to one side and the incoming ball is deflected to the other - consistent with an oblique momentum transfer. Both balls remain, and neither is suspended."
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
    MATS["metal"] = make_mat("mat_metal_ball", (0.62, 0.63, 0.66), roughness=0.18, metallic=1.0)
    MATS["frame"] = make_mat("mat_metal_frame", (0.30, 0.31, 0.34), roughness=0.40, metallic=0.85)
    MATS["black"] = make_mat("mat_black", (0.02, 0.02, 0.025), roughness=0.75)
    MATS["edge"] = make_mat("mat_light_edge", (0.62, 0.63, 0.64), roughness=0.68)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)
    # Two distinct ball colours so the two departing balls are clearly told apart.
    MATS["ball_incoming"] = make_mat("mat_ball_incoming", (0.80, 0.24, 0.20), roughness=0.34, metallic=0.10)
    MATS["ball_target"] = make_mat("mat_ball_target", (0.20, 0.42, 0.82), roughness=0.34, metallic=0.10)


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube(
        "large_floor_base",
        (0.0, 0.0, -0.05),
        (9.8, 9.8, 0.10),
        material=MATS["floor"],
        role="ground",
        color_name="warm_beige",
    )

    add_cube(
        "rear_backdrop_panel",
        (0.0, 3.6, 1.60),
        (10.0, 0.08, 3.20),
        material=MATS["backdrop"],
        role="background",
        color_name="off_white",
    )

    bpy.ops.object.light_add(type="AREA", location=(-3.8, -4.4, 6.5))
    key = bpy.context.object
    key.name = "large_softbox_light"
    key.data.energy = 1050
    key.data.size = 6.0

    bpy.ops.object.light_add(type="POINT", location=(3.7, -2.8, 4.2))
    fill = bpy.context.object
    fill.data.energy = 165
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
# Glancing oblique collision scene
# ============================================================
#
# Layout (top-down, X = right, Y = into the scene, Z = up):
#   The incoming ball starts far in -X and travels in +X along a line that is
#   offset in +Y from the target's centre by the impact parameter `b`. Because
#   the shot is off-centre, at contact the two centres are separated by 2R at
#   an angle to the travel direction. The struck (target) ball departs ALONG
#   the line of centres; the incoming ball departs along the complementary
#   direction. For equal masses in an elastic glancing collision the two exit
#   paths are (close to) perpendicular. Both balls roll to rest via friction.

BALL_RADIUS = 0.42
FLOOR_Z = 0.0
BALL_Z = FLOOR_Z + BALL_RADIUS          # ball centre rests one radius above floor

# Target ball sits stationary near the centre of the table.
TARGET_START = Vector((0.6, 0.10, BALL_Z))

# Impact parameter: how far off-centre the incoming ball's line is (in +Y).
# Fraction of the contact distance 2R; sin(alpha)=b/2R sets the deflection.
IMPACT_PARAM = 0.62 * (2.0 * BALL_RADIUS)   # b

# The incoming ball travels along +X at constant Y = TARGET.y + b, arriving so
# that centres are exactly 2R apart at the contact frame.
INCOMING_Y = TARGET_START.y + IMPACT_PARAM

CONTACT_FRAME = 40                      # frame at which the balls just touch

# Speed of the incoming ball before impact (Blender units per frame).
INCOMING_SPEED = 0.115


def _contact_geometry():
    """Compute the contact point and the two post-collision unit directions.

    At contact the incoming ball centre is at (cx, INCOMING_Y) with the target
    centre fixed at TARGET_START. The centre-to-centre distance is exactly 2R.
    The line of centres (from incoming -> target) is the direction the TARGET
    departs along. The incoming ball is deflected along the complementary
    (perpendicular, for equal masses) direction.
    """
    R = BALL_RADIUS
    contact_dist = 2.0 * R
    dy = INCOMING_Y - TARGET_START.y        # = IMPACT_PARAM (>0)
    # Guard against numeric edge: |dy| must be < contact_dist.
    dy = max(-0.999 * contact_dist, min(0.999 * contact_dist, dy))
    dx = math.sqrt(max(0.0, contact_dist * contact_dist - dy * dy))

    # Incoming ball centre at contact is to the -X side of the target by dx.
    incoming_contact = Vector((TARGET_START.x - dx, INCOMING_Y, BALL_Z))

    # Line of centres, pointing from incoming ball to target ball -> target
    # departs along this. (Points toward +X and -Y here.)
    line_of_centres = (TARGET_START - incoming_contact)
    line_of_centres.z = 0.0
    n_hat = line_of_centres.normalized()    # target exit direction

    # Incoming velocity direction before impact is +X.
    v_in = Vector((1.0, 0.0, 0.0))
    # Component removed from incoming ball is along n_hat; what remains is the
    # tangential part -> incoming ball's post-collision direction.
    v_tan = v_in - v_in.dot(n_hat) * n_hat
    if v_tan.length < 1e-6:
        # Head-on degenerate guard (should not happen with b>0): pick +Y.
        t_hat = Vector((0.0, 1.0, 0.0))
    else:
        t_hat = v_tan.normalized()          # incoming exit direction

    return incoming_contact, n_hat, t_hat


def build_glancing_oblique_collision_scene():
    scene = build_base_scene()
    # Elevated, slightly top-down-ish camera so the 2D angular split of the two
    # departing paths reads clearly on the flat surface.
    setup_camera(scene, location=(0.2, -7.6, 6.4), target=(0.9, 0.35, BALL_Z), lens=40)

    incoming_contact, n_hat, t_hat = _contact_geometry()

    # Incoming ball starts far in -X, at INCOMING_Y, so that at CONTACT_FRAME
    # (moving +X at INCOMING_SPEED) it reaches incoming_contact.
    travel = INCOMING_SPEED * (CONTACT_FRAME - FRAME_START)
    incoming_start = Vector((incoming_contact.x - travel, INCOMING_Y, BALL_Z))

    incoming = add_sphere(
        "incoming_ball",
        BALL_RADIUS,
        incoming_start,
        MATS["ball_incoming"],
        "red",
        role="projectile",
    )
    incoming["pb_ball_role"] = "incoming"
    incoming["pb_motion_constraint"] = "rolls_on_surface"
    incoming["pb_count_conserved"] = True

    target = add_sphere(
        "target_ball",
        BALL_RADIUS,
        Vector(TARGET_START),
        MATS["ball_target"],
        "blue",
        role="target",
    )
    target["pb_ball_role"] = "target"
    target["pb_motion_constraint"] = "rolls_on_surface"
    target["pb_count_conserved"] = True

    return {
        "scene": scene,
        "kind": "glancing_oblique_collision",
        "incoming": incoming,
        "target": target,
        "incoming_start": incoming_start,
        "incoming_contact": incoming_contact,
        "target_start": Vector(TARGET_START),
        "n_hat": n_hat,
        "t_hat": t_hat,
    }


# ============================================================
# Animation
# ============================================================

# Post-collision travel distances before friction brings each ball to rest.
# The struck (target) ball carries most of the along-line momentum; the
# deflected incoming ball keeps its tangential share, so it travels a bit less.
TARGET_TRAVEL = 2.25
INCOMING_TRAVEL = 1.55
SETTLE_FRAME = 108     # both balls have rolled to rest by this frame
ROLL_AXIS_SCALE = 1.0  # visual rolling: radians rolled per unit distance = dist/R


def _incoming_position(frame, objs):
    """Position of the incoming ball at a given frame.

    Before contact: constant-velocity +X approach.
    After contact: decelerating roll along t_hat (friction), easing to rest.
    """
    R = BALL_RADIUS
    start = objs["incoming_start"]
    contact = objs["incoming_contact"]
    t_hat = objs["t_hat"]

    if frame <= CONTACT_FRAME:
        t = clamp01((frame - FRAME_START) / float(CONTACT_FRAME - FRAME_START))
        # Constant speed approach -> linear in frame.
        return start + (contact - start) * t

    # Post-collision: ease-out (friction decel) along t_hat.
    t = clamp01((frame - CONTACT_FRAME) / float(SETTLE_FRAME - CONTACT_FRAME))
    dist = INCOMING_TRAVEL * ease_out_quad(t)
    pos = contact + t_hat * dist
    pos.z = R
    return pos


def _target_position(frame, objs):
    """Position of the target ball at a given frame.

    Stationary until contact, then decelerating roll along the line of centres
    (n_hat), easing to rest via friction.
    """
    R = BALL_RADIUS
    start = objs["target_start"]
    n_hat = objs["n_hat"]

    if frame <= CONTACT_FRAME:
        return Vector(start)

    t = clamp01((frame - CONTACT_FRAME) / float(SETTLE_FRAME - CONTACT_FRAME))
    dist = TARGET_TRAVEL * ease_out_quad(t)
    pos = start + n_hat * dist
    pos.z = R
    return pos


def _roll_rotation(obj, prev_pos, cur_pos):
    """Apply a rolling rotation so the ball visibly rolls in its travel dir.

    Rolls about the horizontal axis perpendicular to the travel direction by
    (distance / R) radians. Accumulated in obj.rotation_euler.
    """
    R = BALL_RADIUS
    delta = cur_pos - prev_pos
    delta.z = 0.0
    dist = delta.length
    if dist < 1e-7:
        return
    travel_dir = delta.normalized()
    # Roll axis is horizontal, perpendicular to travel: (dir x up).
    up = Vector((0.0, 0.0, 1.0))
    axis = travel_dir.cross(up)
    if axis.length < 1e-7:
        return
    axis.normalize()
    angle = (dist / R) * ROLL_AXIS_SCALE
    from mathutils import Quaternion
    q = Quaternion(axis, angle)
    cur = obj.rotation_euler.to_quaternion()
    new = q @ cur
    obj.rotation_euler = new.to_euler()


def animate_glancing_oblique_collision(objs, frame, prev):
    incoming = objs["incoming"]
    target = objs["target"]

    inc_pos = _incoming_position(frame, objs)
    tgt_pos = _target_position(frame, objs)

    # Safety: never let the two centres come closer than 2R (no interpenetration).
    sep = (inc_pos - tgt_pos)
    sep.z = 0.0
    min_sep = 2.0 * BALL_RADIUS
    if sep.length < min_sep - 1e-4 and sep.length > 1e-6:
        push = (min_sep - sep.length)
        inc_pos = inc_pos + sep.normalized() * push

    # Rolling rotation based on the per-frame displacement.
    prev_inc = prev.get("incoming")
    prev_tgt = prev.get("target")
    if prev_inc is not None:
        _roll_rotation(incoming, prev_inc, inc_pos)
    if prev_tgt is not None:
        _roll_rotation(target, prev_tgt, tgt_pos)

    incoming.location = inc_pos
    incoming.keyframe_insert(data_path="location", frame=frame)
    incoming.keyframe_insert(data_path="rotation_euler", frame=frame)

    target.location = tgt_pos
    target.keyframe_insert(data_path="location", frame=frame)
    target.keyframe_insert(data_path="rotation_euler", frame=frame)

    incoming["pb_is_moving"] = bool((inc_pos - (prev_inc if prev_inc is not None else inc_pos)).length > 1e-4)
    target["pb_is_moving"] = bool(frame > CONTACT_FRAME and (tgt_pos - objs["target_start"]).length > 1e-4)
    incoming["pb_state"] = "approaching" if frame <= CONTACT_FRAME else "deflected"
    target["pb_state"] = "stationary" if frame <= CONTACT_FRAME else "struck_moving"

    prev["incoming"] = inc_pos
    prev["target"] = tgt_pos


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    prev = {}
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if kind == "glancing_oblique_collision":
            animate_glancing_oblique_collision(objs, frame, prev)
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

    if kind == "glancing_oblique_collision":
        return build_glancing_oblique_collision_scene()

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
