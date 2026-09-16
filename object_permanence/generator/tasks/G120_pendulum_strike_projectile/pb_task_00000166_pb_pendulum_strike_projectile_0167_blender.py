# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_PENDULUM_STRIKE_PROJECTILE_0167",
  "scene_kind": "pendulum_strike_projectile",
  "prompt": "A heavy metal ball hangs as a pendulum, is raised and released, and swings down to strike a second ball resting on the edge of a ledge. The struck ball is knocked off the ledge and rolls away along the floor, while the heavy pendulum ball follows through slightly, slows, and settles into small damped swings. Momentum transfers; nothing is left suspended unnaturally."
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
    MATS["red"] = make_mat("mat_red", (0.95, 0.10, 0.06), roughness=0.30)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.42, 0.08), roughness=0.30)
    MATS["ledge"] = make_mat("mat_ledge", (0.52, 0.44, 0.34), roughness=0.66)
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
# Pendulum-strike-to-projectile scene
#
# A single pendulum ball hangs on a bifilar string from a top bar. To its RIGHT,
# a target ball rests on the front EDGE of a raised ledge. The pendulum is shown
# raised to the LEFT, released, and swings DOWN through its arc. At the bottom
# of the swing the pendulum ball's surface reaches the target ball (centres one
# diameter apart) -- the strike. Momentum transfers: the target ball is knocked
# off the ledge edge (to the +X/right), falls to the floor, and rolls away along
# the floor; the HEAVY pendulum ball follows through to a smaller right swing,
# then damps toward rest through decaying oscillations. Nothing is left
# suspended: the target ends on the floor, the pendulum hangs at rest.
#
# Geometry is derived so contact is exactly at surface-touch (no interpenetration)
# and the target's launch point is the ledge edge, so it never floats.
# ============================================================

BALL_RADIUS = 0.24
BAR_Z = 2.30              # top support bar / pivot height
STRING_LENGTH = 1.35     # pendulum arm length (pivot -> ball center)
RAISE_ANGLE = math.radians(68.0)   # released-from amplitude (to the LEFT, -X)
PENDULUM_MASS = 8.6
TARGET_MASS = 1.0
COLLISION_RESTITUTION = 0.82

# The pendulum pivot X. At theta = 0 the ball hangs at (PIVOT_X, 0, rest_z).
# Set to the LEFT so the whole strike geometry — pivot, pendulum bottom-of-swing,
# and the gold target ball at target_x = PIVOT_X + 2R — sits together on that
# side. This puts the gold (target) ball's rest position to the LEFT at the
# start of the video while keeping the surfaces-touch strike exact
# (center distance == 2R at theta = 0) and preserving all frame/post clearances.
PIVOT_X = -1.05
REST_Z = BAR_Z - STRING_LENGTH     # ball center z at bottom of swing


