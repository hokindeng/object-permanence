# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_PENDULUM_OCCLUDED_BY_SCREEN_0031",
  "scene_kind": "pendulum_occluded_by_screen",
  "prompt": "A red pendulum bob hangs from a fixed rope and swings left and right. A vertical opaque screen stands in the middle. When the bob swings behind the screen, it becomes hidden, but it should continue moving along the same pendulum arc. The same red bob should later emerge from the other side with the same rope length and continuous motion."
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
    MATS["pillar"] = make_mat("mat_opaque_pillar", (0.30, 0.31, 0.33), roughness=0.80)
    MATS["red"] = make_mat("mat_red", (0.95, 0.03, 0.02), roughness=0.32)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.38, 0.06), roughness=0.30)
    MATS["blue"] = make_mat("mat_blue", (0.15, 0.35, 0.90), roughness=0.42)
    MATS["black"] = make_mat("mat_black", (0.02, 0.02, 0.025), roughness=0.75)
    MATS["rope"] = make_mat("mat_rope_dark", (0.05, 0.05, 0.055), roughness=0.65)
    MATS["box"] = make_mat("mat_box_gray", (0.38, 0.39, 0.40), roughness=0.78)
    MATS["edge"] = make_mat("mat_light_edge", (0.62, 0.63, 0.64), roughness=0.68)
    MATS["glass"] = make_mat("mat_transparent_glass", (0.50, 0.82, 1.0), roughness=0.08, alpha=0.34, blend="BLEND")
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
    fill.name = "right_fill_light"
    fill.data.energy = 145

    return scene


def setup_camera(scene, location=(-0.65, -8.5, 1.75), target=(0.4, 0.0, 0.65), lens=31):
    bpy.ops.object.camera_add(location=location)
    camera = bpy.context.object
    camera.name = "camera_main"
    camera.data.lens = lens
    look_at(camera, target)
    camera.data.dof.use_dof = False
    scene.camera = camera
    return camera


# ============================================================
# Car helpers
# ============================================================

CAR_LENGTH = 0.62
CAR_WIDTH = 0.34
CAR_BODY_HEIGHT = 0.24
WHEEL_RADIUS = 0.080
WHEEL_THICKNESS = 0.065
TRACK_TOP_Z = 0.08
WHEEL_CENTER_Z = TRACK_TOP_Z + WHEEL_RADIUS
BODY_BOTTOM_Z = TRACK_TOP_Z + WHEEL_RADIUS * 2.0
CAR_BODY_CENTER_Z = BODY_BOTTOM_Z + CAR_BODY_HEIGHT / 2.0


def add_wheel(name, location, vehicle_id, side_name):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=40,
        radius=WHEEL_RADIUS,
        depth=WHEEL_THICKNESS,
        location=location,
        rotation=(math.pi / 2.0, 0.0, 0.0),
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(MATS["black"])
    tag(
        obj,
        name,
        "vehicle_wheel",
        "dynamic_vehicle_part",
        "cylinder",
        "black",
        True,
        solid=True,
        pb_vehicle_id=vehicle_id,
        pb_wheel_side=side_name,
    )
    return obj


def build_car(prefix, x, y, color_name="red"):
    mat = MATS["red"] if color_name == "red" else MATS["blue"]
    parts = []

    body = add_cube(
        f"{prefix}_body",
        (x, y, CAR_BODY_CENTER_Z),
        (CAR_LENGTH, CAR_WIDTH, CAR_BODY_HEIGHT),
        material=mat,
        role="target",
        color_name=color_name,
        is_dynamic=True,
        solid=True,
    )
    body["pb_vehicle_type"] = "wheeled_car"
    body["pb_vehicle_id"] = prefix
    body["pb_rel_x"] = 0.0
    body["pb_rel_y"] = 0.0
    body["pb_rel_z"] = CAR_BODY_CENTER_Z
    parts.append(body)

    wheel_offsets = [
        (-CAR_LENGTH * 0.33, -CAR_WIDTH * 0.58, WHEEL_CENTER_Z, "front_near"),
        ( CAR_LENGTH * 0.33, -CAR_WIDTH * 0.58, WHEEL_CENTER_Z, "rear_near"),
        (-CAR_LENGTH * 0.33,  CAR_WIDTH * 0.58, WHEEL_CENTER_Z, "front_far"),
        ( CAR_LENGTH * 0.33,  CAR_WIDTH * 0.58, WHEEL_CENTER_Z, "rear_far"),
    ]

    for dx, dy, dz, side in wheel_offsets:
        wheel = add_wheel(
            f"{prefix}_wheel_{side}",
            (x + dx, y + dy, dz),
            prefix,
            side,
        )
        wheel["pb_rel_x"] = dx
        wheel["pb_rel_y"] = dy
        wheel["pb_rel_z"] = dz
        parts.append(wheel)

    return body, parts


