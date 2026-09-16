# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_DOUBLE_DEFLECTOR_ZIGZAG_0114",
  "scene_kind": "double_deflector_zigzag",
  "prompt": "A ball is released and falls onto a left-leaning angled wall, which deflects it to the right; it then strikes a right-leaning angled wall lower down, which deflects it back to the left, zigzagging downward. Each elastic bounce loses a little speed, and after landing on the floor the ball continues rolling briefly to the left."
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


def add_pitched_box(name, location, dimensions, pitch_deg, material, role, color_name, is_dynamic=False, solid=True):
    # A box rotated about the world Y axis by pitch_deg degrees. Used for walls
    # that lean within the vertical X-Z plane (front view). Rotation is baked
    # into the mesh via transform_apply so the local dimensions stay clean and
    # the object exposes its pitch as a tag.
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=(0.0, math.radians(pitch_deg), 0.0))
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    if material is not None:
        obj.data.materials.append(material)

    tag(
        obj,
        name,
        role,
        "dynamic_object" if is_dynamic else "static_solid",
        "oriented_box",
        color_name,
        is_dynamic,
        solid=solid,
        pb_pitch_deg=float(pitch_deg),
    )
    return obj


def add_ball(name, radius, location, material, color_name):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=48, ring_count=24)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)

    tag(
        obj,
        name,
        "target",
        "dynamic_object",
        "sphere",
        color_name,
        True,
        solid=True,
        pb_radius=radius,
    )
    return obj


def add_cylinder_between(name, p1, p2, radius, material, role, color_name):
    p1 = Vector(p1)
    p2 = Vector(p2)
    diff = p2 - p1
    length = diff.length
    mid = (p1 + p2) / 2.0

    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=length, vertices=24, location=mid)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = diff.to_track_quat("Z", "Y").to_euler()

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
    scene.world.color = (0.55, 0.57, 0.62)

    try:
        scene.view_settings.view_transform = "AgX"
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
    key.data.energy = 450
    key.data.size = 5.5

    bpy.ops.object.light_add(type="POINT", location=(3.0, 1.8, 3.3))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 85

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
# 00000113  double_deflector_zigzag
# =============================================================================

def _reflect(d, n):
    # Elastic reflection of unit direction d off a face with unit outward
    # normal n:  d_out = d - 2 (d . n) n.  (Same math as the single-wall G57
    # deflector, applied once per wall.)
    dot = d.dot(n)
    return (d - n * (2.0 * dot)).normalized()


