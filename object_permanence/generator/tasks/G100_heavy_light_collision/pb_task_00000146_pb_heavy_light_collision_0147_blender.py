# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_HEAVY_LIGHT_COLLISION_0147",
  "scene_kind": "heavy_light_collision",
  "prompt": "A large heavy ball rolls into a small light stationary ball. On impact the small ball shoots off fast in the direction of travel while the large ball keeps rolling forward, only slightly slowed. Both balls remain; neither passes through the other."
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
    # Two distinct ball colours so the heavy and light balls are clearly told apart.
    MATS["ball_heavy"] = make_mat("mat_ball_heavy", (0.80, 0.24, 0.20), roughness=0.34, metallic=0.10)
    MATS["ball_light"] = make_mat("mat_ball_light", (0.20, 0.42, 0.82), roughness=0.34, metallic=0.10)


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
# Heavy / light head-on collision scene
# ============================================================
#
# Layout (top-down, X = right, Y = into the scene, Z = up):
#   A LARGE, heavy ball starts far in -X and rolls in +X along the centre line
#   (Y = 0) straight into a SMALL, light stationary ball sitting on that same
#   line. The hit is DEAD-CENTRE (head-on): the line of centres is exactly the
#   travel direction, so all motion stays on Y = 0.
#
#   At contact the two centres are separated in 3-D by exactly (R_large +
#   R_small) - the balls just touch, no interpenetration and no air gap.
#   (Because the centres sit at different heights, this corresponds to a
#   horizontal gap of 2*sqrt(R_large*R_small), see CONTACT_DX below.)
#
#   For a heavy -> light head-on hit with restitution e (mass M >> m):
#     v_light'  = (1 + e) M / (M + m) * v_in  ->  FASTER than v_in (SHOOTS OFF FAST)
#     v_heavy'  = (M - e m) / (M + m) * v_in  ->  positive, < v_in
#                 (keeps rolling FORWARD, only slightly slowed; never reverses)
#   With M/m = 8 and e = 0.8 this gives v_light' = 1.6 v_in and v_heavy' =
#   0.8 v_in, which conserves momentum EXACTLY (8*0.8 + 1*1.6 = 8*1.0) and
#   loses 4% of the kinetic energy at the strike.
#   Both roll to rest via friction. The heavy ball always stays BEHIND the
#   light ball (it is slower after impact), so it never overtakes or penetrates.

_DIVERSITY = globals().get("DIVERSITY", {})

R_HEAVY = float(_DIVERSITY.get("heavy_radius", 0.62))
R_LIGHT = float(_DIVERSITY.get("light_radius", 0.30))
TRAVEL_DIRECTION = str(_DIVERSITY.get("travel_direction", "left_to_right"))
TRAVEL_SIGN = 1.0 if TRAVEL_DIRECTION == "left_to_right" else -1.0
FLOOR_Z = 0.0                          # lower ground level (light ball lands here)
CONTACT_DIST = R_HEAVY + R_LIGHT       # 3-D centre-to-centre distance when touching
# Both balls roll on the same plane, so their centres sit at DIFFERENT heights
# (dz = R_HEAVY - R_LIGHT = 0.32). Their surfaces touch when the 3-D centre
# distance equals R_HEAVY + R_LIGHT, which happens at a HORIZONTAL centre gap of
#   sqrt((R_H + R_L)^2 - (R_H - R_L)^2) = 2 * sqrt(R_H * R_L) ~ 0.8626,
# NOT at a horizontal gap of R_H + R_L (that would leave a visible air gap at
# the strike). All along-line contact placement uses this horizontal gap.
CONTACT_DX = 2.0 * math.sqrt(R_HEAVY * R_LIGHT)  # horizontal centre gap at touch

# --- Raised platform ------------------------------------------------------
# Both balls start on a raised platform. The heavy ball rolls +X into the
# light ball, which is parked near the platform's +X EDGE. After the hit the
# light ball shoots forward, rolls OFF the edge and free-falls to the lower
# floor below. The heavy ball keeps rolling forward but STOPS on the platform
# (short of the edge) and never falls.
PLATFORM_H = float(_DIVERSITY.get("platform_height", 2.2))
PLATFORM_Z = FLOOR_Z + PLATFORM_H      # platform top surface (balls roll on this)
PLATFORM_EDGE_X = 2.0 * TRAVEL_SIGN    # drop edge in the direction of travel
PLATFORM_FAR_X = -6.0 * TRAVEL_SIGN   # far end behind the incoming ball
PLATFORM_Y_HALF = 3.0                  # half-depth of the platform in Y

