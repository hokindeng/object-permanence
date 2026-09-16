# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_SERPENTINE_RAMP_TUNNEL_0101",
  "scene_kind": "serpentine_ramp_tunnel",
  "kind": "serpentine_ramp_tunnel",
  "prompt": "A ball rolls down a blue S-shaped serpentine ramp with three switchback segments. The middle switchback is enclosed by an opaque gray housing. The ball enters the housing's upper opening, traverses the hidden zigzag inside, and re-emerges from the lower opening, continuing to the floor. The ball keeps its identity and reappears at a time consistent with the hidden path length."
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


def make_mat(name, color, roughness=0.55, metallic=0.0, alpha=1.0, transparent=False):
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

    if transparent:
        # Order-INDEPENDENT transparency (HASHED / DITHERED). BLEND sorting made
        # the opaque ramp behind the glass flicker/vanish for a frame; hashed
        # transparency has no sort order and TAA (64 samples) resolves it smooth.
        # alpha<0.999 also makes the render pipeline preserve it (not recolor it).
        try:
            mat.blend_method = "HASHED"
            mat.show_transparent_back = False
            mat.use_screen_refraction = False
        except Exception:
            pass
        try:
            mat.surface_render_method = "DITHERED"
        except Exception:
            pass

    return mat


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), roughness=0.85)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.92)

    MATS["gray"] = make_mat("mat_gray", (0.62, 0.63, 0.66), roughness=0.75)
    MATS["housing"] = make_mat("mat_housing", (0.32, 0.33, 0.37), roughness=0.85)
    MATS["dark"] = make_mat("mat_dark", (0.18, 0.20, 0.24), roughness=0.55)
    MATS["support"] = make_mat("mat_support", (0.16, 0.18, 0.22), roughness=0.60)

    MATS["red"] = make_mat("mat_red", (0.92, 0.18, 0.18), roughness=0.28)
    MATS["blue"] = make_mat("mat_blue", (0.16, 0.36, 0.95), roughness=0.28)
    MATS["yellow"] = make_mat("mat_yellow", (0.98, 0.78, 0.15), roughness=0.28)
    MATS["orange"] = make_mat("mat_orange", (0.97, 0.45, 0.10), roughness=0.28)
    MATS["glass"] = make_mat("mat_glass", (0.60, 0.80, 1.0), roughness=0.08, alpha=0.24, transparent=True)


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


def add_sphere(name, radius, location, material, color_name, role="target", is_dynamic=True):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=48, ring_count=24)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)

    tag(
        obj,
        name,
        role,
        "dynamic_object" if is_dynamic else "static_solid",
        "sphere",
        color_name,
        is_dynamic,
        solid=True,
        pb_radius=radius,
    )
    return obj


def add_cylinder(name, location, radius, depth, material, role, color_name, rotation=(0.0, 0.0, 0.0), is_dynamic=False):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, vertices=24, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    if material is not None:
        obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "cylinder", color_name, is_dynamic, solid=True)
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


def add_oriented_box(name, location, dimensions, material, role, color_name, rotation=(0.0, 0.0, 0.0), is_dynamic=False, solid=True):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.rotation_euler = rotation

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
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Base Contrast"
    except Exception:
        try:
            scene.view_settings.view_transform = "Standard"
            scene.view_settings.look = "None"
        except Exception:
            pass


def setup_base(camera_loc, target, ortho_scale):
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (12.0, 8.0, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.55, 2.05), (12.0, 0.08, 4.1), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-2.8, -4.5, 6.4))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 600
    key.data.size = 7.0

    bpy.ops.object.light_add(type="POINT", location=(3.0, 1.8, 3.6))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 140

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
# 00000100  serpentine_ramp_tunnel  (Cluster: Baillargeonian Occlusion)
# =============================================================================
#
# The descent is a serpentine of THREE banked switchback segments. Each segment
# is a flat ramp slab; consecutive segments reverse the X-direction
# (switchbacks), so the ball traces an S as it descends:
#
#     seg A (top):    runs left  -> right, z_top     -> z_join_ab
#     seg B (middle): runs right -> left,  z_join_ab -> z_join_bc   <-- HIDDEN
#     seg C (bottom): runs left  -> right, z_join_bc -> floor
#
# An opaque gray HOUSING box covers the middle stretch of segment B. The ball
# enters it at the upper-right open end and re-emerges at the lower-left open
# end. While inside the housing the HOUSING GEOMETRY itself occludes it (roof +
# front/back walls); the ball is never removed from the render, so occlusion is
# honest image-space cover.
# =============================================================================


