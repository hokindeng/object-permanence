# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_PARALLEL_BRIDGES_SOLID_CAR_PASSES_0021",
  "scene_kind": "single_car_passes_solid_bridge",
  "prompt": "There are two simple parallel raised bridges. One bridge has a large rectangular hole in the middle, and the other bridge is solid with no hole. A red wheeled car starts on the solid bridge and drives from left to right at a constant speed. Because the bridge continuously supports the car, the car should pass across successfully without falling or stopping."
}""")
ITEM_ID = CASE["item_id"]

FPS = 24
FRAME_START = 1
FRAME_END = 120

# ============================================================
# Geometry and motion constants
# ============================================================

# Bridge is deliberately high so falling is visually obvious.
BRIDGE_TOP_Z = 1.15
BRIDGE_THICKNESS = 0.14
BRIDGE_CENTER_Z = BRIDGE_TOP_Z - BRIDGE_THICKNESS / 2.0
BRIDGE_WIDTH = 0.80
BRIDGE_LENGTH = 8.10

HOLE_X_MIN = 0.38
HOLE_X_MAX = 1.38
HOLE_CENTER_X = 0.5 * (HOLE_X_MIN + HOLE_X_MAX)
HOLE_WIDTH_X = HOLE_X_MAX - HOLE_X_MIN
# The opening must contain the complete wheel footprint while leaving visible,
# coplanar deck strips along both sides of the rectangular hole.
HOLE_WIDTH_Y = 0.54

NEAR_BRIDGE_Y = -0.82
FAR_BRIDGE_Y = 0.82
SINGLE_BRIDGE_Y = 0.0

CAR_LENGTH = 0.56
CAR_WIDTH = 0.34
CAR_BODY_HEIGHT = 0.22
WHEEL_RADIUS = 0.075
WHEEL_THICKNESS = 0.060
WHEEL_DIAMETER = WHEEL_RADIUS * 2.0

WHEEL_CENTER_Z = BRIDGE_TOP_Z + WHEEL_RADIUS
BODY_BOTTOM_Z = BRIDGE_TOP_Z + WHEEL_DIAMETER
CAR_BODY_CENTER_Z = BODY_BOTTOM_Z + CAR_BODY_HEIGHT / 2.0
CAR_TOTAL_HEIGHT = WHEEL_DIAMETER + CAR_BODY_HEIGHT

# Constant speed. No easing, no acceleration.
SPEED_X = 0.047

X_START = -2.60
X_FINAL = X_START + SPEED_X * (FRAME_END - FRAME_START)

# For 0025: same speed, different starting positions. Rear never waits.
FRONT_X_START = -1.55
REAR_X_START = -3.55

# Begin the free fall the moment the TRAILING axle clears the near lip -- the
# wheels sit at +/-0.33 * CAR_LENGTH from center, so support is lost when the
# center passes HOLE_X_MIN + 0.33 * CAR_LENGTH. Triggering any later would leave
# the car hovering unsupported over the hole.
FALL_TRIGGER_CENTER_X = HOLE_X_MIN + CAR_LENGTH * 0.33

# Ballistic fall to a wheel-on-floor landing while horizontal inertia remains.
FLOOR_TOP_Z = -0.01
FALL_GRAVITY = 9.81
FALL_DROP_Z = FLOOR_TOP_Z - BRIDGE_TOP_Z
FALL_LANDING_FRAMES = int(math.ceil(
    FPS * math.sqrt(2.0 * abs(FALL_DROP_Z) / FALL_GRAVITY)
))

# For front-car-plug task: front car settles into hole; body top becomes flush with bridge deck.
PLUG_FINAL_BODY_CENTER_Z = BRIDGE_TOP_Z - CAR_BODY_HEIGHT / 2.0 + 0.010
PLUG_FINAL_Z_OFFSET = PLUG_FINAL_BODY_CENTER_Z - CAR_BODY_CENTER_Z
PLUG_FALL_DURATION_FRAMES = 34

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
# Utilities
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


def ease_in_quad(t):
    t = clamp01(t)
    return t * t


def smooth01(t):
    t = clamp01(t)
    return 3.0 * t * t - 2.0 * t * t * t


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


def add_wheel(name, location, material, vehicle_id, side_name):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=40,
        radius=WHEEL_RADIUS,
        depth=WHEEL_THICKNESS,
        location=location,
        rotation=(math.pi / 2.0, 0.0, 0.0),
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)

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
    MATS["bridge"] = make_mat("mat_bridge_gray", (0.46, 0.46, 0.46), roughness=0.62)
    MATS["bridge_edge"] = make_mat("mat_bridge_light_edge", (0.62, 0.63, 0.64), roughness=0.68)
    MATS["pit"] = make_mat("mat_dark_pit", (0.045, 0.045, 0.052), roughness=0.95)
    MATS["red"] = make_mat("mat_red_car_body", (0.95, 0.03, 0.02), roughness=0.32)
    MATS["blue"] = make_mat("mat_blue_car_body", (0.05, 0.20, 0.95), roughness=0.32)
    MATS["wheel"] = make_mat("mat_black_wheels", (0.02, 0.02, 0.025), roughness=0.75)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube(
        "large_floor_base",
        (0.0, 0.0, -0.06),
        (9.8, 4.8, 0.10),
        material=MATS["floor"],
        role="ground",
        color_name="warm_beige",
    )

    add_cube(
        "rear_backdrop_panel",
        (0.0, 2.46, 1.70),
        (10.0, 0.08, 3.40),
        material=MATS["backdrop"],
        role="background",
        color_name="off_white",
    )

    bpy.ops.object.light_add(type="AREA", location=(-3.8, -4.4, 5.8))
    key = bpy.context.object
    key.name = "large_softbox_light"
    key.data.energy = 960
    key.data.size = 6.0

    bpy.ops.object.light_add(type="POINT", location=(3.7, -2.8, 3.2))
    fill = bpy.context.object
    fill.name = "right_fill_light"
    fill.data.energy = 145

    return scene


def setup_camera(scene, target=(0.55, 0.0, 0.95)):
    # A moderate downward angle separates the two parallel decks in the image
    # and makes the empty rectangular opening legible without becoming a
    # top-down view.
    bpy.ops.object.camera_add(location=(-0.90, -8.40, 3.65))
    camera = bpy.context.object
    camera.name = "camera_bridge_side_view_no_topdown"
    camera.data.lens = 33
    look_at(camera, target)
    camera.data.dof.use_dof = False
    scene.camera = camera


def add_bridge_supports(prefix, y):
    # Vertical supports make the raised bridge height obvious.
    supports = []
    for i, x in enumerate([-3.55, -2.20, -0.30, 2.15, 3.55]):
        for side_y in [y - BRIDGE_WIDTH * 0.38, y + BRIDGE_WIDTH * 0.38]:
            post_h = BRIDGE_CENTER_Z
            post = add_cube(
                f"{prefix}_support_post_{i}_{'near' if side_y < y else 'far'}",
                (x, side_y, post_h / 2.0),
                (0.08, 0.08, post_h),
                material=MATS["bridge_edge"],
                role="bridge_support_post",
                color_name="light_gray",
            )
            supports.append(post)
    return supports


def build_solid_bridge(prefix, y):
    objs = []
    bridge = add_cube(
        f"{prefix}_solid_bridge_deck",
        (0.0, y, BRIDGE_CENTER_Z),
        (BRIDGE_LENGTH, BRIDGE_WIDTH, BRIDGE_THICKNESS),
        material=MATS["bridge"],
        role="solid_bridge_deck",
        color_name="gray",
    )
    bridge["pb_bridge_has_hole"] = False
    bridge["pb_continuous_support"] = True
    objs.append(bridge)

    objs.append(add_cube(
        f"{prefix}_solid_bridge_near_edge",
        (0.0, y - BRIDGE_WIDTH / 2.0, BRIDGE_TOP_Z + 0.030),
        (BRIDGE_LENGTH, 0.035, 0.060),
        material=MATS["bridge_edge"],
        role="bridge_edge",
        color_name="light_gray",
    ))
    objs.append(add_cube(
        f"{prefix}_solid_bridge_far_edge",
        (0.0, y + BRIDGE_WIDTH / 2.0, BRIDGE_TOP_Z + 0.030),
        (BRIDGE_LENGTH, 0.035, 0.060),
        material=MATS["bridge_edge"],
        role="bridge_edge",
        color_name="light_gray",
    ))

    objs.extend(add_bridge_supports(prefix, y))
    return objs


def build_hole_bridge(prefix, y):
    objs = []

    left_len = HOLE_X_MIN - (-BRIDGE_LENGTH / 2.0)
    left_center = (-BRIDGE_LENGTH / 2.0 + HOLE_X_MIN) / 2.0
    right_len = BRIDGE_LENGTH / 2.0 - HOLE_X_MAX
    right_center = (HOLE_X_MAX + BRIDGE_LENGTH / 2.0) / 2.0

    left = add_cube(
        f"{prefix}_hole_bridge_left_deck",
        (left_center, y, BRIDGE_CENTER_Z),
        (left_len, BRIDGE_WIDTH, BRIDGE_THICKNESS),
        material=MATS["bridge"],
        role="hole_bridge_deck",
        color_name="gray",
    )
    right = add_cube(
        f"{prefix}_hole_bridge_right_deck",
        (right_center, y, BRIDGE_CENTER_Z),
        (right_len, BRIDGE_WIDTH, BRIDGE_THICKNESS),
        material=MATS["bridge"],
        role="hole_bridge_deck",
        color_name="gray",
    )
    objs.extend([left, right])

    # Complete the deck around the opening with two side strips. Their top
    # surfaces are exactly coplanar with the road. There is deliberately no
    # dark horizontal "hole plate" and no raised rim: the middle is real empty
    # space through which the floor below can be seen.
    side_width = 0.5 * (BRIDGE_WIDTH - HOLE_WIDTH_Y)
    side_offset = 0.25 * (BRIDGE_WIDTH + HOLE_WIDTH_Y)
    for side_name, y_offset in (("near", -side_offset), ("far", side_offset)):
        side_deck = add_cube(
            f"{prefix}_hole_bridge_{side_name}_side_deck",
            (HOLE_CENTER_X, y + y_offset, BRIDGE_CENTER_Z),
            (HOLE_WIDTH_X, side_width, BRIDGE_THICKNESS),
            material=MATS["bridge"],
            role="hole_bridge_deck",
            color_name="gray",
        )
        objs.append(side_deck)

    objs.extend(add_bridge_supports(prefix, y))

    for obj in objs:
        obj["pb_bridge_has_hole"] = True
        obj["pb_hole_x_min"] = HOLE_X_MIN
        obj["pb_hole_x_max"] = HOLE_X_MAX

    return objs


def build_car(prefix, x, y, color_name, mat, vehicle_id):
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
    body["pb_vehicle_id"] = vehicle_id
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
            MATS["wheel"],
            vehicle_id,
            side,
        )
        wheel["pb_rel_x"] = dx
        wheel["pb_rel_y"] = dy
        wheel["pb_rel_z"] = dz
        parts.append(wheel)

    return body, parts


def set_car_parts(parts, base_x, base_y, frame, z_offset=0.0, pitch=0.0, x_for_roll=None):
    if x_for_roll is None:
        x_for_roll = base_x

    dist = x_for_roll - X_START
    roll = -dist / max(1e-6, WHEEL_RADIUS)

    cos_pitch = math.cos(pitch)
    sin_pitch = math.sin(pitch)

    for obj in parts:
        rx = obj.get("pb_rel_x", 0.0)
        ry = obj.get("pb_rel_y", 0.0)
        rz = obj.get("pb_rel_z", obj.location.z)

        # Apply one shared rigid transform around the car body centre, so the body
        # and wheels never shear through the bridge lip.
        local_z = rz - CAR_BODY_CENTER_Z
        rotated_x = cos_pitch * rx + sin_pitch * local_z
        rotated_z = -sin_pitch * rx + cos_pitch * local_z
        obj.location = (
            base_x + rotated_x,
            base_y + ry,
            CAR_BODY_CENTER_Z + z_offset + rotated_z,
        )

        if obj.get("pb_role") == "vehicle_wheel":
            obj.rotation_euler = (math.pi / 2.0, roll + pitch, 0.0)
            obj.keyframe_insert(data_path="rotation_euler", frame=frame)
        else:
            obj.rotation_euler = (0.0, pitch, 0.0)
            obj.keyframe_insert(data_path="rotation_euler", frame=frame)

        obj.keyframe_insert(data_path="location", frame=frame)


def const_x(frame, start_x=X_START):
    return start_x + SPEED_X * (frame - FRAME_START)


def fall_start_frame_for(start_x):
    # First frame where the complete car footprint clears the left lip.
    return int(math.ceil((FALL_TRIGGER_CENTER_X - start_x) / SPEED_X)) + FRAME_START


def falling_motion(frame, start_x):
    fall_start = fall_start_frame_for(start_x)

    x = const_x(frame, start_x=start_x)

    if frame < fall_start:
        return x, 0.0, 0.0, "driving_toward_hole", fall_start

    n = frame - fall_start
    elapsed_seconds = n / float(FPS)
    drop = min(abs(FALL_DROP_Z), 0.5 * FALL_GRAVITY * elapsed_seconds ** 2)
    z_offset = -drop

    # A modest rigid nose-down arc during flight, returning to level exactly
    # when all four wheels land on the floor.
    flight_t = clamp01(n / float(FALL_LANDING_FRAMES))
    pitch = 0.24 * math.sin(math.pi * flight_t) if flight_t < 1.0 else 0.0

    if flight_t < 1.0:
        phase = "falling_through_unsupported_hole_with_forward_inertia"
    else:
        phase = "landed_on_floor_and_rolling_forward"

    return x, z_offset, pitch, phase, fall_start


def plug_front_motion(frame):
    start_x = FRONT_X_START
    fall_start = fall_start_frame_for(start_x)

    raw_x = const_x(frame, start_x=start_x)

    if frame < fall_start:
        return raw_x, 0.0, 0.0, "front_car_driving_toward_hole", fall_start, False

    n = frame - fall_start
    t = clamp01(n / float(PLUG_FALL_DURATION_FRAMES))

    # Keep horizontal inertia into the center of the hole, then settle there.
    x = min(raw_x, HOLE_CENTER_X)

    # Immediate fall, no hover; final top surface approximately flush with bridge deck.
    z_offset = PLUG_FINAL_Z_OFFSET * ease_in_quad(t)
    pitch = 0.0

    filled = bool(t >= 0.98)
    phase = "front_car_falling_into_hole" if not filled else "front_car_fills_hole_flush_with_bridge"

    return x, z_offset, pitch, phase, fall_start, filled


def build_scene():
    scene = build_base_scene()
    kind = CASE["scene_kind"]

    objs = {
        "scene": scene,
        "static": [],
    }

    if kind == "single_car_falls_hole_bridge":
        objs["static"].extend(build_hole_bridge("near", NEAR_BRIDGE_Y))
        objs["static"].extend(build_solid_bridge("far", FAR_BRIDGE_Y))

        body, parts = build_car(
            "hole_bridge_red_car",
            X_START,
            NEAR_BRIDGE_Y,
            "red",
            MATS["red"],
            "red_car_on_hole_bridge",
        )
        body["pb_bridge_assignment"] = "hole_bridge"
        objs["fall_body"] = body
        objs["fall_parts"] = parts
        objs["fall_y"] = NEAR_BRIDGE_Y

        setup_camera(scene)

    elif kind == "single_car_passes_solid_bridge":
        objs["static"].extend(build_hole_bridge("near", NEAR_BRIDGE_Y))
        objs["static"].extend(build_solid_bridge("far", FAR_BRIDGE_Y))

        body, parts = build_car(
            "solid_bridge_red_car",
            X_START,
            FAR_BRIDGE_Y,
            "red",
            MATS["red"],
            "red_car_on_solid_bridge",
        )
        body["pb_bridge_assignment"] = "solid_bridge"
        objs["pass_body"] = body
        objs["pass_parts"] = parts
        objs["pass_y"] = FAR_BRIDGE_Y

        setup_camera(scene)

    elif kind == "two_cars_one_passes_one_falls":
        objs["static"].extend(build_hole_bridge("near", NEAR_BRIDGE_Y))
        objs["static"].extend(build_solid_bridge("far", FAR_BRIDGE_Y))

        red_body, red_parts = build_car(
            "solid_bridge_red_car",
            X_START,
            FAR_BRIDGE_Y,
            "red",
            MATS["red"],
            "red_car_on_solid_bridge",
        )
        blue_body, blue_parts = build_car(
            "hole_bridge_blue_car",
            X_START,
            NEAR_BRIDGE_Y,
            "blue",
            MATS["blue"],
            "blue_car_on_hole_bridge",
        )

        red_body["pb_bridge_assignment"] = "solid_bridge"
        blue_body["pb_bridge_assignment"] = "hole_bridge"
        red_body["pb_same_speed_as_other_car"] = True
        blue_body["pb_same_speed_as_other_car"] = True

        objs["pass_body"] = red_body
        objs["pass_parts"] = red_parts
        objs["pass_y"] = FAR_BRIDGE_Y

        objs["fall_body"] = blue_body
        objs["fall_parts"] = blue_parts
        objs["fall_y"] = NEAR_BRIDGE_Y

        setup_camera(scene)

    elif kind == "front_car_fills_hole_rear_passes":
        objs["static"].extend(build_hole_bridge("single", SINGLE_BRIDGE_Y))

        front_body, front_parts = build_car(
            "front_red_plug_car",
            FRONT_X_START,
            SINGLE_BRIDGE_Y,
            "red",
            MATS["red"],
            "front_red_plug_car",
        )
        rear_body, rear_parts = build_car(
            "rear_blue_car",
            REAR_X_START,
            SINGLE_BRIDGE_Y,
            "blue",
            MATS["blue"],
            "rear_blue_car",
        )

        front_body["pb_role_in_scene"] = "front_car_falls_and_fills_hole"
        rear_body["pb_role_in_scene"] = "rear_car_crosses_after_hole_filled"
        front_body["pb_same_speed_as_rear_car"] = True
        rear_body["pb_same_speed_as_front_car"] = True

        objs["front_body"] = front_body
        objs["front_parts"] = front_parts
        objs["rear_body"] = rear_body
        objs["rear_parts"] = rear_parts

        setup_camera(scene, target=(0.62, 0.0, 1.18))

    else:
        raise RuntimeError("Unknown scene_kind: " + str(kind))

    return objs


def animate_scene(objs):
    scene = objs["scene"]
    kind = CASE["scene_kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if kind in ["single_car_falls_hole_bridge", "two_cars_one_passes_one_falls"]:
            x, z_offset, pitch, phase, fall_start = falling_motion(frame, X_START)
            set_car_parts(
                objs["fall_parts"],
                x,
                objs["fall_y"],
                frame,
                z_offset=z_offset,
                pitch=pitch,
                x_for_roll=x,
            )

            body = objs["fall_body"]
            body["pb_state"] = phase
            body["pb_constant_speed_x"] = SPEED_X
            body["pb_fall_start_frame"] = fall_start
            body["pb_no_hovering"] = True
            body["pb_forward_inertia_during_fall"] = bool(frame >= fall_start)
            body["pb_unsupported_by_bridge"] = bool(frame >= fall_start)
            body["pb_expected_behavior"] = "fall_through_bridge_hole_with_forward_inertia"

        if kind in ["single_car_passes_solid_bridge", "two_cars_one_passes_one_falls"]:
            x = const_x(frame, start_x=X_START)
            set_car_parts(
                objs["pass_parts"],
                x,
                objs["pass_y"],
                frame,
                z_offset=0.0,
                pitch=0.0,
                x_for_roll=x,
            )

            body = objs["pass_body"]
            if x < HOLE_X_MIN:
                phase = "driving_before_middle_bridge_region"
            elif x <= HOLE_X_MAX:
                phase = "passing_supported_middle_region"
            else:
                phase = "passed_bridge_middle_region"

            body["pb_state"] = phase
            body["pb_constant_speed_x"] = SPEED_X
            body["pb_motion_state"] = "driving"
            body["pb_supported_by_solid_bridge"] = True
            body["pb_expected_behavior"] = "pass_across_solid_bridge"

        if kind == "front_car_fills_hole_rear_passes":
            front_x, front_z, front_pitch, front_phase, front_fall_start, filled = plug_front_motion(frame)
            set_car_parts(
                objs["front_parts"],
                front_x,
                SINGLE_BRIDGE_Y,
                frame,
                z_offset=front_z,
                pitch=front_pitch,
                x_for_roll=const_x(frame, start_x=FRONT_X_START),
            )

            front = objs["front_body"]
            front["pb_state"] = front_phase
            front["pb_constant_speed_before_fall"] = SPEED_X
            front["pb_no_hovering"] = True
            front["pb_fall_start_frame"] = front_fall_start
            front["pb_fills_hole_flush"] = filled
            front["pb_top_surface_supports_rear_car"] = filled

            # Rear car never waits. Same constant speed from first to last frame.
            rear_x = const_x(frame, start_x=REAR_X_START)
            set_car_parts(
                objs["rear_parts"],
                rear_x,
                SINGLE_BRIDGE_Y,
                frame,
                z_offset=0.0,
                pitch=0.0,
                x_for_roll=rear_x,
            )

            rear = objs["rear_body"]
            if rear_x < HOLE_X_MIN:
                rear_phase = "rear_car_approaching_hole_at_constant_speed"
            elif rear_x <= HOLE_X_MAX:
                rear_phase = "rear_car_crossing_over_filled_gap_at_constant_speed"
            else:
                rear_phase = "rear_car_passed_filled_gap_at_constant_speed"

            rear["pb_state"] = rear_phase
            rear["pb_constant_speed_x"] = SPEED_X
            rear["pb_never_waits_or_stops"] = True
            rear["pb_crosses_only_after_gap_filled"] = bool(frame >= front_fall_start + PLUG_FALL_DURATION_FRAMES)
            rear["pb_does_not_float_over_empty_gap"] = True

        for obj in objs.get("static", []):
            obj["pb_scene_kind"] = kind
            obj["pb_state"] = "static_raised_bridge_scene"
            obj["pb_bridge_top_z"] = BRIDGE_TOP_Z
            obj["pb_hole_x_min"] = HOLE_X_MIN
            obj["pb_hole_x_max"] = HOLE_X_MAX

    scene.frame_set(FRAME_START)


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


def main():
    ensure_dirs()
    clear_scene()

    objs = build_scene()
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
    print("SPEED_X:", SPEED_X)
    print("BRIDGE_TOP_Z:", BRIDGE_TOP_Z)
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