def build_pendulum_strike_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(0.0, -8.8, 1.75), target=(0.35, 0.0, 0.95), lens=36)

    pivot = (PIVOT_X, 0.0, BAR_Z)

    # Support frame: top bar + two posts. The span is widened so the RIGHT post
    # sits well clear (+X) of where the struck target ball rolls to rest.
    half_span = 2.0
    bar_len = 2.0 * half_span
    add_cube(
        "top_support_bar",
        (PIVOT_X, 0.0, BAR_Z + 0.06),
        (bar_len, 0.14, 0.12),
        material=MATS["frame"], role="support_bar", color_name="dark_gray",
    )
    post_h = BAR_Z + 0.12
    for side, sx in (("left", PIVOT_X - half_span + 0.06), ("right", PIVOT_X + half_span - 0.06)):
        add_cube(
            f"{side}_support_post",
            (sx, 0.0, post_h / 2.0),
            (0.12, 0.14, post_h),
            material=MATS["frame"], role="support_post", color_name="dark_gray",
        )

    # Pendulum ball, built at the bottom-of-swing (theta = 0) position.
    bob0 = (PIVOT_X + STRING_LENGTH * math.sin(0.0), 0.0, BAR_Z - STRING_LENGTH * math.cos(0.0))
    pendulum = add_sphere("pendulum_ball", BALL_RADIUS, bob0, MATS["metal"], "metallic_gray", role="target")
    pendulum["pb_motion_constraint"] = "fixed_length_pendulum_arc"
    pendulum["pb_count_conserved"] = True
    pendulum["pb_mass"] = PENDULUM_MASS

    # Bifilar V strings from the bar to the pendulum ball.
    string_y = 0.16
    strings = []
    for sgn in (-1.0, 1.0):
        anchor = (pivot[0], sgn * string_y, pivot[2])
        cyl = add_cylinder_between(
            f"string_{'pos' if sgn > 0 else 'neg'}",
            anchor, bob0, 0.012, MATS["rope"],
            role="string", color_name="dark_gray", is_dynamic=True, solid=True, vertices=12,
        )
        cyl["pb_string_length_constant"] = True
        strings.append((cyl, sgn * string_y))

    # --- Ledge to the RIGHT: a raised platform whose front/top the target ball
    # rests on, with its front edge at the strike point so the strike knocks it
    # off. The ledge top must be at the pendulum ball's center height so the two
    # balls strike center-to-center on a horizontal line.
    ledge_top_z = REST_Z - BALL_RADIUS   # so a ball on top has center at REST_Z
    ledge_top_z = max(ledge_top_z, 0.30)
    # Target ball center sits at (contact_x, 0, REST_Z_target). We want the two
    # ball centers one diameter apart horizontally at the bottom of the swing:
    #   pendulum center at bottom = (PIVOT_X, 0, REST_Z).
    #   target center = (PIVOT_X + 2R, 0, REST_Z)  -> horizontal strike.
    target_x = PIVOT_X + 2.0 * BALL_RADIUS
    target_cz = REST_Z
    # Ledge: its TOP surface is at target_cz - R, so the target rests on it.
    # The ledge extends to the LEFT (-X, toward/under the pendulum's low point);
    # the +X side beyond the edge is OPEN, so when struck the ball rolls off the
    # right edge and falls into empty space, then rolls away along the floor.
    ledge_top = target_cz - BALL_RADIUS
    ledge_h = ledge_top                  # rests on the floor (floor top ~0.0)
    ledge_right_x = target_x + 0.47      # extend right so the ball's whole footprint rests on the box top (not perched on the edge)
    ledge_len_x = 1.25
    ledge_left_x = ledge_right_x - ledge_len_x
    ledge_cx = ledge_right_x - ledge_len_x / 2.0
    ledge = add_cube(
        "target_ledge",
        (ledge_cx, 0.0, ledge_top - ledge_h / 2.0),
        (ledge_len_x, 1.1, ledge_h),
        material=MATS["ledge"], role="ledge", color_name="brown",
    )
    ledge["pb_static"] = True

    # Target ball resting on the ledge front edge.
    target = add_sphere("target_ball_on_ledge", BALL_RADIUS, (target_x, 0.0, target_cz), MATS["orange"], "orange", role="target")
    target["pb_resting_on_ledge_edge"] = True
    target["pb_count_conserved"] = True
    target["pb_mass"] = TARGET_MASS

    return {
        "scene": scene,
        "kind": "pendulum_strike_projectile",
        "pivot": pivot,
        "length": STRING_LENGTH,
        "pendulum": pendulum,
        "strings": strings,
        "string_y": string_y,
        "target": target,
        "target_x": target_x,
        "target_cz": target_cz,
        "ball_r": BALL_RADIUS,
        "ledge_left_x": ledge_left_x,
        "ledge_right_x": ledge_right_x,
        "floor_top_z": 0.0,
    }


# ============================================================
# Animation
# ============================================================

IMPACT_FRAME = 40   # pendulum reaches bottom of swing and strikes the target
RELEASE_FRAME = 12  # short visible hold, then a brisk natural downswing
_IMPACT_THETA_SPEED = RAISE_ANGLE * math.pi / (2.0 * (IMPACT_FRAME - RELEASE_FRAME))
PENDULUM_IMPACT_SPEED = STRING_LENGTH * _IMPACT_THETA_SPEED
PENDULUM_POST_SPEED = (
    (PENDULUM_MASS - COLLISION_RESTITUTION * TARGET_MASS)
    / (PENDULUM_MASS + TARGET_MASS)
    * PENDULUM_IMPACT_SPEED
)
TARGET_LAUNCH_SPEED = (
    (1.0 + COLLISION_RESTITUTION) * PENDULUM_MASS
    / (PENDULUM_MASS + TARGET_MASS)
    * PENDULUM_IMPACT_SPEED
)
FOLLOW_OMEGA = 0.12
FOLLOW_DECAY = 0.030
# Choose the damped-sine amplitude so the first rendered post-impact step has
# exactly the collision-derived horizontal speed (rather than only matching its
# infinitesimal derivative).
FOLLOW_AMPLITUDE = (
    math.asin(PENDULUM_POST_SPEED / STRING_LENGTH)
    / (math.exp(-FOLLOW_DECAY) * math.sin(FOLLOW_OMEGA))
)


def _pendulum_theta(frame):
    """Signed pendulum angle (radians); negative = raised to the LEFT (-X)."""
    A = RAISE_ANGLE
    f = frame

    # Phase A (release -> impact): swing down from -A to 0 (quarter cosine).
    if f <= IMPACT_FRAME:
        t = clamp01((f - RELEASE_FRAME) / float(IMPACT_FRAME - RELEASE_FRAME))
        return -A * math.cos(0.5 * math.pi * t)

    # Phase B (follow-through + damp): the pink ball strikes the gold ball at the
    # bottom of the swing (theta = 0) and, carrying its rightward momentum, first
    # FOLLOWS THROUGH to the RIGHT (theta > 0) into the space the gold ball vacates,
    # then swings back and oscillates with decaying amplitude, settling toward rest.
    # Using sin() makes theta leave 0 moving POSITIVE (to the RIGHT) with a
    # continuous velocity — no leftward jump, no discontinuity at the strike
    # frame.
    df = f - IMPACT_FRAME
    return FOLLOW_AMPLITUDE * math.exp(-FOLLOW_DECAY * df) * math.sin(FOLLOW_OMEGA * df)


