# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "scene_kind": "descending_dome_cover",
  "variant": "two_objects",
  "prompt": "Two objects rest on a table. A dome-shaped cover lowers straight down from above to fully enclose and hide them, holds, then lifts back up — the two objects are revealed unchanged in number and position.",
  "item_id": "PB_DESCENDING_DOME_COVER_0152"
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


def add_dome(name, radius, location, material, role, color_name, is_dynamic=True):
    # An opaque hemispherical dome: a UV sphere with the lower half removed so the
    # open mouth sits at its local z=0 and it caps like a cloche over the objects.
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=64, ring_count=48)
    obj = bpy.context.object
    obj.name = name
    # delete the lower hemisphere (verts below local z=0) so it becomes a dome.
    import bmesh
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    to_del = [v for v in bm.verts if v.co.z < -1e-4]
    bmesh.ops.delete(bm, geom=to_del, context="VERTS")
    bm.to_mesh(me)
    bm.free()
    obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "dome", color_name, is_dynamic, solid=True, pb_radius=radius)
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


# Geometry constants for the table, objects, and dome.
TABLE_TOP_Z = 0.80          # top surface of the tabletop
TABLE_THICK = 0.18
OBJ_Y = 0.35                # objects sit on the table (centered under the dome)
DOME_RADIUS = 1.55          # dome mouth radius; big enough to enclose both objects


def build_descending_dome_cover():
    scene = build_base_scene()

    # 1. Table (single solid tabletop with legs).
    top_center_z = TABLE_TOP_Z - TABLE_THICK / 2.0
    add_cube("table_top", (0.0, 0.35, top_center_z),
             (6.4, 4.0, TABLE_THICK), MATS["table"], "table", "wood")
    for lx, ly, nm in [(-2.9, -1.4, "leg_fl"), (2.9, -1.4, "leg_fr"),
                        (-2.9, 2.1, "leg_bl"), (2.9, 2.1, "leg_br")]:
        add_cube(nm, (lx, ly, (TABLE_TOP_Z - TABLE_THICK) / 2.0),
                 (0.18, 0.18, TABLE_TOP_Z - TABLE_THICK), MATS["table"], "table", "wood")

    # 2. Two distinct STATIC objects on the table, side by side. They never move.
    cube_dim = (0.60, 0.60, 0.60)
    cube_z = TABLE_TOP_Z + cube_dim[2] / 2.0
    add_cube("red_cube_target", (-0.72, OBJ_Y, cube_z), cube_dim, MATS["red"],
             "target_object", "red", is_dynamic=False)

    sph_r = 0.32
    sph_z = TABLE_TOP_Z + sph_r
    add_sphere("blue_sphere_target", sph_r, (0.74, OBJ_Y, sph_z), MATS["blue"],
               "target_object", "blue", is_dynamic=False)

    # 3. Opaque hemispherical DOME cover. Its open mouth (local z=0) rests on the
    #    tabletop when fully lowered, enclosing both objects. It is keyframed only
    #    in z: high above at the start (objects visible), lowered straight DOWN to
    #    cap the objects (hidden), held, then lifted back up (revealed). The dome
    #    radius is large enough to fully cover both objects with clearance, so it
    #    never intersects them as it descends.
    dome_down_z = TABLE_TOP_Z          # mouth sits exactly on the tabletop
    dome_up_z = TABLE_TOP_Z + DOME_RADIUS + 1.85   # fully clear above the objects
    dome = add_dome("descending_dome", DOME_RADIUS,
                    (0.0, OBJ_Y, dome_up_z), MATS["disc"], "descending_cover",
                    "dark_gray", is_dynamic=True)
    dome["pb_motion"] = "dome_lowers_from_above_to_cover_then_lifts_to_reveal"
    dome["pb_fixed_plane_xy"] = True
    dome["pb_cover_large_enough_to_hide_targets"] = True

    return scene, {
        "kind": "descending_dome_cover",
        "dome": dome,
        "dome_x": 0.0,
        "dome_y": OBJ_Y,
        "dome_down_z": dome_down_z,
        "dome_up_z": dome_up_z,
    }


def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "descending_dome_cover":
        return build_descending_dome_cover()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_descending_dome_cover(scene, meta):
    D = meta["dome"]
    x = meta["dome_x"]
    y = meta["dome_y"]
    down_z = meta["dome_down_z"]
    up_z = meta["dome_up_z"]

    # open01: 1.0 = fully OPEN (dome up high, objects visible), 0.0 = fully CLOSED
    # (dome down over the objects, hidden). Starts OPEN so the objects are seen first.
    #   1-20   : open (dome up high, objects visible)
    #   20-55  : dome lowers straight down to cover
    #   55-80  : hold closed (objects hidden under the dome)
    #   80-115 : dome lifts back up to reveal
    #   115-120: open (same objects revealed)
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 20:
            open01 = 1.0
            st = "open_objects_visible"
        elif frame <= 55:
            open01 = 1.0 - smooth01((frame - 20) / 35.0)
            st = "dome_lowering_to_cover"
        elif frame <= 80:
            open01 = 0.0
            st = "closed_objects_hidden"
        elif frame <= 115:
            open01 = smooth01((frame - 80) / 35.0)
            st = "dome_lifting_to_reveal"
        else:
            open01 = 1.0
            st = "open_same_objects_revealed"

        z = lerp(down_z, up_z, open01)
        D.location = (x, y, z)
        D.keyframe_insert(data_path="location", frame=frame)
        D["pb_state"] = st


def animate_scene(scene, meta):
    if meta["kind"] == "descending_dome_cover":
        animate_descending_dome_cover(scene, meta)
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
