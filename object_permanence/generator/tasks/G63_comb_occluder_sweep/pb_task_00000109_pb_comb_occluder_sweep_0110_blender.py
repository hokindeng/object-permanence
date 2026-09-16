# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "scene_kind": "comb_occluder_sweep",
  "variant": "three_blocks",
  "prompt": "Three coloured blocks sit in a row on a table. A rigid comb frame, visibly suspended from sliding carriages on an overhead guide rail, moves horizontally in front of them; as it passes, each block is alternately hidden behind a bar and revealed in the gaps. After the supported comb slides fully past, all three blocks remain in place, unchanged in number and arrangement.",
  "item_id": "PB_COMB_OCCLUDER_SWEEP_0110"
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
    MATS["comb"] = make_mat("mat_comb", (0.28, 0.30, 0.36), 0.75)
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


def setup_camera(scene, camera_loc=(0.0, -8.8, 2.6), target=(0.0, 0.0, 1.15)):
    bpy.ops.object.camera_add(location=camera_loc)
    cam = bpy.context.object
    cam.name = "camera_main"
    cam.data.type = "PERSP"
    cam.data.lens = 42
    look_at(cam, target)
    scene.camera = cam
    return cam


def build_base_scene(camera_loc=(0.0, -8.8, 2.6), target=(0.0, 0.0, 1.15)):
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


# Geometry constants for the table + block row + comb occluder.
TABLE_TOP_Z = 0.80          # top surface of the tabletop
TABLE_THICK = 0.18
BLOCK_Y = 0.45              # blocks sit toward the back (away from camera)
COMB_Y = -0.55             # comb sweeps in front of the blocks (closer to camera)