def animate_pendulum_strike(objs, frame):
    pendulum = objs["pendulum"]
    strings = objs["strings"]
    pivot = objs["pivot"]
    L = objs["length"]
    target = objs["target"]
    target_x = objs["target_x"]
    target_cz = objs["target_cz"]
    R = objs["ball_r"]
    ledge_left_x = objs["ledge_left_x"]
    ledge_right_x = objs["ledge_right_x"]
    floor_top_z = objs["floor_top_z"]

    # --- Pendulum ball on its arc ---
    theta = _pendulum_theta(frame)
    bob = Vector((
        pivot[0] + L * math.sin(theta),
        0.0,
        pivot[2] - L * math.cos(theta),
    ))
    pendulum.location = bob
    pendulum.rotation_euler = (0.0, theta * 0.6, 0.0)
    pendulum.keyframe_insert(data_path="location", frame=frame)
    pendulum.keyframe_insert(data_path="rotation_euler", frame=frame)
    pendulum["pb_state"] = "swinging_down_to_strike" if frame <= IMPACT_FRAME else "rebounding_and_damping"
    pendulum["pb_pendulum_length_constant"] = True

    # Strings follow the pendulum ball.
    for (cyl, anchor_y) in strings:
        anchor = (pivot[0], anchor_y, pivot[2])
        set_cylinder_between(cyl, anchor, bob)
        cyl.keyframe_insert(data_path="location", frame=frame)
        cyl.keyframe_insert(data_path="rotation_euler", frame=frame)
        cyl["pb_state"] = "string_follows_ball"

    # --- Target ball: rests until the strike, then launches off the ledge edge,
    # falls to the floor, and rolls away to the RIGHT (+X) along the floor.
    floor_center_z = floor_top_z + R
    if frame <= IMPACT_FRAME:
        tx = target_x
        tz = target_cz
        tgt_state = "resting_on_ledge_edge"
    else:
        df = frame - IMPACT_FRAME
        drop_h = target_cz - floor_center_z
        # Horizontal launch and pendulum follow-through are derived together
        # from one 1-D collision with the declared masses and restitution. This
        # conserves momentum and prevents independently tuned curves from
        # creating kinetic energy at impact.
        TAU = 5.8
        X_MAX = TARGET_LAUNCH_SPEED / (1.0 - math.exp(-1.0 / TAU))
        x_off = X_MAX * (1.0 - math.exp(-float(df) / TAU))
        tx = target_x + x_off
        # Vertical: the ball is supported by the ledge only while its centre is
        # over the ledge top (contact point directly below the centre). Support
        # is lost the moment the centre crosses the ledge's right edge, so the
        # drop start is DERIVED from that geometry: x_off = edge_off at
        # fall_start (derived below), not hardcoded -- the ball never floats.
        # From separation the arc is ballistic: vertical velocity starts at
        # exactly 0 and builds under a gravity-like quadratic (GRAV chosen so
        # the descending surface just grazes, never clips, the ledge corner).
        edge_off = ledge_right_x - target_x          # centre-over-edge offset (0.47)
        fall_start = -TAU * math.log(1.0 - edge_off / X_MAX)   # ~7.64
        fall_frames = 12.0
        grav = 2.0 * drop_h / (fall_frames * fall_frames)      # ~0.0044 u/f^2
        if df <= fall_start:
            tz = target_cz
            tgt_state = "knocked_off_ledge_rolling_to_edge"
        elif df <= fall_start + fall_frames:
            ft = df - fall_start
            tz = target_cz - 0.5 * grav * ft * ft    # v_z = 0 at separation
            tgt_state = "ballistic_fall_off_ledge_edge"
        else:
            tz = floor_center_z
            tgt_state = "rolling_out_on_floor"

    # Rolling spin: accumulate rotation proportional to the per-frame horizontal
    # displacement (angle = distance / R about +Y for +X travel). The ball has
    # zero spin while resting on the ledge and its spin rate always matches its
    # linear speed, easing to zero as it eases to rest.
    prev_tx = objs.get("_tgt_prev_x", target_x)
    roll = objs.get("_tgt_roll", 0.0) + (tx - prev_tx) / R
    objs["_tgt_prev_x"] = tx
    objs["_tgt_roll"] = roll

    target.location = (tx, 0.0, tz)
    target.rotation_euler = (0.0, roll, 0.0)
    target.keyframe_insert(data_path="location", frame=frame)
    target.keyframe_insert(data_path="rotation_euler", frame=frame)
    target["pb_state"] = tgt_state
    target["pb_no_interpenetration"] = True
    target["pb_not_suspended"] = True


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if kind == "pendulum_strike_projectile":
            animate_pendulum_strike(objs, frame)
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

    if kind == "pendulum_strike_projectile":
        return build_pendulum_strike_scene()

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
