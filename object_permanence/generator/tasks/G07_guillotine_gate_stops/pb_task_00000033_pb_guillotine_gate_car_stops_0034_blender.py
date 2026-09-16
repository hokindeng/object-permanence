# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_GUILLOTINE_GATE_CAR_STOPS_0034",
  "scene_kind": "guillotine_gate_car_stops_wheel_axle_fixed",
  "prompt": "A small red car drives from left to right on a gray road. Ahead of it is a guillotine-style gate with two side posts, a top beam, and a solid gate blade already closed down across the road. The car wheels rotate around their left-right axle as the car moves. The car reaches the left face of the closed gate and stops. The car must not pass through or overlap the solid gate blade."
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


def add_oriented_box(name, p0, p1, width, height, material, role, color_name, is_dynamic=False, solid=True):
    p0 = Vector(p0)
    p1 = Vector(p1)
    mid = (p0 + p1) * 0.5
    vec = p1 - p0
    length = vec.length

    bpy.ops.mesh.primitive_cube_add(size=1, location=mid)
    obj = bpy.context.object
    obj.name = name
    obj.scale = (length / 2.0, width / 2.0, height / 2.0)
    obj.rotation_euler = vec.to_track_quat("X", "Z").to_euler()
    if material is not None:
        obj.data.materials.append(material)

    tag(
        obj,
        name,
        role,
        "dynamic_object" if is_dynamic else ("static_solid" if solid else "non_solid_marker"),
        "oriented_cube",
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


def add_wheel(name, location, material):
    # Cylinder axis is along Z by default.
    # Rotate by 90 deg around X so the axle is along global Y.
    # During animation we rotate around Y by distance / radius.
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=32,
        radius=0.12,
        depth=0.08,
        location=location,
        rotation=(math.radians(90.0), 0.0, 0.0),
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, "wheel", "dynamic_object", "cylinder", "dark_gray", True, solid=True, pb_axle_axis="Y")
    return obj


def add_wheel_spoke(name, location, material):
    # Thin bright spoke through the wheel face, so axle rotation is visible.
    obj = add_cube(
        name,
        location,
        (0.035, 0.025, 0.22),
        material,
        "wheel_spoke",
        "light_gray",
        is_dynamic=True,
        solid=True,
    )
    obj["pb_axle_axis"] = "Y"
    return obj


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), roughness=0.84)
    MATS["gray"] = make_mat("mat_gray", (0.46, 0.46, 0.46), roughness=0.64)
    MATS["dark"] = make_mat("mat_dark", (0.18, 0.19, 0.21), roughness=0.76)
    MATS["light"] = make_mat("mat_light", (0.68, 0.69, 0.71), roughness=0.68)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.38, 0.06), roughness=0.28)
    MATS["red"] = make_mat("mat_red", (0.88, 0.12, 0.12), roughness=0.30)
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


def setup_camera(scene, location, target, lens=32):
    bpy.ops.object.camera_add(location=location)
    cam = bpy.context.object
    cam.name = "camera_main"
    cam.data.lens = lens
    cam.data.dof.use_dof = False
    look_at(cam, target)
    scene.camera = cam
    return cam


# =============================================================================
# 0023 small ball behind screen
# =============================================================================

def build_occ_small_ball_behind_screen():
    scene = build_base_scene()
    setup_camera(scene, location=(0.0, -6.8, 1.85), target=(0.0, 0.0, 0.42), lens=33)

    add_cube("straight_gray_track", (0.0, 0.0, 0.055), (7.5, 0.30, 0.07), MATS["gray"], "track", "gray")
    screen = add_cube(
        "wide_opaque_screen",
        (0.0, -0.06, 0.64),
        (1.38, 0.16, 1.20),
        MATS["light"],
        "occluder_screen",
        "light_gray",
        is_dynamic=False,
        solid=True,
    )
    screen["pb_occludes_ball"] = True

    # Smaller ball.
    ball_r = 0.10
    ball = add_sphere("small_orange_ball", ball_r, (-2.90, 0.0, 0.055 + ball_r + 0.004), MATS["orange"], "orange")
    return {"scene": scene, "kind": "occ_small_ball_behind_screen", "ball": ball, "ball_r": ball_r}


