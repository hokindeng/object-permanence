# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "scene_kind": "rolling_shutter",
  "variant": "two_objects",
  "prompt": "Two objects sit on a table. A segmented rolling shutter descends from above in front of them, its horizontal slats coming down one region at a time until the objects are fully covered; it holds, then rolls back up, revealing the same two objects unchanged.",
  "item_id": "PB_ROLLING_SHUTTER_0128"
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
    MATS["table"] = make_mat("mat_table", (0.74, 0.62, 0.44), 0.70)
    MATS["shutter"] = make_mat("mat_shutter", (0.46, 0.48, 0.53), 0.55)
    MATS["shutter_gap"] = make_mat("mat_shutter_gap", (0.14, 0.15, 0.18), 0.70)
    MATS["frame"] = make_mat("mat_frame", (0.20, 0.22, 0.26), 0.50)
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


def add_cylinder(name, radius, depth, location, material, role, color_name, is_dynamic=False, solid=True):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, location=location, vertices=48)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "cylinder", color_name, is_dynamic, solid=solid)
    return obj


def add_sphere(name, radius, location, material, color_name, is_dynamic=False):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=48, ring_count=24)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, "target", "dynamic_object" if is_dynamic else "static_solid", "sphere", color_name, is_dynamic, solid=True, pb_radius=radius)
    return obj


def setup_camera(scene, camera_loc=(0.0, -9.2, 2.35), target=(0.0, 0.0, 1.55)):
    bpy.ops.object.camera_add(location=camera_loc)
    cam = bpy.context.object
    cam.name = "camera_main"
    cam.data.type = "PERSP"
    cam.data.lens = 46
    look_at(cam, target)
    scene.camera = cam
    return cam


def build_base_scene(camera_loc=(0.0, -9.2, 2.35), target=(0.0, 0.0, 1.55)):
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    # Floor / room.
    add_cube("large_floor_base", (0.0, 0.0, -0.05), (16.0, 8.5, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.55, 2.55), (16.0, 0.08, 5.10), MATS["backdrop"], "background", "off_white")

    # Lights.
    bpy.ops.object.light_add(type="AREA", location=(-3.0, -4.5, 6.8))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 1100
    key.data.size = 5.5

    bpy.ops.object.light_add(type="POINT", location=(3.4, -3.4, 3.6))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 160

    setup_camera(scene, camera_loc=camera_loc, target=target)
    return scene


# Geometry constants for the table + shutter.
TABLE_TOP_Z = 0.80          # top surface of the tabletop
TABLE_THICK = 0.18
SHUTTER_Y = -0.55           # the shutter descends in front of the objects (camera side)
OBJECT_Y = 0.28             # the two static objects sit behind the shutter plane
SHUTTER_HALF_W = 2.5