# Mass ratio for a heavy -> light elastic head-on collision. Using uniform
# density spheres, M/m scales as (R_heavy / R_light)^3, but we clamp it to a
# clean, clearly-heavy ratio so the exit speeds read cleanly on screen.
MASS_HEAVY = float(_DIVERSITY.get("heavy_mass", 8.0))
MASS_LIGHT = float(_DIVERSITY.get("light_mass", 1.0))

# Both balls travel along the centre line Y = 0.
LINE_Y = 0.0

# Light (target) ball sits stationary near the +X EDGE of the raised platform
# (its centre one light-radius above the platform top). A short forward roll
# after the hit carries it off the edge and into free-fall.
LIGHT_START = Vector((PLATFORM_EDGE_X - TRAVEL_SIGN * 0.55, LINE_Y, PLATFORM_Z + R_LIGHT))

CONTACT_FRAME = 40                     # frame at which the balls just touch

# Speed of the heavy ball before impact (Blender units per frame).
INCOMING_SPEED = float(_DIVERSITY.get("incoming_speed", 0.080))

# Post-collision exit speeds from the 1-D collision with restitution e
# (heavy hits light).  Momentum is conserved exactly at the impact instant:
#   M*v_in = M*v_heavy' + m*v_light'
#   light gains:  (1 + e) M / (M + m) * v_in
#   heavy keeps:  (M - e m) / (M + m) * v_in
# With M/m = 8 and e = 0.8: v_light' = 0.128 u/f (1.6x incoming) and
# v_heavy' = 0.064 u/f (0.8x incoming). KE drops 4% at the strike.
RESTITUTION = float(_DIVERSITY.get("restitution", 0.8))
V_LIGHT_EXIT = INCOMING_SPEED * (1.0 + RESTITUTION) * MASS_HEAVY / (MASS_HEAVY + MASS_LIGHT)       # 0.128
V_HEAVY_EXIT = INCOMING_SPEED * (MASS_HEAVY - RESTITUTION * MASS_LIGHT) / (MASS_HEAVY + MASS_LIGHT)  # 0.064


def _contact_geometry():
    """Compute the heavy ball's centre at the contact frame.

    Head-on: everything is on the centre line Y = LINE_Y. At contact the heavy
    ball centre sits exactly CONTACT_DX (the horizontal gap at surface touch,
    accounting for the two centre heights) to the -X side of the light ball,
    so the 3-D centre distance is exactly R_HEAVY + R_LIGHT: the surfaces just
    touch, no interpenetration and no air gap.
    """
    heavy_contact = Vector((LIGHT_START.x - TRAVEL_SIGN * CONTACT_DX, LINE_Y, PLATFORM_Z + R_HEAVY))
    travel_dir = Vector((TRAVEL_SIGN, 0.0, 0.0))
    return heavy_contact, travel_dir


