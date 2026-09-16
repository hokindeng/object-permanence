# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_SLIDING_COVER_PANEL_0170",
  "scene_kind": "sliding_cover_panel",
  "prompt": "A single ball rests on the floor. A flat upright cover panel standing on a low track slides sideways in front of the ball, fully hiding it from view; it holds there, then slides back the way it came, revealing the same ball unchanged and in the same place. The ball never moves; nothing appears or vanishes."
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
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)
    MATS["panel"] = make_mat("mat_panel_teal", (0.10, 0.42, 0.45), roughness=0.58)
    MATS["rail"] = make_mat("mat_rail_dark", (0.16, 0.16, 0.18), roughness=0.70)
    MATS["ball"] = make_mat("mat_ball_yellow", (0.90, 0.68, 0.10), roughness=0.26)


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube(
        "large_floor_base",
        (0.0, 0.6, -0.05),
        (13.0, 9.0, 0.10),
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
# Sliding cover panel scene  (LINEAR SLIDE OCCLUSION)
# ============================================================
#
# A yellow ball rests on the floor at the origin and never moves. An upright
# flat panel stands on a low track in FRONT of the ball (between ball and
# camera, at y = PANEL_Y < 0). The panel starts well off to the LEFT so the
# ball is fully visible, slides linearly along +X with smooth ease-in/ease-
# out until it is centered in front of the ball (fully hiding it from the
# camera), holds there, then slides back to its start, revealing the same
# ball unchanged. Panel and ball never touch (0.54 m clearance in Y); the
# panel bottom rests exactly on the track top at every frame.

BALL_R = 0.28
BALL_X = 0.0
BALL_Z = BALL_R

PANEL_W = 1.40           # panel width along X
PANEL_T = 0.06           # panel thickness along Y
PANEL_H = 1.20           # panel height
PANEL_Y = -0.85          # panel plane (in front of the ball, behind nothing)

RAIL_H = 0.05            # low track the panel stands on and slides along
RAIL_TOP_Z = RAIL_H
PANEL_CZ = RAIL_TOP_Z + PANEL_H / 2.0     # panel center z (bottom on rail top)

PANEL_X_OUT = -2.60      # start / end: ball fully visible
PANEL_X_COVER = 0.0      # centered in front of the ball: fully hidden

SLIDE_IN_START = 20      # panel begins sliding in
SLIDE_IN_END = 48        # panel centered over the ball
SLIDE_OUT_START = 72     # panel begins sliding back
SLIDE_OUT_END = 100      # panel back at start; ball revealed


def panel_x_at(frame):
    if frame <= SLIDE_IN_START:
        return PANEL_X_OUT
    if frame <= SLIDE_IN_END:
        t = smooth01((frame - SLIDE_IN_START) / float(SLIDE_IN_END - SLIDE_IN_START))
        return lerp(PANEL_X_OUT, PANEL_X_COVER, t)
    if frame <= SLIDE_OUT_START:
        return PANEL_X_COVER
    if frame <= SLIDE_OUT_END:
        t = smooth01((frame - SLIDE_OUT_START) / float(SLIDE_OUT_END - SLIDE_OUT_START))
        return lerp(PANEL_X_COVER, PANEL_X_OUT, t)
    return PANEL_X_OUT


def build_sliding_cover_panel_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(0.0, -9.0, 1.60), target=(0.0, 0.0, 0.75), lens=36)

    # Low track: spans the full panel travel (panel spans -3.30..0.70 in X).
    rail = add_cube(
        "panel_guide_rail",
        (-1.30, PANEL_Y, RAIL_H / 2.0),
        (4.80, 0.18, RAIL_H),
        MATS["rail"],
        role="guide_rail",
        color_name="dark_gray",
    )
    rail["pb_count_conserved"] = True

    panel = add_cube(
        "sliding_cover_panel",
        (PANEL_X_OUT, PANEL_Y, PANEL_CZ),
        (PANEL_W, PANEL_T, PANEL_H),
        MATS["panel"],
        role="cover_panel",
        color_name="teal",
        is_dynamic=True,
    )
    panel["pb_count_conserved"] = True
    panel["pb_motion_constraint"] = "slides_linearly_along_track"

    ball = add_sphere(
        "hidden_ball",
        BALL_R,
        (BALL_X, 0.0, BALL_Z),
        MATS["ball"],
        "yellow",
        role="hidden_ball",
    )
    ball["pb_count_conserved"] = True
    ball["pb_motion_constraint"] = "static_never_moves"

    return {
        "scene": scene,
        "kind": "sliding_cover_panel",
        "panel": panel,
        "ball": ball,
    }


# ============================================================
# Animation
# ============================================================

def animate_sliding_cover_panel(objs, frame):
    panel = objs["panel"]
    ball = objs["ball"]

    px = panel_x_at(frame)
    panel.location = (px, PANEL_Y, PANEL_CZ)
    panel.rotation_euler = (0.0, 0.0, 0.0)
    panel.keyframe_insert(data_path="location", frame=frame)
    panel.keyframe_insert(data_path="rotation_euler", frame=frame)

    if frame <= SLIDE_IN_START:
        panel["pb_state"] = "parked_clear_of_ball"
    elif frame < SLIDE_IN_END:
        panel["pb_state"] = "sliding_in_to_cover"
    elif frame <= SLIDE_OUT_START:
        panel["pb_state"] = "holding_ball_covered"
    elif frame < SLIDE_OUT_END:
        panel["pb_state"] = "sliding_back_to_reveal"
    else:
        panel["pb_state"] = "parked_clear_of_ball"
    panel["pb_is_moving"] = bool(SLIDE_IN_START < frame < SLIDE_IN_END or SLIDE_OUT_START < frame < SLIDE_OUT_END)

    # Ball: perfectly static the whole clip -- no motion, no spin.
    ball.location = (BALL_X, 0.0, BALL_Z)
    ball.rotation_euler = (0.0, 0.0, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    covered = SLIDE_IN_END <= frame <= SLIDE_OUT_START
    ball["pb_state"] = "resting_hidden_behind_panel" if covered else "resting_visible"
    ball["pb_is_moving"] = False


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "sliding_cover_panel":
            animate_sliding_cover_panel(objs, frame)
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

    if kind == "sliding_cover_panel":
        return build_sliding_cover_panel_scene()

    raise RuntimeError("Unknown scene_kind: " + str(kind))


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
