# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_U_TRACK_SMALL_HOLE_THEN_LARGE_HOLE_0046",
  "scene_kind": "small_then_large",
  "prompt": "A slightly large orange ball is released from the highest point of the left half of a roller-coaster style U-shaped track. The U bottom connects smoothly to a long horizontal platform extending to the right. On the platform there are three vertical barriers. The first barrier has a circular hole near the bottom whose bottom aligns with the ball bottom, but the hole diameter is only half of the ball diameter, so the ball cannot pass. On contact, the ball should rebound slightly, then gradually lose speed and come to rest just in front of the barrier by the end of the video; it must not freeze abruptly. The second barrier has a much larger circular hole with diameter twice the ball diameter. The third barrier is solid and has no hole. The ball motion must stay continuous and physically plausible."
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

# ---------------------------------------------------------------------
# Core scene geometry
# ---------------------------------------------------------------------
BALL_RADIUS = 0.30  # intentionally slightly larger
PLATFORM_TOP_Z = 0.40
BALL_CENTER_FLAT_Z = PLATFORM_TOP_Z + BALL_RADIUS

U_CENTER_X = -3.80
U_CENTER_Z = 1.90
U_RADIUS = 1.50

U_TOP_X = U_CENTER_X - U_RADIUS
# U_TOP_Z / U_BOTTOM_Z are track CONTACT SURFACE heights.
# The ball center is always contact_surface_z + BALL_RADIUS.
U_TOP_Z = U_CENTER_Z
U_BOTTOM_X = U_CENTER_X
U_BOTTOM_Z = U_CENTER_Z - U_RADIUS  # equals PLATFORM_TOP_Z, smoothly matches platform top

TRACK_RAIL_Y_OFFSET = 0.17
TRACK_RAIL_RADIUS = 0.045
TRACK_TIE_Z = BALL_CENTER_FLAT_Z - BALL_RADIUS + 0.02

FLAT_END_X = 5.10

BARRIER_WIDTH_Y = 1.40
BARRIER_THICK_X = 0.12
BARRIER_HEIGHT_Z = 1.70

BARRIER_XS = [-0.70, 1.60, 3.90]

BALL_DIAMETER = 2.0 * BALL_RADIUS
SMALL_HOLE_DIAMETER = BALL_DIAMETER * 0.5
LARGE_HOLE_DIAMETER = BALL_DIAMETER * 2.0

# Motion tuning
ARC_END_FRAME = 40
FLAT_SPEED = 0.112

# Collision settling
SETTLE_BACK = 0.35   # visible elastic rebound (~1.2 ball radii), matching G03
REBOUND_SETTLE_FRAMES = 14


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
        "dynamic_object" if is_dynamic else ("static_solid" if solid else "non_solid_marker"),
        "cube",
        color_name,
        is_dynamic,
        solid=solid,
    )
    return obj


def add_cylinder(name, location, radius, depth, rotation, material, role, color_name, is_dynamic=False, solid=True):
    bpy.ops.mesh.primitive_cylinder_add(
        radius=radius,
        depth=depth,
        location=location,
        rotation=rotation,
        vertices=32,
    )
    obj = bpy.context.object
    obj.name = name

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


def add_uv_sphere(name, location, radius, material, color_name):
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=radius,
        location=location,
        segments=48,
        ring_count=24,
    )
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