def set_car_parts(parts, base_x, base_y, frame, x_start):
    dist = base_x - x_start
    roll = -dist / max(1e-6, WHEEL_RADIUS)

    for obj in parts:
        rx = obj.get("pb_rel_x", 0.0)
        ry = obj.get("pb_rel_y", 0.0)
        rz = obj.get("pb_rel_z", obj.location.z)

        obj.location = (base_x + rx, base_y + ry, rz)

        if obj.get("pb_role") == "vehicle_wheel":
            obj.rotation_euler = (math.pi / 2.0, roll, 0.0)
            obj.keyframe_insert(data_path="rotation_euler", frame=frame)

        obj.keyframe_insert(data_path="location", frame=frame)


# ============================================================
# Scene builders
# ============================================================

def build_u_track_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(-0.75, -8.3, 1.75), target=(0.25, 0.0, 0.76), lens=31)

    # U-shaped track as many small gray blocks along a smooth U curve.
    pts = []
    for i in range(48):
        u = i / 47.0
        x = lerp(-3.2, 3.2, u)
        z = 0.38 + 0.58 * ((x / 3.2) ** 2)
        pts.append((x, 0.0, z))

    for i, p in enumerate(pts):
        add_cube(
            f"gray_u_track_segment_{i:02d}",
            p,
            (0.18, 0.50, 0.08),
            material=MATS["gray"],
            role="u_track_segment",
            color_name="gray",
        )

    pillar = add_cube(
        "wide_opaque_center_pillar",
        (0.08, -0.18, 0.86),
        (1.22, 0.42, 1.72),
        material=MATS["pillar"],
        role="occluder",
        color_name="dark_gray",
    )
    pillar["pb_occludes_ball_completely"] = True

    ball = add_sphere(
        "orange_ball",
        0.18,
        (pts[0][0], pts[0][1], pts[0][2] + 0.20),
        MATS["orange"],
        "orange",
    )
    ball["pb_expected_behavior"] = "continue_along_u_track_behind_pillar"

    return {"scene": scene, "kind": "u_track_occluded_ball", "ball": ball, "pts": pts, "pillar": pillar}


def build_pendulum_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(0.0, -8.2, 1.85), target=(0.0, 0.0, 1.10), lens=33)

    pivot = (0.0, 0.0, 2.18)
    length = 1.28
    theta0 = math.radians(46.0)

    screen = add_cube(
        "opaque_vertical_occluding_screen",
        (0.0, -0.20, 1.05),
        (0.78, 0.34, 1.72),
        material=MATS["pillar"],
        role="occluder",
        color_name="dark_gray",
    )
    screen["pb_occludes_pendulum_bob"] = True

    add_sphere("fixed_pendulum_pivot", 0.055, pivot, MATS["black"], "black", role="pivot")

    initial_theta = theta0 * math.cos(0.0)
    bob_pos = (
        pivot[0] + length * math.sin(initial_theta),
        0.0,
        pivot[2] - length * math.cos(initial_theta),
    )
    bob = add_sphere("red_pendulum_bob", 0.17, bob_pos, MATS["red"], "red")
    bob["pb_motion_constraint"] = "fixed_length_pendulum_arc"

    rope = add_cylinder_between(
        "dark_pendulum_rope",
        pivot,
        bob_pos,
        0.018,
        MATS["rope"],
        role="rope",
        color_name="dark_gray",
        is_dynamic=True,
        solid=True,
        vertices=16,
    )
    rope["pb_rope_length_constant"] = True

    return {
        "scene": scene,
        "kind": "pendulum_occluded_by_screen",
        "pivot": pivot,
        "length": length,
        "theta0": theta0,
        "bob": bob,
        "rope": rope,
        "screen": screen,
    }


