# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector
import bmesh

CASE = json.loads(r"""{
  "item_id": "PB_LATCH_RELEASE_FLAP_DROP_0195",
  "scene_kind": "latch_release_flap_drop",
  "prompt": "A ball rests on a small horizontal flap, a hinged panel on a bracket stand, held level by a latch pin under its free end. The pin is pulled out sideways; released, the flap flips down about its hinge and the ball loses its support and falls straight down to the floor, bouncing before it settles. The pin is pulled before the flap drops. Nothing remains suspended."
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


def ease_out_sine(t):
    t = clamp01(t)
    return math.sin(0.5 * math.pi * t)


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
    MATS["dark"] = make_mat("mat_dark_gray", (0.04, 0.04, 0.05), roughness=0.92)
    MATS["box"] = make_mat("mat_box_gray", (0.38, 0.39, 0.40), roughness=0.78)
    MATS["edge"] = make_mat("mat_light_edge", (0.62, 0.63, 0.64), roughness=0.68)
    MATS["panel"] = make_mat("mat_panel_gray", (0.44, 0.45, 0.47), roughness=0.70)
    MATS["hinge"] = make_mat("mat_hinge", (0.20, 0.20, 0.22), roughness=0.45, metallic=0.6)
    MATS["pin"] = make_mat("mat_pin", (0.28, 0.29, 0.32), roughness=0.35, metallic=0.8)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.38, 0.06), roughness=0.30)
    MATS["red"] = make_mat("mat_red", (0.85, 0.12, 0.10), roughness=0.32)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (9.8, 4.8, 0.10), MATS["floor"], role="ground", color_name="warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 2.42, 1.90), (10.0, 0.08, 4.20), MATS["backdrop"], role="background", color_name="off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.8, -4.4, 6.2))
    key = bpy.context.object
    key.name = "large_softbox_light"
    key.data.energy = 1050
    key.data.size = 6.0

    bpy.ops.object.light_add(type="POINT", location=(3.7, -2.8, 3.6))
    fill = bpy.context.object
    fill.name = "right_fill_light"
    fill.data.energy = 165

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
# 0195 latch-release flap drop
#
# A small horizontal FLAP (a hinged panel) is mounted on a bracket stand at
# table height. The flap is hinged along its -X edge (an empty) and extends
# +X; a ball rests centred on its top surface. A LATCH PIN (a metal rod) sits
# under the flap's free (+X) end, propping it level. The sequence is a clean
# cause -> effect chain:
#   1. the PIN is PULLED OUT sideways (translates in -Y, away),
#   2. THEN, released, the FLAP FLIPS DOWN ~90 deg about its hinge, so the ball
#      loses its support and free-falls straight down (x, y constant) to the
#      floor, BOUNCING (restitution ~0.5) before settling.
# The flap flips with an ease-out (fast start) so its top surface clears out
# from under the ball faster than gravity pulls the ball -- no clipping.
# ============================================================

BALL_R = 0.26
FLOOR_Z = 0.0
FLAP_TOP_Z = 1.10                       # level flap top surface height
FLAP_THICK = 0.08
FLAP_LEN_X = 1.20                       # flap length along X (hinge edge -> free edge)
FLAP_WID_Y = 1.00
HINGE_X = -FLAP_LEN_X / 2.0             # -0.60: hinge along the -X edge
FLAP_MID_Z = FLAP_TOP_Z - FLAP_THICK / 2.0   # 1.06: flap mid-plane (hinge z)
BALL_REST_Z = FLAP_TOP_Z + BALL_R       # 1.36: ball centre resting on the level flap
FREE_EDGE_X = HINGE_X + FLAP_LEN_X      # +0.60: free end of the flap

# Latch pin geometry: a horizontal rod (axis along Y) tucked just under the
# flap's free end, propping it level. Pulled out in -Y.
PIN_R = 0.055
PIN_X = FREE_EDGE_X - 0.06
PIN_Z = (FLAP_TOP_Z - FLAP_THICK) - PIN_R   # just below the flap underside
PIN_Y0 = 0.0
PIN_Y_OUT = -1.75                           # pulled fully clear in -Y


def build_latch_release_flap_drop_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(-4.2, -6.8, 3.05), target=(0.2, 0.0, 0.78), lens=34)

    # --- Bracket stand: an upright post at the hinge (-X) side plus a foot,
    #     holding the hinge at table height. Apparatus gray.
    post_top_z = FLAP_MID_Z
    add_cube(
        "flap_bracket_support",
        (HINGE_X - 0.10, 0.0, post_top_z / 2.0),
        (0.18, 0.9, post_top_z),
        MATS["box"], role="flap_bracket_support", color_name="gray",
    )
    add_cube(
        "flap_bracket_foot_support",
        (HINGE_X - 0.10, 0.0, 0.05),
        (0.8, 1.2, 0.10),
        MATS["box"], role="flap_bracket_support", color_name="gray",
    )

    # --- Hinge empty along the -X edge; the flap is parented to it. ---
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(HINGE_X, 0.0, FLAP_MID_Z))
    hinge = bpy.context.object
    hinge.name = "flap_hinge"
    tag(hinge, "flap_hinge", "flap_hinge_support", "static_solid", "empty", "dark_metal", False, solid=True)

    # --- The flap: a thin horizontal panel filling from hinge to free edge. ---
    flap = add_cube(
        "release_flap_panel",
        (0.0, 0.0, FLAP_MID_Z),
        (FLAP_LEN_X, FLAP_WID_Y, FLAP_THICK),
        MATS["panel"], role="release_flap_panel", color_name="gray",
    )
    flap.parent = hinge
    flap.matrix_parent_inverse = hinge.matrix_world.inverted()
    flap["pb_is_flap"] = True

    # Dark hinge bar along the hinge edge (depth cue, apparatus).
    hinge_bar = add_cube(
        "flap_hinge_bar_support",
        (HINGE_X, 0.0, FLAP_MID_Z),
        (0.06, FLAP_WID_Y * 1.02, 0.08),
        MATS["hinge"], role="flap_hinge_bar_support", color_name="dark_metal",
    )
    hinge_bar["pb_is_hinge"] = True

    # --- Latch pin: horizontal rod under the flap's free end, propping it. ---
    pin = add_cylinder(
        "latch_pin_rod",
        (PIN_X, PIN_Y0, PIN_Z),
        PIN_R, 1.10,
        MATS["pin"], role="latch_pin_rod", color_name="dark_metal",
        is_dynamic=True, rotation=(math.pi / 2.0, 0.0, 0.0), vertices=24,
    )
    pin["pb_is_latch_pin"] = True

    # --- Ball: the vivid TARGET, resting centred on the level flap. ---
    ball = add_sphere(
        "falling_ball", BALL_R, (0.0, 0.0, BALL_REST_Z),
        MATS["orange"], "orange", role="falling_ball",
    )
    ball["pb_expected_behavior"] = "pin_pulled_then_flap_flips_then_ball_free_falls_and_bounces"

    return {
        "scene": scene,
        "kind": "latch_release_flap_drop",
        "ball": ball,
        "hinge": hinge,
        "flap": flap,
        "pin": pin,
        "floor_z": FLOOR_Z,
        "ball_r": BALL_R,
        "ball_rest_z": BALL_REST_Z,
        # bounce integration state
        "b_z": BALL_REST_Z,
        "b_vz": 0.0,
    }


# ---- Timeline ----
PIN_PULL_START = 12
PIN_PULL_END = 28        # pin fully out before the flap moves
FLAP_START = 32          # flap begins to flip AFTER the pin is clear
FLAP_END = 52            # flap fully down (~90 deg)
BALL_RELEASE = FLAP_START

MAX_FLAP_ANGLE = math.pi / 2.0
GRAVITY = 0.010          # per-frame^2 free-fall acceleration
RESTITUTION = 0.5        # bounce coefficient
STOP_V = 0.006           # below this rebound speed the ball is settled


def animate_latch_release_flap_drop(objs, frame):
    ball = objs["ball"]
    hinge = objs["hinge"]
    pin = objs["pin"]
    floor_z = objs["floor_z"]
    ball_r = objs["ball_r"]
    ball_rest_z = objs["ball_rest_z"]
    floor_rest_z = floor_z + ball_r

    # ---- Pin pull (translate in -Y) ----
    if frame <= PIN_PULL_START:
        o_pin = 0.0
    elif frame >= PIN_PULL_END:
        o_pin = 1.0
    else:
        o_pin = smooth01((frame - PIN_PULL_START) / float(PIN_PULL_END - PIN_PULL_START))
    pin_y = lerp(PIN_Y0, PIN_Y_OUT, o_pin)
    pin.location = (PIN_X, pin_y, PIN_Z)
    pin.keyframe_insert(data_path="location", frame=frame)
    pin["pb_state"] = "in_place" if o_pin <= 0.0 else ("pulling_out" if o_pin < 1.0 else "pulled_clear")

    # ---- Flap flip (ease-out: fast start clears out from under the ball) ----
    if frame <= FLAP_START:
        o_flap = 0.0
    elif frame >= FLAP_END:
        o_flap = 1.0
    else:
        o_flap = ease_out_sine((frame - FLAP_START) / float(FLAP_END - FLAP_START))
    angle = MAX_FLAP_ANGLE * o_flap
    hinge.rotation_euler = (0.0, angle, 0.0)
    hinge.keyframe_insert(data_path="rotation_euler", frame=frame)

    # ---- Ball: rests until release, then free-falls straight down and bounces ----
    if frame <= BALL_RELEASE:
        objs["b_z"] = ball_rest_z
        objs["b_vz"] = 0.0
        bz = ball_rest_z
        state = "resting_on_level_flap"
    else:
        vz = objs["b_vz"] - GRAVITY      # accelerate downward
        z = objs["b_z"] + vz
        if z <= floor_rest_z and vz < 0.0:
            z = floor_rest_z
            vz = -vz * RESTITUTION        # bounce
            if abs(vz) < STOP_V:
                vz = 0.0
                z = floor_rest_z
                state = "settled_on_floor"
            else:
                state = "bouncing"
        else:
            state = "free_falling" if z > floor_rest_z else "settled_on_floor"
        objs["b_vz"] = vz
        objs["b_z"] = z
        bz = z

    ball.location = (0.0, 0.0, bz)        # x, y held CONSTANT -> straight-down drop
    ball.rotation_euler = (0.0, -0.05 * frame, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball["pb_state"] = state
    ball["pb_never_suspended"] = True


# ============================================================
# Build / animate dispatch
# ============================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "latch_release_flap_drop":
        return build_latch_release_flap_drop_scene()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "latch_release_flap_drop":
            animate_latch_release_flap_drop(objs, frame)
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
    render_png(scene, 60, OPTIONAL_FRAME_PATH)
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
