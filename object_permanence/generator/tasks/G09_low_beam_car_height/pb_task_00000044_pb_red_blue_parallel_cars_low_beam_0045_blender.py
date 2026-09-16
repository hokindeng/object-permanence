# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_RED_BLUE_PARALLEL_CARS_LOW_BEAM_0045",
  "scene_kind": "parallel_red_blocked_blue_passes",
  "prompt": "A red tall car and a blue short car drive side by side from left to right toward the same low horizontal beam gate area. Both cars start with the same speed. The beam height is lower than the red car roof but higher than the blue car roof. The red tall car must keep moving until its roof touches the beam, then stop at contact and remain stopped. The blue short car must pass under the beam, then decelerate and come to rest by the end of the video. The cars must preserve their identities and colors."
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


# Geometry constants
X_START = -3.20
CAR_SPEED = 0.053

GATE_X = 0.0
GATE_HALF_X = 0.07
GATE_LEFT_FACE_X = GATE_X - GATE_HALF_X

BODY_HALF_X = 0.48
ROOF_CENTER_FORWARD_OFFSET = 0.12
TALL_ROOF_HALF_X = 0.24

# Red roof front is x + 0.12 + 0.24 = x + 0.36.
# Contact should happen exactly when roof front touches left face of beam.
RED_ROOF_FRONT_OFFSET = ROOF_CENTER_FORWARD_OFFSET + TALL_ROOF_HALF_X
RED_CONTACT_X = GATE_LEFT_FACE_X - RED_ROOF_FRONT_OFFSET

BEAM_BOTTOM_Z = 0.58
BEAM_THICKNESS_Z = 0.12


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
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, location=location, rotation=rotation, vertices=28)
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


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), roughness=0.84)
    MATS["road"] = make_mat("mat_road", (0.44, 0.44, 0.46), roughness=0.72)
    MATS["beam"] = make_mat("mat_beam", (0.60, 0.62, 0.64), roughness=0.65)
    MATS["dark"] = make_mat("mat_dark", (0.12, 0.12, 0.13), roughness=0.82)
    MATS["red"] = make_mat("mat_red", (0.92, 0.18, 0.15), roughness=0.35)
    MATS["blue"] = make_mat("mat_blue", (0.18, 0.42, 0.95), roughness=0.35)
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


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (10.0, 6.0, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 2.75, 1.65), (10.0, 0.08, 3.30), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.8, -4.5, 5.8))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 980
    key.data.size = 6.2

    bpy.ops.object.light_add(type="POINT", location=(3.0, -3.0, 3.4))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 150

    return scene


def setup_camera_single(scene):
    # Left-biased oblique view. Same scene direction, but both gate posts are visible.
    bpy.ops.object.camera_add(location=(-2.15, -8.05, 2.45))
    cam = bpy.context.object
    cam.name = "camera_low_beam_single_left_oblique"
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 7.55
    cam.data.dof.use_dof = False
    look_at(cam, (0.0, 0.0, 0.68))
    scene.camera = cam


def setup_camera_parallel(scene):
    # Left-biased oblique view for two lanes; both posts and both cars visible.
    bpy.ops.object.camera_add(location=(-2.35, -8.55, 2.85))
    cam = bpy.context.object
    cam.name = "camera_low_beam_parallel_left_oblique"
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 6.35
    cam.data.dof.use_dof = False
    look_at(cam, (0.0, 0.0, 0.78))
    scene.camera = cam


def build_road(single=True):
    if single:
        add_cube("road_surface", (0.0, 0.0, 0.02), (8.8, 1.25, 0.06), MATS["road"], "road", "dark_gray")
    else:
        add_cube("road_surface_parallel", (0.0, 0.0, 0.02), (8.8, 2.75, 0.06), MATS["road"], "road", "dark_gray")
        add_cube("lane_divider_block_01", (-2.0, 0.0, 0.055), (0.55, 0.05, 0.02), MATS["beam"], "lane_divider", "light_gray")
        add_cube("lane_divider_block_02", (0.0, 0.0, 0.055), (0.55, 0.05, 0.02), MATS["beam"], "lane_divider", "light_gray")
        add_cube("lane_divider_block_03", (2.0, 0.0, 0.055), (0.55, 0.05, 0.02), MATS["beam"], "lane_divider", "light_gray")


