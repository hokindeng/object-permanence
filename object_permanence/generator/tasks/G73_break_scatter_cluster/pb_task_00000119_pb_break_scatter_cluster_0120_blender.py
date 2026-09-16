# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_BREAK_SCATTER_CLUSTER_0120",
  "scene_kind": "break_scatter_cluster",
  "prompt": "A cue ball rolls across a flat surface into a tight triangular cluster of stationary balls. On impact the cluster scatters - the balls spread outward along different directions and speeds - while the cue ball slows. The total number of balls is conserved; none appear or vanish."
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
    # Distinct pool-ball colours for the rack so the scatter directions read
    # clearly, plus a bright cue-ball material.
    MATS["cue"] = make_mat("mat_cue_ball", (0.95, 0.94, 0.90), roughness=0.20)
    MATS["rack_red"] = make_mat("mat_rack_red", (0.78, 0.12, 0.12), roughness=0.24)
    MATS["rack_yellow"] = make_mat("mat_rack_yellow", (0.88, 0.72, 0.10), roughness=0.24)
    MATS["rack_blue"] = make_mat("mat_rack_blue", (0.12, 0.28, 0.72), roughness=0.24)
    MATS["rack_green"] = make_mat("mat_rack_green", (0.10, 0.52, 0.24), roughness=0.24)
    MATS["rack_orange"] = make_mat("mat_rack_orange", (0.86, 0.42, 0.08), roughness=0.24)
    MATS["rack_purple"] = make_mat("mat_rack_purple", (0.42, 0.14, 0.56), roughness=0.24)


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
# Break-scatter-cluster scene
# ============================================================
#
# A cue ball rolls in from -X (left) across a flat table and strikes the front
# ball of a tight triangular rack of 6 balls sitting at rest. On impact the
# rack balls scatter outward along different directions/speeds and decelerate
# to rest (friction); the cue ball slows and slightly deflects. All motion is
# keyframed on a flat plane (Z of every ball center stays at BALL_RADIUS).
# Ball count is conserved (7 total: 1 cue + 6 rack) and never interpenetrates
# at rest.

BALL_RADIUS = 0.30
BALL_Z = BALL_RADIUS  # every ball center rides on the table top (floor top ~ 0)

# Rack apex: the front ball nearest the incoming cue ball. The rack opens
# toward +X (away from the cue ball), classic 3-row triangle (1 + 2 + 3 = 6).
RACK_APEX_X = 0.6
# Small (~4%) gap added so the racked spheres just barely separate at rest --
# rigid-body solver needs non-overlapping start states or it "explodes".
_RACK_GAP = 1.04
ROW_DX = 2.0 * BALL_RADIUS * math.cos(math.radians(30.0)) * _RACK_GAP   # row-to-row spacing along +X
ROW_DY = BALL_RADIUS * _RACK_GAP                                        # half-spacing across Y within a row

CUE_START_X = -4.6          # cue starts left (closer => gentler break, balls stay on table)
CUE_START_Y = 0.0
IMPACT_FRAME = 34           # cue ball reaches the apex ball at ~frame 34
SETTLE_FRAME = 96           # scattered balls have fully decelerated to rest by here

# Rack colours cycle through the distinct pool materials (front ball -> back).
RACK_MAT_KEYS = ["rack_red", "rack_yellow", "rack_blue", "rack_green", "rack_orange", "rack_purple"]
RACK_COLOR_NAMES = ["red", "yellow", "blue", "green", "orange", "purple"]


def _rack_layout():
    """Return the 6 rest positions (x, y) of a tight triangular rack.

    Row 0: 1 ball (apex, nearest cue), Row 1: 2 balls, Row 2: 3 balls.
    Balls just touch; the triangle opens toward +X.
    """
    positions = []
    for row in range(3):
        rx = RACK_APEX_X + row * ROW_DX
        n = row + 1
        for j in range(n):
            # centre each row on Y = 0
            ry = (j - (n - 1) / 2.0) * (2.0 * ROW_DY)
            positions.append((rx, ry))
    return positions


