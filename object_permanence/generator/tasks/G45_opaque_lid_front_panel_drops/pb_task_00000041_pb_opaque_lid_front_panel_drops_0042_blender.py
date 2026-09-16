# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_OPAQUE_LID_FRONT_PANEL_DROPS_0042",
  "scene_kind": "opaque_lid_front_panel_drops_center_ball_high_view",
  "prompt": "A gray box starts with its top open, viewed from a high angle, and an orange ball is clearly visible near the center of the box. An opaque gray lid slides over the top and hides the ball. After the lid is closed, the front panel of the box slowly folds downward like a hinged flap. When the front panel has folded down, the same centered orange ball is visible inside the box. The ball must continue to exist inside the closed box and must not disappear, teleport, or pass through the box walls."
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
        try:
            mat.blend_method = "BLEND"
            mat.show_transparent_back = True
            mat.use_screen_refraction = True
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


def add_sphere(name, radius, location, material, color_name, role="target"):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object", "sphere", color_name, True, solid=True, pb_radius=radius)
    return obj


def add_cylinder_between(name, p0, p1, radius, material, role, color_name, solid=True):
    p0 = Vector(p0)
    p1 = Vector(p1)
    mid = (p0 + p1) * 0.5
    vec = p1 - p0
    length = vec.length

    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=radius, depth=length, location=mid)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = vec.to_track_quat("Z", "Y").to_euler()

    if material is not None:
        obj.data.materials.append(material)

    tag(
        obj,
        name,
        role,
        "static_solid" if solid else "non_solid_marker",
        "cylinder",
        color_name,
        False,
        solid=solid,
    )
    return obj


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), roughness=0.84)
    MATS["gray"] = make_mat("mat_gray", (0.46, 0.46, 0.46), roughness=0.64)
    MATS["dark"] = make_mat("mat_dark", (0.18, 0.19, 0.21), roughness=0.76)
    MATS["light"] = make_mat("mat_light", (0.68, 0.69, 0.71), roughness=0.68)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.38, 0.06), roughness=0.28)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.92)
    MATS["glass"] = make_mat("mat_glass", (0.58, 0.86, 1.0), roughness=0.08, alpha=0.28, transparent=True)
    MATS["lid"] = make_mat("mat_opaque_lid", (0.34, 0.35, 0.37), roughness=0.72)


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
        scene.eevee.use_ssr = True
        scene.eevee.use_ssr_refraction = True
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

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (10.0, 5.0, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 2.48, 1.62), (10.2, 0.08, 3.24), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.4, -4.2, 5.5))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 980
    key.data.size = 6.0

    bpy.ops.object.light_add(type="POINT", location=(3.4, -3.0, 3.0))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 150

    return scene


def setup_camera(scene, location, target, lens=32, ortho=False, ortho_scale=4.0):
    bpy.ops.object.camera_add(location=location)
    cam = bpy.context.object
    cam.name = "camera_main"
    cam.data.lens = lens
    cam.data.dof.use_dof = False
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho_scale
    look_at(cam, target)
    scene.camera = cam
    return cam


# =============================================================================
# 0026 continuous roller-coaster U rail
# =============================================================================

def cubic_bezier(p0, p1, p2, p3, t):
    t = clamp01(t)
    a = (1 - t) ** 3
    b = 3 * (1 - t) ** 2 * t
    c = 3 * (1 - t) * t ** 2
    d = t ** 3
    return (
        a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
        0.0,
        a * p0[2] + b * p1[2] + c * p2[2] + d * p3[2],
    )


def centerline_point_raw(t):
    # One continuous rail centerline. No segmented teleport.
    # t=0 high left, t≈0.55 bottom of U, t=1 stopped at right wall.
    t = clamp01(t)

    ball_r = 0.14
    rail_r = 0.035
    rail_top_offset = ball_r + rail_r + 0.006

    # Rail center height at box floor. Ball center will be rail_z + rail_top_offset.
    floor_rail_z = 0.10

    if t <= 0.58:
        u = t / 0.58
        # Roller-coaster style descending U curve.
        # End point is exactly the bottom connection to the box floor.
        p0 = (-3.30, 0.0, 1.16)
        p1 = (-3.10, 0.0, 0.76)
        p2 = (-2.15, 0.0, floor_rail_z)
        p3 = (-1.18, 0.0, floor_rail_z)
        return cubic_bezier(p0, p1, p2, p3, u)

    u = (t - 0.58) / 0.42
    # Direct horizontal connection through the open left side into the box.
    return (
        lerp(-1.18, 2.43, u),
        0.0,
        floor_rail_z,
    )


