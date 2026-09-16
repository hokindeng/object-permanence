# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_SLIDING_HATCH_DROP_0176",
  "scene_kind": "sliding_hatch_drop",
  "prompt": "A ball rests centered on a square hatch panel set flush into a raised platform, filling a hole. The hatch slides sideways fully clear of the hole, removing the support, so the ball free-falls straight down through the opening to the floor below, where it bounces and settles, with nothing left suspended."
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


def add_sphere(name, radius, location, material, color_name, role="falling_ball"):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object", "sphere", color_name, True, solid=True, pb_radius=radius)
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
    MATS["rail"] = make_mat("mat_rail", (0.30, 0.31, 0.33), roughness=0.55, metallic=0.4)
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


def setup_camera(scene, location=(-4.2, -6.8, 3.05), target=(0.3, 0.0, 0.72), lens=34):
    bpy.ops.object.camera_add(location=location)
    camera = bpy.context.object
    camera.name = "camera_main"
    camera.data.lens = lens
    look_at(camera, target)
    camera.data.dof.use_dof = False
    scene.camera = camera


# ============================================================
# 0176 sliding_hatch_drop
#
# A raised solid PLATFORM at table height has a square HOLE at its +X end.
# A thin square HATCH panel sits flush in the hole, riding on guide rails.
# The hatch SLIDES sideways (translates in +X) fully clear of the hole,
# removing the support from a ball resting centered on it. The ball then
# free-falls straight down through the hole to the floor and BOUNCES with
# decaying hops before settling. (Distinct from G94's hinged trapdoor.)
# ============================================================

FLOOR_Z = 0.0
_DIVERSITY = globals().get("DIVERSITY", {})
PLATFORM_TOP_Z = 1.10
PLATFORM_THICK = 0.16
PLATFORM_CENTER_Z = PLATFORM_TOP_Z - PLATFORM_THICK / 2.0     # 1.02
PLATFORM_BOTTOM_Z = PLATFORM_CENTER_Z - PLATFORM_THICK / 2.0  # 0.94

BALL_R = float(_DIVERSITY.get("ball_radius", 0.26))
REST_Z = PLATFORM_TOP_Z + BALL_R          # 1.36 ball-centre at rest on the hatch
FLOOR_REST_Z = FLOOR_Z + BALL_R           # 0.26 ball-centre resting on the floor

HOLE = 1.00
HOLE_HALF = HOLE / 2.0                     # 0.50 (> BALL_R = 0.26)
BORDER = 0.80

PANEL_SIDE = HOLE - 0.02                    # 0.98 fills the hole with a hairline gap
PANEL_HALF = PANEL_SIDE / 2.0              # 0.49
PANEL_THICK = 0.06
PANEL_CENTER_Z = PLATFORM_TOP_Z - PANEL_THICK / 2.0   # 1.07 top flush with platform top

# The hatch slides in +X, cantilevering out over the open +X side, fully clear.
SLIDE_D = 1.20                             # panel left edge -0.49 -> 0.71 (> HOLE_HALF)
SLIDE_START = 26
SLIDE_FRAMES = 24                          # slides over frames 26..50

# free-fall + bounce
GRAVITY = float(_DIVERSITY.get("gravity", 0.006))
RESTITUTION = float(_DIVERSITY.get("restitution", 0.5))
SETTLE_V = 0.02                            # |v| below this on impact -> settle


