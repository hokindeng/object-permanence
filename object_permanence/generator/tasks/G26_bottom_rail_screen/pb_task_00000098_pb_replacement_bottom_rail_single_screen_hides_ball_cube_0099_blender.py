# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "kind": "bottom_rail_single_screen",
  "variant": "ball_cube",
  "prompt": "An orange ball and a blue cube are visible. A single large opaque screen rides on a bottom double rail with a visible carriage and wheel blocks. It starts parked on the right without touching the right post, slides into the center foreground to fully hide the objects, then slides back right. The same ball and cube must reappear unchanged.",
  "item_id": "PB_REPLACEMENT_BOTTOM_RAIL_SINGLE_SCREEN_HIDES_BALL_CUBE_0099"
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
    MATS["screen"] = make_mat("mat_screen", (0.46, 0.48, 0.53), 0.88)
    MATS["support"] = make_mat("mat_support", (0.16, 0.18, 0.22), 0.60)
    MATS["red"] = make_mat("mat_red", (0.92, 0.18, 0.18), 0.28)
    MATS["blue"] = make_mat("mat_blue", (0.16, 0.36, 0.95), 0.28)
    MATS["yellow"] = make_mat("mat_yellow", (0.98, 0.78, 0.15), 0.28)
    MATS["orange"] = make_mat("mat_orange", (0.97, 0.45, 0.10), 0.28)


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


def add_ball(name, radius, location, material, color_name):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=48, ring_count=24)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, "target", "dynamic_object", "sphere", color_name, True, solid=True, pb_radius=radius)
    return obj


def add_cube_target(name, location, size, material, color_name):
    return add_cube(name, location, (size, size, size), material, "target_cube", color_name, is_dynamic=True)


def setup_base(ortho=8.8, camera_loc=(0.0, -10.0, 4.0), target=(0.0, 0.0, 0.95)):
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (16.0, 8.5, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.55, 1.95), (16.0, 0.08, 3.90), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.0, -4.5, 5.8))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 950
    key.data.size = 5.5

    bpy.ops.object.light_add(type="POINT", location=(3.0, 1.8, 3.3))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 120

    bpy.ops.object.camera_add(location=camera_loc)
    cam = bpy.context.object
    cam.name = "camera_main"
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = ortho
    look_at(cam, target)
    scene.camera = cam
    return scene


TARGET_Y = 0.32
OCC_Y = -0.92


def add_ball_cube():
    add_ball("orange_ball", 0.20, (-0.55, TARGET_Y, 0.20), MATS["orange"], "orange")
    add_cube_target("blue_cube", (0.55, TARGET_Y, 0.21), 0.42, MATS["blue"], "blue")


def add_three_balls():
    add_ball("red_ball", 0.20, (-0.70, TARGET_Y, 0.20), MATS["red"], "red")
    add_ball("blue_ball", 0.20, (0.0, TARGET_Y, 0.20), MATS["blue"], "blue")
    add_ball("yellow_ball", 0.20, (0.70, TARGET_Y, 0.20), MATS["yellow"], "yellow")


def mark_group(group, motion):
    for obj in group:
        obj["pb_motion"] = motion
        obj["pb_target_y"] = TARGET_Y
        obj["pb_occluder_y"] = OCC_Y
        obj["pb_foreground_depth_separated_from_targets"] = True
        obj["pb_large_enough_to_fully_hide_targets"] = True
        obj["pb_no_panel_panel_intersection"] = True


