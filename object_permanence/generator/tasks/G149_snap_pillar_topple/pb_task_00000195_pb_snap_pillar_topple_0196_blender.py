# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_SNAP_PILLAR_TOPPLE_0196",
  "scene_kind": "snap_pillar_topple",
  "prompt": "A ball rests on top of a single slender pillar. The pillar topples over sideways, rotating about its base away from under the ball. Losing its support, the ball drops nearly straight down to the floor and bounces to rest. It is never suspended in mid-air."
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


def ease_out_quad(t):
    # Decelerating profile: speed is highest at t=0 and decreases monotonically to
    # 0 at t=1 -- used for the pillar's topple and for its brief settle, so both
    # taper to rest.
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
# 0196 snap pillar topple
#
# A vivid ball rests on top of a single slender vertical PILLAR (apparatus,
# gray). The pillar TOPPLES over sideways: it rotates about its base (pivot at
# the ground) toward +X while its base kicks out in the same +X direction, so
# the fallen pillar ends up lying flat WELL CLEAR of the ball's fall column.
# Losing its support, the ball DROPS straight down (x held constant) to the
# floor and bounces (restitution ~0.5). It is never suspended in mid-air.
# ============================================================

def build_snap_pillar_topple_scene():
    scene = build_base_scene()
    # Three-quarter front view so the balanced ball, the topple and the drop read.
    setup_camera(scene, location=(-1.1, -8.2, 2.3), target=(0.5, 0.0, 0.9), lens=33)

    R_BALL = 0.26
    PIL_R = 0.12
    PIL_H = 1.5

    pil_base_x0 = 0.0
    pil_cy = 0.0
    pil_cz0 = PIL_H / 2.0                    # vertical pillar center (base on floor)

    # Slender pillar: role "pillar_post" carries the apparatus keyword "post" so
    # render.py repaints it gray (rig) and never treats it as the target.
    pillar = add_cylinder(
        "pillar_post",
        (pil_base_x0, pil_cy, pil_cz0),
        PIL_R,
        PIL_H,
        MATS["frame"],
        role="pillar_post",
        color_name="gray",
        solid=True,
        vertices=32,
    )
    pillar["pb_is_apparatus"] = True

    # Ball: vivid target resting on the pillar top (center one radius above the top).
    ball_x0 = 0.0
    ball_rest_z = PIL_H + R_BALL
    ball = add_sphere(
        "falling_ball",
        R_BALL,
        (ball_x0, pil_cy, ball_rest_z),
        MATS["orange"],
        "orange",
        role="falling_ball",
    )
    ball["pb_expected_behavior"] = "drops_when_pillar_topples"

    return {
        "scene": scene,
        "kind": "snap_pillar_topple",
        "pillar": pillar,
        "ball": ball,
        "r_ball": R_BALL,
        "pil_r": PIL_R,
        "pil_h": PIL_H,
        "pil_base_x0": pil_base_x0,
        "pil_cy": pil_cy,
        "ball_x0": ball_x0,
        "ball_rest_z": ball_rest_z,
    }