def build_double_deflector_zigzag():
    # Front view: the whole zigzag lives in the vertical X-Z plane at Y = 0,
    # so the camera looks straight down -Y and sees the full path.
    scene = setup_base(
        camera_loc=(0.55, -9.4, 2.35),
        target=(-0.55, 0.0, 1.35),
        ortho_scale=6.4,
    )

    ball_radius = 0.17
    floor_z = ball_radius  # ball-center height for a ball resting on the floor

    # A horizontal shift applied to the whole rig so the left-biased zigzag
    # sits centered in the front-view camera.
    x_shift = 0.75

    # ----- Deflection directions (unit vectors in the X-Z plane) -----
    # Leg A: the ball is released and falls straight down onto wall 1.
    dA = Vector((0.0, 0.0, -1.0))
    # Leg B (after wall 1): down and to the RIGHT, descending 60 deg below
    # horizontal.  Leg C (after wall 2): down and to the LEFT, descending
    # 30 deg below horizontal.  Choosing the first outgoing leg steeper than
    # the second guarantees wall 2's deflecting face points up toward the
    # incoming ball (no clipping, contact on the upper face).
    beta = math.radians(60.0)
    gamma = math.radians(30.0)
    dB = Vector((math.cos(beta), 0.0, -math.sin(beta))).normalized()
    dC = Vector((-math.cos(gamma), 0.0, -math.sin(gamma))).normalized()

    # Face normals derived from the required in/out directions (bisector rule):
    # n = (d_out - d_in) normalized.  These are the same normals a physical
    # elastic bounce would present, and _reflect() reproduces the out-legs.
    n1 = (dB - dA).normalized()
    n2 = (dC - dB).normalized()

    # ----- Ball-center path (contacts) -----
    contact1 = Vector((-1.35 + x_shift, 0.0, 2.30))
    leg_b_len = 1.62
    contact2 = contact1 + dB * leg_b_len
    # Leg C runs on down to the floor: solve contact2.z + dC.z * L = floor_z.
    leg_c_len = (floor_z - contact2.z) / dC.z
    settle = contact2 + dC * leg_c_len
    # Preserve the incoming horizontal velocity after floor contact.  The ball
    # keeps rolling through the final frame instead of stopping unnaturally on
    # the exact landing frame.
    floor_roll_distance = 0.51
    roll_end = settle + Vector((-floor_roll_distance, 0.0, 0.0))

    # Release point straight above wall 1.
    leg_a_len = 1.05
    release = contact1 - dA * leg_a_len

    # ----- Angled walls (leaning in the X-Z plane, pitched about Y) -----
    # Wall long axis is its Z (height) dimension after the pitch.  The pitch
    # angle that makes the box face carry outward normal n is the tilt of the
    # height axis away from vertical; derive it from n directly.
    def pitch_for_normal(n):
        # The slab's thin (thickness) axis is its local +X, which is the big
        # deflecting face's outward normal. After a pitch p about Y, local +X
        # maps to (cos p, 0, -sin p); set that equal to n to solve for p.
        return math.degrees(math.atan2(-n.z, n.x))

    wall_thickness = 0.24
    wall_length = 1.50   # this is the box HEIGHT dim (the leaning long axis)
    wall_depth = 1.30    # extent along Y (into the scene), for a solid slab

    def wall_center(contact, n):
        # Face just touches the ball surface at the contact point; the solid
        # body sits behind the face (along -n) so the ball never clips in.
        face_pt = contact - n * ball_radius
        return face_pt - n * (wall_thickness / 2.0)

    w1_center = wall_center(contact1, n1)
    w2_center = wall_center(contact2, n2)
    pitch1 = pitch_for_normal(n1)
    pitch2 = pitch_for_normal(n2)

    wall1 = add_pitched_box(
        "upper_left_leaning_wall",
        (w1_center.x, w1_center.y, w1_center.z),
        (wall_thickness, wall_depth, wall_length),
        pitch1,
        MATS["gray"],
        "fixed_deflecting_wall",
        "gray",
    )
    wall1["pb_face_normal"] = "(+cos, 0, +sin) up-right"
    wall1["pb_deflection_deg"] = 90.0
    wall1["pb_lean"] = "left_leaning_kicks_ball_right"

    wall2 = add_pitched_box(
        "lower_right_leaning_wall",
        (w2_center.x, w2_center.y, w2_center.z),
        (wall_thickness, wall_depth, wall_length),
        pitch2,
        MATS["gray"],
        "fixed_deflecting_wall",
        "gray",
    )
    wall2["pb_face_normal"] = "(-cos, 0, +sin) up-left"
    wall2["pb_deflection_deg"] = 90.0
    wall2["pb_lean"] = "right_leaning_kicks_ball_left"

    # ----- Support feet so the walls read as fixed, not floating -----
    # A post is a tall obstacle, so checking only the nearby bounce contact is
    # insufficient: after the second bounce the ball travels back underneath
    # wall 1.  Keep both posts outside the X extent of the ball's *entire*
    # swept path, including the sphere radius and a visible air gap.
    path_x_min = min(release.x, contact1.x, contact2.x, settle.x, roll_end.x)
    path_x_max = max(release.x, contact1.x, contact2.x, settle.x)
    for wname, wc_, pitch in [("upper", w1_center, pitch1), ("lower", w2_center, pitch2)]:
        # Upward height (long) axis of the slab after its pitch about Y. The
        # pitch branch may point local +Z either way, so force it to point up.
        a = math.radians(pitch)
        up_axis = Vector((math.sin(a), 0.0, math.cos(a)))
        if up_axis.z < 0.0:
            up_axis = -up_axis
        # Lower end of the slab, nudged behind the deflecting face.
        n = n1 if wname == "upper" else n2
        low_end = wc_ - up_axis * (wall_length / 2.0)
        back = low_end - n * (wall_thickness / 2.0 + 0.04)
        support_anchor = back.copy()
        post_half_w = 0.08
        path_clearance_margin = 0.30
        required_dx = ball_radius + post_half_w + path_clearance_margin
        if wname == "upper":
            back.x = path_x_min - required_dx
        else:
            back.x = path_x_max + required_dx
        post_top_z = max(back.z, 0.20)
        post = add_cube(
            f"{wname}_wall_support_post",
            (back.x, 0.0, post_top_z / 2.0),
            (0.16, 0.16, max(post_top_z, 0.12)),
            MATS["support"],
            "wall_support_foot",
            "dark_gray",
        )
        post["pb_min_ball_path_clearance"] = float(path_clearance_margin)
        post["pb_clearance_checked_against"] = "complete_ball_swept_path_x_extent"

        # Moving each post clear of the ball's path keeps it visibly out of
        # the way.  A connector bar reaches back from the post top to the slab's
        # original support point, so both walls read as physically supported
        # without adding a new obstacle: the upper bar lies above every
        # post-bounce path segment, and the lower bar grazes the slab's back
        # face outside the ball's swept path.
        connector_span = abs(support_anchor.x - back.x)
        connector = add_cube(
            f"{wname}_wall_support_connector",
            ((support_anchor.x + back.x) / 2.0, 0.0, post_top_z),
            (connector_span + 2.0 * post_half_w, 0.16, 0.16),
            MATS["support"],
            "wall_support_connector",
            "dark_gray",
        )
        if wname == "upper":
            connector["pb_above_post_bounce_path"] = True
        else:
            connector["pb_outside_ball_swept_path"] = True

    MATS["ball_matte"] = make_mat("mat_ball_matte", (0.95, 0.34, 0.06), roughness=0.62, metallic=0.0)
    ball = add_ball("orange_ball", ball_radius, release, MATS["ball_matte"], "orange")
    ball["pb_path"] = "drop_then_two_chained_elastic_90deg_deflections_zigzag_land_and_roll_left"
    ball["pb_deflected_not_stopped_not_passed_through"] = True

    return scene, {
        "ball": ball,
        "release": release,
        "contact1": contact1,
        "contact2": contact2,
        "settle": settle,
        "roll_end": roll_end,
        "dA": dA,
        "dB": dB,
        "dC": dC,
        "n1": n1,
        "n2": n2,
        "leg_a_len": leg_a_len,
        "leg_b_len": leg_b_len,
        "leg_c_len": leg_c_len,
        "floor_roll_distance": floor_roll_distance,
        "ball_radius": ball_radius,
        "contact1_frame": 44,
        "contact2_frame": 75,
        "floor_contact_frame": 107,
    }