def _seg_endpoints():
    # A clearly VISIBLE S/zigzag facing the camera. The three segments alternate
    # X-direction so the switchback shape is obvious:  A down-RIGHT, B down-LEFT,
    # C down-RIGHT. A short opaque tunnel later covers only the MIDDLE of B, so the
    # whole zigzag stays visible while the ball briefly disappears mid-descent.
    # Consecutive segments are joined by level semicircular hairpin turns, so the
    # ball path is continuous.
    x_left = -2.25
    x_right = 2.25
    z_top = 3.05
    z_ab = 2.20
    z_bc = 1.42
    z_floor = 0.42
    # The switchbacks occupy two front/back lanes. Their end turns therefore
    # wrap around in depth like real hairpins instead of folding through the
    # vertical X-Z plane.
    turn_radius = 0.56
    y_front = -turn_radius
    y_back = turn_radius
    a_start = Vector((x_left, y_front, z_top))
    a_end   = Vector((x_right, y_front, z_ab))
    b_start = Vector((x_right, y_back, z_ab))
    b_end   = Vector((x_left, y_back, z_bc))
    c_start = Vector((x_left, y_front, z_bc))
    c_end   = Vector((x_right - 0.55, y_front, z_floor))
    return {
        "a": (a_start, a_end),
        "b": (b_start, b_end),
        "c": (c_start, c_end),
        "x_left": x_left,
        "x_right": x_right,
        "z_top": z_top,
        "z_ab": z_ab,
        "z_bc": z_bc,
        "z_floor": z_floor,
        "y": 0.0,
        "turn_radius": turn_radius,
        "tunnel_x_half": 0.72,
    }

def _banked_ramp(name, p1, p2, width, thickness, material, role, color_name):
    p1 = Vector(p1)
    p2 = Vector(p2)
    diff = p2 - p1
    length = diff.length
    mid = (p1 + p2) / 2.0

    obj = add_oriented_box(
        name,
        (mid.x, mid.y, mid.z),
        (length, width, thickness),
        material,
        role,
        color_name,
    )
    # Track local X follows the centreline in full 3-D. Local Z remains as
    # close as possible to world-up, so a depth-wise U-turn stays horizontal.
    obj.rotation_euler = diff.normalized().to_track_quat("X", "Z").to_euler()
    return obj


def _surf_normal(p_start, p_end):
    d = (p_end - p_start).normalized()
    lateral = Vector((-d.y, d.x, 0.0))
    if lateral.length < 1.0e-8:
        lateral = Vector((0.0, 1.0, 0.0))
    lateral.normalize()
    n = d.cross(lateral)
    if n.z < 0:
        n = -n
    return n


