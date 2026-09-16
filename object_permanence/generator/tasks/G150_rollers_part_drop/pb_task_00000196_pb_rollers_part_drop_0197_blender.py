# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_ROLLERS_PART_DROP_0197",
  "scene_kind": "rollers_part_drop",
  "prompt": "A ball rests nestled in the valley between two parallel horizontal rollers. The two rollers move apart sideways; once the gap exceeds the ball, it drops straight down between them to the floor and bounces to rest. It is never suspended in mid-air."
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


def add_sphere(name, radius, location, material, color_name, role="target", is_dynamic=True):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "sphere", color_name, is_dynamic, solid=True, pb_radius=radius)
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
# 0197 rollers part drop
#
# A vivid ball rests nestled in the valley between two parallel horizontal
# ROLLERS (cylinders, axis along Y, apparatus gray). The ball touches both
# rollers: its center is (R_ball + R_roller) from each roller axis. The two
# rollers translate APART sideways in opposite X. As they part the ball sinks
# lower (still supported) until the surface gap exceeds the ball diameter; then
# the ball DROPS straight down (x=y=0 held) between them to the floor and
# bounces (restitution ~0.5). It is never suspended in mid-air.
# ============================================================

def build_rollers_part_drop_scene():
    scene = build_base_scene()
    # Front view down the roller axis so the valley, the parting and the drop read.
    setup_camera(scene, location=(-0.9, -8.4, 2.2), target=(0.0, 0.0, 1.0), lens=33)

    R_BALL = 0.30
    R_ROLL = 0.22
    ROLL_LEN = 1.8
    Z_ROLL = 1.20                                   # roller axis height (elevated on end posts)
    D0 = 0.30                                        # half axis separation at rest
    CONTACT = R_BALL + R_ROLL                        # center-to-axis distance while nestled

    ball_x = 0.0
    ball_y = 0.0
    ball_rest_z = Z_ROLL + math.sqrt(CONTACT ** 2 - D0 ** 2)

    # Roller motion constants (also used to compute the fall-start frame).
    HOLD_END = 18
    PART_START = HOLD_END
    PART_END = 70
    D_MAX = 0.95

    def half_sep(fr):
        if fr <= PART_START:
            return D0
        return D0 + (D_MAX - D0) * smooth01((fr - PART_START) / float(PART_END - PART_START))

    # Solve the exact sub-frame time when the gap first becomes wide enough for
    # the ball.  Starting free-fall from that continuous instant avoids spending
    # one whole rendered frame suspended at roller-axis height.
    # NOTE: degenerate case — if D_MAX < CONTACT the gap never reaches the ball,
    # yet clamp01 caps target_progress at 1.0 and the ball would still release.
    target_progress = clamp01((CONTACT - D0) / (D_MAX - D0))
    lo, hi = 0.0, 1.0
    for _ in range(32):
        mid = 0.5 * (lo + hi)
        if smooth01(mid) < target_progress:
            lo = mid
        else:
            hi = mid
    fall_start_time = PART_START + hi * (PART_END - PART_START)
    fall_start = int(math.ceil(fall_start_time))

    rollers = []
    legs = []
    for sgn, side in ((-1.0, "left"), (1.0, "right")):
        cx = sgn * D0
        roller = add_cylinder(
            f"support_roller_{side}",
            (cx, 0.0, Z_ROLL),
            R_ROLL,
            ROLL_LEN,
            MATS["frame"],
            role="support_roller",
            color_name="gray",
            solid=True,
            rotation=(math.radians(90.0), 0.0, 0.0),   # axis along Y
            vertices=40,
        )
        roller["pb_sign"] = sgn
        roller["pb_is_apparatus"] = True
        rollers.append(roller)
        # End bearing posts (apparatus gray) hold each roller up and slide with it.
        for syn, yn in ((-ROLL_LEN / 2.0 - 0.06, "n"), (ROLL_LEN / 2.0 + 0.06, "p")):
            leg = add_cube(
                f"roller_support_post_{side}_{yn}",
                (cx, syn, Z_ROLL / 2.0),
                (0.16, 0.14, Z_ROLL),
                MATS["gray"],
                role="roller_support_post",
                color_name="gray",
                solid=True,
            )
            leg["pb_sign"] = sgn
            legs.append(leg)

    ball = add_sphere(
        "falling_ball",
        R_BALL,
        (ball_x, ball_y, ball_rest_z),
        MATS["orange"],
        "orange",
        role="falling_ball",
    )
    ball["pb_expected_behavior"] = "drops_when_rollers_part"

    return {
        "scene": scene,
        "kind": "rollers_part_drop",
        "rollers": rollers,
        "legs": legs,
        "ball": ball,
        "r_ball": R_BALL,
        "r_roll": R_ROLL,
        "z_roll": Z_ROLL,
        "d0": D0,
        "d_max": D_MAX,
        "contact": CONTACT,
        "part_start": PART_START,
        "part_end": PART_END,
        "hold_end": HOLD_END,
        "fall_start": fall_start,
        "fall_start_time": fall_start_time,
        "ball_x": ball_x,
        "ball_y": ball_y,
        "ball_rest_z": ball_rest_z,
    }