def cylinder_between(name, p1, p2, radius, material, role, color_name):
    p1 = Vector(p1)
    p2 = Vector(p2)
    mid = (p1 + p2) / 2.0
    vec = p2 - p1
    depth = vec.length

    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, location=mid, vertices=20)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_mode = 'QUATERNION'
    obj.rotation_quaternion = vec.to_track_quat('Z', 'Y')
    obj.rotation_mode = 'XYZ'

    if material is not None:
        obj.data.materials.append(material)

    tag(obj, name, role, "static_solid", "cylinder", color_name, False, solid=True)
    return obj


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), roughness=0.85)
    MATS["platform"] = make_mat("mat_platform", (0.56, 0.57, 0.60), roughness=0.62)
    MATS["rail"] = make_mat("mat_rail", (0.44, 0.44, 0.46), roughness=0.45, metallic=0.10)
    MATS["tie"] = make_mat("mat_tie", (0.32, 0.34, 0.37), roughness=0.76)
    MATS["barrier"] = make_mat("mat_barrier", (0.70, 0.72, 0.75), roughness=0.55)
    MATS["ball"] = make_mat("mat_ball", (1.00, 0.46, 0.06), roughness=0.24)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.92)


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
        scene.view_settings.exposure = 0.0
        scene.view_settings.gamma = 1.0
    except Exception:
        pass


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (13.0, 6.5, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.0, 2.0), (13.0, 0.08, 4.0), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-4.8, -4.8, 6.4))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 1150
    key.data.size = 7.0

    bpy.ops.object.light_add(type="POINT", location=(4.2, -2.8, 4.2))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 170

    return scene


def setup_camera(scene):
    # Pull the camera farther back and move it to the +X side a bit
    # so we can see the RIGHT side of the barriers instead of only a flat frontal view.
    bpy.ops.object.camera_add(location=(3.20, -11.40, 4.90))
    cam = bpy.context.object
    cam.name = "camera_u_track_hole_barriers"
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 10.8
    cam.data.dof.use_dof = False
    look_at(cam, (-0.10, 0.0, 0.98))
    scene.camera = cam


def sample_centerline_points():
    pts = []

    # Left half U-shaped centerline
    n_arc = 22
    for i in range(n_arc + 1):
        theta = math.pi + (math.pi * 0.5) * (i / float(n_arc))
        x = U_CENTER_X + U_RADIUS * math.cos(theta)
        z = U_CENTER_Z + U_RADIUS * math.sin(theta)
        pts.append((x, z))

    # Horizontal extension
    n_flat = 28
    for i in range(1, n_flat + 1):
        x = lerp(U_BOTTOM_X, FLAT_END_X, i / float(n_flat))
        z = U_BOTTOM_Z
        pts.append((x, z))

    return pts


def build_track_and_platform():
    # Long platform deck to the right from the U bottom.
    add_cube(
        "horizontal_long_platform",
        ((U_BOTTOM_X + FLAT_END_X) / 2.0, 0.0, PLATFORM_TOP_Z / 2.0),
        (FLAT_END_X - U_BOTTOM_X + 0.2, 1.65, PLATFORM_TOP_Z),
        MATS["platform"],
        "platform",
        "gray",
    )

    pts = sample_centerline_points()

    # Two rails
    for side_idx, yoff in enumerate([-TRACK_RAIL_Y_OFFSET, TRACK_RAIL_Y_OFFSET], start=1):
        for i in range(len(pts) - 1):
            # pts[i][1] is the CONTACT SURFACE height.
            # Put the rail cylinder just under it, so the rail top is tangent to the ball bottom.
            p1 = (pts[i][0], yoff, pts[i][1] - TRACK_RAIL_RADIUS)
            p2 = (pts[i + 1][0], yoff, pts[i + 1][1] - TRACK_RAIL_RADIUS)
            cylinder_between(
                f"rail_{side_idx}_{i:02d}",
                p1,
                p2,
                TRACK_RAIL_RADIUS,
                MATS["rail"],
                "track_rail",
                "gray",
            )

    # Cross ties
    for i in range(0, len(pts), 2):
        x, z = pts[i]
        # Cross ties sit below the rail contact surface.
        add_cube(
            f"track_tie_{i:02d}",
            (x, 0.0, z - 0.10),
            (0.10, TRACK_RAIL_Y_OFFSET * 2.7, 0.05),
            MATS["tie"],
            "track_tie",
            "dark_gray",
        )

    # Some vertical supports
    for idx in [3, 8, 13, 18]:
        if idx < len(pts):
            x, z = pts[idx]
            support_top_z = max(0.10, z - 0.12)
            add_cube(
                f"track_support_{idx:02d}",
                (x, 0.0, support_top_z / 2.0),
                (0.10, 0.10, support_top_z),
                MATS["tie"],
                "track_support",
                "dark_gray",
            )