def sample_centerline(n=260):
    pts = [centerline_point_raw(i / (n - 1)) for i in range(n)]
    lengths = [0.0]
    total = 0.0

    for i in range(1, len(pts)):
        p0 = Vector(pts[i - 1])
        p1 = Vector(pts[i])
        total += (p1 - p0).length
        lengths.append(total)

    return pts, lengths, total


def point_at_arc_fraction(pts, lengths, total, frac):
    if frac <= 0:
        return pts[0], 0.0
    if frac >= 1:
        return pts[-1], total

    target = frac * total

    lo = 0
    hi = len(lengths) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if lengths[mid] < target:
            lo = mid + 1
        else:
            hi = mid

    i = max(1, lo)
    l0 = lengths[i - 1]
    l1 = lengths[i]
    local = 0.0 if l1 == l0 else (target - l0) / (l1 - l0)

    p0 = pts[i - 1]
    p1 = pts[i]
    p = (
        lerp(p0[0], p1[0], local),
        lerp(p0[1], p1[1], local),
        lerp(p0[2], p1[2], local),
    )
    return p, target


def build_continuous_rollercoaster_u_track_into_glass_box():
    scene = build_base_scene()

    setup_camera(
        scene,
        location=(0.60, -7.55, 2.95),
        target=(-0.35, 0.0, 0.56),
        lens=33,
    )

    rail_y = 0.18
    rail_r = 0.035

    pts, lengths, total = sample_centerline(260)

    # Dual rails following the exact same continuous centerline used by the ball.
    for i in range(0, len(pts) - 1, 3):
        p0 = pts[i]
        p1 = pts[min(i + 3, len(pts) - 1)]

        add_cylinder_between(
            f"left_metal_rail_{i:03d}",
            (p0[0], -rail_y, p0[2]),
            (p1[0], -rail_y, p1[2]),
            rail_r,
            MATS["gray"],
            "rollercoaster_rail",
            "gray",
        )
        add_cylinder_between(
            f"right_metal_rail_{i:03d}",
            (p0[0], rail_y, p0[2]),
            (p1[0], rail_y, p1[2]),
            rail_r,
            MATS["gray"],
            "rollercoaster_rail",
            "gray",
        )

    # Cross ties. They sit below rail centerline, not under the ball path.
    for j, idx in enumerate(range(0, len(pts), 14)):
        p = pts[idx]
        add_cube(
            f"rail_cross_tie_{j:02d}",
            (p[0], 0.0, p[2] - 0.065),
            (0.09, 0.50, 0.045),
            MATS["dark"],
            "rail_cross_tie",
            "dark_gray",
            solid=True,
        )

    # Transparent box. The floor z matches rail bottom connection.
    add_cube("glass_box_floor", (0.72, 0.0, 0.05), (3.85, 1.30, 0.10), MATS["glass"], "transparent_box_floor", "transparent_blue", solid=True)
    add_cube("glass_box_back_wall", (0.72, 0.62, 0.48), (3.85, 0.08, 0.86), MATS["glass"], "transparent_box_wall", "transparent_blue", solid=True)
    add_cube("glass_box_front_wall_left_transparent", (-0.10, -0.62, 0.48), (1.55, 0.08, 0.86), MATS["glass"], "transparent_box_wall", "transparent_blue", solid=True)
    add_cube("glass_box_front_wall_right_transparent", (1.82, -0.62, 0.48), (1.55, 0.08, 0.86), MATS["glass"], "transparent_box_wall", "transparent_blue", solid=True)

    add_cube(
        "opaque_side_segment_on_glass_box",
        (0.86, -0.64, 0.48),
        (0.72, 0.10, 0.86),
        MATS["light"],
        "opaque_side_segment",
        "light_gray",
        solid=True,
    )

    add_cube("glass_box_right_wall", (2.65, 0.0, 0.48), (0.08, 1.30, 0.86), MATS["glass"], "transparent_box_right_wall", "transparent_blue", solid=True)
    add_cube("open_left_box_floor_connection", (-1.18, 0.0, 0.05), (0.16, 1.30, 0.10), MATS["gray"], "box_floor_connection_marker", "gray", solid=True)

    ball_r = 0.14
    rail_top_offset = ball_r + rail_r + 0.006
    p0 = pts[0]
    ball = add_sphere(
        "orange_ball_from_u_track_inside_glass_box",
        ball_r,
        (p0[0], 0.0, p0[2] + rail_top_offset),
        MATS["orange"],
        "orange",
    )
    ball["pb_radius"] = ball_r
    ball["pb_continuous_arc_length_path"] = True

    return {
        "scene": scene,
        "kind": "continuous_rollercoaster_u_track_into_glass_box",
        "ball": ball,
        "pts": pts,
        "lengths": lengths,
        "total": total,
        "rail_top_offset": rail_top_offset,
        "ball_r": ball_r,
    }


