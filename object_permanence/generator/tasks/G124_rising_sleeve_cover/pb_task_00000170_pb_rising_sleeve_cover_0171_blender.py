# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "scene_kind": "rising_sleeve_cover",
  "variant": "single_object",
  "prompt": "A single object rests on a raised round pedestal. An open cylindrical sleeve, visibly wider than the pedestal, starts low around it with the object visible above its rim, then rises straight up to fully engulf and hide the object, holds, then lowers back down to reveal the object unchanged in position and appearance.",
  "item_id": "PB_RISING_SLEEVE_COVER_0171"
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


def smooth01(t):
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


def lerp(a, b, t):
    return a + (b - a) * t


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
        scene.eevee.gtao_distance = 3.0
        scene.eevee.gtao_factor = 1.2
    except Exception:
        pass

    if scene.world is None:
        scene.world = bpy.data.worlds.new("clean_world")
    scene.world.color = (1.0, 1.0, 1.0)


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def make_mat(name, color, roughness=0.55):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (color[0], color[1], color[2], 1.0)
    try:
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = roughness
    except Exception:
        pass
    return mat


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), 0.85)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), 0.92)
    MATS["backboard"] = make_mat("mat_backboard", (0.88, 0.90, 0.93), 0.90)
    MATS["table"] = make_mat("mat_table", (0.74, 0.62, 0.44), 0.70)
    MATS["disc"] = make_mat("mat_disc", (0.24, 0.26, 0.30), 0.80)
    MATS["red"] = make_mat("mat_red", (0.92, 0.18, 0.18), 0.28)
    MATS["blue"] = make_mat("mat_blue", (0.16, 0.36, 0.95), 0.28)
    MATS["yellow"] = make_mat("mat_yellow", (0.98, 0.78, 0.15), 0.28)
    MATS["green"] = make_mat("mat_green", (0.18, 0.68, 0.30), 0.28)


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
    obj["pb_component_first_design"] = True
    for k, v in extras.items():
        obj[k] = v


def add_cube(name, location, dimensions, material, role, color_name, is_dynamic=False, solid=True):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "cube", color_name, is_dynamic, solid=solid)
    return obj


def add_sphere(name, radius, location, material, role, color_name, is_dynamic=False):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=48, ring_count=24)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "sphere", color_name, is_dynamic, solid=True, pb_radius=radius)
    return obj


def add_cylinder_disc(name, radius, depth, location, material, role, color_name, is_dynamic=False):
    # A short solid disc (base). Cylinder axis stays vertical (Z), so the flat round
    # face lies horizontally like a plate/base for the object to rest on.
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, location=location, vertices=64)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "disc", color_name, is_dynamic, solid=True, pb_radius=radius)
    return obj


def add_open_sleeve(name, radius, height, location, material, role, color_name, is_dynamic=True):
    # An open cylindrical sleeve / tube: a vertical cylindrical WALL with no top or
    # bottom cap (end_fill_type NOTHING). Its axis is vertical (Z). Because both ends
    # are open, when it sits low its top rim rings the base and the object pokes out
    # above it; when it rises its wall engulfs the object from all sides and the near
    # wall occludes the object from the camera.
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=height, location=location,
                                         vertices=64, end_fill_type="NOTHING")
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "tube", color_name, is_dynamic, solid=True, pb_radius=radius)
    return obj


def setup_camera(scene, camera_loc=(0.0, -9.0, 1.9), target=(0.0, 0.0, 1.65)):
    bpy.ops.object.camera_add(location=camera_loc)
    cam = bpy.context.object
    cam.name = "camera_main"
    cam.data.type = "PERSP"
    cam.data.lens = 42
    look_at(cam, target)
    scene.camera = cam
    return cam


def build_base_scene(camera_loc=(0.0, -9.0, 1.9), target=(0.0, 0.0, 1.65)):
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    # Floor / room.
    add_cube("large_floor_base", (0.0, 0.0, -0.05), (16.0, 8.5, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.55, 1.95), (16.0, 0.08, 3.90), MATS["backdrop"], "background", "off_white")

    # Lights.
    bpy.ops.object.light_add(type="AREA", location=(-3.0, -4.5, 6.2))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 1000
    key.data.size = 5.5

    bpy.ops.object.light_add(type="POINT", location=(3.4, -1.4, 3.6))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 140

    setup_camera(scene, camera_loc=camera_loc, target=target)
    return scene


# Geometry constants for the table, base, object, and rising sleeve.
TABLE_TOP_Z = 0.80          # top surface of the tabletop
TABLE_THICK = 0.18
OBJ_Y = 0.35                # object sits on the table, centered under the sleeve

BASE_H = 0.75               # tall raised round pedestal the object stands on
BASE_R = 0.50
BASE_TOP_Z = TABLE_TOP_Z + BASE_H       # top face of the base

OBJ_DIM = 0.62              # cube target edge length
OBJ_CTR_Z = BASE_TOP_Z + OBJ_DIM / 2.0  # object center
OBJ_TOP_Z = BASE_TOP_Z + OBJ_DIM        # object top

SLEEVE_R = 0.82             # visibly wider than the 0.50-radius pedestal
SLEEVE_H = 0.90             # tall enough to fully cover object at apex