def build_gate_single():
    post_h = BEAM_BOTTOM_Z
    add_cube("gate_left_post", (GATE_X, -0.55, post_h / 2.0), (0.14, 0.14, post_h), MATS["beam"], "gate_post", "light_gray")
    add_cube("gate_right_post", (GATE_X, 0.55, post_h / 2.0), (0.14, 0.14, post_h), MATS["beam"], "gate_post", "light_gray")
    add_cube(
        "low_beam_crossbar",
        (GATE_X, 0.0, BEAM_BOTTOM_Z + BEAM_THICKNESS_Z / 2.0),
        (0.14, 1.24, BEAM_THICKNESS_Z),
        MATS["beam"],
        "low_beam",
        "light_gray",
        solid=True,
    )
    return {"beam_bottom": BEAM_BOTTOM_Z, "left_face_x": GATE_LEFT_FACE_X}


def build_gate_parallel():
    post_h = BEAM_BOTTOM_Z
    add_cube("parallel_gate_left_post", (GATE_X, -1.10, post_h / 2.0), (0.14, 0.14, post_h), MATS["beam"], "gate_post", "light_gray")
    add_cube("parallel_gate_right_post", (GATE_X, 1.10, post_h / 2.0), (0.14, 0.14, post_h), MATS["beam"], "gate_post", "light_gray")
    add_cube(
        "parallel_low_beam_crossbar",
        (GATE_X, 0.0, BEAM_BOTTOM_Z + BEAM_THICKNESS_Z / 2.0),
        (0.14, 2.34, BEAM_THICKNESS_Z),
        MATS["beam"],
        "low_beam",
        "light_gray",
        solid=True,
    )
    return {"beam_bottom": BEAM_BOTTOM_Z, "left_face_x": GATE_LEFT_FACE_X}


def create_car(prefix, lane_y, car_color="red", tall=True):
    body_mat = MATS["red"] if car_color == "red" else MATS["blue"]
    wheel_mat = MATS["dark"]

    body_dims = (0.96, 0.56, 0.22)
    wheel_r = 0.12
    wheel_depth = 0.10

    if tall:
        # Taller red car roof: clearly higher than the low beam.
        roof_dims = (0.50, 0.50, 0.50)
        roof_z = 0.60
    else:
        # Lower blue car roof: clearly lower than the low beam.
        roof_dims = (0.42, 0.46, 0.12)
        roof_z = 0.40

    body = add_cube(
        f"{prefix}_body",
        (X_START, lane_y, 0.24),
        body_dims,
        body_mat,
        f"{prefix}_car",
        car_color,
        is_dynamic=True,
    )
    roof = add_cube(
        f"{prefix}_roof",
        (X_START + ROOF_CENTER_FORWARD_OFFSET, lane_y, roof_z),
        roof_dims,
        body_mat,
        f"{prefix}_car",
        car_color,
        is_dynamic=True,
    )

    wheels = []
    wheel_offsets = [
        (-0.28, -0.24),
        (0.28, -0.24),
        (-0.28, 0.24),
        (0.28, 0.24),
    ]
    for i, (dx, dy) in enumerate(wheel_offsets):
        wh = add_cylinder(
            f"{prefix}_wheel_{i+1}",
            (X_START + dx, lane_y + dy, wheel_r),
            wheel_r,
            wheel_depth,
            (math.pi / 2.0, 0.0, 0.0),
            wheel_mat,
            "wheel",
            "black",
            is_dynamic=True,
        )
        wheels.append(wh)

    top_height = roof_z + roof_dims[2] / 2.0
    roof_front_offset = ROOF_CENTER_FORWARD_OFFSET + roof_dims[0] / 2.0

    # Explicit visual clearance metadata.
    if tall:
        roof["pb_height_class"] = "tall_roof_clearly_above_low_beam"
    else:
        roof["pb_height_class"] = "short_roof_clearly_below_low_beam"

    body["pb_top_height"] = 0.24 + body_dims[2] / 2.0
    roof["pb_top_height"] = top_height
    roof["pb_roof_front_offset"] = roof_front_offset

    return {
        "prefix": prefix,
        "lane_y": lane_y,
        "car_color": car_color,
        "tall": tall,
        "body": body,
        "roof": roof,
        "wheels": wheels,
        "wheel_r": wheel_r,
        "body_dims": body_dims,
        "roof_dims": roof_dims,
        "roof_z": roof_z,
        "top_height": top_height,
        "roof_front_offset": roof_front_offset,
    }