def make_barrier_with_optional_hole(name, x, hole_diameter=None):
    body = add_cube(
        name,
        (x, 0.0, BARRIER_HEIGHT_Z / 2.0),
        (BARRIER_THICK_X, BARRIER_WIDTH_Y, BARRIER_HEIGHT_Z),
        MATS["barrier"],
        "barrier",
        "light_gray",
        solid=True,
    )

    body["pb_barrier_x"] = x
    body["pb_barrier_type"] = "solid" if hole_diameter is None else "hole_barrier"

    if hole_diameter is None:
        body["pb_hole_diameter"] = 0.0
        return body

    hole_radius = hole_diameter / 2.0
    hole_center_z = PLATFORM_TOP_Z + hole_radius  # hole bottom aligns with ball bottom

    bpy.ops.mesh.primitive_cylinder_add(
        radius=hole_radius,
        depth=BARRIER_THICK_X * 3.0,
        location=(x, 0.0, hole_center_z),
        rotation=(0.0, math.pi / 2.0, 0.0),
        vertices=48,
    )
    cutter = bpy.context.object
    cutter.name = f"{name}_hole_cutter"

    mod = body.modifiers.new(name="hole_boolean", type='BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.object = cutter

    bpy.context.view_layer.objects.active = body
    body.select_set(True)
    try:
        bpy.ops.object.modifier_apply(modifier=mod.name)
    except Exception:
        pass

    # IMPORTANT:
    # Do NOT use selection-based bpy.ops.object.delete() here.
    # After applying the boolean, the barrier body may still be selected.
    # Selection deletion can delete the barrier body itself, causing:
    #   ReferenceError: StructRNA of type Object has been removed
    # Remove only the cutter object directly.
    try:
        bpy.data.objects.remove(cutter, do_unlink=True)
    except ReferenceError:
        pass

    body["pb_hole_diameter"] = float(hole_diameter)
    body["pb_hole_bottom_z"] = float(PLATFORM_TOP_Z)
    body["pb_hole_center_z"] = float(hole_center_z)

    return body


def build_barriers():
    if CASE["scene_kind"] == "small_then_large":
        hole_list = [SMALL_HOLE_DIAMETER, LARGE_HOLE_DIAMETER, None]
    elif CASE["scene_kind"] == "large_then_small":
        hole_list = [LARGE_HOLE_DIAMETER, SMALL_HOLE_DIAMETER, None]
    else:
        raise RuntimeError("Unknown scene kind: " + str(CASE["scene_kind"]))

    barriers = []
    names = ["barrier_01", "barrier_02", "barrier_03"]
    for i, (x, hole_d) in enumerate(zip(BARRIER_XS, hole_list)):
        barriers.append(make_barrier_with_optional_hole(names[i], x, hole_d))
    return barriers


def build_ball():
    # Start tangent on the CONCAVE side of the arc, identical to the frame-1 animated pose
    # (raw_arc_position at FRAME_START) so the rest pose and first keyframe agree.
    start_x, start_z, _ = raw_arc_position(FRAME_START)
    return add_uv_sphere(
        "target_orange_ball",
        (start_x, 0.0, start_z),
        BALL_RADIUS,
        MATS["ball"],
        "orange",
    )


def build_scene():
    scene = build_base_scene()
    setup_camera(scene)
    build_track_and_platform()
    barriers = build_barriers()
    ball = build_ball()

    return {
        "scene": scene,
        "ball": ball,
        "barriers": barriers,
    }


def barrier_contact_center_x(barrier_obj):
    bx = float(barrier_obj["pb_barrier_x"])
    return bx - (BARRIER_THICK_X / 2.0) - BALL_RADIUS


def raw_arc_position(frame):
    # Accelerating down the left half U.
    u = clamp01((frame - FRAME_START) / float(ARC_END_FRAME - FRAME_START))
    s = u ** 1.85
    theta = math.pi + (math.pi * 0.5) * s
    # The ball rolls on the CONCAVE side of the arc, so its center must sit one ball-radius
    # inward along the SURFACE NORMAL (radially toward the arc center) — i.e. on the circle
    # of radius (U_RADIUS - BALL_RADIUS).
    roll_radius = U_RADIUS - BALL_RADIUS
    x = U_CENTER_X + roll_radius * math.cos(theta)
    z = U_CENTER_Z + roll_radius * math.sin(theta)
    return x, z, theta


def raw_flat_center_x(frame):
    # Continue to the right with stable velocity after leaving the U bottom.
    return U_BOTTOM_X + FLAT_SPEED * (frame - ARC_END_FRAME)


def animate_small_then_large(scene, ball, barriers):
    # Barrier 1 is small hole, barrier 2 is large hole, barrier 3 solid.
    block_barrier = barriers[0]
    pass_barrier = barriers[1]
    contact_x = barrier_contact_center_x(block_barrier)

    # Determine the frame where raw motion first reaches the blocking barrier.
    contact_frame = None
    for frame in range(ARC_END_FRAME, FRAME_END + 1):
        if raw_flat_center_x(frame) >= contact_x:
            contact_frame = frame
            break
    if contact_frame is None:
        contact_frame = FRAME_END

    settle_end_frame = min(FRAME_END, contact_frame + REBOUND_SETTLE_FRAMES)

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= ARC_END_FRAME:
            x, z, theta = raw_arc_position(frame)
            rot_y = -(theta - math.pi) * (U_RADIUS / BALL_RADIUS)
            state = "rolling_down_left_u_track"
        elif frame < contact_frame:
            x = raw_flat_center_x(frame)
            z = BALL_CENTER_FLAT_Z
            dist = (U_BOTTOM_X - U_TOP_X) + (x - U_BOTTOM_X)
            rot_y = -(dist / BALL_RADIUS)
            if x + BALL_RADIUS < BARRIER_XS[1] - BARRIER_THICK_X / 2.0:
                state = "rolling_on_horizontal_platform_toward_small_hole_barrier"
            else:
                state = "still_before_large_hole_barrier_but_will_never_reach_it"
        elif frame <= settle_end_frame:
            t = (frame - contact_frame) / float(max(1, settle_end_frame - contact_frame))
            rebound_progress = 1.0 - (1.0 - clamp01(t)) ** 2
            x = lerp(contact_x, contact_x - SETTLE_BACK, rebound_progress)
            z = BALL_CENTER_FLAT_Z
            dist = (U_BOTTOM_X - U_TOP_X) + (x - U_BOTTOM_X)
            rot_y = -(dist / BALL_RADIUS)
            state = "rebounding_and_gradually_decelerating_after_small_hole_collision"
        else:
            x = contact_x - SETTLE_BACK
            z = BALL_CENTER_FLAT_Z
            dist = (U_BOTTOM_X - U_TOP_X) + (x - U_BOTTOM_X)
            rot_y = -(dist / BALL_RADIUS)
            state = "stopped_at_small_hole_barrier"

        ball.location = (x, 0.0, z)
        ball.rotation_euler = (0.0, rot_y, 0.0)
        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)

        ball["pb_state"] = state
        ball["pb_ball_diameter"] = BALL_DIAMETER
        ball["pb_small_hole_diameter"] = SMALL_HOLE_DIAMETER
        ball["pb_large_hole_diameter"] = LARGE_HOLE_DIAMETER

    scene.frame_set(FRAME_START)