def build_lidded_box_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(2.7, -7.6, 2.10), target=(0.35, 0.0, 0.58), lens=32)

    # Floor track/ramp into box.
    add_cube("gray_entry_track", (-1.15, 0.0, 0.08), (2.6, 0.45, 0.10), MATS["gray"], role="track", color_name="gray")

    # Box: open top, opaque walls.
    box_x = 0.72
    box_y = 0.0
    floor_z = 0.13
    wall_h = 0.68
    wall_t = 0.08
    box_len = 1.20
    box_w = 0.86

    add_cube("gray_box_floor", (box_x, box_y, floor_z), (box_len, box_w, 0.10), MATS["box"], role="container_floor", color_name="gray")
    add_cube("gray_box_back_wall", (box_x, box_y + box_w / 2.0, floor_z + wall_h / 2.0), (box_len, wall_t, wall_h), MATS["box"], role="container_wall", color_name="gray")
    add_cube("gray_box_front_wall", (box_x, box_y - box_w / 2.0, floor_z + wall_h / 2.0), (box_len, wall_t, wall_h), MATS["box"], role="container_wall", color_name="gray")
    add_cube("gray_box_right_wall", (box_x + box_len / 2.0, box_y, floor_z + wall_h / 2.0), (wall_t, box_w, wall_h), MATS["box"], role="container_wall", color_name="gray")
    add_cube("gray_box_left_low_lip", (box_x - box_len / 2.0, box_y, floor_z + 0.11), (wall_t, box_w, 0.22), MATS["box"], role="container_entry_lip", color_name="gray")

    lid = add_cube(
        "hinged_gray_lid",
        (box_x, box_y, floor_z + wall_h + 0.04),
        (box_len, box_w, 0.08),
        MATS["box"],
        role="hinged_lid",
        color_name="gray",
        is_dynamic=True,
        solid=True,
    )
    lid["pb_hinge_side"] = "back"
    lid["pb_closes_after_ball_enters"] = True

    ball = add_sphere("orange_ball", 0.16, (-1.80, 0.0, 0.28), MATS["orange"], "orange")
    ball["pb_expected_behavior"] = "enter_box_then_remain_hidden_inside"

    return {"scene": scene, "kind": "lidded_box_ball_enters", "ball": ball, "lid": lid, "box_x": box_x, "floor_z": floor_z, "wall_h": wall_h}


def build_elevator_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(2.9, -7.7, 2.25), target=(0.35, 0.0, 1.05), lens=32)

    base_x = 0.0
    base_y = 0.0
    box_w = 0.94
    box_h = 0.86
    box_d = 0.74
    wall_t = 0.07
    bottom_z0 = 0.18

    add_cube("left_vertical_guide_rail", (-0.78, 0.50, 1.35), (0.06, 0.06, 2.45), MATS["edge"], role="elevator_guide_rail", color_name="light_gray")
    add_cube("right_vertical_guide_rail", (0.78, 0.50, 1.35), (0.06, 0.06, 2.45), MATS["edge"], role="elevator_guide_rail", color_name="light_gray")

    parts = []
    def part(name, rel_loc, dims, role):
        obj = add_cube(
            name,
            (base_x + rel_loc[0], base_y + rel_loc[1], bottom_z0 + rel_loc[2]),
            dims,
            MATS["box"],
            role=role,
            color_name="gray",
            is_dynamic=True,
            solid=True,
        )
        obj["pb_rel_x"] = rel_loc[0]
        obj["pb_rel_y"] = rel_loc[1]
        obj["pb_rel_z"] = rel_loc[2]
        parts.append(obj)
        return obj

    part("elevator_box_floor", (0.0, 0.0, 0.0), (box_w, box_d, wall_t), "elevator_floor")
    part("elevator_box_back_wall", (0.0, box_d / 2.0, box_h / 2.0), (box_w, wall_t, box_h), "elevator_wall")
    part("elevator_box_left_wall", (-box_w / 2.0, 0.0, box_h / 2.0), (wall_t, box_d, box_h), "elevator_wall")
    part("elevator_box_right_wall", (box_w / 2.0, 0.0, box_h / 2.0), (wall_t, box_d, box_h), "elevator_wall")
    part("elevator_box_roof", (0.0, 0.0, box_h), (box_w, box_d, wall_t), "elevator_roof")

    door = add_cube(
        "elevator_front_sliding_door",
        (base_x, base_y - box_d / 2.0 - 0.035, bottom_z0 + box_h / 2.0),
        (box_w, wall_t, box_h),
        MATS["edge"],
        role="elevator_door",
        color_name="light_gray",
        is_dynamic=True,
        solid=True,
    )
    door["pb_rel_x"] = 0.0
    door["pb_rel_y"] = -box_d / 2.0 - 0.035
    door["pb_rel_z"] = box_h / 2.0
    parts.append(door)

    ball = add_sphere("orange_ball_inside_elevator", 0.15, (base_x, base_y - 0.05, bottom_z0 + 0.22), MATS["orange"], "orange")
    ball["pb_rel_x"] = 0.0
    ball["pb_rel_y"] = -0.05
    ball["pb_rel_z"] = 0.22
    ball["pb_expected_behavior"] = "move_up_with_hidden_elevator_box"

    return {"scene": scene, "kind": "elevator_box_hidden_ball", "parts": parts, "door": door, "ball": ball, "bottom_z0": bottom_z0}