def build_no_top_side_post_panel():
    scene = setup_base(ortho=8.6)

    y = OCC_Y

    # Fixed components first.
    # No top frame. The inner guide strips directly touch the posts.
    left_post_x = -1.95
    right_post_x = 1.95

    add_cube("left_side_post", (left_post_x, y, 1.45), (0.18, 0.20, 2.90), MATS["support"], "left_side_post", "dark_gray")
    add_cube("right_side_post", (right_post_x, y, 1.45), (0.18, 0.20, 2.90), MATS["support"], "right_side_post", "dark_gray")

    # Left post right edge = -1.86. Left guide left edge = -1.86, so it is connected.
    add_cube("left_inner_guide_strip", (-1.81, y, 1.45), (0.10, 0.24, 2.70), MATS["support"], "left_guide_connected_to_post", "dark_gray")
    # Right guide right edge = 1.86. Right post left edge = 1.86, so it is connected.
    add_cube("right_inner_guide_strip", (1.81, y, 1.45), (0.10, 0.24, 2.70), MATS["support"], "right_guide_connected_to_post", "dark_gray")

    add_cube("left_base_foot", (left_post_x, y, 0.03), (0.36, 0.28, 0.06), MATS["support"], "left_base_foot", "dark_gray")
    add_cube("right_base_foot", (right_post_x, y, 0.03), (0.36, 0.28, 0.06), MATS["support"], "right_base_foot", "dark_gray")

    z_open = 2.55
    z_closed = 1.02

    add_ball_cube()

    # Panel width 3.00: x extent [-1.50, 1.50], safely between side posts.
    # Connector chain is continuous:
    # left guide -> slider -> connector -> panel edge.
    group = [
        add_cube("large_vertical_panel", (0.0, y, z_open), (3.00, 0.10, 1.78), MATS["screen"], "single_vertical_panel", "gray", is_dynamic=True),

        add_cube("left_panel_connector", (-1.57, y, z_open), (0.14, 0.08, 0.32), MATS["support"], "left_panel_connector", "dark_gray", is_dynamic=True),
        add_cube("left_panel_slider", (-1.70, y, z_open), (0.12, 0.20, 0.32), MATS["support"], "left_panel_slider", "dark_gray", is_dynamic=True),

        add_cube("right_panel_connector", (1.57, y, z_open), (0.14, 0.08, 0.32), MATS["support"], "right_panel_connector", "dark_gray", is_dynamic=True),
        add_cube("right_panel_slider", (1.70, y, z_open), (0.12, 0.20, 0.32), MATS["support"], "right_panel_slider", "dark_gray", is_dynamic=True),
    ]

    for obj in group:
        obj["pb_no_top_frame"] = True
        obj["pb_guide_connected_to_post"] = True
        obj["pb_connector_chain_has_no_gap"] = True

    mark_group(group, "single_panel_moves_vertically_between_connected_side_guides")
    return scene, {"kind": "z", "group": group, "z0": z_open, "z1": z_closed}


def build_no_gap_top_rail_curtain():
    scene = setup_base(ortho=9.3)

    y = OCC_Y
    left_post_x = -5.05
    right_post_x = 5.05

    # Fixed components first.
    add_cube("left_rail_post", (left_post_x, y, 1.35), (0.12, 0.16, 2.70), MATS["support"], "left_rail_post", "dark_gray")
    add_cube("right_rail_post", (right_post_x, y, 1.35), (0.12, 0.16, 2.70), MATS["support"], "right_rail_post", "dark_gray")
    add_cube("top_rectangular_rail", (0.0, y, 2.65), (10.10, 0.12, 0.08), MATS["support"], "top_rail", "dark_gray")

    # Motion range. Panel width 2.70; open extent [-4.40, -1.70], clear of left post at -5.05.
    x_open = -3.05
    x_closed = 0.0

    add_three_balls()

    # Continuous vertical contact chain:
    # panel top = 2.37
    # top clamp bottom = 2.37, top = 2.47
    # hanger bottom = 2.47, top = 2.61
    # fixed rail bottom = 2.61
    panel_center_z = 1.22
    panel_h = 2.30

    group = [
        add_cube("single_curtain_panel", (x_open, y, panel_center_z), (2.70, 0.08, panel_h), MATS["screen"], "single_curtain_panel", "gray", is_dynamic=True),
        add_cube("curtain_top_clamp_bar", (x_open, y, 2.42), (2.70, 0.10, 0.10), MATS["support"], "curtain_top_clamp_touching_panel", "dark_gray", is_dynamic=True),

        add_cube("curtain_hanger_1", (x_open - 0.95, y, 2.54), (0.08, 0.08, 0.14), MATS["support"], "curtain_hanger_touching_rail", "dark_gray", is_dynamic=True),
        add_cube("curtain_hanger_2", (x_open - 0.32, y, 2.54), (0.08, 0.08, 0.14), MATS["support"], "curtain_hanger_touching_rail", "dark_gray", is_dynamic=True),
        add_cube("curtain_hanger_3", (x_open + 0.32, y, 2.54), (0.08, 0.08, 0.14), MATS["support"], "curtain_hanger_touching_rail", "dark_gray", is_dynamic=True),
        add_cube("curtain_hanger_4", (x_open + 0.95, y, 2.54), (0.08, 0.08, 0.14), MATS["support"], "curtain_hanger_touching_rail", "dark_gray", is_dynamic=True),

        add_cube("curtain_rail_block_1", (x_open - 0.95, y, 2.61), (0.20, 0.14, 0.08), MATS["support"], "rail_block_touching_top_rail", "dark_gray", is_dynamic=True),
        add_cube("curtain_rail_block_2", (x_open - 0.32, y, 2.61), (0.20, 0.14, 0.08), MATS["support"], "rail_block_touching_top_rail", "dark_gray", is_dynamic=True),
        add_cube("curtain_rail_block_3", (x_open + 0.32, y, 2.61), (0.20, 0.14, 0.08), MATS["support"], "rail_block_touching_top_rail", "dark_gray", is_dynamic=True),
        add_cube("curtain_rail_block_4", (x_open + 0.95, y, 2.61), (0.20, 0.14, 0.08), MATS["support"], "rail_block_touching_top_rail", "dark_gray", is_dynamic=True),
    ]

    for obj in group:
        obj["pb_no_visible_gap_to_top_rail"] = True
        obj["pb_not_floating"] = True

    mark_group(group, "single_curtain_slides_with_continuous_top_connection")
    return scene, {"kind": "x", "group": group, "x0": x_open, "x1": x_closed}