def build_heavy_light_collision_scene():
    scene = build_base_scene()
    # Elevated camera, slightly to the side, so both the along-line speed
    # difference AND the light ball's fall off the platform edge read clearly.
    setup_camera(
        scene,
        location=(1.65 * TRAVEL_SIGN, -9.2, 5.6),
        target=(1.25 * TRAVEL_SIGN, 0.0, PLATFORM_Z * 0.5 + 0.4),
        lens=38,
    )

    # Raised platform the balls start on. Its +X face is the drop edge; the
    # light ball rolls off it and free-falls to the lower floor (built in
    # build_base_scene at FLOOR_Z).
    plat_len_x = abs(PLATFORM_EDGE_X - PLATFORM_FAR_X)
    plat_cx = 0.5 * (PLATFORM_EDGE_X + PLATFORM_FAR_X)
    add_cube(
        "raised_platform",
        (plat_cx, LINE_Y, FLOOR_Z + 0.5 * PLATFORM_H),
        (plat_len_x, 2.0 * PLATFORM_Y_HALF, PLATFORM_H),
        material=MATS["gray"],
        role="platform",
        color_name="gray",
    )

    heavy_contact, travel_dir = _contact_geometry()

    # Heavy ball starts far in -X on the centre line so that at CONTACT_FRAME
    # (moving +X at INCOMING_SPEED) it reaches heavy_contact.
    travel = INCOMING_SPEED * (CONTACT_FRAME - FRAME_START)
    heavy_start = Vector((
        heavy_contact.x - TRAVEL_SIGN * travel,
        LINE_Y,
        PLATFORM_Z + R_HEAVY,
    ))

    heavy = add_sphere(
        "heavy_ball",
        R_HEAVY,
        heavy_start,
        MATS["ball_heavy"],
        "red",
        role="projectile",
    )
    heavy["pb_ball_role"] = "heavy_incoming"
    heavy["pb_motion_constraint"] = "rolls_on_surface"
    heavy["pb_count_conserved"] = True
    heavy["pb_mass"] = MASS_HEAVY

    light = add_sphere(
        "light_ball",
        R_LIGHT,
        Vector(LIGHT_START),
        MATS["ball_light"],
        "blue",
        role="target",
    )
    light["pb_ball_role"] = "light_target"
    light["pb_motion_constraint"] = "rolls_on_surface"
    light["pb_count_conserved"] = True
    light["pb_mass"] = MASS_LIGHT

    return {
        "scene": scene,
        "kind": "heavy_light_collision",
        "heavy": heavy,
        "light": light,
        "heavy_start": heavy_start,
        "heavy_contact": heavy_contact,
        "light_start": Vector(LIGHT_START),
        "travel_dir": travel_dir,
    }


# ============================================================
# Animation
# ============================================================

# Post-collision motion. All segments are explicit constant-deceleration
# kinematics (x = v0*t - a*t^2/2) so per-frame velocity is continuous inside
# each phase and only changes at genuine impacts, where it DROPS.
#
# Heavy ball: exits the strike at V_HEAVY_EXIT (< incoming) and keeps rolling
# FORWARD, but must STOP on the platform, short of the edge, so it never
# falls. Friction is chosen so it comes to rest after exactly HEAVY_TRAVEL.
HEAVY_STOP_MARGIN = 0.10               # keep the heavy ball this far back from
                                       # its maximum safe centre position
_HEAVY_CONTACT_X = LIGHT_START.x - TRAVEL_SIGN * CONTACT_DX
_HEAVY_MAX_CENTRE_X = PLATFORM_EDGE_X - TRAVEL_SIGN * (R_HEAVY + HEAVY_STOP_MARGIN)
HEAVY_TRAVEL = max(
    0.0,
    TRAVEL_SIGN * (_HEAVY_MAX_CENTRE_X - _HEAVY_CONTACT_X),
)  # stays on platform
HEAVY_FRICTION = (V_HEAVY_EXIT * V_HEAVY_EXIT) / (2.0 * HEAVY_TRAVEL)  # u/f^2
HEAVY_STOP_DT = V_HEAVY_EXIT / HEAVY_FRICTION          # ~21.6 frames of roll-out
HEAVY_SETTLE_FRAME = CONTACT_FRAME + HEAVY_STOP_DT     # ~61.6: at rest on platform

# Light ball: shoots forward FAST at V_LIGHT_EXIT (1.6x incoming), loses a
# little speed to platform friction on its short roll to the edge, leaves the
# edge at LIGHT_EDGE_SPEED, then free-falls ballistically: horizontal velocity
# CONSTANT (= LIGHT_EDGE_SPEED, continuous through the edge crossing) while a
# gravity-like quadratic drop builds vertical speed from exactly 0.
LIGHT_ROLL = abs(PLATFORM_EDGE_X - LIGHT_START.x)      # roll to the edge (0.55)
LIGHT_EDGE_SPEED = 0.80 * V_LIGHT_EXIT                 # physical deceleration before the edge
LIGHT_FRICTION = (V_LIGHT_EXIT * V_LIGHT_EXIT - LIGHT_EDGE_SPEED * LIGHT_EDGE_SPEED) / (2.0 * LIGHT_ROLL)
EDGE_DT = (V_LIGHT_EXIT - LIGHT_EDGE_SPEED) / LIGHT_FRICTION   # ~3.96 frames to the edge
EDGE_FRAME = CONTACT_FRAME + EDGE_DT                   # ~43.96: leaves the platform edge
FALL_FRAMES = 12.0                                     # ballistic fall duration
GRAVITY = 2.0 * PLATFORM_H / (FALL_FRAMES * FALL_FRAMES)  # ~0.0306 u/f^2 over the 2.2 drop
LAND_FRAME = EDGE_FRAME + FALL_FRAMES                  # ~55.96: touches the lower floor
LIGHT_FALL_FORWARD = LIGHT_EDGE_SPEED * FALL_FRAMES    # 1.8 forward carry during fall
# Landing: inelastic (no bounce). Vertical speed drops to 0 at floor impact and
# horizontal speed scrubs down (impact + floor friction), then rolls out to rest.
LAND_SCRUB = 0.5                                       # horizontal speed kept at landing
LIGHT_LAND_SPEED = LIGHT_EDGE_SPEED * LAND_SCRUB       # 0.075
ROLLOUT_DT = 18.0                                      # frames of floor roll-out
FLOOR_FRICTION = LIGHT_LAND_SPEED / ROLLOUT_DT
LIGHT_ROLLOUT = (LIGHT_LAND_SPEED * LIGHT_LAND_SPEED) / (2.0 * FLOOR_FRICTION)  # 0.675
SETTLE_FRAME = LAND_FRAME + ROLLOUT_DT                 # ~73.96: at rest on the lower floor
ROLL_AXIS_SCALE = 1.0  # visual rolling: radians rolled per unit distance = dist/R