def animate_large_then_small(scene, ball, barriers):
    # Barrier 1 is large hole (pass), barrier 2 is small hole (block), barrier 3 solid.
    pass_barrier = barriers[0]
    block_barrier = barriers[1]
    contact_x = barrier_contact_center_x(block_barrier)

    contact_frame = None
    for frame in range(ARC_END_FRAME, FRAME_END + 1):
        if raw_flat_center_x(frame) >= contact_x:
            contact_frame = frame
            break
    if contact_frame is None:
        contact_frame = FRAME_END

    settle_end_frame = min(FRAME_END, contact_frame + REBOUND_SETTLE_FRAMES)

    pass_threshold_enter = BARRIER_XS[0] - BARRIER_THICK_X / 2.0 - BALL_RADIUS
    pass_threshold_exit = BARRIER_XS[0] + BARRIER_THICK_X / 2.0 + BALL_RADIUS

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= ARC_END_FRAME:
            x, z, theta = raw_arc_position(frame)
            rot_y = -(theta - math.pi) * (U_RADIUS / BALL_RADIUS)
            state = "rolling_down_left_u_track"
        elif frame < contact_frame:
            x = raw_flat_center_x(frame)
            z = BALL_CENTER_FLAT_Z
            dist = (U_BOTTOM_X - U_TOP_X) + (x - U_BOTTOM_X)
            rot_y = -(dist / BALL_RADIUS)

            if x < pass_threshold_enter:
                state = "rolling_on_horizontal_platform_toward_large_hole_barrier"
            elif x <= pass_threshold_exit:
                state = "passing_through_large_hole_barrier"
            else:
                state = "past_large_hole_now_heading_to_small_hole_barrier"
        elif frame <= settle_end_frame:
            t = (frame - contact_frame) / float(max(1, settle_end_frame - contact_frame))
            rebound_progress = 1.0 - (1.0 - clamp01(t)) ** 2
            x = lerp(contact_x, contact_x - SETTLE_BACK, rebound_progress)
            z = BALL_CENTER_FLAT_Z
            dist = (U_BOTTOM_X - U_TOP_X) + (x - U_BOTTOM_X)
            rot_y = -(dist / BALL_RADIUS)
            state = "rebounding_and_gradually_decelerating_after_second_small_hole_collision"
        else:
            x = contact_x - SETTLE_BACK
            z = BALL_CENTER_FLAT_Z
            dist = (U_BOTTOM_X - U_TOP_X) + (x - U_BOTTOM_X)
            rot_y = -(dist / BALL_RADIUS)
            state = "stopped_at_second_small_hole_barrier"

        ball.location = (x, 0.0, z)
        ball.rotation_euler = (0.0, rot_y, 0.0)
        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)

        ball["pb_state"] = state
        ball["pb_ball_diameter"] = BALL_DIAMETER
        ball["pb_small_hole_diameter"] = SMALL_HOLE_DIAMETER
        ball["pb_large_hole_diameter"] = LARGE_HOLE_DIAMETER

    scene.frame_set(FRAME_START)


def animate_scene(objs):
    scene = objs["scene"]
    ball = objs["ball"]
    barriers = objs["barriers"]

    if CASE["scene_kind"] == "small_then_large":
        animate_small_then_large(scene, ball, barriers)
    elif CASE["scene_kind"] == "large_then_small":
        animate_large_then_small(scene, ball, barriers)
    else:
        raise RuntimeError("Unknown scene kind: " + str(CASE["scene_kind"]))


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
    render_png(scene, 70, OPTIONAL_FRAME_PATH)
    render_png(scene, 120, OPTIONAL_FRAME_02B_PATH)

    render_animation(scene)
    write_task_json()
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("scene_kind:", CASE["scene_kind"])
    print("BALL_RADIUS:", BALL_RADIUS)
    print("SMALL_HOLE_DIAMETER:", SMALL_HOLE_DIAMETER)
    print("LARGE_HOLE_DIAMETER:", LARGE_HOLE_DIAMETER)
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