def place_car(car, x, spin):
    lane_y = car["lane_y"]
    body = car["body"]
    roof = car["roof"]

    body.location = (x, lane_y, 0.24)
    roof.location = (x + ROOF_CENTER_FORWARD_OFFSET, lane_y, car["roof_z"])
    body.rotation_euler = (0.0, 0.0, 0.0)
    roof.rotation_euler = (0.0, 0.0, 0.0)

    frame = bpy.context.scene.frame_current
    body.keyframe_insert(data_path="location", frame=frame)
    roof.keyframe_insert(data_path="location", frame=frame)
    body.keyframe_insert(data_path="rotation_euler", frame=frame)
    roof.keyframe_insert(data_path="rotation_euler", frame=frame)

    wheel_offsets = [
        (-0.28, -0.24),
        (0.28, -0.24),
        (-0.28, 0.24),
        (0.28, 0.24),
    ]
    for wh, (dx, dy) in zip(car["wheels"], wheel_offsets):
        wh.location = (x + dx, lane_y + dy, car["wheel_r"])
        wh.rotation_euler = (math.pi / 2.0, spin, 0.0)
        wh.keyframe_insert(data_path="location", frame=frame)
        wh.keyframe_insert(data_path="rotation_euler", frame=frame)


def raw_constant_speed_x(frame):
    return X_START + CAR_SPEED * (frame - FRAME_START)


BLUE_DECEL_START = 90
BLUE_STOP_FRAME = 112


def blue_x_at_frame(frame):
    """Pass the beam, then brake smoothly to a visible end-of-clip rest."""
    if frame <= BLUE_DECEL_START:
        return raw_constant_speed_x(frame)
    duration = float(BLUE_STOP_FRAME - BLUE_DECEL_START)
    t = max(0.0, min(1.0, (frame - BLUE_DECEL_START) / duration))
    decel_distance = CAR_SPEED * duration * (t - 0.5 * t * t)
    return raw_constant_speed_x(BLUE_DECEL_START) + decel_distance


def red_contact_x():
    return RED_CONTACT_X


# --- Blocked tall car: slight elastic rebound at the low beam ---
# FLAT ground: no restoring force, so after recoiling off the beam the car
# comes to REST at the rebound position (it does NOT settle forward toward the
# beam, unlike the G03 slope case). SLIGHT recoil, it is a car.
REBOUND_BACK = 0.18
RED_REBOUND_X = RED_CONTACT_X - REBOUND_BACK   # final resting position

# Contact frame is when the constant-speed motion first reaches contact_x.
RED_CONTACT_FRAME = FRAME_START + int(round((RED_CONTACT_X - X_START) / CAR_SPEED))
RED_REBOUND_FRAME = RED_CONTACT_FRAME + 10     # recoil and come to rest over ~10 frames


