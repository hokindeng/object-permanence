# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "scene_kind": "sliding_double_doors",
  "variant": "two_objects",
  "prompt": "Two objects sit on a table in front of a flat backboard. Two opaque doors slide in from the left and right until they meet and fully cover the two objects, hold, then slide back apart — revealing the same two objects, unchanged in number and position.",
  "item_id": "PB_EXPANDING_IRIS_DISC_0127"
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


def add_cylinder_disc(name, radius, depth, location, material, role, color_name, is_dynamic=True):
    # A flat round disc. The cylinder axis points along Y (toward the camera) so the
    # circular face lies in the vertical X-Z plane, facing the camera front view.
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, location=location, vertices=64)
    obj = bpy.context.object
    obj.name = name
    # Rotate so the cylinder axis lies along Y (default axis is Z).
    obj.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "disc", color_name, is_dynamic, solid=True, pb_radius=radius)
    return obj


def setup_camera(scene, camera_loc=(0.0, -9.0, 1.9), target=(0.0, 0.0, 1.35)):
    bpy.ops.object.camera_add(location=camera_loc)
    cam = bpy.context.object
    cam.name = "camera_main"
    cam.data.type = "PERSP"
    cam.data.lens = 42
    look_at(cam, target)
    scene.camera = cam
    return cam


def build_base_scene(camera_loc=(0.0, -9.0, 1.9), target=(0.0, 0.0, 1.35)):
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


# Geometry constants for the table, backboard, objects, and disc.
TABLE_TOP_Z = 0.80          # top surface of the tabletop
TABLE_THICK = 0.18
OBJ_Y = 0.55                # objects sit on the table, in front of the backboard
BACKBOARD_Y = 1.20          # flat backboard behind the objects
DISC_Y = -0.55              # disc plane sits in FRONT of the objects (camera side)


def build_sliding_double_doors():
    scene = build_base_scene()

    # 1. Table (single solid tabletop with legs).
    top_center_z = TABLE_TOP_Z - TABLE_THICK / 2.0
    add_cube("table_top", (0.0, 0.35, top_center_z),
             (6.4, 4.0, TABLE_THICK), MATS["table"], "table", "wood")
    for lx, ly, nm in [(-2.9, -1.4, "leg_fl"), (2.9, -1.4, "leg_fr"),
                        (-2.9, 2.1, "leg_bl"), (2.9, 2.1, "leg_br")]:
        add_cube(nm, (lx, ly, (TABLE_TOP_Z - TABLE_THICK) / 2.0),
                 (0.18, 0.18, TABLE_TOP_Z - TABLE_THICK), MATS["table"], "table", "wood")

    # 2. Flat vertical backboard behind the objects.
    board_center_z = TABLE_TOP_Z + 1.55
    add_cube("flat_backboard", (0.0, BACKBOARD_Y, board_center_z),
             (5.2, 0.12, 3.10), MATS["backboard"], "backboard", "light_gray")

    # 3. Two distinct STATIC objects on the table, side by side. They never move.
    cube_dim = (0.66, 0.66, 0.66)
    cube_z = TABLE_TOP_Z + cube_dim[2] / 2.0
    add_cube("red_cube_target", (-0.80, OBJ_Y, cube_z), cube_dim, MATS["red"],
             "target_object", "red", is_dynamic=False)

    sph_r = 0.36
    sph_z = TABLE_TOP_Z + sph_r
    add_sphere("blue_sphere_target", sph_r, (0.85, OBJ_Y, sph_z), MATS["blue"],
               "target_object", "blue", is_dynamic=False)

    # 4. Two opaque SLIDING DOORS in a plane just IN FRONT of the objects (camera
    #    side), standing on the tabletop. They slide horizontally in X: apart = OPEN
    #    (objects visible), together = CLOSED (objects fully hidden). Only the doors
    #    move; the table, backboard and objects are static. The doors sit in a plane
    #    (door_y) clearly in front of the objects so they never intersect them, and
    #    their bottom edge rests on the tabletop (no table clipping).
    door_y = 0.12
    door_w, door_t, door_h = 1.62, 0.10, 1.02
    door_cz = TABLE_TOP_Z + door_h / 2.0        # bottom edge exactly on the tabletop
    # Closed: the two doors meet (slightly overlapping) at the center seam and cover
    # the whole object span. Open: each door has slid fully off to its own side.
    closed_lx, closed_rx = -0.78, 0.78
    open_lx, open_rx = -3.15, 3.15
    left_door = add_cube("sliding_door_left", (closed_lx, door_y, door_cz),
                         (door_w, door_t, door_h), MATS["disc"], "sliding_door",
                         "dark_gray", is_dynamic=True)
    right_door = add_cube("sliding_door_right", (closed_rx, door_y, door_cz),
                          (door_w, door_t, door_h), MATS["disc"], "sliding_door",
                          "dark_gray", is_dynamic=True)
    for d in (left_door, right_door):
        d["pb_motion"] = "doors_slide_together_to_cover_then_apart_to_reveal"
        d["pb_fixed_plane_y"] = door_y
        d["pb_foreground_depth_separated_from_targets"] = True

    return scene, {
        "kind": "sliding_double_doors",
        "left_door": left_door,
        "right_door": right_door,
        "closed_lx": closed_lx,
        "closed_rx": closed_rx,
        "open_lx": open_lx,
        "open_rx": open_rx,
        "door_y": door_y,
        "door_cz": door_cz,
    }


def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "sliding_double_doors":
        return build_sliding_double_doors()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_sliding_double_doors(scene, meta):
    L = meta["left_door"]
    R = meta["right_door"]
    clx, crx = meta["closed_lx"], meta["closed_rx"]
    olx, orx = meta["open_lx"], meta["open_rx"]
    y = meta["door_y"]
    cz = meta["door_cz"]

    # open01: 1.0 = fully OPEN (doors apart, objects visible), 0.0 = fully CLOSED
    # (doors together, objects hidden). Starts OPEN so the objects are seen first.
    #   1-20   : open (objects visible)
    #   20-55  : doors slide together to cover
    #   55-80  : hold closed (objects hidden)
    #   80-115 : doors slide apart to reveal
    #   115-120: open (same objects revealed)
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 20:
            open01 = 1.0
            st = "open_objects_visible"
        elif frame <= 55:
            open01 = 1.0 - smooth01((frame - 20) / 35.0)
            st = "doors_sliding_together_to_cover"
        elif frame <= 80:
            open01 = 0.0
            st = "closed_objects_hidden"
        elif frame <= 115:
            open01 = smooth01((frame - 80) / 35.0)
            st = "doors_sliding_apart_to_reveal"
        else:
            open01 = 1.0
            st = "open_same_objects_revealed"

        lx = lerp(clx, olx, open01)
        rx = lerp(crx, orx, open01)
        L.location = (lx, y, cz)
        R.location = (rx, y, cz)
        L.keyframe_insert(data_path="location", frame=frame)
        R.keyframe_insert(data_path="location", frame=frame)
        L["pb_state"] = st
        R["pb_state"] = st


def animate_scene(scene, meta):
    if meta["kind"] == "sliding_double_doors":
        animate_sliding_double_doors(scene, meta)
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