def animate_continuous_rollercoaster_u_track_into_glass_box(objs):
    scene = objs["scene"]
    ball = objs["ball"]
    pts = objs["pts"]
    lengths = objs["lengths"]
    total = objs["total"]
    rail_top_offset = objs["rail_top_offset"]
    ball_r = objs["ball_r"]

    previous_distance = 0.0

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 104:
            # Smooth speed curve, but arc-length parameterization prevents position jumps.
            frac = smooth01((frame - 1) / 103.0)
        else:
            frac = 1.0

        p, dist = point_at_arc_fraction(pts, lengths, total, frac)
        x, y, rail_z = p

        ball.location = (x, 0.0, rail_z + rail_top_offset)

        # Continuous rotation proportional to arc length travelled.
        spin = -dist / max(ball_r, 0.001)
        ball.rotation_euler = (0.0, spin, 0.0)

        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)

        if frame <= 52:
            state = "rolling_continuously_on_u_shaped_dual_rails"
        elif frame <= 68:
            state = "rolling_through_bottom_connection_into_box_floor"
        elif frame <= 104:
            state = "rolling_inside_transparent_box"
        else:
            state = "stopped_by_transparent_right_wall"

        ball["pb_state"] = state
        ball["pb_no_position_jump"] = True
        ball["pb_inside_transparent_box_after_entry"] = frame >= 69
        ball["pb_must_not_pass_transparent_wall"] = True

        previous_distance = dist

    scene.frame_set(FRAME_START)


# =============================================================================
# 0042 high view centered ball
# =============================================================================

def build_opaque_lid_front_panel_drops_center_ball_high_view():
    scene = build_base_scene()

    # More vertical and closer top/front view.
    setup_camera(
        scene,
        location=(1.15, -3.65, 4.85),
        target=(0.0, -0.02, 0.46),
        lens=34,
        ortho=True,
        ortho_scale=2.20,
    )

    base_z = 0.16
    ball_radius = 0.16 * DIVERSITY.get("ball_radius_scale", 1.0)

    add_cube("box_floor", (0.0, 0.0, base_z), (1.45, 1.12, 0.10), MATS["gray"], "box_floor", "gray")
    add_cube("box_left_wall", (-0.67, 0.0, base_z + 0.36), (0.10, 1.12, 0.72), MATS["gray"], "box_wall", "gray")
    add_cube("box_right_wall", (0.67, 0.0, base_z + 0.36), (0.10, 1.12, 0.72), MATS["gray"], "box_wall", "gray")
    add_cube("box_back_wall", (0.0, 0.53, base_z + 0.36), (1.45, 0.10, 0.72), MATS["gray"], "box_wall", "gray")

    front_panel = add_cube(
        "front_panel_hinged_flap",
        (0.0, -0.56, base_z + 0.36),
        (1.45, 0.08, 0.72),
        MATS["gray"],
        "front_hinged_panel",
        "gray",
        is_dynamic=True,
        solid=True,
    )

    lid = add_cube(
        "opaque_sliding_lid",
        (0.0, -1.18, base_z + 0.75),
        (1.45, 1.12, 0.08),
        MATS["lid"],
        "opaque_lid",
        "dark_gray",
        is_dynamic=True,
        solid=True,
    )

    # Ball centered in the box, not tight against the rear wall.
    ball = add_sphere(
        "orange_ball_inside_box",
        ball_radius,
        (0.0, 0.0, base_z + ball_radius + 0.04),
        MATS["orange"],
        "orange",
    )
    ball["pb_centered_inside_box"] = True

    return {
        "scene": scene,
        "kind": "opaque_lid_front_panel_drops_center_ball_high_view",
        "front_panel": front_panel,
        "lid": lid,
        "ball": ball,
        "base_z": base_z,
    }