def build_comb_occluder_sweep():
    scene = build_base_scene()

    # 1. Solid tabletop that the blocks rest on.
    top_center_z = TABLE_TOP_Z - TABLE_THICK / 2.0
    add_cube("table_top", (0.0, 0.0, top_center_z),
             (6.8, 3.2, TABLE_THICK), MATS["table"], "table", "wood")

    # Table legs.
    for lx, ly, nm in [(-3.1, -1.3, "leg_fl"), (3.1, -1.3, "leg_fr"),
                        (-3.1, 1.3, "leg_bl"), (3.1, 1.3, "leg_br")]:
        add_cube(nm, (lx, ly, (TABLE_TOP_Z - TABLE_THICK) / 2.0),
                 (0.18, 0.18, TABLE_TOP_Z - TABLE_THICK), MATS["table"], "table", "wood")

    # 2. Three STATIC coloured blocks in a row on the tabletop. These never move.
    block_dim = (0.62, 0.62, 0.62)
    block_z = TABLE_TOP_Z + block_dim[2] / 2.0
    block_xs = [-1.35, 0.0, 1.35]
    block_specs = [
        ("red_block", block_xs[0], MATS["red"], "red"),
        ("green_block", block_xs[1], MATS["green"], "green"),
        ("blue_block", block_xs[2], MATS["blue"], "blue"),
    ]
    for nm, bx, mat, cname in block_specs:
        b = add_cube(nm, (bx, BLOCK_Y, block_z), block_dim, mat,
                     "target_block", cname, is_dynamic=False)
        b["pb_static_target"] = True

    # 3. Comb occluder = an empty carrier with several vertical bar cubes as children.
    #    The bars are evenly spaced with gaps roughly the width of a bar, so as the
    #    comb sweeps horizontally each block is alternately hidden behind a bar and
    #    revealed in the gaps (periodic coverage).
    block_top = block_z + block_dim[2] / 2.0
    bar_bottom = TABLE_TOP_Z + 0.01
    bar_top = block_top + 0.55            # bars clearly taller than the blocks
    bar_h = bar_top - bar_bottom
    bar_center_z = (bar_bottom + bar_top) / 2.0
    bar_w = 0.60                          # bar width along x
    bar_depth = 0.14                      # thin in y
    bar_gap = 0.70                        # gap between adjacent bars (~ block width)
    bar_pitch = bar_w + bar_gap           # center-to-center spacing

    n_bars = 6
    # Center the bar set about the carrier origin.
    span = (n_bars - 1) * bar_pitch
    bar_local_xs = [(-span / 2.0) + i * bar_pitch for i in range(n_bars)]

    # Make the horizontal motion mechanically legible: the bars form one rigid
    # hanging assembly carried by an overhead guide, rather than floating pieces.
    guide_z = bar_top + 0.38
    guide_length = 15.4
    add_cube("comb_overhead_guide_rail", (0.0, COMB_Y, guide_z),
             (guide_length, 0.18, 0.14), MATS["support"],
             "fixed_overhead_guide", "dark_gray")
    post_h = guide_z - TABLE_TOP_Z
    for px, name in [(-7.55, "comb_guide_left_post"), (7.55, "comb_guide_right_post")]:
        add_cube(name, (px, COMB_Y, TABLE_TOP_Z + post_h / 2.0),
                 (0.16, 0.22, post_h), MATS["support"],
                 "guide_support_post", "dark_gray")

    # Rigid carrier empty (parent). Bars are parented so they move together.
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0.0, COMB_Y, bar_center_z))
    carrier = bpy.context.object
    carrier.name = "comb_carrier"

    bars = []
    for i, lx in enumerate(bar_local_xs):
        bar = add_cube(f"comb_bar_{i:02d}",
                       (lx, COMB_Y, bar_center_z),
                       (bar_w, bar_depth, bar_h), MATS["comb"],
                       "comb_bar_occluder", "dark_gray", is_dynamic=True)
        bar["pb_large_enough_to_fully_hide_targets"] = True
        bar["pb_foreground_depth_separated_from_targets"] = True
        # Parent to carrier while keeping current world transform.
        bar.parent = carrier
        bar.matrix_parent_inverse = carrier.matrix_world.inverted()
        bars.append(bar)

    moving_frame = []
    spine_z = bar_top + 0.10
    spine = add_cube("comb_rigid_top_spine", (0.0, COMB_Y, spine_z),
                     (span + bar_w, 0.20, 0.18), MATS["support"],
                     "rigid_comb_spine", "dark_gray", is_dynamic=True)
    moving_frame.append(spine)
    for i, hx in enumerate((-2.25, 2.25)):
        link_bottom = spine_z + 0.09
        link_top = guide_z - 0.07
        link = add_cube(f"comb_hanger_{i}", (hx, COMB_Y, (link_bottom + link_top) / 2.0),
                        (0.12, 0.14, link_top - link_bottom), MATS["support"],
                        "comb_hanger", "dark_gray", is_dynamic=True)
        carriage = add_cube(f"comb_sliding_carriage_{i}", (hx, COMB_Y, guide_z),
                            (0.42, 0.30, 0.22), MATS["support"],
                            "sliding_rail_carriage", "dark_gray", is_dynamic=True)
        moving_frame.extend((link, carriage))

    for part in moving_frame:
        part["pb_mechanically_supported"] = True
        part.parent = carrier
        part.matrix_parent_inverse = carrier.matrix_world.inverted()
    bars.extend(moving_frame)

    # Sweep range: start with the whole comb off to the -x side (past the leftmost
    # block), end with the whole comb fully off to the +x side (past the rightmost
    # block), so it passes completely across and off to one side.
    block_left = block_xs[0] - block_dim[0] / 2.0
    block_right = block_xs[-1] + block_dim[0] / 2.0
    comb_half_span = span / 2.0 + bar_w / 2.0
    margin = 0.6
    x_start = block_left - comb_half_span - margin      # comb fully clear on the left
    x_end = block_right + comb_half_span + margin        # comb fully clear on the right

    carrier.location = Vector((x_start, COMB_Y, bar_center_z))
    carrier["pb_motion"] = "comb_slides_horizontally_across_static_blocks"
    carrier["pb_x_start"] = x_start
    carrier["pb_x_end"] = x_end
    carrier["pb_n_bars"] = n_bars
    carrier["pb_periodic_coverage"] = True

    return scene, {
        "kind": "comb_occluder_sweep",
        "carrier": carrier,
        "bars": bars,
        "x0": x_start,
        "x1": x_end,
        "z": bar_center_z,
        "y": COMB_Y,
    }


def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "comb_occluder_sweep":
        return build_comb_occluder_sweep()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_comb_occluder_sweep(scene, meta):
    carrier = meta["carrier"]
    x0 = meta["x0"]
    x1 = meta["x1"]
    y = meta["y"]
    z = meta["z"]

    # Phase plan over 120 frames:
    #   1-12    : comb resting fully off to the left (blocks all visible)
    #   12-108  : comb sweeps steadily across to the right (periodic coverage)
    #   108-120 : comb resting fully off to the right (blocks all visible again)
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 12:
            t = 0.0
        elif frame <= 108:
            t = smooth01((frame - 12) / 96.0)
        else:
            t = 1.0

        x = lerp(x0, x1, t)
        carrier.location = Vector((x, y, z))
        carrier.keyframe_insert(data_path="location", frame=frame)
        carrier["pb_state"] = "clear" if (t == 0.0 or t == 1.0) else "sweeping"


def animate_scene(scene, meta):
    if meta["kind"] == "comb_occluder_sweep":
        animate_comb_occluder_sweep(scene, meta)
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
    render_png(scene, 60, OPTIONAL_FRAME_PATH)
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