def build_rising_sleeve_cover():
    scene = build_base_scene()

    # 1. Table (single solid tabletop with legs).
    top_center_z = TABLE_TOP_Z - TABLE_THICK / 2.0
    add_cube("table_top", (0.0, 0.35, top_center_z),
             (6.4, 4.0, TABLE_THICK), MATS["table"], "table", "wood")
    for lx, ly, nm in [(-2.9, -1.4, "leg_fl"), (2.9, -1.4, "leg_fr"),
                        (-2.9, 2.1, "leg_bl"), (2.9, 2.1, "leg_br")]:
        add_cube(nm, (lx, ly, (TABLE_TOP_Z - TABLE_THICK) / 2.0),
                 (0.18, 0.18, TABLE_TOP_Z - TABLE_THICK), MATS["table"], "table", "wood")

    # 2. Tall raised round PEDESTAL base (apparatus/gray) the object stands on.
    add_cylinder_disc("cover_base_support", BASE_R, BASE_H,
                      (0.0, OBJ_Y, TABLE_TOP_Z + BASE_H / 2.0),
                      MATS["disc"], "base_support", "dark_gray", is_dynamic=False)

    # 3. A single STATIC TARGET object on the base (vivid). It never moves; it is
    #    keyframed at a constant location so it has keys on every frame.
    obj = add_cube("shown_cube_target", (0.0, OBJ_Y, OBJ_CTR_Z),
                   (OBJ_DIM, OBJ_DIM, OBJ_DIM), MATS["red"],
                   "shown_object", "red", is_dynamic=True)
    obj["pb_static_target"] = True

    # 4. Open cylindrical SLEEVE (apparatus/gray). It is keyframed only in z:
    #    LOW at the start (rim just around the base, object visible above it), then
    #    rises straight UP to fully engulf/cover the object (top rim above object top,
    #    bottom rim LEVEL WITH the object base at apex -- covered because the camera
    #    sits above the object base), holds, then lowers back down to reveal.
    #
    # INVARIANTS (three literals satisfy two equations -- keep them in sync):
    #   BASE_H + 0.15 == SLEEVE_H   -> low rim clears the tabletop
    #   SLEEVE_H == OBJ_DIM + 0.28  -> apex rim level with the object base
    # The 0.01 lift below keeps the low rim strictly ABOVE the tabletop, so the
    # two surfaces are never coplanar and cannot z-fight.
    sleeve_center_low = BASE_TOP_Z + 0.15 + 0.01 - SLEEVE_H / 2.0  # low rim = table_top + 0.01
    sleeve_top_high = OBJ_TOP_Z + 0.28                        # above object top
    sleeve_center_high = sleeve_top_high - SLEEVE_H / 2.0
    sleeve = add_open_sleeve("rising_sleeve", SLEEVE_R, SLEEVE_H,
                             (0.0, OBJ_Y, sleeve_center_low), MATS["disc"],
                             "rising_sleeve_cover", "dark_gray", is_dynamic=True)
    sleeve["pb_motion"] = "sleeve_rises_from_below_to_cover_then_lowers_to_reveal"
    sleeve["pb_fixed_plane_xy"] = True
    sleeve["pb_cover_large_enough_to_hide_target"] = True

    return scene, {
        "kind": "rising_sleeve_cover",
        "sleeve": sleeve,
        "obj": obj,
        "obj_loc": (0.0, OBJ_Y, OBJ_CTR_Z),
        "sleeve_x": 0.0,
        "sleeve_y": OBJ_Y,
        "sleeve_center_low": sleeve_center_low,
        "sleeve_center_high": sleeve_center_high,
        "sleeve_top_high": sleeve_top_high,
        "sleeve_h": SLEEVE_H,
        "obj_top_z": OBJ_TOP_Z,
    }


def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "rising_sleeve_cover":
        return build_rising_sleeve_cover()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_rising_sleeve_cover(scene, meta):
    S = meta["sleeve"]
    obj = meta["obj"]
    ox, oy, oz = meta["obj_loc"]
    x = meta["sleeve_x"]
    y = meta["sleeve_y"]
    center_low = meta["sleeve_center_low"]
    center_high = meta["sleeve_center_high"]

    # cover01: 0.0 = sleeve LOW (object visible), 1.0 = sleeve HIGH (object hidden).
    #   1-20   : low (object visible above rim)
    #   20-55  : sleeve rises to fully cover
    #   55-80  : hold covered (object hidden inside sleeve)
    #   80-115 : sleeve lowers back to reveal
    #   115-120: low (same object revealed)
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 20:
            cover01 = 0.0
            st = "low_object_visible"
        elif frame <= 55:
            cover01 = smooth01((frame - 20) / 35.0)
            st = "sleeve_rising_to_cover"
        elif frame <= 80:
            cover01 = 1.0
            st = "covered_object_hidden"
        elif frame <= 115:
            cover01 = 1.0 - smooth01((frame - 80) / 35.0)
            st = "sleeve_lowering_to_reveal"
        else:
            cover01 = 0.0
            st = "low_same_object_revealed"

        z = lerp(center_low, center_high, cover01)
        S.location = (x, y, z)
        S.keyframe_insert(data_path="location", frame=frame)
        S["pb_state"] = st

        # static target: constant location, keyed every frame.
        obj.location = (ox, oy, oz)
        obj.keyframe_insert(data_path="location", frame=frame)


def animate_scene(scene, meta):
    if meta["kind"] == "rising_sleeve_cover":
        animate_rising_sleeve_cover(scene, meta)
    else:
        raise RuntimeError("Unknown animation kind: " + str(meta["kind"]))
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


def write_task_json(task):
    with open(TASK_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(task, f, indent=2, ensure_ascii=False)


def save_scene():
    bpy.ops.wm.save_as_mainfile(filepath=SCENE_FILE)


def main():
    ensure_dirs()
    clear_scene()

    scene, meta = build_scene_by_kind()
    animate_scene(scene, meta)

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

    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, 67, OPTIONAL_FRAME_PATH)
    render_png(scene, 120, OPTIONAL_FRAME_02B_PATH)
    render_animation(scene)
    write_task_json(task)
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("scene_kind:", CASE["scene_kind"], "variant:", CASE["variant"])
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
