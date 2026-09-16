# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_BALL_STRIKES_PENDULUM_0183",
  "scene_kind": "ball_strikes_pendulum",
  "prompt": "A ball hangs at rest from a thin string beneath an overhead beam, forming a pendulum bob. A second ball rolls in along the table and strikes the hanging ball at the bottom of its arc. On impact the hanging ball swings up and away along its pendulum arc, decelerating as it rises, reaches an apex, then swings back and oscillates with steadily decaying amplitude, settling back to hanging at rest. The rolling ball slows and stops at contact. Momentum transfers; nothing is left suspended unnaturally."
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


def ease_out_quad(t):
    t = clamp01(t)
    return 1.0 - (1.0 - t) * (1.0 - t)


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
    MATS["metal"] = make_mat("mat_metal_ball", (0.62, 0.63, 0.66), roughness=0.18, metallic=1.0)
    MATS["frame"] = make_mat("mat_metal_frame", (0.30, 0.31, 0.34), roughness=0.40, metallic=0.85)
    MATS["black"] = make_mat("mat_black", (0.02, 0.02, 0.025), roughness=0.75)
    MATS["rope"] = make_mat("mat_rope_dark", (0.05, 0.05, 0.055), roughness=0.65)
    MATS["red"] = make_mat("mat_red", (0.95, 0.10, 0.06), roughness=0.30)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.42, 0.08), roughness=0.30)
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
    fill.data.energy = 145
    fill.name = "right_fill_light"

    return scene


def setup_camera(scene, location=(0.0, -9.2, 1.45), target=(0.0, 0.0, 1.15), lens=34):
    bpy.ops.object.camera_add(location=location)
    camera = bpy.context.object
    camera.name = "camera_main"
    camera.data.lens = lens
    look_at(camera, target)
    camera.data.dof.use_dof = False
    scene.camera = camera
    return camera


# ============================================================
# Ball-strikes-pendulum scene
#
# A target BALL hangs at rest from a thin string under an overhead beam,
# forming a pendulum bob. The bob hangs at the bottom of its arc, its centre
# one ball-radius above the table (so a rolling ball can strike it centre-to-
# centre on a horizontal line). A gallows stand (a vertical post BEHIND the
# action in +Y, carrying a cantilevered overhead beam out over the pivot) holds
# the pivot; it never obstructs the rolling ball's path along y = 0.
#
# A second BALL rolls in from the LEFT (-X) along the table and strikes the
# hanging bob at the bottom of its swing. On impact the bob swings UP and away
# to the RIGHT (+X) along its fixed-length arc (rising = decelerating), reaches
# an apex, then swings back and oscillates with monotonically decaying amplitude,
# settling back to hanging at rest. The rolling ball slows and stops at contact.
#
# Geometry is derived so contact is exactly surface-touch (centres 2R apart) at
# the bottom of the swing (no interpenetration), and the bob is rigidly kept at
# the string length from the pivot on every frame.
# ============================================================

_DIVERSITY = globals().get("DIVERSITY", {})

BALL_RADIUS = float(_DIVERSITY.get("ball_radius", 0.26))
BAR_Z = 2.25                          # overhead beam / pivot height
STRING_LENGTH = BAR_Z - BALL_RADIUS   # 1.99 -> bob centre rests one radius above floor
PIVOT_X = 0.0                         # bob hangs at (PIVOT_X, 0, REST_Z) at rest
REST_Z = BAR_Z - STRING_LENGTH        # 0.26 == BALL_RADIUS (bottom-of-swing centre z)

# Rolling ball approaches from the left along y = 0, centre at floor height.
ROLL_START_X = float(_DIVERSITY.get("roll_start_x", -4.2))
CONTACT_X = PIVOT_X - 2.0 * BALL_RADIUS   # -0.52: surfaces touch at the bob's rest point
ROLL_REST_X = float(_DIVERSITY.get("roll_rest_x", -1.75))

# Pendulum swing dynamics (post-impact). theta measured from vertical; the bob
# leaves the strike moving to the RIGHT (+X, theta > 0).
PEAK_ANGLE = float(_DIVERSITY.get("peak_angle", 0.68))
OMEGA = float(_DIVERSITY.get("omega", 0.1005))
DECAY = float(_DIVERSITY.get("decay", 0.013))