def build_dropping_barrier_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(-0.55, -8.45, 1.55), target=(0.65, 0.0, 0.55), lens=31)

    add_cube("straight_gray_track", (0.0, 0.0, 0.04), (8.8, 0.46, 0.08), MATS["gray"], role="track", color_name="gray")
    car_body, car_parts = build_car("red_wheeled_car", -3.20, 0.0, "red")

    barrier = add_cube(
        "vertical_dropping_barrier",
        (1.05, 0.0, 1.42),
        (0.16, 1.06, 0.92),
        MATS["pillar"],
        role="dropping_barrier",
        color_name="dark_gray",
        is_dynamic=True,
        solid=True,
    )
    barrier["pb_drops_before_car_arrives"] = True
    barrier["pb_blocks_car_after_drop"] = True

    return {"scene": scene, "kind": "dropping_barrier_car_stops", "car_body": car_body, "car_parts": car_parts, "barrier": barrier}


def build_support_pin_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(2.8, -7.8, 2.25), target=(0.15, 0.0, 0.90), lens=32)

    hinge = (0.92, 0.0, 0.98)
    platform_len = 1.55
    platform_w = 0.48
    platform_t = 0.09
    pin_x = hinge[0] - platform_len + 0.12

    hinge_block = add_cube("right_hinge_block", hinge, (0.12, 0.62, 0.16), MATS["edge"], role="hinge", color_name="light_gray")

    platform = add_cube(
        "tilting_platform",
        (hinge[0] - platform_len / 2.0, 0.0, hinge[2]),
        (platform_len, platform_w, platform_t),
        MATS["gray"],
        role="tilting_platform",
        color_name="gray",
        is_dynamic=True,
        solid=True,
    )
    platform["pb_right_hinge"] = True
    platform["pb_supported_by_pin_initially"] = True

    pin = add_cube(
        "left_support_pin",
        (pin_x, 0.0, hinge[2] - 0.18),
        (0.15, 0.58, 0.18),
        MATS["edge"],
        role="support_pin",
        color_name="light_gray",
        is_dynamic=True,
        solid=True,
    )
    pin["pb_supports_platform_until_retracted"] = True

    ball = add_sphere("orange_ball_on_platform", 0.16, (hinge[0] - 0.95, 0.0, hinge[2] + 0.19), MATS["orange"], "orange")
    ball["pb_expected_behavior"] = "wait_until_pin_removed_then_roll_and_fall"

    return {
        "scene": scene,
        "kind": "support_pin_platform_tips_ball_falls",
        "hinge": hinge,
        "platform": platform,
        "pin": pin,
        "ball": ball,
        "platform_len": platform_len,
        "pin_x": pin_x,
    }