def ease_out01(t):
    # Decelerating: fast right after impact, slowing to a stop at the rebound rest.
    t = max(0.0, min(1.0, float(t)))
    return math.sin(0.5 * math.pi * t)


def red_x_at_frame(frame):
    """Constant-speed approach -> contact -> decelerating recoil -> rest."""
    if frame <= RED_CONTACT_FRAME:
        return min(raw_constant_speed_x(frame), RED_CONTACT_X)
    if frame <= RED_REBOUND_FRAME:
        t = (frame - RED_CONTACT_FRAME) / max(1, (RED_REBOUND_FRAME - RED_CONTACT_FRAME))
        return lerp(RED_CONTACT_X, RED_REBOUND_X, ease_out01(t))
    return RED_REBOUND_X


def build_scene_single_tall_red_blocked():
    scene = build_base_scene()
    setup_camera_single(scene)
    build_road(single=True)
    gate = build_gate_single()
    red_car = create_car("red_tall", lane_y=0.0, car_color="red", tall=True)

    red_car["roof"]["pb_beam_clearance_bottom_z"] = BEAM_BOTTOM_Z
    red_car["roof"]["pb_roof_top_above_beam_bottom"] = True
    red_car["roof"]["pb_contact_x"] = red_contact_x()

    return {"scene": scene, "gate": gate, "red_car": red_car, "kind": "single_tall_red_blocked"}


def build_scene_single_short_blue_passes():
    scene = build_base_scene()
    setup_camera_single(scene)
    build_road(single=True)
    gate = build_gate_single()
    blue_car = create_car("blue_short", lane_y=0.0, car_color="blue", tall=False)

    blue_car["roof"]["pb_beam_clearance_bottom_z"] = BEAM_BOTTOM_Z
    blue_car["roof"]["pb_roof_top_below_beam_bottom"] = True

    return {"scene": scene, "gate": gate, "blue_car": blue_car, "kind": "single_short_blue_passes"}


def build_scene_parallel_red_blocked_blue_passes():
    scene = build_base_scene()
    setup_camera_parallel(scene)
    build_road(single=False)
    gate = build_gate_parallel()
    red_car = create_car("red_tall_parallel", lane_y=-0.62, car_color="red", tall=True)
    blue_car = create_car("blue_short_parallel", lane_y=0.62, car_color="blue", tall=False)

    red_car["roof"]["pb_beam_clearance_bottom_z"] = BEAM_BOTTOM_Z
    red_car["roof"]["pb_roof_top_above_beam_bottom"] = True
    red_car["roof"]["pb_contact_x"] = red_contact_x()

    blue_car["roof"]["pb_beam_clearance_bottom_z"] = BEAM_BOTTOM_Z
    blue_car["roof"]["pb_roof_top_below_beam_bottom"] = True

    return {"scene": scene, "gate": gate, "red_car": red_car, "blue_car": blue_car, "kind": "parallel_red_blocked_blue_passes"}


def animate_single_tall_red_blocked(objs):
    scene = objs["scene"]
    car = objs["red_car"]

    contact_x = red_contact_x()

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        raw_x = raw_constant_speed_x(frame)
        x = min(raw_x, contact_x)

        dist = x - X_START
        spin = -dist / max(car["wheel_r"], 1e-6)

        place_car(car, x, spin)

        roof_front_x = x + car["roof_front_offset"]

        if raw_x < contact_x:
            state = "approaching_low_beam_same_speed"
        else:
            state = "roof_front_touching_low_beam_and_stopped"

        car["body"]["pb_state"] = state
        car["roof"]["pb_state"] = state
        car["roof"]["pb_roof_front_x"] = roof_front_x
        car["roof"]["pb_low_beam_left_face_x"] = GATE_LEFT_FACE_X
        car["roof"]["pb_contact_exact_when_stopped"] = abs(roof_front_x - GATE_LEFT_FACE_X) < 1e-4

    scene.frame_set(FRAME_START)