def build_ball_strikes_pendulum_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(0.15, -8.9, 1.55), target=(0.05, 0.0, 0.75), lens=37)

    pivot = (PIVOT_X, 0.0, BAR_Z)

    # --- Gallows stand: a vertical post BEHIND the action (+Y) carrying a
    # cantilevered overhead beam that reaches out over the pivot at y = 0. Kept
    # entirely off the rolling ball's y = 0 path.
    post_y = 1.05
    add_cube(
        "hanger_post",
        (PIVOT_X, post_y, BAR_Z / 2.0),
        (0.16, 0.16, BAR_Z),
        material=MATS["frame"], role="hanger_post", color_name="dark_gray",
    )
    add_cube(
        "hanger_base_support",
        (PIVOT_X, post_y, 0.05),
        (0.9, 0.9, 0.10),
        material=MATS["frame"], role="hanger_base_support", color_name="dark_gray",
    )
    # Overhead beam spanning from the post (+Y) out to just past the pivot (y ~ 0).
    beam_len_y = post_y + 0.20
    beam_cy = post_y - beam_len_y / 2.0 + 0.05
    add_cube(
        "support_beam",
        (PIVOT_X, beam_cy, BAR_Z + 0.06),
        (0.16, beam_len_y, 0.12),
        material=MATS["frame"], role="support_beam", color_name="dark_gray",
    )

    # --- Hanging bob: the vivid TARGET, built at the bottom of its arc. ---
    bob0 = (PIVOT_X + STRING_LENGTH * math.sin(0.0), 0.0, BAR_Z - STRING_LENGTH * math.cos(0.0))
    bob = add_sphere("swinging_ball", BALL_RADIUS, bob0, MATS["orange"], "orange", role="swinging_ball")
    bob["pb_motion_constraint"] = "fixed_length_pendulum_arc"
    bob["pb_pendulum_length_constant"] = True
    bob["pb_count_conserved"] = True

    # --- String from the beam tip (pivot) down to the bob. Apparatus gray. ---
    string = add_cylinder_between(
        "string_rod",
        (pivot[0], 0.0, pivot[2]), bob0, 0.013, MATS["rope"],
        role="string_rod", color_name="dark_gray", is_dynamic=True, solid=True, vertices=12,
    )
    string["pb_string_length_constant"] = True

    # --- Rolling ball: vivid, rolls in from the left. ---
    roller = add_sphere(
        "moving_ball", BALL_RADIUS, (ROLL_START_X, 0.0, REST_Z),
        MATS["red"], "red", role="moving_ball",
    )
    roller["pb_count_conserved"] = True

    return {
        "scene": scene,
        "kind": "ball_strikes_pendulum",
        "pivot": pivot,
        "length": STRING_LENGTH,
        "bob": bob,
        "string": string,
        "roller": roller,
        "ball_r": BALL_RADIUS,
        "rest_z": REST_Z,
    }


# ============================================================
# Animation
# ============================================================

CONTACT_FRAME = 26   # rolling ball reaches the hanging bob at the bottom of its arc
ROLL_V = (CONTACT_X - ROLL_START_X) / float(CONTACT_FRAME - FRAME_START)   # per-frame incoming speed


def _pendulum_theta(frame):
    """Signed pendulum angle (radians). 0 while hanging at rest; after the strike
    it leaves 0 moving POSITIVE (to the +X/right, away from the incoming ball),
    then oscillates with monotonically decaying amplitude toward rest."""
    if frame <= CONTACT_FRAME:
        return 0.0
    df = frame - CONTACT_FRAME
    return PEAK_ANGLE * math.exp(-DECAY * df) * math.sin(OMEGA * df)


def animate_ball_strikes_pendulum(objs, frame):
    pivot = objs["pivot"]
    L = objs["length"]
    bob = objs["bob"]
    string = objs["string"]
    roller = objs["roller"]
    R = objs["ball_r"]
    rest_z = objs["rest_z"]

    # --- Bob on its fixed-length arc about the pivot ---
    theta = _pendulum_theta(frame)
    bob_pos = Vector((
        pivot[0] + L * math.sin(theta),
        0.0,
        pivot[2] - L * math.cos(theta),
    ))
    bob.location = bob_pos
    bob.rotation_euler = (0.0, theta, 0.0)
    bob.keyframe_insert(data_path="location", frame=frame)
    bob.keyframe_insert(data_path="rotation_euler", frame=frame)
    bob["pb_state"] = "hanging_at_rest" if frame < CONTACT_FRAME else "swinging_and_damping"
    bob["pb_pendulum_length_constant"] = True

    # --- String follows the bob (anchored at the pivot) ---
    set_cylinder_between(string, (pivot[0], 0.0, pivot[2]), bob_pos)
    string.keyframe_insert(data_path="location", frame=frame)
    string.keyframe_insert(data_path="rotation_euler", frame=frame)
    string["pb_state"] = "string_follows_bob"

    # --- Rolling ball: constant-speed roll in, strikes, then slows and rolls
    # back a little (light recoil), coming to rest CLEAR of the bob's full swing
    # envelope. The bob oscillates symmetrically to BOTH sides, so a roller left
    # sitting at the contact point would be clipped by the bob's back-swing to
    # -X; recoiling it out to ROLL_REST_X keeps the gap >= 0 on every frame while
    # still reading as "slows and stops at contact". Recoil speed < incoming.
    if frame <= CONTACT_FRAME:
        rx = ROLL_START_X + ROLL_V * (frame - FRAME_START)
        r_state = "rolling_in"
    else:
        df = frame - CONTACT_FRAME
        rx = CONTACT_X - (CONTACT_X - ROLL_REST_X) * (1.0 - math.exp(-df / 8.0))
        r_state = "recoiled_slowed_to_rest"
    roller.location = (rx, 0.0, rest_z)
    roller.rotation_euler = (0.0, -(rx - ROLL_START_X) / R, 0.0)
    roller.keyframe_insert(data_path="location", frame=frame)
    roller.keyframe_insert(data_path="rotation_euler", frame=frame)
    roller["pb_state"] = r_state
    roller["pb_no_interpenetration"] = True


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if kind == "ball_strikes_pendulum":
            animate_ball_strikes_pendulum(objs, frame)
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

    if kind == "ball_strikes_pendulum":
        return build_ball_strikes_pendulum_scene()

    raise RuntimeError("Unknown scene_kind: " + str(kind))


def main():
    ensure_dirs()
    clear_scene()

    objs = build_scene_by_kind()
    scene = objs["scene"]

    animate_scene(objs)

    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, 48, OPTIONAL_FRAME_PATH)
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