def build_break_scatter_cluster_scene():
    scene = build_base_scene()
    # Slightly elevated camera so the outward scatter spread on the table is
    # clearly visible; framed on the rack region.
    setup_camera(scene, location=(-1.2, -8.4, 3.6), target=(1.4, 0.2, BALL_Z), lens=36)

    rack_positions = _rack_layout()

    # Cue ball (white), starting far left, rolling toward +X.
    cue = add_sphere(
        "cue_ball",
        BALL_RADIUS,
        (CUE_START_X, CUE_START_Y, BALL_Z),
        MATS["cue"],
        "white",
        role="cue_ball",
    )
    cue["pb_ball_index"] = 0
    cue["pb_count_conserved"] = True
    cue["pb_motion_constraint"] = "rolls_on_flat_table"

    rack_balls = []
    for k, (rx, ry) in enumerate(rack_positions):
        ball = add_sphere(
            f"rack_ball_{k}",
            BALL_RADIUS,
            (rx, ry, BALL_Z),
            MATS[RACK_MAT_KEYS[k]],
            RACK_COLOR_NAMES[k],
            role="rack_ball",
        )
        ball["pb_ball_index"] = k + 1
        ball["pb_count_conserved"] = True
        ball["pb_motion_constraint"] = "rolls_on_flat_table"
        rack_balls.append(ball)

    # Precompute a plausible outward scatter velocity (direction + speed) for
    # each rack ball. Directions fan outward from the impact point (the apex),
    # speeds differ per ball; the apex ball, taking the head-on hit, goes
    # mostly straight forward and fastest.
    apex = Vector((rack_positions[0][0], rack_positions[0][1], 0.0))
    scatter = []  # (dir_x, dir_y, distance) per rack ball
    # Per-ball outward angle (deg, measured from +X) and travel distance.
    # Front ball straight ahead; others fan symmetrically to both sides.
    specs = [
        (0.0, 3.1),      # apex (front) - head-on, fastest/farthest
        (28.0, 2.1),     # row1 left
        (-28.0, 2.0),    # row1 right
        (52.0, 1.5),     # row2 left
        (0.0, 1.1),      # row2 centre - lightly nudged forward
        (-52.0, 1.6),    # row2 right
    ]
    for k, (rx, ry) in enumerate(rack_positions):
        ang_deg, dist = specs[k]
        # Base outward direction: from apex toward this ball, blended with the
        # prescribed fan angle so the spread reads cleanly and plausibly.
        radial = Vector((rx, ry, 0.0)) - apex
        if radial.length < 1e-6:
            radial = Vector((1.0, 0.0, 0.0))
        radial.normalize()
        fan = Vector((math.cos(math.radians(ang_deg)), math.sin(math.radians(ang_deg)), 0.0))
        d = (0.45 * radial + 0.55 * fan)
        if d.length < 1e-6:
            d = Vector((1.0, 0.0, 0.0))
        d.normalize()
        scatter.append((d.x, d.y, dist))

    return {
        "scene": scene,
        "kind": "break_scatter_cluster",
        "cue": cue,
        "rack_balls": rack_balls,
        "rack_positions": rack_positions,
        "scatter": scatter,
    }


# ============================================================
# Animation
# ============================================================


def _cue_position(frame):
    """Cue ball center at the given frame.

    Phase 1 (1..IMPACT): rolls from CUE_START_X toward the apex, ease-in
    (accelerating toward the strike). Phase 2 (IMPACT..end): slows sharply and
    drifts a little forward and slightly off-axis (deflection), decelerating to
    rest by SETTLE_FRAME.
    """
    apex_x = RACK_APEX_X
    # Cue ball must stop one diameter behind the apex ball at contact so the
    # two spheres just touch (no interpenetration).
    contact_x = apex_x - 2.0 * BALL_RADIUS

    if frame <= IMPACT_FRAME:
        t = clamp01((frame - FRAME_START) / float(IMPACT_FRAME - FRAME_START))
        x = lerp(CUE_START_X, contact_x, ease_in_quad(t))
        return Vector((x, CUE_START_Y, BALL_Z))

    # After impact: small forward creep + slight deflection, decelerating.
    t = clamp01((frame - IMPACT_FRAME) / float(SETTLE_FRAME - IMPACT_FRAME))
    s = smooth01(t)
    x = lerp(contact_x, contact_x + 0.55, s)
    y = lerp(CUE_START_Y, -0.28, s)
    return Vector((x, y, BALL_Z))


def _rack_position(frame, k, rest_pos, sdir):
    """Rack ball k center at the given frame.

    Stationary until IMPACT, then scatters outward along sdir=(dx,dy,dist),
    decelerating (ease-out) to rest at rest + dist*dir by SETTLE_FRAME, and
    holding there afterward.
    """
    rx, ry = rest_pos
    dx, dy, dist = sdir

    if frame <= IMPACT_FRAME:
        return Vector((rx, ry, BALL_Z))

    t = clamp01((frame - IMPACT_FRAME) / float(SETTLE_FRAME - IMPACT_FRAME))
    # Ease-out (decelerating due to friction): fast right after impact, then
    # slowing to rest. 1-(1-t)^2 style.
    s = 1.0 - (1.0 - t) * (1.0 - t)
    x = rx + dx * dist * s
    y = ry + dy * dist * s
    return Vector((x, y, BALL_Z))


def animate_break_scatter_cluster(objs, frame):
    cue = objs["cue"]
    rack_balls = objs["rack_balls"]
    rack_positions = objs["rack_positions"]
    scatter = objs["scatter"]

    cpos = _cue_position(frame)
    cue.location = cpos
    cue.keyframe_insert(data_path="location", frame=frame)
    cue["pb_state"] = "cue_rolling" if frame <= IMPACT_FRAME else "cue_slowing"
    cue["pb_is_moving"] = bool(frame < SETTLE_FRAME)

    for k, ball in enumerate(rack_balls):
        pos = _rack_position(frame, k, rack_positions[k], scatter[k])
        ball.location = pos
        ball.keyframe_insert(data_path="location", frame=frame)
        if frame <= IMPACT_FRAME:
            ball["pb_state"] = "rack_stationary"
            ball["pb_is_moving"] = False
        elif frame < SETTLE_FRAME:
            ball["pb_state"] = "scattering"
            ball["pb_is_moving"] = True
        else:
            ball["pb_state"] = "scattered_at_rest"
            ball["pb_is_moving"] = False