def build_transparent_tube_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(1.9, -7.8, 2.15), target=(0.05, 0.0, 0.98), lens=33)

    start = Vector((-2.45, 0.0, 1.55))
    end = Vector((1.85, 0.0, 0.55))
    direction = (end - start).normalized()
    tube_radius = 0.26

    tube = add_cylinder_between(
        "transparent_inclined_tube",
        start,
        end,
        tube_radius,
        MATS["glass"],
        role="transparent_tube",
        color_name="transparent_blue",
        solid=True,
        vertices=64,
    )
    tube["pb_transparent"] = True
    tube["pb_solid"] = True
    tube["pb_contains_ball"] = True

    cap_center = end + direction * 0.08
    cap = add_cylinder_between(
        "transparent_end_cap",
        cap_center - direction * 0.025,
        cap_center + direction * 0.025,
        tube_radius * 1.06,
        MATS["glass"],
        role="transparent_end_cap",
        color_name="transparent_blue",
        solid=True,
        vertices=64,
    )
    cap["pb_transparent"] = True
    cap["pb_solid"] = True
    cap["pb_blocks_ball"] = True

    ball = add_sphere("orange_ball_inside_transparent_tube", 0.15, start + direction * 0.50, MATS["orange"], "orange")
    ball["pb_expected_behavior"] = "roll_down_tube_and_stop_at_end_cap"

    return {"scene": scene, "kind": "transparent_tube_endcap_ball_blocks", "ball": ball, "start": start, "end": end, "direction": direction, "cap": cap}


# ============================================================
# Animation
# ============================================================

def animate_u_track(objs, frame):
    pts = objs["pts"]
    ball = objs["ball"]
    u = (frame - FRAME_START) / float(FRAME_END - FRAME_START)
    idx_f = u * (len(pts) - 1)
    i = min(len(pts) - 2, int(idx_f))
    t = idx_f - i
    p0 = Vector(pts[i])
    p1 = Vector(pts[i + 1])
    p = p0.lerp(p1, t)
    ball.location = (p.x, p.y, p.z + 0.20)
    ball.rotation_euler = (0.0, -u * 7.5, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)

    if -0.60 <= p.x <= 0.72:
        state = "fully_occluded_behind_opaque_pillar"
    elif p.x < -0.60:
        state = "visible_before_pillar"
    else:
        state = "visible_after_pillar"
    ball["pb_state"] = state
    ball["pb_continues_behind_occluder"] = True


def animate_pendulum(objs, frame):
    bob = objs["bob"]
    rope = objs["rope"]
    pivot = objs["pivot"]
    L = objs["length"]
    theta0 = objs["theta0"]

    # About one full swing over 120 frames.
    tau = (frame - FRAME_START) / float(FRAME_END - FRAME_START)
    theta = theta0 * math.cos(2.0 * math.pi * tau)

    pos = Vector((pivot[0] + L * math.sin(theta), 0.0, pivot[2] - L * math.cos(theta)))
    bob.location = pos
    bob.keyframe_insert(data_path="location", frame=frame)
    set_cylinder_between(rope, pivot, pos)
    rope.keyframe_insert(data_path="location", frame=frame)
    rope.keyframe_insert(data_path="rotation_euler", frame=frame)

    if abs(pos.x) < 0.38:
        state = "occluded_behind_vertical_screen"
    elif pos.x < 0:
        state = "visible_left_of_screen"
    else:
        state = "visible_right_of_screen"

    bob["pb_state"] = state
    bob["pb_pendulum_length_constant"] = True
    bob["pb_continues_behind_occluder"] = True
    rope["pb_state"] = "rope_connected_to_bob"