def build_bottom_rail_single_screen():
    scene = setup_base(ortho=8.8)

    y = OCC_Y
    left_post_x = -4.85
    right_post_x = 4.85

    # Fixed components first.
    add_cube("left_bottom_post", (left_post_x, y, 0.38), (0.12, 0.16, 0.76), MATS["support"], "left_bottom_post", "dark_gray")
    add_cube("right_bottom_post", (right_post_x, y, 0.38), (0.12, 0.16, 0.76), MATS["support"], "right_bottom_post", "dark_gray")
    add_cube("front_bottom_rail", (0.0, y - 0.08, 0.08), (9.50, 0.08, 0.08), MATS["support"], "front_bottom_rail", "dark_gray")
    add_cube("rear_bottom_rail", (0.0, y + 0.08, 0.08), (9.50, 0.08, 0.08), MATS["support"], "rear_bottom_rail", "dark_gray")

    # Motion range. Panel width 2.30; x_open=3.05 gives extent [1.90, 4.20], clear of right post at 4.85.
    x_open = 3.05
    x_closed = 0.0

    add_ball_cube()

    group = [
        add_cube("single_bottom_rail_screen", (x_open, y, 1.32), (2.30, 0.10, 2.20), MATS["screen"], "single_bottom_rail_screen", "gray", is_dynamic=True),
        add_cube("screen_bottom_carriage", (x_open, y, 0.17), (2.15, 0.28, 0.10), MATS["support"], "screen_bottom_carriage", "dark_gray", is_dynamic=True),
        add_cube("left_wheel_block", (x_open - 0.72, y, 0.06), (0.20, 0.20, 0.10), MATS["support"], "left_wheel_block", "dark_gray", is_dynamic=True),
        add_cube("right_wheel_block", (x_open + 0.72, y, 0.06), (0.20, 0.20, 0.10), MATS["support"], "right_wheel_block", "dark_gray", is_dynamic=True),
    ]

    for obj in group:
        obj["pb_bottom_rail_supported"] = True
        obj["pb_no_top_frame"] = True

    mark_group(group, "single_screen_slides_on_bottom_double_rail")
    return scene, {"kind": "x", "group": group, "x0": x_open, "x1": x_closed}


def build_scene():
    kind = CASE["kind"]
    if kind == "no_top_side_post_panel":
        return build_no_top_side_post_panel()
    if kind == "no_gap_top_rail_curtain":
        return build_no_gap_top_rail_curtain()
    if kind == "bottom_rail_single_screen":
        return build_bottom_rail_single_screen()
    raise RuntimeError("Unknown kind: " + str(kind))


def animate_x(scene, group, x0, x1):
    loc0 = [Vector(obj.location) for obj in group]
    dx = x1 - x0

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 18:
            t = 0.0
        elif frame <= 48:
            t = (frame - 18) / 30.0
        elif frame <= 82:
            t = 1.0
        elif frame <= 112:
            t = 1.0 - (frame - 82) / 30.0
        else:
            t = 0.0

        for obj, base in zip(group, loc0):
            obj.location = base + Vector((dx * t, 0.0, 0.0))
            obj.keyframe_insert(data_path="location", frame=frame)
            obj["pb_state"] = "open" if t == 0.0 else ("closed" if t == 1.0 else "moving")


def animate_z(scene, group, z0, z1):
    loc0 = [Vector(obj.location) for obj in group]
    dz = z1 - z0

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 18:
            t = 0.0
        elif frame <= 48:
            t = (frame - 18) / 30.0
        elif frame <= 82:
            t = 1.0
        elif frame <= 112:
            t = 1.0 - (frame - 82) / 30.0
        else:
            t = 0.0

        for obj, base in zip(group, loc0):
            obj.location = base + Vector((0.0, 0.0, dz * t))
            obj.keyframe_insert(data_path="location", frame=frame)
            obj["pb_state"] = "open" if t == 0.0 else ("closed" if t == 1.0 else "moving")


def animate_scene(scene, meta):
    if meta["kind"] == "x":
        animate_x(scene, meta["group"], meta["x0"], meta["x1"])
    elif meta["kind"] == "z":
        animate_z(scene, meta["group"], meta["z0"], meta["z1"])
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

    scene, meta = build_scene()
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
    print("kind:", CASE["kind"], "variant:", CASE["variant"])
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