def _heavy_position(frame, objs):
    """Position of the heavy ball at a given frame.

    Before contact: constant-velocity +X approach.
    After contact: keeps rolling forward along +X but decelerating (friction),
    easing to rest. It never reverses and always trails the light ball.
    """
    R = R_HEAVY
    start = objs["heavy_start"]
    contact = objs["heavy_contact"]
    travel_dir = objs["travel_dir"]

    if frame <= CONTACT_FRAME:
        t = clamp01((frame - FRAME_START) / float(CONTACT_FRAME - FRAME_START))
        # Constant speed approach -> linear in frame.
        return start + (contact - start) * t

    # Post-collision: exits at V_HEAVY_EXIT (0.8x incoming; speed DROPS at the
    # impact), then constant friction deceleration to rest ON the platform
    # short of the edge (never falls). Z stays on top of the platform.
    tau = frame - CONTACT_FRAME
    if tau >= HEAVY_STOP_DT:
        dist = HEAVY_TRAVEL
    else:
        dist = V_HEAVY_EXIT * tau - 0.5 * HEAVY_FRICTION * tau * tau
    pos = contact + travel_dir * dist
    pos.z = PLATFORM_Z + R
    return pos


def _light_position(frame, objs):
    """Position of the light ball at a given frame.

    Stationary until contact, then shoots off FAST along +X, decelerating
    (friction) to rest. Because it starts one contact-gap ahead of the heavy
    ball's contact centre and moves faster, it stays ahead throughout.
    """
    R = R_LIGHT
    start = objs["light_start"]           # on the platform, near the edge
    travel_dir = objs["travel_dir"]

    top_z = PLATFORM_Z + R                 # centre height while on the platform
    floor_z = FLOOR_Z + R                  # centre height at rest on lower floor
    edge_x = start.x + TRAVEL_SIGN * LIGHT_ROLL

    # Stationary until struck.
    if frame <= CONTACT_FRAME:
        return Vector(start)

    tau = frame - CONTACT_FRAME

    # Phase 1 - struck: leaves the impact at V_LIGHT_EXIT (1.6x incoming),
    # rolls across the platform with slight friction deceleration, reaching
    # the edge still moving at LIGHT_EDGE_SPEED.
    if tau <= EDGE_DT:
        x = start.x + TRAVEL_SIGN * (
            V_LIGHT_EXIT * tau - 0.5 * LIGHT_FRICTION * tau * tau
        )
        return Vector((x, LINE_Y, top_z))

    # Phase 2 - ballistic fall off the edge: horizontal velocity stays exactly
    # LIGHT_EDGE_SPEED (continuous through the edge crossing) while a
    # gravity-like quadratic drop builds vertical speed from 0.
    tf = tau - EDGE_DT
    if tf <= FALL_FRAMES:
        x = edge_x + TRAVEL_SIGN * LIGHT_EDGE_SPEED * tf
        z = top_z - 0.5 * GRAVITY * tf * tf
        return Vector((x, LINE_Y, z))

    # Phase 3 - inelastic landing (vertical speed -> 0, horizontal speed scrubs
    # to LIGHT_LAND_SPEED), then friction roll-out on the lower floor to rest.
    tl = tf - FALL_FRAMES
    land_x = edge_x + TRAVEL_SIGN * LIGHT_FALL_FORWARD
    if tl <= ROLLOUT_DT:
        x = land_x + TRAVEL_SIGN * (
            LIGHT_LAND_SPEED * tl - 0.5 * FLOOR_FRICTION * tl * tl
        )
    else:
        x = land_x + TRAVEL_SIGN * LIGHT_ROLLOUT
    return Vector((x, LINE_Y, floor_z))


