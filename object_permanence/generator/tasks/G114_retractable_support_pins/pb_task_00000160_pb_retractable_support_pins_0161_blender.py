# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_RETRACTABLE_SUPPORT_PINS_0161",
  "scene_kind": "retractable_support_pins",
  "prompt": "An object rests across two horizontal pins that jut out from a wall. The two pins retract sideways into the wall, removing all support, and the object falls straight down to the floor. Nothing stays suspended."
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
    tag(obj, name, role, "dynamic_object", "sphere", color_name, True, solid=True, pb_radius=radius)
    return obj


def add_cylinder(name, location, radius, depth, material=None, role="static_solid", color_name="gray", is_dynamic=False, solid=True, rotation=(0.0, 0.0, 0.0), vertices=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location, rotation=rotation)
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
    MATS["gray"] = make_mat("mat_neutral_gray", (0.66, 0.66, 0.68), roughness=0.62)
    MATS["dark"] = make_mat("mat_dark_gray", (0.14, 0.14, 0.16), roughness=0.88)
    MATS["wall"] = make_mat("mat_wall", (0.52, 0.54, 0.58), roughness=0.72)
    MATS["pin"] = make_mat("mat_pin", (0.90, 0.15, 0.15), roughness=0.5, metallic=0.0)  # vivid red; kept (role has no apparatus keyword so render.py will not repaint it)
    MATS["frame"] = make_mat("mat_frame", (0.40, 0.41, 0.43), roughness=0.62)
    MATS["edge"] = make_mat("mat_light_edge", (0.62, 0.63, 0.64), roughness=0.68)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.38, 0.06), roughness=0.30)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (9.8, 4.8, 0.10), MATS["floor"], role="ground", color_name="warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 2.42, 1.60), (10.0, 0.08, 3.20), MATS["backdrop"], role="background", color_name="off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.8, -4.4, 5.5))
    key = bpy.context.object
    key.name = "large_softbox_light"
    key.data.energy = 600
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


# ============================================================
# 0161 retractable support pins
#
# A vertical back wall stands behind the drop zone. Two horizontal round pins
# jut FORWARD (in -Y, toward the camera) out of the wall face, side by side in
# X. A ball rests across the two pins, its center one radius above the pin tops.
# The two pins then retract sideways INTO the wall (translate in +Y, back
# through the wall face) until their tips are flush with / inside the wall,
# removing all support. The instant the pin tops no longer sit under the ball
# it free-falls straight down (constant gravity acceleration) to rest on the
# floor. x/y of the ball are held constant so it drops straight down; the pins
# move in +Y, away from the ball's fall column, so they never clip the ball.
# ============================================================

def build_retractable_support_pins_scene():
    scene = build_base_scene()
    # Slight three-quarter front view so the two pins jutting from the wall, the
    # ball resting across them, the retraction, and the fall to the floor read.
    setup_camera(scene, location=(-1.1, -8.2, 2.2), target=(0.0, 0.4, 0.9), lens=33)

    BALL_R = 0.26

    # --- Back wall (static) --------------------------------------------------
    WALL_Y = 0.85               # wall face front plane is at wall_y - wall_t/2
    WALL_T = 0.30
    WALL_H = 2.6
    WALL_W = 3.2
    WALL_CZ = WALL_H / 2.0
    wall_front_y = WALL_Y - WALL_T / 2.0
    add_cube(
        "back_wall",
        (0.0, WALL_Y, WALL_CZ),
        (WALL_W, WALL_T, WALL_H),
        MATS["wall"],
        role="static_wall",
        color_name="gray",
        solid=True,
    )

    # --- Two horizontal support pins (cylinders, axis along Y) ---------------
    # The pins jut forward from the wall face toward the camera. Pin top surface
    # is where the ball rests. Pins are spaced in X so the ball straddles them.
    PIN_R = 0.10
    PIN_LEN = 1.1                       # how far the pin sticks out (along Y)
    PIN_SPACING = 0.16                  # half-distance between the two pins in X (inside the ball radius so the ball rests ON the two pins)
    pin_top_z = 1.20                    # top surface of the pins (ball rest level)
    pin_cz = pin_top_z - PIN_R          # cylinder center z
    # Pin center Y so the pin extends from inside the wall out to -Y in front.
    # At rest the pin tip reaches pin_tip_y (in front of the wall face).
    pin_tip_y = -0.10                   # tip sticks out in front of the drop column
    pin_cy_rest = pin_tip_y + PIN_LEN / 2.0

    pins = []
    for sx, side in ((-PIN_SPACING, "left"), (PIN_SPACING, "right")):
        pin = add_cylinder(
            f"support_pin_{side}",
            (sx, pin_cy_rest, pin_cz),
            PIN_R,
            PIN_LEN,
            MATS["pin"],
            role="retractable_pin",
            color_name="red",
            is_dynamic=True,
            solid=True,
            rotation=(math.radians(90.0), 0.0, 0.0),
            vertices=24,
        )
        pin["pb_supports_ball_initially"] = True
        pin["pb_rest_cy"] = pin_cy_rest
        pins.append(pin)

    # --- Ball resting across the two pins ------------------------------------
    # Ball center over x=0 (midway between the pins), y aligned with the pin
    # exposed span, one radius above the pin top surface.
    ball_x = 0.0
    ball_y = pin_tip_y + 0.30           # sits on the exposed part of the pins
    # Ball rests ON both pin cylinders: center is (BALL_R+PIN_R) from each pin axis.
    import math as _m
    ball_rest_z = pin_cz + _m.sqrt(max(0.0, (BALL_R + PIN_R) ** 2 - PIN_SPACING ** 2))
    ball = add_sphere(
        "orange_ball_on_pins",
        BALL_R,
        (ball_x, ball_y, ball_rest_z),
        MATS["orange"],
        "orange",
        role="ball_drops_when_pins_retract",
    )
    ball["pb_expected_behavior"] = "free_fall_to_floor_after_pins_retract"

    return {
        "scene": scene,
        "kind": "retractable_support_pins",
        "pins": pins,
        "ball": ball,
        "ball_r": BALL_R,
        "ball_x": ball_x,
        "ball_y": ball_y,
        "pin_top_z": pin_top_z,
        "ball_rest_z": ball_rest_z,
        "pin_len": PIN_LEN,
        "wall_front_y": wall_front_y,
    }