def build_sliding_hatch_drop_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(-4.2, -6.8, 3.05), target=(0.15, 0.0, 0.72), lens=34)

    depth = 2.0 * (HOLE_HALF + BORDER)      # 2.60 platform depth in Y
    y_border_c = HOLE_HALF + BORDER / 2.0   # 0.90 centre of the Y borders

    # Platform is solid on -X, +Y and -Y around the hole; the +X side is OPEN so the
    # hatch can slide out over open air (drawer-style). The +Y / -Y borders run from
    # the -X border to the +X hole edge.
    px_edge = HOLE_HALF                     # 0.50 -- the platform's open +X edge (= hole edge)
    nx_outer = -(HOLE_HALF + BORDER)        # -1.30
    solid_len_x = px_edge - nx_outer        # 1.80
    solid_cx = (px_edge + nx_outer) / 2.0   # -0.40

    add_cube(
        "platform_frame_py",
        (solid_cx, y_border_c, PLATFORM_CENTER_Z),
        (solid_len_x, BORDER, PLATFORM_THICK),
        MATS["gray"], role="platform_frame", color_name="gray",
    )
    add_cube(
        "platform_frame_ny",
        (solid_cx, -y_border_c, PLATFORM_CENTER_Z),
        (solid_len_x, BORDER, PLATFORM_THICK),
        MATS["gray"], role="platform_frame", color_name="gray",
    )
    add_cube(
        "platform_frame_nx",
        (-(HOLE_HALF + BORDER / 2.0), 0.0, PLATFORM_CENTER_Z),
        (BORDER, HOLE, PLATFORM_THICK),
        MATS["gray"], role="platform_frame", color_name="gray",
    )

    # Four legs so the platform reads as a raised table (apparatus -> gray).
    leg_h = PLATFORM_BOTTOM_Z - FLOOR_Z
    for (lx, ly) in [(-1.12, 1.12), (-1.12, -1.12), (0.34, 1.05), (0.34, -1.05)]:
        add_cube(
            f"platform_leg_{'p' if lx > 0 else 'n'}x_{'p' if ly > 0 else 'n'}y",
            (lx, ly, FLOOR_Z + leg_h / 2.0),
            (0.16, 0.16, leg_h),
            MATS["box"], role="platform_leg", color_name="dark_gray",
        )

    # Guide rails (apparatus -> gray) flanking the hole in Y, running out in +X so the
    # sliding hatch has a track to ride on as it cantilevers clear. Well outside the
    # ball's footprint in Y (ball spans +-0.26; rails at +-0.53) so they never clip it.
    rail_y = HOLE_HALF + 0.03               # 0.53
    rail_top_z = PANEL_CENTER_Z - PANEL_THICK / 2.0   # 1.04 (supports panel bottom)
    rail_h = 0.05
    rail_cz = rail_top_z - rail_h / 2.0
    rail_x0 = -HOLE_HALF
    rail_x1 = HOLE_HALF + SLIDE_D + 0.20
    rail_len = rail_x1 - rail_x0
    rail_cx = (rail_x0 + rail_x1) / 2.0
    for side, sy in [("py", rail_y), ("ny", -rail_y)]:
        add_cube(
            f"hatch_guide_rail_{side}",
            (rail_cx, sy, rail_cz),
            (rail_len, 0.05, rail_h),
            MATS["rail"], role="hatch_guide_rail", color_name="dark_gray",
        )

    # --- Sliding HATCH panel: thin square filling the hole (apparatus -> gray). ---
    # is_dynamic (it translates), but role contains "panel" -> classified as apparatus.
    panel = add_cube(
        "sliding_hatch_panel",
        (0.0, 0.0, PANEL_CENTER_Z),
        (PANEL_SIDE, PANEL_SIDE, PANEL_THICK),
        MATS["panel"], role="sliding_hatch_panel", color_name="gray",
        is_dynamic=True,
    )
    panel["pb_is_sliding_hatch"] = True
    panel["pb_slides_clear_of_hole"] = True

    # --- Ball: the TARGET (vivid). Rests centered over the hole on the closed hatch. --
    ball = add_sphere(
        "falling_ball",
        BALL_R,
        (0.0, 0.0, REST_Z),
        MATS["orange"],
        "orange",
        role="falling_ball",
    )
    ball["pb_expected_behavior"] = "hatch_slides_clear_then_ball_free_falls_and_bounces"

    return {
        "scene": scene,
        "kind": "sliding_hatch_drop",
        "ball": ball,
        "panel": panel,
        "panel_center_z": PANEL_CENTER_Z,
        # bounce integrator state (mutable, advanced per frame):
        "released": False,
        "bz": REST_Z,
        "vz": 0.0,
    }


def slide_at_frame(frame):
    if frame <= SLIDE_START:
        return 0.0
    if frame >= SLIDE_START + SLIDE_FRAMES:
        return SLIDE_D
    return SLIDE_D * smooth01((frame - SLIDE_START) / float(SLIDE_FRAMES))


def animate_sliding_hatch_drop(objs, frame):
    ball = objs["ball"]
    panel = objs["panel"]
    panel_center_z = objs["panel_center_z"]

    # ---- Hatch slides sideways (+X) fully clear of the hole ----
    slide = slide_at_frame(frame)
    panel.location = (slide, 0.0, panel_center_z)
    panel.rotation_euler = (0.0, 0.0, 0.0)
    panel.keyframe_insert(data_path="location", frame=frame)
    panel.keyframe_insert(data_path="rotation_euler", frame=frame)
    if slide >= SLIDE_D - 1e-4:
        panel["pb_state"] = "slid_fully_clear_of_hole"
    elif slide > 0.0:
        panel["pb_state"] = "sliding_open"
    else:
        panel["pb_state"] = "closed_flush_in_hole"

    # ---- Ball: supported until the hatch trailing (left) edge passes the ball centre,
    # then a real free-fall with a bouncing (restitution) landing. x, y held CONSTANT. --
    panel_left_edge = -PANEL_HALF + slide
    if not objs["released"] and panel_left_edge >= 0.0:
        objs["released"] = True

    if not objs["released"]:
        objs["bz"] = REST_Z
        objs["vz"] = 0.0
        state = "resting_on_closed_hatch"
    else:
        objs["vz"] -= GRAVITY
        objs["bz"] += objs["vz"]
        if objs["bz"] <= FLOOR_REST_Z:
            objs["bz"] = FLOOR_REST_Z
            if objs["vz"] < 0.0:
                objs["vz"] = -objs["vz"] * RESTITUTION
                if objs["vz"] < SETTLE_V:
                    objs["vz"] = 0.0
            state = "bouncing_on_floor"
        else:
            state = "free_falling_through_hole"
        if objs["vz"] == 0.0 and objs["bz"] <= FLOOR_REST_Z + 1e-6:
            state = "settled_on_floor"

    bz = objs["bz"]
    ball.location = (0.0, 0.0, bz)          # x, y held CONSTANT -> straight-down drop
    ball.rotation_euler = (0.0, -0.08 * frame, 0.0)   # gentle spin, no effect on physics
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball["pb_state"] = state
    ball["pb_never_suspended"] = True


def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "sliding_hatch_drop":
        return build_sliding_hatch_drop_scene()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "sliding_hatch_drop":
            animate_sliding_hatch_drop(objs, frame)
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