def animate_opaque_lid_front_panel_drops_center_ball_high_view(objs):
    scene = objs["scene"]
    front_panel = objs["front_panel"]
    lid = objs["lid"]
    ball = objs["ball"]
    base_z = objs["base_z"]

    H = 0.72
    hinge_y = -0.56
    hinge_z = base_z + 0.02

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 35:
            lid_t = smooth01((frame - 1) / 34.0)
        else:
            lid_t = 1.0

        lid_y = lerp(-1.18, 0.0, lid_t)
        lid.location = (0.0, lid_y, base_z + 0.75)
        lid.keyframe_insert(data_path="location", frame=frame)

        if frame <= 35:
            lid["pb_state"] = "opaque_lid_sliding_closed"
        else:
            lid["pb_state"] = "opaque_lid_closed_hiding_top_view"

        if frame <= 70:
            theta = 0.0
        else:
            theta = math.radians(94.0) * smooth01((frame - 70) / 50.0)

        cy = hinge_y - math.sin(theta) * (H / 2.0)
        cz = hinge_z + math.cos(theta) * (H / 2.0)

        front_panel.location = (0.0, cy, cz)
        front_panel.rotation_euler = (theta, 0.0, 0.0)
        front_panel.keyframe_insert(data_path="location", frame=frame)
        front_panel.keyframe_insert(data_path="rotation_euler", frame=frame)

        if frame <= 70:
            front_panel["pb_state"] = "front_panel_closed"
        else:
            front_panel["pb_state"] = "front_panel_folding_down_to_reveal_centered_ball"

        ball.location = (0.0, 0.0, base_z + 0.20)
        ball.keyframe_insert(data_path="location", frame=frame)

        if frame <= 20:
            ball["pb_state"] = "clearly_visible_centered_inside_open_box_from_high_view"
        elif frame <= 70:
            ball["pb_state"] = "hidden_centered_inside_box_under_opaque_lid_and_front_panel"
        else:
            ball["pb_state"] = "revealed_centered_inside_box_after_front_panel_drops"

        ball["pb_must_remain_inside_box"] = True
        ball["pb_centered_not_touching_rear_wall"] = True

    scene.frame_set(FRAME_START)


# =============================================================================
# dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "continuous_rollercoaster_u_track_into_glass_box":
        return build_continuous_rollercoaster_u_track_into_glass_box()
    if kind == "opaque_lid_front_panel_drops_center_ball_high_view":
        return build_opaque_lid_front_panel_drops_center_ball_high_view()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(objs):
    kind = objs["kind"]
    if kind == "continuous_rollercoaster_u_track_into_glass_box":
        return animate_continuous_rollercoaster_u_track_into_glass_box(objs)
    if kind == "opaque_lid_front_panel_drops_center_ball_high_view":
        return animate_opaque_lid_front_panel_drops_center_ball_high_view(objs)
    raise RuntimeError("Unknown kind: " + str(kind))


# =============================================================================
# output
# =============================================================================

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

    objs = build_scene_by_kind()
    scene = objs["scene"]
    animate_scene_by_kind(objs)

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