def animate_occ_small_ball_behind_screen(objs):
    scene = objs["scene"]
    ball = objs["ball"]
    ball_r = objs["ball_r"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        x = lerp(-2.90, 2.90, (frame - 1) / 119.0)
        ball.location = (x, 0.0, 0.055 + ball_r + 0.004)
        ball.rotation_euler = (0.0, -0.20 * frame, 0.0)
        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)

        if -0.69 <= x <= 0.69:
            ball["pb_state"] = "fully_occluded_behind_screen_but_continuing"
        elif x < -0.69:
            ball["pb_state"] = "visible_before_occlusion"
        else:
            ball["pb_state"] = "visible_after_occlusion"

    scene.frame_set(FRAME_START)


# =============================================================================
# 0026 U-track into transparent glass box
# =============================================================================

def u_track_point(t):
    # t in [0,1], side view path in x-z.
    # High left -> U bottom -> straight into transparent box.
    if t < 0.42:
        u = t / 0.42
        x = lerp(-3.35, -2.35, u)
        z = lerp(1.10, 0.25, smooth01(u))
    elif t < 0.66:
        u = (t - 0.42) / 0.24
        theta = lerp(math.pi, 2.0 * math.pi, u)
        x = -1.92 + 0.43 * math.cos(theta)
        z = 0.25 + 0.18 * (1.0 + math.sin(theta))
    else:
        u = (t - 0.66) / 0.34
        x = lerp(-1.50, 2.36, u)
        z = 0.25
    return (x, 0.0, z)


def build_u_track_into_transparent_box_wall_blocks_ball():
    scene = build_base_scene()
    setup_camera(scene, location=(0.25, -7.3, 2.20), target=(-0.15, 0.0, 0.56), lens=32)

    # U-shaped gray slide track on the left, continuing into glass box.
    points = [u_track_point(i / 32.0) for i in range(33)]
    for i in range(len(points) - 1):
        add_oriented_box(
            f"u_shaped_gray_track_segment_{i:02d}",
            points[i],
            points[i + 1],
            width=0.34,
            height=0.075,
            material=MATS["gray"],
            role="u_track_segment",
            color_name="gray",
            solid=True,
        )

    # Transparent box on the right. Left side open so the ball can enter.
    add_cube("glass_box_floor", (0.72, 0.0, 0.09), (3.85, 1.30, 0.08), MATS["glass"], "transparent_box_floor", "transparent_blue", solid=True)
    add_cube("glass_box_front_wall", (0.72, -0.62, 0.48), (3.85, 0.08, 0.78), MATS["glass"], "transparent_box_wall", "transparent_blue", solid=True)
    add_cube("glass_box_back_wall", (0.72, 0.62, 0.48), (3.85, 0.08, 0.78), MATS["glass"], "transparent_box_wall", "transparent_blue", solid=True)
    add_cube("glass_box_right_wall", (2.65, 0.0, 0.48), (0.08, 1.30, 0.78), MATS["glass"], "transparent_box_right_wall", "transparent_blue", solid=True)
    add_cube("glass_box_top_edge_marker", (0.72, 0.0, 0.88), (3.85, 0.08, 0.04), MATS["glass"], "transparent_box_top_edge", "transparent_blue", solid=True)

    ball = add_sphere("orange_ball_from_u_track_inside_glass_box", 0.14, points[0], MATS["orange"], "orange")
    return {"scene": scene, "kind": "u_track_into_transparent_box_wall_blocks_ball", "ball": ball}


