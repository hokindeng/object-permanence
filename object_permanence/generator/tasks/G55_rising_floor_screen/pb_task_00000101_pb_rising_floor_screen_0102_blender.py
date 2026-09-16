# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "scene_kind": "rising_floor_screen",
  "variant": "two_blocks",
  "prompt": "Two colored blocks rest side by side on a table. A gray opaque panel rises vertically out of a slot in the table, covering the blocks from the bottom up until they are fully hidden, holds briefly, then descends back into the slot to reveal the two blocks unchanged in number and position.",
  "item_id": "PB_RISING_FLOOR_SCREEN_0102"
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
    MATS["slot"] = make_mat("mat_slot", (0.12, 0.12, 0.14), 0.80)
    MATS["screen"] = make_mat("mat_screen", (0.46, 0.48, 0.53), 0.88)
    MATS["support"] = make_mat("mat_support", (0.16, 0.18, 0.22), 0.60)
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


def add_sphere(name, radius, location, material, color_name):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=48, ring_count=24)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, "target", "dynamic_object", "sphere", color_name, True, solid=True, pb_radius=radius)
    return obj


def setup_camera(scene, camera_loc=(3.6, -8.4, 4.6), target=(0.0, 0.0, 1.15)):
    bpy.ops.object.camera_add(location=camera_loc)
    cam = bpy.context.object
    cam.name = "camera_main"
    cam.data.type = "PERSP"
    cam.data.lens = 42
    look_at(cam, target)
    scene.camera = cam
    return cam


def build_base_scene(camera_loc=(3.6, -8.4, 4.6), target=(0.0, 0.0, 1.15)):
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


# Geometry constants for the table + slot.
TABLE_TOP_Z = 0.80          # top surface of the tabletop
TABLE_THICK = 0.18
SLOT_Y = -0.30              # the slot sits in front of the blocks (closer to camera)
BLOCK_Y = 0.18             # blocks sit behind the slot
SLOT_HALF_W = 2.6


def build_rising_floor_screen():
    scene = build_base_scene()

    # 1. Table with a slot. We build the tabletop as two halves (front / back) so a
    #    visible dark slot runs across the middle for the panel to rise through.
    top_center_z = TABLE_TOP_Z - TABLE_THICK / 2.0
    # Front half (camera side) and back half (block side) of the tabletop, leaving a
    # narrow gap around SLOT_Y for the slot.
    front_depth = (SLOT_Y - 0.10) - (-2.4)
    front_center = ((SLOT_Y - 0.10) + (-2.4)) / 2.0
    add_cube("table_top_front", (0.0, front_center, top_center_z),
             (6.4, max(front_depth, 0.2), TABLE_THICK), MATS["table"], "table", "wood")
    back_depth = 2.6 - (SLOT_Y + 0.10)
    back_center = (2.6 + (SLOT_Y + 0.10)) / 2.0
    add_cube("table_top_back", (0.0, back_center, top_center_z),
             (6.4, max(back_depth, 0.2), TABLE_THICK), MATS["table"], "table", "wood")

    # Dark slot insert sitting just below the gap (the mouth of the slot).
    add_cube("table_slot", (0.0, SLOT_Y, TABLE_TOP_Z - 0.02),
             (2.0 * SLOT_HALF_W, 0.22, 0.06), MATS["slot"], "table", "dark_gray")

    # Table legs.
    for lx, ly, nm in [(-2.9, -2.1, "leg_fl"), (2.9, -2.1, "leg_fr"),
                        (-2.9, 2.3, "leg_bl"), (2.9, 2.3, "leg_br")]:
        add_cube(nm, (lx, ly, (TABLE_TOP_Z - TABLE_THICK) / 2.0),
                 (0.18, 0.18, TABLE_TOP_Z - TABLE_THICK), MATS["table"], "table", "wood")

    # 2. Two static colored blocks resting on the tabletop, side by side, behind the slot.
    block_dim = (0.62, 0.62, 0.62)
    block_z = TABLE_TOP_Z + block_dim[2] / 2.0
    add_cube("red_block", (-0.80, BLOCK_Y, block_z), block_dim, MATS["red"],
             "target_block", "red", is_dynamic=True)
    add_cube("green_block", (0.80, BLOCK_Y, block_z), block_dim, MATS["green"],
             "target_block", "green", is_dynamic=True)

    # 3. Rising panel. Panel height chosen to fully cover the blocks at peak.
    #    Block tops at TABLE_TOP_Z + 0.62 = 1.42. Because the camera looks DOWN at a
    #    3/4 angle, the panel top must clear the block tops by a generous margin so no
    #    sliver peeks over the edge along the line of sight. Panel is tall enough to
    #    cover from above the blocks down well past the slot mouth.
    block_top = block_z + block_dim[2] / 2.0
    panel_top_target = block_top + 0.85      # generous over-cover for the angled view
    # z_hidden: panel center such that its TOP sits just below the slot mouth
    # (fully retracted into the slot, below TABLE_TOP_Z).
    z_hidden_top = TABLE_TOP_Z - 0.04
    # Panel height spans from the retracted top up to the cover top target, so that at
    # the hidden pose the top is in the slot and at cover it reaches panel_top_target.
    panel_h = (panel_top_target - z_hidden_top) + 0.10
    panel_w = 2.0 * SLOT_HALF_W - 0.30
    z_hidden = z_hidden_top - panel_h / 2.0
    # z_cover: panel center such that its TOP clears the block tops with margin.
    z_cover = panel_top_target - panel_h / 2.0

    panel = add_cube("rising_floor_panel", (0.0, SLOT_Y, z_hidden),
                     (panel_w, 0.10, panel_h), MATS["screen"],
                     "rising_screen_panel", "gray", is_dynamic=True)

    panel["pb_z_hidden"] = z_hidden
    panel["pb_z_cover"] = z_cover
    panel["pb_motion"] = "panel_rises_vertically_from_slot"
    panel["pb_large_enough_to_fully_hide_targets"] = True
    panel["pb_foreground_depth_separated_from_targets"] = True

    return scene, {
        "kind": "rising_floor_screen",
        "panel": panel,
        "z0": z_hidden,
        "z1": z_cover,
    }


def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "rising_floor_screen":
        return build_rising_floor_screen()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_rising_floor_screen(scene, meta):
    panel = meta["panel"]
    z0 = meta["z0"]
    z1 = meta["z1"]
    base = Vector(panel.location)

    # Phase plan over 120 frames:
    #   1-20   : hidden (in slot)
    #   20-55  : rise to full cover
    #   55-80  : hold (fully covering)
    #   80-115 : descend back into slot
    #   115-120: hidden again
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 20:
            t = 0.0
        elif frame <= 55:
            t = smooth01((frame - 20) / 35.0)
        elif frame <= 80:
            t = 1.0
        elif frame <= 115:
            t = smooth01(1.0 - (frame - 80) / 35.0)
        else:
            t = 0.0

        z = lerp(z0, z1, t)
        panel.location = Vector((base.x, base.y, z))
        panel.keyframe_insert(data_path="location", frame=frame)
        panel["pb_state"] = "hidden" if t == 0.0 else ("covering" if t >= 0.999 else "moving")


def animate_scene(scene, meta):
    if meta["kind"] == "rising_floor_screen":
        animate_rising_floor_screen(scene, meta)
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