def animate_snap_pillar_topple(objs, frame):
    pillar = objs["pillar"]
    ball = objs["ball"]
    R_BALL = objs["r_ball"]
    PIL_R = objs["pil_r"]
    PIL_H = objs["pil_h"]
    pil_base_x0 = objs["pil_base_x0"]
    pil_cy = objs["pil_cy"]
    ball_x0 = objs["ball_x0"]
    ball_rest_z = objs["ball_rest_z"]

    HOLD_END = 18
    TOP_START = HOLD_END
    TOP_END = 52
    THETA_MAX = math.radians(88.0)
    THETA_FLAT = math.radians(90.0)   # raised far end rocks the last bit down to fully flat
    BASE_KICK = 0.9        # base slides +X while toppling so the fallen pillar clears the ball column
    SETTLE_END = 80        # after landing the pillar keeps rolling a touch, then decelerates to rest
    SETTLE_DRIFT = 0.14    # small continued roll in the fall (+X) direction, ~one pillar radius

    # --- Pillar: hold, then topple over sideways (rotate about base, base kicks +X)
    if frame <= TOP_START:
        theta = 0.0
        base_x = pil_base_x0
        settle = 0.0
    else:
        # This is a snap/topple event: move the pillar top out of the ball's
        # vertical fall column immediately, then decelerate toward the floor.
        # The ease-out profile is what keeps the top moving fastest in those
        # first frames, so the descending sphere never intersects the cylinder.
        tp = ease_out_quad((frame - TOP_START) / float(TOP_END - TOP_START))
        theta = THETA_MAX * tp
        base_x = pil_base_x0 + BASE_KICK * tp
        settle = 0.0
        # After the pillar hits the ground it does NOT freeze instantly: the raised
        # far end rocks down flat and the whole pillar rolls forward ~one radius in
        # the fall (+X) direction, then this settle DECELERATES smoothly (ease-out)
        # to rest. The motion is small so the pillar never rolls back under the
        # ball's fall column or off-screen.
        if frame > TOP_END:
            ts = ease_out_quad((frame - TOP_END) / float(SETTLE_END - TOP_END))
            theta = THETA_MAX + (THETA_FLAT - THETA_MAX) * ts
            settle = SETTLE_DRIFT * ts
    # Rotate about Y (local +Z tilts toward +X). Keep the bottom cap grounded:
    # z of the axis center so the low end stays ~on the floor as it lays down.
    z_axis = PIL_R + (PIL_H / 2.0 - PIL_R) * math.cos(theta)
    center_x = base_x + (PIL_H / 2.0) * math.sin(theta) + settle
    pillar.location = (center_x, pil_cy, z_axis)
    pillar.rotation_euler = (0.0, theta, 0.0)
    pillar.keyframe_insert(data_path="location", frame=frame)
    pillar.keyframe_insert(data_path="rotation_euler", frame=frame)
    if theta < 1e-4:
        pillar["pb_state"] = "standing"
    elif frame <= TOP_END:
        pillar["pb_state"] = "toppling"
    elif frame < SETTLE_END:
        pillar["pb_state"] = "settling_flat"
    else:
        pillar["pb_state"] = "toppled_flat"

    # --- Ball: rest, then pure vertical free-fall to the floor + bounce ---------
    # Support is removed the instant the pillar begins to topple; the ball drops
    # promptly (brisk descent) so it clears the tilting pillar top cleanly.
    fall_start = HOLD_END
    rest_z = ball_rest_z
    floor_z = R_BALL
    LAND_FRAME = 44
    g = 2.0 * (rest_z - floor_z) / float((LAND_FRAME - fall_start) ** 2)
    REST_E = 0.5

    if frame <= fall_start:
        z = rest_z
        state = "resting_on_pillar"
    else:
        t = frame - fall_start
        T0 = math.sqrt(2.0 * (rest_z - floor_z) / g)
        if t <= T0:
            z = rest_z - 0.5 * g * t * t
            state = "free_falling_to_floor"
        else:
            tau = t - T0
            v = REST_E * (g * T0)
            z = floor_z
            state = "settled_on_floor"
            while v > 0.03:
                d = 2.0 * v / g
                if tau <= d:
                    z = floor_z + v * tau - 0.5 * g * tau * tau
                    state = "bouncing_on_floor"
                    break
                tau -= d
                v *= REST_E

    ball.location = (ball_x0, pil_cy, z)     # x held constant -> straight down
    ball.rotation_euler = (0.0, 0.0, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball["pb_state"] = state
    ball["pb_never_suspended"] = True
    ball["pb_does_not_fall_before_support_removed"] = bool(frame <= fall_start)
    ball["pb_falls_after_support_removed"] = bool(frame > fall_start)


# ============================================================
# Build / animate dispatch
# ============================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "snap_pillar_topple":
        return build_snap_pillar_topple_scene()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "snap_pillar_topple":
            animate_snap_pillar_topple(objs, frame)
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