def _roll_rotation(obj, radius, prev_pos, cur_pos):
    """Apply a rolling rotation so the ball visibly rolls in its travel dir.

    Rolls about the horizontal axis perpendicular to the travel direction by
    (distance / radius) radians. Accumulated in obj.rotation_euler. Each ball
    uses its OWN radius, so spin is proportional to distance / own radius.
    """
    delta = cur_pos - prev_pos
    delta.z = 0.0
    dist = delta.length
    if dist < 1e-7:
        return
    travel_d = delta.normalized()
    # Roll axis is horizontal, perpendicular to travel: (up x dir), so the
    # contact point is instantaneously at rest (true rolling, not backspin).
    up = Vector((0.0, 0.0, 1.0))
    axis = up.cross(travel_d)
    if axis.length < 1e-7:
        return
    axis.normalize()
    angle = (dist / radius) * ROLL_AXIS_SCALE
    from mathutils import Quaternion
    q = Quaternion(axis, angle)
    cur = obj.rotation_euler.to_quaternion()
    new = q @ cur
    obj.rotation_euler = new.to_euler()


def animate_heavy_light_collision(objs, frame, prev):
    heavy = objs["heavy"]
    light = objs["light"]

    heavy_pos = _heavy_position(frame, objs)
    light_pos = _light_position(frame, objs)

    # Safety: never let the two centres come horizontally closer than
    # CONTACT_DX (the surface-touch gap, i.e. 3-D centre distance R_H + R_L)
    # WHILE BOTH BALLS ARE ON THE PLATFORM. Once the light ball has left the
    # platform edge and dropped below the heavy ball, the 3-D separation is
    # large (vertical gap), so the flat/horizontal check no longer applies and
    # must not spuriously drag the heavy ball backwards.
    if frame <= EDGE_FRAME:
        sep = (light_pos - heavy_pos)
        sep.z = 0.0
        min_sep = CONTACT_DX
        if sep.length < min_sep - 1e-4 and sep.length > 1e-6:
            push = (min_sep - sep.length)
            # Heavy ball trails on -X; push it back along -sep to keep the gap.
            heavy_pos = heavy_pos - sep.normalized() * push

    # Rolling rotation based on the per-frame displacement (each own radius).
    prev_heavy = prev.get("heavy")
    prev_light = prev.get("light")
    if prev_heavy is not None:
        _roll_rotation(heavy, R_HEAVY, prev_heavy, heavy_pos)
    if prev_light is not None:
        _roll_rotation(light, R_LIGHT, prev_light, light_pos)

    heavy.location = heavy_pos
    heavy.keyframe_insert(data_path="location", frame=frame)
    heavy.keyframe_insert(data_path="rotation_euler", frame=frame)

    light.location = light_pos
    light.keyframe_insert(data_path="location", frame=frame)
    light.keyframe_insert(data_path="rotation_euler", frame=frame)

    heavy["pb_is_moving"] = bool((heavy_pos - (prev_heavy if prev_heavy is not None else heavy_pos)).length > 1e-4)
    light["pb_is_moving"] = bool(frame > CONTACT_FRAME and (light_pos - objs["light_start"]).length > 1e-4)
    heavy["pb_state"] = "rolling_in" if frame <= CONTACT_FRAME else "slowed_forward_on_platform"
    if frame <= CONTACT_FRAME:
        light["pb_state"] = "stationary"
    elif frame <= EDGE_FRAME:
        light["pb_state"] = "shot_forward"
    elif frame <= LAND_FRAME:
        light["pb_state"] = "free_falling"
    else:
        light["pb_state"] = "resting_on_floor"

    prev["heavy"] = heavy_pos
    prev["light"] = light_pos


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    prev = {}
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if kind == "heavy_light_collision":
            animate_heavy_light_collision(objs, frame, prev)
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

    if kind == "heavy_light_collision":
        return build_heavy_light_collision_scene()

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