def build_rolling_shutter():
    scene = build_base_scene()

    # 1. Table.
    top_center_z = TABLE_TOP_Z - TABLE_THICK / 2.0
    add_cube("table_top", (0.0, 0.10, top_center_z),
             (6.6, 5.0, TABLE_THICK), MATS["table"], "table", "wood")
    for lx, ly, nm in [(-2.9, -2.1, "leg_fl"), (2.9, -2.1, "leg_fr"),
                        (-2.9, 2.3, "leg_bl"), (2.9, 2.3, "leg_br")]:
        add_cube(nm, (lx, ly, (TABLE_TOP_Z - TABLE_THICK) / 2.0),
                 (0.18, 0.18, TABLE_TOP_Z - TABLE_THICK), MATS["table"], "table", "wood")

    # 2. Two DISTINCT static objects resting on the tabletop, side by side, behind the
    #    shutter plane. These never move. One cube, one cylinder for clear distinction.
    box_dim = (0.66, 0.66, 0.66)
    box_z = TABLE_TOP_Z + box_dim[2] / 2.0
    left_obj = add_cube("red_box", (-0.90, OBJECT_Y, box_z), box_dim, MATS["red"],
                        "target_object", "red", is_dynamic=False)

    cyl_r = 0.34
    cyl_h = 0.86
    cyl_z = TABLE_TOP_Z + cyl_h / 2.0
    right_obj = add_cylinder("blue_cylinder", cyl_r, cyl_h, (0.90, OBJECT_Y, cyl_z),
                             MATS["blue"], "target_object", "blue", is_dynamic=False)

    tallest_top = max(box_z + box_dim[2] / 2.0, cyl_z + cyl_h / 2.0)

    # 3. Overhead frame/housing that the shutter rolls out of (visual anchor at top so
    #    the shutter is never a floating panel; it descends from this housing).
    #    Coverage span: shutter must cover from near the tabletop up past the object tops.
    cover_bottom = TABLE_TOP_Z + 0.02        # just above the tabletop surface
    cover_top = tallest_top + 0.60           # generous over-cover above tallest object
    span = cover_top - cover_bottom          # vertical extent that must be covered

    housing_z = cover_top + 0.55
    add_cube("shutter_housing", (0.0, SHUTTER_Y, housing_z),
             (2.0 * SHUTTER_HALF_W + 0.60, 0.42, 0.42), MATS["frame"], "shutter_housing", "dark_gray")
    # Side rails framing the shutter travel path.
    rail_h = (housing_z) - cover_bottom
    rail_cz = (housing_z + cover_bottom) / 2.0
    for rx, nm in [(-(SHUTTER_HALF_W + 0.16), "shutter_rail_l"),
                   ((SHUTTER_HALF_W + 0.16), "shutter_rail_r")]:
        add_cube(nm, (rx, SHUTTER_Y, rail_cz),
                 (0.16, 0.42, rail_h), MATS["frame"], "shutter_frame", "dark_gray")

    # 4. Segmented rolling shutter: a stack of thin horizontal slat boxes parented to a
    #    single rigid empty controller. Moving the controller moves all slats as one
    #    rigid panel. Slat lines give the segmented rolling-shutter look.
    n_slats = 8
    panel_w = 2.0 * SHUTTER_HALF_W
    panel_h = span + 0.30                    # slightly taller than coverage span
    slat_gap = 0.03
    slat_h = (panel_h - slat_gap * (n_slats - 1)) / n_slats

    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0.0, SHUTTER_Y, 0.0))
    controller = bpy.context.object
    controller.name = "rolling_shutter_controller"
    tag(controller, "rolling_shutter_controller", "rolling_shutter_panel", "dynamic_object",
        "empty", "gray", True, solid=False)

    # Slats built local to the controller: panel bottom at local z = 0, going up.
    slats = []
    for i in range(n_slats):
        local_cz = slat_h / 2.0 + i * (slat_h + slat_gap)
        slat = add_cube(f"shutter_slat_{i:02d}", (0.0, SHUTTER_Y, local_cz),
                        (panel_w, 0.10, slat_h), MATS["shutter"], "shutter_slat", "gray",
                        is_dynamic=True)
        # thin dark gap strip beneath each slat (except the first) for segmented look
        if i > 0:
            gap_cz = local_cz - slat_h / 2.0 - slat_gap / 2.0
            gapbar = add_cube(f"shutter_gap_{i:02d}", (0.0, SHUTTER_Y - 0.005, gap_cz),
                              (panel_w, 0.115, slat_gap), MATS["shutter_gap"],
                              "shutter_slat_gap", "dark_gray", is_dynamic=True)
            gapbar.parent = controller
            slats.append(gapbar)
        slat.parent = controller
        slats.append(slat)

    # Poses for the controller (which sets the panel bottom's world z via local origin).
    # z_hidden: panel fully retracted so its BOTTOM sits at/above the housing (rolled up
    #           into the housing, out of view of the objects).
    #   controller.z + panel_bottom_local(=0) should place bottom near housing base.
    z_hidden = housing_z - 0.30              # panel bottom tucked up near the housing
    # z_cover: panel bottom reaches cover_bottom (just above the tabletop) so the whole
    #          coverage span is occluded from the front.
    z_cover = cover_bottom

    controller.location = Vector((0.0, SHUTTER_Y, z_hidden))

    controller["pb_z_hidden"] = z_hidden
    controller["pb_z_cover"] = z_cover
    controller["pb_n_slats"] = n_slats
    controller["pb_motion"] = "segmented_shutter_descends_from_housing"
    controller["pb_large_enough_to_fully_hide_targets"] = True
    controller["pb_foreground_depth_separated_from_targets"] = True

    return scene, {
        "kind": "rolling_shutter",
        "controller": controller,
        "z0": z_hidden,
        "z1": z_cover,
    }


def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "rolling_shutter":
        return build_rolling_shutter()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_rolling_shutter(scene, meta):
    controller = meta["controller"]
    z0 = meta["z0"]
    z1 = meta["z1"]
    base = Vector(controller.location)

    # Phase plan over 120 frames:
    #   1-18   : hidden (rolled up in housing)
    #   18-55  : descend to full cover (slats come down region by region)
    #   55-82  : hold (fully covering)
    #   82-116 : roll back up into housing
    #   116-120: hidden again
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 18:
            t = 0.0
        elif frame <= 55:
            t = smooth01((frame - 18) / 37.0)
        elif frame <= 82:
            t = 1.0
        elif frame <= 116:
            t = smooth01(1.0 - (frame - 82) / 34.0)
        else:
            t = 0.0

        z = lerp(z0, z1, t)
        controller.location = Vector((base.x, base.y, z))
        controller.keyframe_insert(data_path="location", frame=frame)
        controller["pb_state"] = "hidden" if t == 0.0 else ("covering" if t >= 0.999 else "moving")


def animate_scene(scene, meta):
    if meta["kind"] == "rolling_shutter":
        animate_rolling_shutter(scene, meta)
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