def animate_rollers_part_drop(objs, frame):
    rollers = objs["rollers"]
    legs = objs["legs"]
    ball = objs["ball"]
    R_BALL = objs["r_ball"]
    Z_ROLL = objs["z_roll"]
    D0 = objs["d0"]
    D_MAX = objs["d_max"]
    CONTACT = objs["contact"]
    PART_START = objs["part_start"]
    PART_END = objs["part_end"]
    fall_start = objs["fall_start"]
    fall_start_time = objs["fall_start_time"]
    ball_x = objs["ball_x"]
    ball_y = objs["ball_y"]
    rest_z = objs["ball_rest_z"]

    # --- Rollers (+ their end posts): translate apart in opposite X -------------
    if frame <= PART_START:
        d = D0
    else:
        d = D0 + (D_MAX - D0) * smooth01((frame - PART_START) / float(PART_END - PART_START))
    for roller in rollers:
        sgn = roller["pb_sign"]
        roller.location = (sgn * d, 0.0, Z_ROLL)
        roller.keyframe_insert(data_path="location", frame=frame)
        roller["pb_state"] = "supporting_ball" if frame < fall_start_time else "parted"
    for leg in legs:
        sgn = leg["pb_sign"]
        leg.location = (sgn * d, leg.location.y, Z_ROLL / 2.0)
        leg.keyframe_insert(data_path="location", frame=frame)

    # --- Ball: nestled (sinking as rollers part), then straight-down fall + bounce
    floor_z = R_BALL
    # Give the ball a clear downward velocity as soon as the final roller
    # contact clears.  Starting free fall from zero velocity would read as a
    # one-frame mid-air pause even though the support is already gone.
    LAND_FRAME = 54
    RELEASE_DOWN_V = 0.045
    flight_time = LAND_FRAME - fall_start_time
    g = 2.0 * ((Z_ROLL - floor_z) - RELEASE_DOWN_V * flight_time) / float(flight_time ** 2)
    g = max(g, 1.0e-6)
    REST_E = 0.5

    if frame < fall_start_time:
        # Nestled: center stays (R_ball+R_roller) from each roller axis -> sinks as d grows.
        z = Z_ROLL + math.sqrt(max(0.0, CONTACT ** 2 - d * d))
        state = "resting_in_valley" if frame <= objs["hold_end"] else "sinking_as_rollers_part"
    else:
        t = frame - fall_start_time
        T0 = (-RELEASE_DOWN_V + math.sqrt(RELEASE_DOWN_V ** 2 + 2.0 * g * (Z_ROLL - floor_z))) / g
        if t <= T0:
            z = Z_ROLL - RELEASE_DOWN_V * t - 0.5 * g * t * t
            state = "free_falling_to_floor"
        else:
            tau = t - T0
            v = REST_E * (RELEASE_DOWN_V + g * T0)
            z = floor_z
            state = "settled_on_floor"
            while v > 0.03:
                dd = 2.0 * v / g
                if tau <= dd:
                    z = floor_z + v * tau - 0.5 * g * tau * tau
                    state = "bouncing_on_floor"
                    break
                tau -= dd
                v *= REST_E

    ball.location = (ball_x, ball_y, z)      # x,y held constant -> straight down
    ball.rotation_euler = (0.0, 0.0, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball["pb_state"] = state
    ball["pb_never_suspended"] = True
    ball["pb_does_not_fall_before_support_removed"] = bool(frame < fall_start_time)
    ball["pb_falls_after_support_removed"] = bool(frame >= fall_start_time)


# ============================================================
# Build / animate dispatch
# ============================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "rollers_part_drop":
        return build_rollers_part_drop_scene()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "rollers_part_drop":
            animate_rollers_part_drop(objs, frame)
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
