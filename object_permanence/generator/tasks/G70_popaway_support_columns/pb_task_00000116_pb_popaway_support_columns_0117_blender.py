# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_POPAWAY_SUPPORT_COLUMNS_0117",
  "scene_kind": "popaway_support_columns",
  "prompt": "A flat slab rests on top of two side columns, with a ball sitting on the slab. The two columns slide out sideways from under the slab; with its support removed, the slab and the ball on it drop straight down together to the floor. Nothing remains suspended in the air."
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
    MATS["slab"] = make_mat("mat_slab_gray", (0.58, 0.60, 0.64), roughness=0.58)
    MATS["column"] = make_mat("mat_column_blue", (0.24, 0.42, 0.72), roughness=0.50)
    MATS["box"] = make_mat("mat_box_gray", (0.38, 0.39, 0.40), roughness=0.78)
    MATS["edge"] = make_mat("mat_light_edge", (0.62, 0.63, 0.64), roughness=0.68)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.38, 0.06), roughness=0.30)
    MATS["red"] = make_mat("mat_red", (0.85, 0.12, 0.10), roughness=0.32)
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
    key.data.energy = 950
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
# 0117 pop away support columns
# ============================================================

def build_popaway_support_columns_scene():
    scene = build_base_scene()
    # Front view: camera low and centered on -y, looking at the slab so the two
    # side columns, the slab across their tops, and the ball on the slab all read
    # clearly, and the straight-down drop is obvious.
    setup_camera(scene, location=(0.0, -8.6, 2.05), target=(0.0, 0.0, 1.0), lens=34)

    FLOOR_TOP_Z = 0.0

    # ---- Two vertical support columns (left and right) ----
    COL_H = 1.60
    COL_W = 0.46           # square footprint side length
    COL_TOP_Z = FLOOR_TOP_Z + COL_H
    COL_X = 1.55           # symmetric left (-) / right (+) offset
    col_center_z = FLOOR_TOP_Z + COL_H / 2.0

    left_col = add_cube(
        "left_support_column",
        (-COL_X, 0.0, col_center_z),
        (COL_W, COL_W, COL_H),
        MATS["column"],
        role="support_column_left",
        color_name="blue",
        solid=True,
    )
    left_col["pb_is_support"] = True

    right_col = add_cube(
        "right_support_column",
        (COL_X, 0.0, col_center_z),
        (COL_W, COL_W, COL_H),
        MATS["column"],
        role="support_column_right",
        color_name="blue",
        solid=True,
    )
    right_col["pb_is_support"] = True

    # ---- Horizontal slab resting across the tops of both columns ----
    SLAB_THICK = 0.20
    SLAB_LEN_X = 4.10      # spans across both column tops with overhang
    SLAB_LEN_Y = 1.30
    slab_center_z = COL_TOP_Z + SLAB_THICK / 2.0

    slab = add_cube(
        "flat_slab",
        (0.0, 0.0, slab_center_z),
        (SLAB_LEN_X, SLAB_LEN_Y, SLAB_THICK),
        MATS["slab"],
        role="slab_resting_on_columns",
        color_name="gray",
        solid=True,
    )
    slab["pb_rests_on_columns"] = True
    SLAB_TOP_Z = slab_center_z + SLAB_THICK / 2.0

    # ---- Ball sitting on top of the slab ----
    BALL_R = 0.42
    BALL_X = 0.0
    ball_center_z = SLAB_TOP_Z + BALL_R

    ball = add_sphere(
        "red_ball_on_slab",
        BALL_R,
        (BALL_X, 0.0, ball_center_z),
        MATS["red"],
        "red",
        role="ball_on_slab",
    )
    ball["pb_rests_on_slab"] = True

    # Vertical offset of the ball center above the slab center (kept constant while
    # they fall together so the ball stays on the slab).
    BALL_ABOVE_SLAB = ball_center_z - slab_center_z

    return {
        "scene": scene,
        "kind": "popaway_support_columns",
        "left_col": left_col,
        "right_col": right_col,
        "slab": slab,
        "ball": ball,
        "floor_top_z": FLOOR_TOP_Z,
        "col_x": COL_X,
        "col_w": COL_W,
        "slab_len_x": SLAB_LEN_X,
        "slab_thick": SLAB_THICK,
        "slab_rest_center_z": slab_center_z,
        "ball_x": BALL_X,
        "ball_r": BALL_R,
        "ball_above_slab": BALL_ABOVE_SLAB,
    }