def animate_u_track_into_transparent_box_wall_blocks_ball(objs):
    scene = objs["scene"]
    ball = objs["ball"]

    # stop before right transparent wall.
    stop_x = 2.65 - 0.04 - 0.14 - 0.018

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 104:
            t = (frame - 1) / 103.0
            x, y, z = u_track_point(t)
            if x > stop_x:
                x = stop_x
            state = "rolling_from_u_track_into_glass_box"
        else:
            x, y, z = stop_x, 0.0, 0.25
            state = "stopped_by_transparent_right_wall"

        ball.location = (x, y, z + 0.14 + 0.004)
        ball.rotation_euler = (0.0, -0.16 * frame, 0.0)
        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)

        ball["pb_state"] = state
        ball["pb_must_not_pass_transparent_wall"] = True
        ball["pb_inside_transparent_box_after_entry"] = frame >= 58

    scene.frame_set(FRAME_START)


# =============================================================================
# 0034 car stops at guillotine gate, wheel axle fixed
# =============================================================================

def build_guillotine_gate_car_stops_wheel_axle_fixed():
    scene = build_base_scene()
    setup_camera(scene, location=(-2.4, -7.2, 1.95), target=(0.8, 0.0, 0.58), lens=32)

    add_cube("gray_road", (0.0, 0.0, 0.05), (8.8, 1.05, 0.10), MATS["gray"], "road", "gray")

    gate_x = 1.35
    add_cube("guillotine_near_post", (gate_x, -0.48, 1.00), (0.16, 0.12, 2.00), MATS["light"], "gate_post", "light_gray")
    add_cube("guillotine_far_post", (gate_x, 0.48, 1.00), (0.16, 0.12, 2.00), MATS["light"], "gate_post", "light_gray")
    add_cube("guillotine_top_beam", (gate_x, 0.0, 2.02), (0.20, 1.10, 0.16), MATS["light"], "gate_top_beam", "light_gray")
    add_cube("closed_gate_blade", (gate_x, 0.0, 0.55), (0.16, 0.76, 0.92), MATS["dark"], "closed_gate_blade", "dark_gray", solid=True)

    body = add_cube("red_car_body", (-2.60, 0.0, 0.33), (0.70, 0.42, 0.32), MATS["red"], "car_body", "red", is_dynamic=True)
    roof = add_cube("red_car_roof", (-2.60, 0.0, 0.57), (0.40, 0.34, 0.22), MATS["red"], "car_roof", "red", is_dynamic=True)

    wheels = []
    spokes = []
    wheel_names = ["front_near", "front_far", "rear_near", "rear_far"]
    offsets = [(0.22, -0.25, 0.18), (0.22, 0.25, 0.18), (-0.22, -0.25, 0.18), (-0.22, 0.25, 0.18)]

    for name, off in zip(wheel_names, offsets):
        wheels.append(add_wheel(f"{name}_wheel", (-2.60 + off[0], off[1], off[2]), MATS["dark"]))
        spokes.append(add_wheel_spoke(f"{name}_wheel_visible_spoke", (-2.60 + off[0], off[1], off[2]), MATS["light"]))

    return {
        "scene": scene,
        "kind": "guillotine_gate_car_stops_wheel_axle_fixed",
        "body": body,
        "roof": roof,
        "wheels": wheels,
        "spokes": spokes,
        "offsets": offsets,
    }


# --- G07 car elastic rebound at closed gate (FLAT ground) ---
# On flat ground there is no restoring force, so after bouncing off the gate the
# car recoils backward and comes to REST at the rebound position (away from the
# gate). The recoil is a decelerating ease-out: fast right after impact, slowing
# to a stop. Car is a box; REBOUND_BACK ~ 0.18. Wheel spin follows actual travel.
CAR_REBOUND_BACK = 0.18
CAR_CONTACT_FRAME = 78
CAR_REBOUND_FRAME = 90

def ease_out01(t):
    # decelerating: fast at start, slowing to a stop (derivative -> 0 at t=1).
    t = clamp01(t)
    return 1.0 - (1.0 - t) * (1.0 - t)

def car_x_at_frame(frame, stop_body_x, raw_x_at):
    """drive -> contact gate -> recoil backward and come to rest (no settle forward)."""
    if frame <= CAR_CONTACT_FRAME:
        return min(raw_x_at(frame), stop_body_x)
    rebound_x = stop_body_x - CAR_REBOUND_BACK
    if frame <= CAR_REBOUND_FRAME:
        t = (frame - CAR_CONTACT_FRAME) / max(1, (CAR_REBOUND_FRAME - CAR_CONTACT_FRAME))
        return lerp(stop_body_x, rebound_x, ease_out01(t))
    return rebound_x