def build_serpentine_ramp_tunnel():
    scene = setup_base(
        camera_loc=(2.2, -9.6, 2.5),
        target=(0.0, 0.0, 1.75),
        ortho_scale=6.9,
    )

    E = _seg_endpoints()
    y = E["y"]
    ramp_width = 0.72
    ramp_thick = 0.15
    ball_radius = 0.20
    surf_off = ramp_thick / 2.0 + ball_radius

    a_start, a_end = E["a"]
    b_start, b_end = E["b"]
    c_start, c_end = E["c"]

    # Each reversal is a semicircle in the X-Y plane. The turn remains level at
    # the shared Z height while moving from the front lane to the back lane (or
    # vice versa), so neither the track nor the ball ever folds vertically.
    turn_steps = 20
    turn_radius = E["turn_radius"]

    def _semicircle_turn(cx, z, right_side):
        points = []
        for i in range(turn_steps):
            theta = math.pi * i / float(turn_steps - 1)
            if right_side:
                x = cx + turn_radius * math.sin(theta)
                y_turn = -turn_radius * math.cos(theta)
            else:
                x = cx - turn_radius * math.sin(theta)
                y_turn = turn_radius * math.cos(theta)
            points.append(Vector((x, y_turn, z)))
        return points

    right_turn = _semicircle_turn(E["x_right"], E["z_ab"], True)
    left_turn = _semicircle_turn(E["x_left"], E["z_bc"], False)

    _banked_ramp("ramp_seg_a_top", a_start, a_end, ramp_width, ramp_thick, MATS["blue"], "ramp_segment", "blue")
    _banked_ramp("ramp_seg_b_middle", b_start, b_end, ramp_width, ramp_thick, MATS["blue"], "ramp_segment", "blue")
    _banked_ramp("ramp_seg_c_bottom", c_start, c_end, ramp_width, ramp_thick, MATS["blue"], "ramp_segment", "blue")
    for turn_name, points in (("right", right_turn), ("left", left_turn)):
        for i in range(len(points) - 1):
            _banked_ramp(
                "%s_switchback_curve_%02d" % (turn_name, i),
                points[i], points[i + 1], ramp_width, ramp_thick,
                MATS["blue"], "switchback_curve", "blue",
            )

    # --- Transparent guard walls so the ball is visibly kept ON the track ------
    # A GLASS guard wall runs along the far edge of every ramp segment, plus glass
    # end caps at the two hairpin turns, so the ball is physically contained -- it
    # can't fly off the sides or overshoot the switchbacks -- while the see-through
    # walls add no opaque-bar clutter.
    WALL_H = 0.45
    WALL_T = 0.05
    edge_dy = ramp_width / 2.0 - WALL_T / 2.0

    def _glass_side_wall(name, p1, p2, dy):
        p1 = Vector(p1); p2 = Vector(p2)
        diff = p2 - p1
        tangent = diff.normalized()
        n = _surf_normal(p1, p2)
        lateral = Vector((-tangent.y, tangent.x, 0.0)).normalized()
        mid = (p1 + p2) / 2.0
        length = diff.length
        center = mid + n * (ramp_thick / 2.0 + WALL_H / 2.0) + lateral * dy
        w = add_oriented_box(name, (center.x, center.y, center.z),
                             (length, WALL_T, WALL_H), MATS["glass"],
                             "guard_wall_transparent", "glass")
        w.rotation_euler = tangent.to_track_quat("X", "Z").to_euler()
        w["pb_transparent"] = True

    # Only the FAR (back, +Y) edge wall per ramp. A near/front wall sits between
    # the camera and the ramp top, and being transparent it made the blue slab
    # look see-through on the upper ramps. The far wall stays behind the opaque
    # ramp (never covers the blue) and, with the hairpin end caps, still contains
    # the ball on the track.
    _glass_side_wall("guardwall_a_back", a_start, a_end, edge_dy)
    _glass_side_wall("guardwall_b_back", b_start, b_end, -edge_dy)
    _glass_side_wall("guardwall_c_back", c_start, c_end, edge_dy)
    for turn_name, points in (("right", right_turn), ("left", left_turn)):
        for i in range(len(points) - 1):
            _glass_side_wall(
                "guardwall_%s_curve_%02d_back" % (turn_name, i),
                points[i], points[i + 1], -edge_dy,
            )

    # Ordered support-surface centreline.  Labels stay aligned one-per-segment
    # so occlusion can still be limited to the middle straight inside the box.
    path_nodes = [a_start, a_end]
    path_nodes.extend(right_turn[1:])
    path_nodes.append(b_end)
    path_nodes.extend(left_turn[1:])
    path_nodes.append(c_end)
    path_labels = (
        ["a"]
        + ["turn_ab"] * (len(right_turn) - 1)
        + ["b"]
        + ["turn_bc"] * (len(left_turn) - 1)
        + ["c"]
    )

    # Offset the ball from the support using a node tangent, not a per-segment
    # normal. This keeps the centreline continuous at every sampled curve joint.
    ball_path_nodes = []
    for i, node in enumerate(path_nodes):
        if i == 0:
            tangent = path_nodes[1] - node
        elif i == len(path_nodes) - 1:
            tangent = node - path_nodes[i - 1]
        else:
            tangent = path_nodes[i + 1] - path_nodes[i - 1]
        tangent.normalize()
        lateral = Vector((-tangent.y, tangent.x, 0.0))
        if lateral.length < 1.0e-8:
            lateral = Vector((0.0, 1.0, 0.0))
        lateral.normalize()
        normal = tangent.cross(lateral)
        if normal.z < 0.0:
            normal = -normal
        ball_path_nodes.append(node + normal * surf_off)

    tx = E["tunnel_x_half"]
    def b_surf_z(x):
        u = (E["x_right"] - x) / (E["x_right"] - E["x_left"])
        return E["z_ab"] + (E["z_bc"] - E["z_ab"]) * u
    z_xr = b_surf_z(+tx)
    z_xl = b_surf_z(-tx)
    t_top = max(z_xr, z_xl) + surf_off + 0.34
    t_bot = min(z_xr, z_xl) - 0.02
    t_cz = (t_top + t_bot) / 2.0
    t_h = (t_top - t_bot)
    t_w = 2.0 * tx
    # Depth (front-to-back, along Y) must be wide enough that the housing walls sit
    # OUTBOARD of the ramp channel, so the housing encloses segment B and its glass
    # guard wall instead of clipping through them.
    t_depth = 2.25
    wall_t = 0.10
    front_y = y - t_depth / 2.0 + wall_t / 2.0
    back_y = y + t_depth / 2.0 - wall_t / 2.0
    add_cube("tunnel_front_wall", (0.0, front_y, t_cz), (t_w, wall_t, t_h), MATS["housing"], "tunnel_front_wall", "gray")
    add_cube("tunnel_back_wall", (0.0, back_y, t_cz), (t_w, wall_t, t_h), MATS["housing"], "tunnel_wall", "gray")
    add_cube("tunnel_roof", (0.0, y, t_top - wall_t / 2.0), (t_w, t_depth, wall_t), MATS["housing"], "tunnel_wall", "gray")
    # The posts sit just in front of the housing, fully outside the ramp channel
    # and ball radius.
    support_y = front_y - wall_t / 2.0 - 0.10
    add_cube("tunnel_post_l", (-tx + 0.07, support_y, t_bot / 2.0), (0.12, 0.12, max(0.1, t_bot)), MATS["support"], "tunnel_support", "dark_gray")
    add_cube("tunnel_post_r", (tx - 0.07, support_y, t_bot / 2.0), (0.12, 0.12, max(0.1, t_bot)), MATS["support"], "tunnel_support", "dark_gray")

    ball_start = ball_path_nodes[0]
    ball = add_sphere("serpentine_ball", ball_radius, ball_start, MATS["orange"], "orange")
    ball["pb_path"] = "serpentine_zigzag_descent_under_middle_tunnel"
    ball["pb_can_disappear"] = False

    return scene, {
        "ball": ball,
        "ball_radius": ball_radius,
        "surf_off": surf_off,
        "ball_path_nodes": ball_path_nodes,
        "path_labels": path_labels,
        "ramp_thick": ramp_thick,
        "tunnel_x_half": tx,
    }