def animate_single_short_blue_passes(objs):
    scene = objs["scene"]
    car = objs["blue_car"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        x = blue_x_at_frame(frame)
        dist = x - X_START
        spin = -dist / max(car["wheel_r"], 1e-6)

        place_car(car, x, spin)

        if x + car["roof_front_offset"] < GATE_LEFT_FACE_X:
            state = "approaching_low_beam_same_speed"
        elif x - BODY_HALF_X <= GATE_X <= x + BODY_HALF_X:
            state = "passing_under_low_beam"
        else:
            state = "past_low_beam_decelerating_to_final_rest" if frame < BLUE_STOP_FRAME else "past_low_beam_stopped_at_end"

        car["body"]["pb_state"] = state
        car["roof"]["pb_state"] = state
        car["roof"]["pb_clearance_ok"] = car["top_height"] < BEAM_BOTTOM_Z

    scene.frame_set(FRAME_START)


def animate_parallel_red_blocked_blue_passes(objs):
    scene = objs["scene"]
    red = objs["red_car"]
    blue = objs["blue_car"]

    contact_x = red_contact_x()

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        shared_raw_x = raw_constant_speed_x(frame)

        red_x = red_x_at_frame(frame)
        blue_x = blue_x_at_frame(frame)

        red_dist = red_x - X_START
        blue_dist = blue_x - X_START

        red_spin = -red_dist / max(red["wheel_r"], 1e-6)
        blue_spin = -blue_dist / max(blue["wheel_r"], 1e-6)

        place_car(red, red_x, red_spin)
        place_car(blue, blue_x, blue_spin)

        if shared_raw_x < contact_x:
            red_state = "approaching_low_beam_same_speed_as_blue"
        else:
            red_state = "roof_front_touching_low_beam_and_stopped"

        if blue_x + blue["roof_front_offset"] < GATE_LEFT_FACE_X:
            blue_state = "approaching_low_beam_same_speed_as_red"
        elif blue_x - BODY_HALF_X <= GATE_X <= blue_x + BODY_HALF_X:
            blue_state = "passing_under_low_beam_same_speed"
        else:
            blue_state = "past_low_beam_continuing_same_speed"

        red["body"]["pb_state"] = red_state
        red["roof"]["pb_state"] = red_state
        blue["body"]["pb_state"] = blue_state
        blue["roof"]["pb_state"] = blue_state

        red["body"]["pb_shared_speed_before_contact"] = CAR_SPEED
        blue["body"]["pb_shared_speed_before_contact"] = CAR_SPEED
        red["roof"]["pb_contact_exact_when_stopped"] = abs((red_x + red["roof_front_offset"]) - GATE_LEFT_FACE_X) < 1e-4 if shared_raw_x >= contact_x else False
        blue["roof"]["pb_clearance_ok"] = blue["top_height"] < BEAM_BOTTOM_Z

    scene.frame_set(FRAME_START)


def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "single_tall_red_blocked":
        return build_scene_single_tall_red_blocked()
    if kind == "single_short_blue_passes":
        return build_scene_single_short_blue_passes()
    if kind == "parallel_red_blocked_blue_passes":
        return build_scene_parallel_red_blocked_blue_passes()
    raise RuntimeError("Unknown scene kind: " + str(kind))


def animate_scene_by_kind(objs):
    kind = objs["kind"]
    if kind == "single_tall_red_blocked":
        return animate_single_tall_red_blocked(objs)
    if kind == "single_short_blue_passes":
        return animate_single_short_blue_passes(objs)
    if kind == "parallel_red_blocked_blue_passes":
        return animate_parallel_red_blocked_blue_passes(objs)
    raise RuntimeError("Unknown kind: " + str(kind))


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
    print("CAR_SPEED:", CAR_SPEED)
    print("GATE_LEFT_FACE_X:", GATE_LEFT_FACE_X)
    print("RED_CONTACT_X:", RED_CONTACT_X)
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