def animate_popaway_support_columns(objs, frame):
    left_col = objs["left_col"]
    right_col = objs["right_col"]
    slab = objs["slab"]
    ball = objs["ball"]
    floor_top_z = objs["floor_top_z"]
    col_x = objs["col_x"]
    col_w = objs["col_w"]
    slab_len_x = objs["slab_len_x"]
    slab_thick = objs["slab_thick"]
    slab_rest_center_z = objs["slab_rest_center_z"]
    ball_x = objs["ball_x"]
    ball_r = objs["ball_r"]
    ball_above_slab = objs["ball_above_slab"]

    # Timeline:
    #   Phase 0 (1-24):  hold. Slab rests on both columns, ball rests on slab.
    #   Phase 1 (24-52): the two columns slide outward (left -> -x, right -> +x)
    #                    until they fully clear the ends of the slab (no clipping).
    #   Phase 2 (52-...): support removed -> slab + ball free-fall straight down
    #                    together (ease-in quad -> accelerating) and land on the floor.
    hold_end = 24
    slide_start = 24
    slide_end = 52
    fall_end = 72

    # Columns must travel far enough that their INNER face passes beyond the slab END.
    # slab end is at slab_len_x/2 from center; column inner face starts at col_x - col_w/2.
    # Clearance so the column is fully outside the slab footprint before the drop.
    clear_gap = 0.30
    col_slide_dist = (slab_len_x / 2.0) + (col_w / 2.0) + clear_gap - col_x
    if col_slide_dist < 0.0:
        col_slide_dist = 0.0

    # The slab loses support as soon as each column's inner face clears its end,
    # before the columns finish travelling to their final extra-clear positions.
    # Solve the smooth slide continuously so integer frame rounding cannot add a
    # visible unsupported pause.
    support_clear_slide = (slab_len_x / 2.0) + (col_w / 2.0) - col_x
    target_progress = clamp01(support_clear_slide / max(col_slide_dist, 1e-8))
    lo, hi = 0.0, 1.0
    for _ in range(32):
        mid = 0.5 * (lo + hi)
        if smooth01(mid) < target_progress:
            lo = mid
        else:
            hi = mid
    fall_start_time = slide_start + hi * (slide_end - slide_start)

    # ---- Columns slide outward ----
    if frame <= slide_start:
        cs = 0.0
    elif frame <= slide_end:
        cs = smooth01((frame - slide_start) / float(slide_end - slide_start)) * col_slide_dist
    else:
        cs = col_slide_dist

    # Columns keep their build-time height; they only translate outward in x.
    left_col.location = (-col_x - cs, 0.0, left_col.location[2])
    right_col.location = (col_x + cs, 0.0, right_col.location[2])
    left_col.keyframe_insert(data_path="location", frame=frame)
    right_col.keyframe_insert(data_path="location", frame=frame)
    col_state = "holding_slab" if frame <= slide_start else ("sliding_out" if frame < slide_end else "cleared_of_slab")
    left_col["pb_state"] = col_state
    right_col["pb_state"] = col_state

    # ---- Slab + ball fall together once unsupported ----
    slab_land_center_z = floor_top_z + slab_thick / 2.0  # slab lands flat on the floor
    if frame <= fall_start_time:
        slab_z = slab_rest_center_z
        drop_state = "supported_on_columns"
    else:
        t = clamp01((frame - fall_start_time) / float(fall_end - fall_start_time))
        # A small initial downward component makes support loss legible on the
        # first rendered frame, followed by accelerating gravity-like motion.
        ft = 0.35 * t + 0.65 * t * t
        slab_z = lerp(slab_rest_center_z, slab_land_center_z, ft)
        slab_z = max(slab_land_center_z, slab_z)
        drop_state = "free_falling" if slab_z > slab_land_center_z + 0.01 else "landed_on_floor"

    slab.location = (0.0, 0.0, slab_z)
    slab.keyframe_insert(data_path="location", frame=frame)
    slab["pb_state"] = drop_state
    slab["pb_never_suspended"] = True

    # Ball stays on the slab: same relative vertical offset, same x, throughout.
    ball_z = slab_z + ball_above_slab
    ball.location = (ball_x, 0.0, ball_z)
    # Gentle spin only during/after the fall for a touch of life; stays glued in x/z.
    ball.rotation_euler = (0.0, -0.05 * max(0.0, frame - fall_start_time), 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball["pb_state"] = "riding_slab_" + drop_state
    ball["pb_never_suspended"] = True


# ============================================================
# Build / animate dispatch
# ============================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "popaway_support_columns":
        return build_popaway_support_columns_scene()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "popaway_support_columns":
            animate_popaway_support_columns(objs, frame)
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