def animate_lidded_box(objs, frame):
    ball = objs["ball"]
    lid = objs["lid"]

    # Ball rolls into box by frame 54.
    if frame <= 54:
        t = smooth01((frame - FRAME_START) / 53.0)
        x = lerp(-1.80, 0.62, t)
        z = 0.29
        state = "rolling_into_open_box"
    else:
        x = 0.62
        z = 0.29
        state = "inside_box_hidden_after_lid_closes" if frame > 86 else "inside_box_before_lid_fully_closes"

    ball.location = (x, 0.0, z)
    ball.rotation_euler = (0.0, -0.12 * frame, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball["pb_state"] = state
    ball["pb_inside_container"] = bool(frame > 54)

    # Lid closes around back hinge.
    if frame <= 50:
        frac = 0.0
    elif frame >= 88:
        frac = 1.0
    else:
        frac = smooth01((frame - 50) / 38.0)

    # Open lid is tilted upward/back; closed is horizontal.
    open_angle = math.radians(-72.0)
    angle = open_angle * (1.0 - frac)

    box_x = objs["box_x"]
    floor_z = objs["floor_z"]
    wall_h = objs["wall_h"]
    lid.location = (box_x, 0.0, floor_z + wall_h + 0.04 + 0.20 * (1.0 - frac))
    lid.rotation_euler = (angle, 0.0, 0.0)
    lid.keyframe_insert(data_path="location", frame=frame)
    lid.keyframe_insert(data_path="rotation_euler", frame=frame)
    lid["pb_state"] = "open" if frac < 0.05 else ("closing" if frac < 0.98 else "closed_hiding_ball")
    lid["pb_blocks_ball_when_closed"] = True


def animate_elevator(objs, frame):
    parts = objs["parts"]
    ball = objs["ball"]
    bottom_z0 = objs["bottom_z0"]

    if frame <= 36:
        lift = 0.0
        door_frac = smooth01(frame / 36.0)  # closing
    elif frame <= 84:
        lift = smooth01((frame - 36) / 48.0) * 1.05
        door_frac = 1.0
    else:
        lift = 1.05
        door_frac = 1.0 - smooth01((frame - 84) / 36.0)  # opening

    for obj in parts:
        rx = obj.get("pb_rel_x", 0.0)
        ry = obj.get("pb_rel_y", 0.0)
        rz = obj.get("pb_rel_z", 0.0)

        if obj.name == "elevator_front_sliding_door":
            # Door slides sideways: open at frac=0, closed at frac=1.
            door_side_offset = -0.70 * (1.0 - door_frac)
            obj.location = (rx + door_side_offset, ry, bottom_z0 + rz + lift)
            obj["pb_state"] = "open" if door_frac < 0.10 else ("closed_hiding_ball" if door_frac > 0.90 else "moving")
        else:
            obj.location = (rx, ry, bottom_z0 + rz + lift)
            obj["pb_state"] = "elevator_box_moving_up" if lift > 0.0 else "elevator_box_initial"

        obj.keyframe_insert(data_path="location", frame=frame)

    ball.location = (
        ball.get("pb_rel_x", 0.0),
        ball.get("pb_rel_y", 0.0),
        bottom_z0 + ball.get("pb_rel_z", 0.22) + lift,
    )
    ball.keyframe_insert(data_path="location", frame=frame)
    ball["pb_state"] = "visible_inside_elevator" if door_frac < 0.2 else "hidden_inside_moving_elevator"
    ball["pb_moves_with_elevator_box"] = True


def animate_dropping_barrier(objs, frame):
    car_parts = objs["car_parts"]
    car_body = objs["car_body"]
    barrier = objs["barrier"]

    barrier_x = 1.05
    barrier_ground_center_z = 0.08 + 0.92 / 2.0
    barrier_high_z = 1.42

    if frame <= 20:
        z = barrier_high_z
    elif frame <= 50:
        z = lerp(barrier_high_z, barrier_ground_center_z, ease_in_quad((frame - 20) / 30.0))
    else:
        z = barrier_ground_center_z

    barrier.location = (barrier_x, 0.0, z)
    barrier.keyframe_insert(data_path="location", frame=frame)
    barrier["pb_state"] = "falling_down" if 20 < frame < 50 else ("blocking_track" if frame >= 50 else "above_track")

    x_start = -3.20
    speed = 0.055
    contact_x = barrier_x - 0.08 - CAR_LENGTH / 2.0 - 0.006
    raw_x = x_start + speed * (frame - FRAME_START)
    x = min(raw_x, contact_x)

    set_car_parts(car_parts, x, 0.0, frame, x_start=x_start)
    car_body["pb_state"] = "driving_toward_dropped_barrier" if raw_x < contact_x else "stopped_by_dropped_barrier"
    car_body["pb_no_barrier_penetration"] = True
    car_body["pb_barrier_dropped_before_arrival"] = bool(frame >= 50)


def animate_support_pin(objs, frame):
    hinge = Vector(objs["hinge"])
    platform = objs["platform"]
    pin = objs["pin"]
    ball = objs["ball"]
    L = objs["platform_len"]

    # Pin retracts first.
    if frame <= 42:
        pin_x = objs["pin_x"]
    elif frame <= 62:
        pin_x = lerp(objs["pin_x"], objs["pin_x"] - 0.85, smooth01((frame - 42) / 20.0))
    else:
        pin_x = objs["pin_x"] - 0.85

    pin.location = (pin_x, 0.0, hinge.z - 0.18)
    pin.keyframe_insert(data_path="location", frame=frame)
    pin["pb_state"] = "supporting_platform" if frame <= 42 else ("retracting" if frame <= 62 else "removed")

    # Platform tips after pin removal.
    if frame <= 62:
        angle = 0.0
        frac = 0.0
    else:
        frac = smooth01((frame - 62) / 38.0)
        angle = math.radians(-46.0) * frac

    # Platform center relative to right hinge.
    center_local = Vector((-L / 2.0, 0.0, 0.0))
    rot_x = center_local.x * math.cos(angle)
    rot_z = center_local.x * math.sin(angle)
    platform.location = (hinge.x + rot_x, 0.0, hinge.z + rot_z)
    platform.rotation_euler = (0.0, angle, 0.0)
    platform.keyframe_insert(data_path="location", frame=frame)
    platform.keyframe_insert(data_path="rotation_euler", frame=frame)
    platform["pb_state"] = "level_supported_by_pin" if frame <= 62 else "tipping_after_pin_removed"

    # Ball: stationary until platform tips, then rolls left/down and falls.
    if frame <= 62:
        local_x = -0.95
        ball_z_offset = 0.20
        world_x = hinge.x + local_x
        world_z = hinge.z + ball_z_offset
        phase = "resting_on_supported_platform"
    elif frame <= 92:
        t = smooth01((frame - 62) / 30.0)
        local_x = lerp(-0.95, -1.55, t)
        angle_now = angle
        world_x = hinge.x + local_x * math.cos(angle_now)
        world_z = hinge.z + local_x * math.sin(angle_now) + 0.20
        phase = "rolling_down_tilting_platform"
    else:
        t = (frame - 92) / 28.0
        start_x = hinge.x + (-1.55) * math.cos(math.radians(-46.0))
        start_z = hinge.z + (-1.55) * math.sin(math.radians(-46.0)) + 0.20
        world_x = start_x - 0.32 * t
        world_z = max(0.20, start_z - 0.95 * ease_in_quad(t))
        phase = "falling_to_floor_after_leaving_platform"

    ball.location = (world_x, 0.0, world_z)
    ball.rotation_euler = (0.0, -0.14 * frame, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball["pb_state"] = phase
    ball["pb_does_not_fall_before_pin_removed"] = bool(frame <= 62)


def animate_transparent_tube(objs, frame):
    ball = objs["ball"]
    start = objs["start"]
    end = objs["end"]
    direction = objs["direction"]

    # Stop just before end cap.
    path_start = start + direction * 0.50
    path_stop = end - direction * 0.24

    if frame <= 88:
        t = smooth01((frame - FRAME_START) / 87.0)
        pos = path_start.lerp(path_stop, t)
        state = "rolling_down_inside_transparent_tube"
    else:
        pos = path_stop
        state = "stopped_by_transparent_end_cap"

    ball.location = pos
    ball.rotation_euler = (0.0, -0.10 * frame, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball["pb_state"] = state
    ball["pb_inside_transparent_tube"] = True
    ball["pb_blocked_by_transparent_cap"] = bool(frame > 88)


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if kind == "u_track_occluded_ball":
            animate_u_track(objs, frame)
        elif kind == "pendulum_occluded_by_screen":
            animate_pendulum(objs, frame)
        elif kind == "lidded_box_ball_enters":
            animate_lidded_box(objs, frame)
        elif kind == "elevator_box_hidden_ball":
            animate_elevator(objs, frame)
        elif kind == "dropping_barrier_car_stops":
            animate_dropping_barrier(objs, frame)
        elif kind == "support_pin_platform_tips_ball_falls":
            animate_support_pin(objs, frame)
        elif kind == "transparent_tube_endcap_ball_blocks":
            animate_transparent_tube(objs, frame)
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

    if kind == "u_track_occluded_ball":
        return build_u_track_scene()
    if kind == "pendulum_occluded_by_screen":
        return build_pendulum_scene()
    if kind == "lidded_box_ball_enters":
        return build_lidded_box_scene()
    if kind == "elevator_box_hidden_ball":
        return build_elevator_scene()
    if kind == "dropping_barrier_car_stops":
        return build_dropping_barrier_scene()
    if kind == "support_pin_platform_tips_ball_falls":
        return build_support_pin_scene()
    if kind == "transparent_tube_endcap_ball_blocks":
        return build_transparent_tube_scene()

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