def animate_guillotine_gate_car_stops_wheel_axle_fixed(objs):
    scene = objs["scene"]
    body = objs["body"]
    roof = objs["roof"]
    wheels = objs["wheels"]
    spokes = objs["spokes"]
    offsets = objs["offsets"]

    gate_x = 1.35
    gate_half = 0.08
    car_half = 0.35
    wheel_r = 0.12
    start_x = -2.60
    stop_body_x = gate_x - gate_half - car_half - 0.02

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        raw_x = start_x + 0.046 * (frame - 1)
        car_x = car_x_at_frame(
            frame, stop_body_x, lambda fr: start_x + 0.046 * (fr - 1)
        )
        dx = car_x - start_x

        # Correct wheel spin: angle = traveled distance / wheel radius.
        # Axis is global Y, not vertical Z.
        spin = -dx / wheel_r

        body.location = (car_x, 0.0, 0.33)
        roof.location = (car_x, 0.0, 0.57)
        body.keyframe_insert(data_path="location", frame=frame)
        roof.keyframe_insert(data_path="location", frame=frame)

        for w, sp, off in zip(wheels, spokes, offsets):
            center = (car_x + off[0], off[1], off[2])
            w.location = center
            sp.location = center

            # Wheel cylinder axle along Y, spin around Y.
            w.rotation_euler = (math.radians(90.0), spin, 0.0)
            sp.rotation_euler = (0.0, spin, 0.0)

            w.keyframe_insert(data_path="location", frame=frame)
            w.keyframe_insert(data_path="rotation_euler", frame=frame)
            sp.keyframe_insert(data_path="location", frame=frame)
            sp.keyframe_insert(data_path="rotation_euler", frame=frame)

            w["pb_state"] = "rolling_around_y_axle" if raw_x < stop_body_x else "stopped_at_gate"
            sp["pb_state"] = "visible_spoke_rotating_around_y_axle" if raw_x < stop_body_x else "visible_spoke_stopped"

        if raw_x >= stop_body_x:
            body["pb_state"] = "stopped_at_closed_gate"
            roof["pb_state"] = "stopped_at_closed_gate"
        else:
            body["pb_state"] = "driving_toward_closed_gate"
            roof["pb_state"] = "driving_toward_closed_gate"

        body["pb_must_not_pass_gate"] = True

    scene.frame_set(FRAME_START)


# =============================================================================
# 0042 opaque lid closes, front panel drops
# =============================================================================

def build_opaque_lid_closes_front_panel_drops():
    scene = build_base_scene()
    setup_camera(scene, location=(2.0, -6.7, 2.35), target=(0.0, -0.05, 0.55), lens=33)

    base_z = 0.16

    # Box with open top and front panel initially upright.
    add_cube("box_floor", (0.0, 0.0, base_z), (1.35, 1.05, 0.10), MATS["gray"], "box_floor", "gray")
    add_cube("box_left_wall", (-0.62, 0.0, base_z + 0.36), (0.10, 1.05, 0.72), MATS["gray"], "box_wall", "gray")
    add_cube("box_right_wall", (0.62, 0.0, base_z + 0.36), (0.10, 1.05, 0.72), MATS["gray"], "box_wall", "gray")
    add_cube("box_back_wall", (0.0, 0.48, base_z + 0.36), (1.35, 0.10, 0.72), MATS["gray"], "box_wall", "gray")

    front_panel = add_cube(
        "front_panel_hinged_flap",
        (0.0, -0.52, base_z + 0.36),
        (1.35, 0.08, 0.72),
        MATS["gray"],
        "front_hinged_panel",
        "gray",
        is_dynamic=True,
        solid=True,
    )

    # Opaque lid starts open toward camera/front and slides back to cover top.
    lid = add_cube(
        "opaque_sliding_lid",
        (0.0, -1.12, base_z + 0.75),
        (1.35, 1.05, 0.08),
        MATS["lid"],
        "opaque_lid",
        "dark_gray",
        is_dynamic=True,
        solid=True,
    )

    ball = add_sphere("orange_ball_inside_box", 0.16, (0.0, 0.02, base_z + 0.20), MATS["orange"], "orange")

    return {
        "scene": scene,
        "kind": "opaque_lid_closes_front_panel_drops",
        "front_panel": front_panel,
        "lid": lid,
        "ball": ball,
        "base_z": base_z,
    }