def animate_retractable_support_pins(objs, frame):
    pins = objs["pins"]
    ball = objs["ball"]
    ball_r = objs["ball_r"]
    ball_x = objs["ball_x"]
    ball_y = objs["ball_y"]
    pin_top_z = objs["pin_top_z"]
    pin_len = objs["pin_len"]
    wall_front_y = objs["wall_front_y"]

    # --- Pins: hold, then retract into the wall (+Y) fast (ease-in) ----------
    # Support is removed once the pin tip has passed back behind the ball's y
    # (ball_y), i.e. the exposed pin no longer sits under the ball. Retract far
    # enough that the tips end up inside/flush with the wall face.
    HOLD_END = 26
    RETRACT_DUR = 16.0
    # Distance to move each pin in +Y so its tip (rest tip at pin_tip_y) ends
    # flush with the wall face. rest tip y = pin_cy_rest - pin_len/2.
    for pin in pins:
        rest_cy = pin["pb_rest_cy"]
        rest_tip_y = rest_cy - pin_len / 2.0
        retract_dist = wall_front_y - rest_tip_y - 0.03   # tip ends flush/slightly proud -> visible red dot on the wall
        if frame <= HOLD_END:
            shift = 0.0
            pin_state = "supporting_ball"
        else:
            t = ease_in_quad((frame - HOLD_END) / RETRACT_DUR)
            shift = retract_dist * t
            pin_state = "retracting_into_wall" if t < 0.98 else "retracted_flush_with_wall"
        pin.location = (pin.location.x, rest_cy + shift, pin.location.z)
        pin.keyframe_insert(data_path="location", frame=frame)
        pin["pb_state"] = pin_state

    # Frame at which the pin tip passes back behind the ball's y (support gone).
    # tip_y(t) = rest_tip_y + retract_dist * t^2 ; gone when tip_y >= ball_y.
    rest_cy0 = pins[0]["pb_rest_cy"]
    rest_tip_y0 = rest_cy0 - pin_len / 2.0
    # Must be the SAME distance the pins actually travel above, or the release
    # time is solved against a stroke the pins never make.
    retract_dist0 = wall_front_y - rest_tip_y0 - 0.03
    need = (ball_y - rest_tip_y0) / retract_dist0
    need = max(0.0, min(1.0, need))
    frac = math.sqrt(need)
    fall_start = HOLD_END + frac * RETRACT_DUR

    # --- Ball: rest, then pure vertical free-fall to the floor ---------------
    rest_z = objs["ball_rest_z"]
    floor_z = ball_r            # ball rests on floor (top at z=0) with center = radius
    LAND_FRAME = 56
    g = 2.0 * (rest_z - floor_z) / float((LAND_FRAME - fall_start) ** 2)
    REST_E = 0.5                # restitution: the ball bounces on landing, decaying to rest

    if frame <= fall_start:
        z = rest_z
        state = "resting_supported_on_pins"
    else:
        t = frame - fall_start
        T0 = math.sqrt(2.0 * (rest_z - floor_z) / g)   # frames to first floor impact
        if t <= T0:
            z = rest_z - 0.5 * g * t * t
            state = "free_falling_to_floor"
        else:
            # successive parabolic bounces, apex shrinking by REST_E**2 each hop
            tau = t - T0
            v = REST_E * (g * T0)      # rebound speed just after the first impact
            z = floor_z
            state = "settled_on_floor"
            while v > 0.03:
                d = 2.0 * v / g        # duration of this up-and-back-down arc
                if tau <= d:
                    z = floor_z + v * tau - 0.5 * g * tau * tau
                    state = "bouncing_on_floor"
                    break
                tau -= d
                v *= REST_E

    ball.location = (ball_x, ball_y, z)
    ball.rotation_euler = (0.0, 0.0, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball["pb_state"] = state
    ball["pb_does_not_fall_before_pins_retract"] = bool(frame <= fall_start)
    ball["pb_falls_after_support_removed"] = bool(frame > fall_start)


# ============================================================
# Build / animate dispatch
# ============================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "retractable_support_pins":
        return build_retractable_support_pins_scene()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "retractable_support_pins":
            animate_retractable_support_pins(objs, frame)
        else:
            raise RuntimeError("Unknown kind: " + str(kind))

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