def _setup_rigidbody_world(scene):
    if scene.rigidbody_world is None:
        bpy.ops.rigidbody.world_add()
    rw = scene.rigidbody_world
    if rw.collection is None:
        coll = bpy.data.collections.new("RigidBodyWorld")
        bpy.context.scene.collection.children.link(coll)
        rw.collection = coll
    rw.point_cache.frame_start = FRAME_START
    rw.point_cache.frame_end = FRAME_END
    try:
        rw.substeps_per_frame = 30
        rw.solver_iterations = 30
    except Exception:
        pass
    return rw


def _add_active_ball(obj, restitution=0.62):
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.rigidbody.object_add()
    rb = obj.rigid_body
    rb.type = "ACTIVE"
    rb.collision_shape = "SPHERE"
    rb.mass = 1.0
    rb.restitution = restitution
    rb.friction = 0.75
    rb.linear_damping = 0.45
    rb.angular_damping = 0.60
    return rb


def simulate_break(objs):
    """Real rigid-body break: the racked spheres collide and rebound off one
    another (SPHERE colliders => no interpenetration), then friction settles
    them. The cue is KINEMATIC during its approach and switches to DYNAMIC at
    impact, so its carried momentum transfers into the rack. The whole sim is
    baked to keyframes so the render harness just plays it back."""
    scene = objs["scene"]
    cue = objs["cue"]
    rack_balls = objs["rack_balls"]

    _setup_rigidbody_world(scene)

    # Passive floor collider so the balls roll on the table, never fall through.
    floor = bpy.data.objects.get("large_floor_base")
    if floor is not None:
        bpy.ops.object.select_all(action="DESELECT")
        bpy.context.view_layer.objects.active = floor
        floor.select_set(True)
        bpy.ops.rigidbody.object_add()
        floor.rigid_body.type = "PASSIVE"
        floor.rigid_body.collision_shape = "BOX"
        floor.rigid_body.friction = 0.5
        floor.rigid_body.restitution = 0.4

    # Rack balls: dynamic from frame 1 (resting, just-touching).
    for b in rack_balls:
        _add_active_ball(b, restitution=0.42)

    # Cue: kinematic approach (keyframed) -> dynamic at impact.
    _add_active_ball(cue, restitution=0.42)
    contact_x = RACK_APEX_X - 2.0 * BALL_RADIUS
    for f in range(FRAME_START, IMPACT_FRAME + 1):
        t = clamp01((f - FRAME_START) / float(IMPACT_FRAME - FRAME_START))
        x = lerp(CUE_START_X, contact_x, ease_in_quad(t))
        cue.location = (x, CUE_START_Y, BALL_Z)
        cue.keyframe_insert(data_path="location", frame=f)
        cue.rigid_body.kinematic = True
        cue.keyframe_insert(data_path="rigid_body.kinematic", frame=f)
    cue.rigid_body.kinematic = False
    cue.keyframe_insert(data_path="rigid_body.kinematic", frame=IMPACT_FRAME + 1)

    all_balls = list(rack_balls) + [cue]

    # Manually BAKE the sim: step frames sequentially (the rigid-body solver
    # evaluates on each frame_set), record each ball's simulated transform, then
    # switch the sim off and write the recorded motion as plain keyframes. The
    # bake_to_keyframes OPERATOR can't run in --background (it needs a 3D-view
    # context), so we do the bake by hand with only data-level keyframe_insert.
    deps = bpy.context.evaluated_depsgraph_get()
    rec = {b.name: {} for b in all_balls}
    for f in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(f)
        deps.update()
        for b in all_balls:
            mw = b.evaluated_get(deps).matrix_world
            rec[b.name][f] = (mw.translation.copy(), mw.to_euler().copy())

    for b in all_balls:
        b.animation_data_clear()
        if b.rigid_body is not None:
            b.rigid_body.kinematic = True   # follow keyframes, no re-simulation
        for f in range(FRAME_START, FRAME_END + 1):
            loc, rot = rec[b.name][f]
            b.location = loc
            b.rotation_euler = rot
            b.keyframe_insert(data_path="location", frame=f)
            b.keyframe_insert(data_path="rotation_euler", frame=f)
        b["pb_count_conserved"] = True
    scene.frame_set(FRAME_START)


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    if kind == "break_scatter_cluster":
        simulate_break(objs)
        scene.frame_set(FRAME_START)
        return

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        raise RuntimeError("Unknown kind: " + str(kind))


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

    if kind == "break_scatter_cluster":
        return build_break_scatter_cluster_scene()

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