def animate_opaque_lid_closes_front_panel_drops(objs):
    scene = objs["scene"]
    front_panel = objs["front_panel"]
    lid = objs["lid"]
    ball = objs["ball"]
    base_z = objs["base_z"]

    # Front panel hinge line at bottom front.
    H = 0.72
    hinge_y = -0.52
    hinge_z = base_z + 0.02

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        # 1-35: opaque lid slides closed.
        # 36-70: closed box hides ball.
        # 71-120: front panel slowly folds downward, revealing ball.
        if frame <= 35:
            lid_t = smooth01((frame - 1) / 34.0)
        else:
            lid_t = 1.0

        lid_y = lerp(-1.12, 0.0, lid_t)
        lid.location = (0.0, lid_y, base_z + 0.75)
        lid.keyframe_insert(data_path="location", frame=frame)

        if frame <= 35:
            lid["pb_state"] = "opaque_lid_sliding_closed"
        else:
            lid["pb_state"] = "opaque_lid_closed_hiding_top_view"

        if frame <= 70:
            theta = 0.0
        else:
            theta = math.radians(90.0) * smooth01((frame - 70) / 50.0)

        # Center follows hinge rotation: vertical closed -> horizontal folded down outward.
        cy = hinge_y - math.sin(theta) * (H / 2.0)
        cz = hinge_z + math.cos(theta) * (H / 2.0)

        front_panel.location = (0.0, cy, cz)
        front_panel.rotation_euler = (theta, 0.0, 0.0)
        front_panel.keyframe_insert(data_path="location", frame=frame)
        front_panel.keyframe_insert(data_path="rotation_euler", frame=frame)

        if frame <= 70:
            front_panel["pb_state"] = "front_panel_closed"
        else:
            front_panel["pb_state"] = "front_panel_folding_down_to_reveal_ball"

        ball.location = (0.0, 0.02, base_z + 0.20)
        ball.keyframe_insert(data_path="location", frame=frame)

        if frame <= 20:
            ball["pb_state"] = "visible_inside_open_top_box"
        elif frame <= 70:
            ball["pb_state"] = "hidden_inside_box_under_opaque_lid_and_front_panel"
        else:
            ball["pb_state"] = "revealed_inside_box_after_front_panel_drops"

        ball["pb_must_remain_inside_box"] = True

    scene.frame_set(FRAME_START)


# =============================================================================
# dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "occ_small_ball_behind_screen":
        return build_occ_small_ball_behind_screen()
    if kind == "u_track_into_transparent_box_wall_blocks_ball":
        return build_u_track_into_transparent_box_wall_blocks_ball()
    if kind == "guillotine_gate_car_stops_wheel_axle_fixed":
        return build_guillotine_gate_car_stops_wheel_axle_fixed()
    if kind == "opaque_lid_closes_front_panel_drops":
        return build_opaque_lid_closes_front_panel_drops()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(objs):
    kind = objs["kind"]
    if kind == "occ_small_ball_behind_screen":
        return animate_occ_small_ball_behind_screen(objs)
    if kind == "u_track_into_transparent_box_wall_blocks_ball":
        return animate_u_track_into_transparent_box_wall_blocks_ball(objs)
    if kind == "guillotine_gate_car_stops_wheel_axle_fixed":
        return animate_guillotine_gate_car_stops_wheel_axle_fixed(objs)
    if kind == "opaque_lid_closes_front_panel_drops":
        return animate_opaque_lid_closes_front_panel_drops(objs)
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