def animate_serpentine_ramp_tunnel(scene, meta):
    ball = meta["ball"]
    radius = meta["ball_radius"]
    tx = meta["tunnel_x_half"]
    path_nodes = meta["ball_path_nodes"]
    path_labels = meta["path_labels"]
    path_lengths = [
        (path_nodes[i + 1] - path_nodes[i]).length
        for i in range(len(path_nodes) - 1)
    ]
    total_len = sum(path_lengths)

    rest_frames = 8
    a_accel = 1.55

    def pos_along(s):
        remaining = s
        for i, length in enumerate(path_lengths):
            if remaining <= length or i == len(path_lengths) - 1:
                u = min(1.0, remaining / max(length, 1.0e-8))
                pos = path_nodes[i] + (path_nodes[i + 1] - path_nodes[i]) * u
                return pos, path_labels[i]
            remaining -= length
        return path_nodes[-1], path_labels[-1]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= rest_frames:
            s = 0.0
        else:
            t = (frame - rest_frames) / FPS
            s = min(total_len, 0.5 * a_accel * t * t)

        pos, seg = pos_along(s)
        # Documentary-only approximation of the covered stretch (world-x window,
        # full containment incl. radius). The camera sits at x=+2.2 so the true
        # image-space window is ~3 frames later; real occlusion is done by the
        # housing geometry, not by this flag.
        inside = (seg == "b") and (abs(pos.x) + radius <= tx)

        ball.location = pos
        ball.rotation_euler = (0.0, s / radius, 0.0)
        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)

        if inside:
            ball["pb_state"] = "hidden_under_middle_tunnel"
        elif seg in ("turn_bc", "c") or (seg == "b" and pos.x < -tx):
            ball["pb_state"] = "reemerged_continuing_down_zigzag"
        else:
            ball["pb_state"] = "visible_descending_zigzag_before_tunnel"
        ball["pb_path_s"] = float(s)
        ball["pb_occluded"] = bool(inside)

    scene.frame_set(FRAME_START)

# =============================================================================
# Dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE.get("scene_kind", CASE.get("kind"))

    if kind == "serpentine_ramp_tunnel":
        return build_serpentine_ramp_tunnel()

    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(scene, meta):
    kind = CASE.get("scene_kind", CASE.get("kind"))

    if kind == "serpentine_ramp_tunnel":
        return animate_serpentine_ramp_tunnel(scene, meta)

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
    print("scene_kind:", CASE.get("scene_kind"))
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