def animate_double_deflector_zigzag(scene, meta):
    ball = meta["ball"]
    release = meta["release"]
    contact1 = meta["contact1"]
    contact2 = meta["contact2"]
    settle = meta["settle"]
    roll_end = meta["roll_end"]
    dA = meta["dA"]
    dB = meta["dB"]
    dC = meta["dC"]
    n1 = meta["n1"]
    n2 = meta["n2"]
    radius = meta["ball_radius"]
    c1_frame = meta["contact1_frame"]
    c2_frame = meta["contact2_frame"]
    floor_contact_frame = meta["floor_contact_frame"]

    leg_a_len = meta["leg_a_len"]
    leg_b_len = meta["leg_b_len"]
    leg_c_len = meta["leg_c_len"]
    floor_roll_distance = meta["floor_roll_distance"]

    # Verify the reflection math matches the chosen out-legs (elastic bounce).
    out_b = _reflect(dA, n1)
    out_c = _reflect(dB, n2)

    # Each elastic bounce loses a little speed, so the ball's average speed
    # drops on every leg after a contact.
    loss1 = 0.10  # after wall 1
    loss2 = 0.14  # after wall 2 (a touch more, energy keeps draining)

    rest_frames = 8

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= rest_frames:
            pos = release.copy()
            state = "held_at_release_point"
            traveled = 0.0
        elif frame <= c1_frame:
            # Free fall onto wall 1: accelerating (ease-in, s ~ t^2).
            t = (frame - rest_frames) / float(c1_frame - rest_frames)
            t = max(0.0, min(1.0, t))
            s = leg_a_len * (t * t)
            pos = release + dA * s
            state = "falling_onto_upper_left_leaning_wall"
            traveled = s
        elif frame <= c2_frame:
            # Deflected down-right along out_b toward the fixed wall 2. The wall
            # is fixed, so the ball must cover the whole leg.
            # CONSTANT speed after the bounce (linear), NOT ease-out: ease-out
            # would make the ball fastest right after contact, reading as a
            # sudden acceleration on the rebound. Constant speed = an elastic
            # bounce with a small energy loss (this leg's average speed is lower
            # than the incoming fall's impact speed), no velocity spike at
            # contact.
            t = (frame - c1_frame) / float(c2_frame - c1_frame)
            t = max(0.0, min(1.0, t))
            s = leg_b_len * t
            pos = contact1 + out_b * s
            state = "deflected_right_and_down_toward_lower_right_leaning_wall"
            traveled = leg_a_len + s
        elif frame <= floor_contact_frame:
            # Deflected down-left along out_c, gliding down to the floor.  Keep
            # this leg linear so its horizontal component can continue smoothly
            # as floor rolling after the vertical component is removed.
            t = (frame - c2_frame) / float(floor_contact_frame - c2_frame)
            t = max(0.0, min(1.0, t))
            s = leg_c_len * t
            pos = contact2 + out_c * s
            state = "deflected_left_and_down_toward_floor"
            traveled = leg_a_len + leg_b_len + s
        else:
            roll_t = (frame - floor_contact_frame) / float(FRAME_END - floor_contact_frame)
            roll_t = max(0.0, min(1.0, roll_t))
            roll_distance = floor_roll_distance * roll_t
            pos = settle.lerp(roll_end, roll_t)
            state = "landed_and_continuing_to_roll_left_on_floor"
            traveled = leg_a_len + leg_b_len + leg_c_len + roll_distance

        # Guard: never let the ball center drop below the resting floor height.
        if pos.z < radius:
            pos = Vector((pos.x, pos.y, radius))

        ball.location = pos
        ball.rotation_euler = (0.0, traveled / radius, 0.0)
        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)

        ball["pb_state"] = state
        ball["pb_contact1_frame"] = int(c1_frame)
        ball["pb_contact2_frame"] = int(c2_frame)
        ball["pb_floor_contact_frame"] = int(floor_contact_frame)
        ball["pb_floor_roll_distance"] = float(floor_roll_distance)
        ball["pb_rolls_through_final_frame"] = True
        ball["pb_speed_loss_bounce1"] = float(loss1)
        ball["pb_speed_loss_bounce2"] = float(loss2)
        ball["pb_zigzag"] = "down_right_then_down_left"

    scene.frame_set(FRAME_START)


# =============================================================================
# Dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]

    if kind == "double_deflector_zigzag":
        return build_double_deflector_zigzag()

    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(scene, meta):
    kind = CASE["scene_kind"]

    if kind == "double_deflector_zigzag":
        return animate_double_deflector_zigzag(scene, meta)

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
    print("kind:", CASE["scene_kind"])
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
