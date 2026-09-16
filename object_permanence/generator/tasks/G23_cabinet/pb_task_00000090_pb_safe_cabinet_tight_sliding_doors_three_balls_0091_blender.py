# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "kind": "cabinet_tight_doors",
  "variant": "three_balls",
  "prompt": "A shallow display cabinet with a real open interior contains three balls: red, blue, and yellow. Two front sliding doors move inward on a visible top rail and bottom rail. When closed, the doors meet exactly at the center with no large gap and no overlap. Then the doors reopen, and the three balls must reappear in the same order.",
  "item_id": "PB_SAFE_CABINET_TIGHT_SLIDING_DOORS_THREE_BALLS_0091"
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
    MATS["case"] = make_mat("mat_case", (0.70, 0.71, 0.74), 0.74)
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


def add_pyramid(name, size, location, material, color_name):
    bpy.ops.mesh.primitive_cone_add(
        vertices=3,
        radius1=size * 0.62,
        radius2=0.0,
        depth=size,
        location=location,
        rotation=(0.0, 0.0, math.radians(-30)),
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, "target", "dynamic_object", "triangular_pyramid", color_name, True, solid=True)
    return obj


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


def add_three_shapes():
    add_ball("orange_ball", 0.20, (-0.78, TARGET_Y, 0.20), MATS["orange"], "orange")
    add_cube("blue_cube", (0.0, TARGET_Y, 0.21), (0.42, 0.42, 0.42), MATS["blue"], "target_cube", "blue", is_dynamic=True)
    add_pyramid("yellow_pyramid", 0.50, (0.78, TARGET_Y, 0.25), MATS["yellow"], "yellow")


def add_two_balls():
    add_ball("red_ball", 0.20, (-0.45, TARGET_Y, 0.20), MATS["red"], "red")
    add_ball("blue_ball", 0.20, (0.45, TARGET_Y, 0.20), MATS["blue"], "blue")


def add_ball_cube_inside_cabinet(box_y):
    # Cabinet floor top = 0.12, so ball center = 0.12 + 0.18 = 0.30.
    add_ball("orange_ball_inside_cabinet", 0.18, (-0.45, box_y, 0.30), MATS["orange"], "orange")
    add_cube(
        "blue_cube_inside_cabinet",
        (0.45, box_y, 0.30),
        (0.36, 0.36, 0.36),
        MATS["blue"],
        "target_cube",
        "blue",
        is_dynamic=True,
    )


def add_three_balls_inside_cabinet(box_y):
    add_ball("red_ball_inside_cabinet", 0.17, (-0.65, box_y, 0.29), MATS["red"], "red")
    add_ball("blue_ball_inside_cabinet", 0.17, (0.0, box_y, 0.29), MATS["blue"], "blue")
    add_ball("yellow_ball_inside_cabinet", 0.17, (0.65, box_y, 0.29), MATS["yellow"], "yellow")


def mark_group(group, motion):
    for obj in group:
        obj["pb_motion"] = motion
        obj["pb_target_y"] = TARGET_Y
        obj["pb_occluder_y"] = OCC_Y
        obj["pb_foreground_depth_separated_from_targets"] = True
        obj["pb_large_enough_to_fully_hide_targets"] = True
        obj["pb_no_panel_panel_intersection"] = True


def build_cabinet_shell(prefix, box_y=0.32):
    # Real cavity: front is open; not a solid box.
    add_cube(f"{prefix}_floor", (0.0, box_y, 0.06), (2.90, 1.10, 0.12), MATS["case"], "cabinet_floor", "gray")
    add_cube(f"{prefix}_back_wall", (0.0, box_y + 0.52, 0.72), (2.90, 0.08, 1.32), MATS["case"], "cabinet_back_wall", "gray")
    add_cube(f"{prefix}_left_wall", (-1.41, box_y, 0.72), (0.08, 1.10, 1.32), MATS["case"], "cabinet_left_wall", "gray")
    add_cube(f"{prefix}_right_wall", (1.41, box_y, 0.72), (0.08, 1.10, 1.32), MATS["case"], "cabinet_right_wall", "gray")
    add_cube(f"{prefix}_top", (0.0, box_y, 1.42), (2.90, 1.10, 0.12), MATS["case"], "cabinet_top", "gray")


def build_top_rail_screen():
    scene = setup_base(ortho=9.2)

    # 1. Fixed rail frame.
    y = OCC_Y
    left_post_x = -5.10
    right_post_x = 5.10
    add_cube("left_overhead_post", (left_post_x, y, 1.38), (0.12, 0.16, 2.76), MATS["support"], "overhead_post", "dark_gray")
    add_cube("right_overhead_post", (right_post_x, y, 1.38), (0.12, 0.16, 2.76), MATS["support"], "overhead_post", "dark_gray")
    add_cube("top_overhead_beam", (0.0, y, 2.82), (10.35, 0.16, 0.12), MATS["support"], "overhead_beam", "dark_gray")
    add_cube("inner_trolley_rail", (0.0, y, 2.60), (9.70, 0.10, 0.08), MATS["support"], "trolley_rail", "dark_gray")

    # 2. Motion range. Panel width 2.70; x_open=-3.10 gives extents [-4.45,-1.75], clear of left post.
    x_open = -3.10
    x_closed = 0.0

    # 3. Targets.
    add_three_shapes()

    # 4. Moving occluder.
    group = [
        add_cube("single_large_screen_panel", (x_open, y, 1.12), (2.70, 0.10, 2.24), MATS["screen"], "single_sliding_screen_panel", "gray", is_dynamic=True),
        add_cube("screen_top_carrier", (x_open, y, 2.36), (2.35, 0.16, 0.12), MATS["support"], "screen_top_carrier", "dark_gray", is_dynamic=True),
        add_cube("left_hanger", (x_open - 0.78, y, 2.20), (0.08, 0.08, 0.34), MATS["support"], "screen_hanger", "dark_gray", is_dynamic=True),
        add_cube("right_hanger", (x_open + 0.78, y, 2.20), (0.08, 0.08, 0.34), MATS["support"], "screen_hanger", "dark_gray", is_dynamic=True),
        add_cube("left_trolley_block", (x_open - 0.78, y, 2.58), (0.24, 0.18, 0.12), MATS["support"], "trolley_block", "dark_gray", is_dynamic=True),
        add_cube("right_trolley_block", (x_open + 0.78, y, 2.58), (0.24, 0.18, 0.12), MATS["support"], "trolley_block", "dark_gray", is_dynamic=True),
    ]

    mark_group(group, "single_screen_slides_on_top_rail")
    return scene, {"kind": "x", "group": group, "x0": x_open, "x1": x_closed}


def build_vertical_guide_panel():
    scene = setup_base(ortho=8.4)

    # 1. Fixed vertical guide frame.
    y = OCC_Y
    left_post_x = -1.85
    right_post_x = 1.85
    add_cube("left_vertical_guide", (left_post_x, y, 1.48), (0.16, 0.18, 2.96), MATS["support"], "left_vertical_guide", "dark_gray")
    add_cube("right_vertical_guide", (right_post_x, y, 1.48), (0.16, 0.18, 2.96), MATS["support"], "right_vertical_guide", "dark_gray")
    add_cube("top_guide_beam", (0.0, y, 3.02), (3.86, 0.18, 0.14), MATS["support"], "top_guide_beam", "dark_gray")
    add_cube("bottom_guide_beam", (0.0, y, 0.06), (3.86, 0.18, 0.12), MATS["support"], "bottom_guide_beam", "dark_gray")

    # 2. Motion range.
    z_open = 2.58
    z_closed = 1.02

    # 3. Targets.
    add_two_balls()

    # 4. Moving panel between posts.
    group = [
        add_cube("large_vertical_panel", (0.0, y, z_open), (2.90, 0.10, 1.82), MATS["screen"], "vertical_guided_panel", "gray", is_dynamic=True),
        add_cube("left_panel_slider", (-1.55, y, z_open), (0.18, 0.20, 0.30), MATS["support"], "left_panel_slider", "dark_gray", is_dynamic=True),
        add_cube("right_panel_slider", (1.55, y, z_open), (0.18, 0.20, 0.30), MATS["support"], "right_panel_slider", "dark_gray", is_dynamic=True),
    ]

    mark_group(group, "single_panel_moves_vertically_inside_guides")
    return scene, {"kind": "z", "group": group, "z0": z_open, "z1": z_closed}


def build_cabinet_single_cover():
    scene = setup_base(
        ortho=8.8,
        camera_loc=(6.8, -8.0, 5.0),
        target=(0.0, 0.15, 0.85),
    )

    # 1. Fixed cabinet shell and front rails.
    box_y = TARGET_Y
    build_cabinet_shell("cabinet", box_y=box_y)

    y = OCC_Y
    add_cube("front_upper_rail", (0.0, y, 1.58), (9.60, 0.10, 0.08), MATS["support"], "front_cover_rail", "dark_gray")
    add_cube("front_lower_rail", (0.0, y, 0.08), (9.60, 0.10, 0.08), MATS["support"], "front_cover_rail", "dark_gray")
    add_cube("left_far_cover_stop", (-4.85, y, 0.83), (0.10, 0.12, 1.50), MATS["support"], "cover_stop", "dark_gray")
    add_cube("right_far_cover_stop", (4.85, y, 0.83), (0.10, 0.12, 1.50), MATS["support"], "cover_stop", "dark_gray")

    # 2. Motion range.
    x_open = -3.25
    x_closed = 0.0

    # 3. Targets inside true cavity.
    add_ball_cube_inside_cabinet(box_y)

    # 4. Moving single front cover in front of cabinet, not inside cabinet.
    group = [
        add_cube("single_front_cover_panel", (x_open, y, 0.83), (2.95, 0.08, 1.42), MATS["screen"], "single_front_cover", "gray", is_dynamic=True),
        add_cube("front_cover_top_slider", (x_open, y, 1.56), (2.65, 0.12, 0.08), MATS["support"], "front_cover_slider", "dark_gray", is_dynamic=True),
        add_cube("front_cover_bottom_slider", (x_open, y, 0.08), (2.65, 0.12, 0.08), MATS["support"], "front_cover_slider", "dark_gray", is_dynamic=True),
    ]

    mark_group(group, "single_front_cover_slides_on_cabinet_front_rails")
    return scene, {"kind": "x", "group": group, "x0": x_open, "x1": x_closed}


def build_cabinet_tight_doors():
    scene = setup_base(
        ortho=8.8,
        camera_loc=(0.0, -9.6, 3.8),
        target=(0.0, 0.10, 0.85),
    )

    # 1. Fixed cabinet shell and door rails.
    box_y = TARGET_Y
    build_cabinet_shell("cabinet", box_y=box_y)

    y = OCC_Y
    add_cube("front_upper_door_rail", (0.0, y, 1.58), (7.20, 0.10, 0.08), MATS["support"], "door_rail", "dark_gray")
    add_cube("front_lower_door_rail", (0.0, y, 0.08), (7.20, 0.10, 0.08), MATS["support"], "door_rail", "dark_gray")
    add_cube("left_door_stop", (-3.65, y, 0.83), (0.10, 0.12, 1.50), MATS["support"], "door_stop", "dark_gray")
    add_cube("right_door_stop", (3.65, y, 0.83), (0.10, 0.12, 1.50), MATS["support"], "door_stop", "dark_gray")

    # 2. Motion range.
    # Door width = 1.45. Closed positions:
    # left center -0.725 -> edge right = 0
    # right center +0.725 -> edge left = 0
    # So there is no large gap and no overlap.
    left_open_x = -2.45
    right_open_x = 2.45
    left_closed_x = -0.725
    right_closed_x = 0.725

    # 3. Targets inside true cavity.
    add_three_balls_inside_cabinet(box_y)

    # 4. Moving doors in front plane.
    left_group = [
        add_cube("left_sliding_door_panel", (left_open_x, y, 0.83), (1.45, 0.08, 1.42), MATS["screen"], "left_sliding_door", "gray", is_dynamic=True),
        add_cube("left_top_slider", (left_open_x, y, 1.56), (1.18, 0.12, 0.08), MATS["support"], "left_door_slider", "dark_gray", is_dynamic=True),
        add_cube("left_bottom_slider", (left_open_x, y, 0.08), (1.18, 0.12, 0.08), MATS["support"], "left_door_slider", "dark_gray", is_dynamic=True),
    ]
    right_group = [
        add_cube("right_sliding_door_panel", (right_open_x, y, 0.83), (1.45, 0.08, 1.42), MATS["screen"], "right_sliding_door", "gray", is_dynamic=True),
        add_cube("right_top_slider", (right_open_x, y, 1.56), (1.18, 0.12, 0.08), MATS["support"], "right_door_slider", "dark_gray", is_dynamic=True),
        add_cube("right_bottom_slider", (right_open_x, y, 0.08), (1.18, 0.12, 0.08), MATS["support"], "right_door_slider", "dark_gray", is_dynamic=True),
    ]

    for obj in left_group + right_group:
        obj["pb_closed_doors_meet_at_center_without_overlap"] = True
        obj["pb_foreground_depth_separated_from_targets"] = True

    return scene, {
        "kind": "two_door_x",
        "left_group": left_group,
        "right_group": right_group,
        "left_open_x": left_open_x,
        "right_open_x": right_open_x,
        "left_closed_x": left_closed_x,
        "right_closed_x": right_closed_x,
    }


def build_scene():
    kind = CASE["kind"]
    if kind == "top_rail_screen":
        return build_top_rail_screen()
    if kind == "vertical_guide_panel":
        return build_vertical_guide_panel()
    if kind == "cabinet_single_cover":
        return build_cabinet_single_cover()
    if kind == "cabinet_tight_doors":
        return build_cabinet_tight_doors()
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


def animate_two_door_x(scene, meta):
    left_group = meta["left_group"]
    right_group = meta["right_group"]

    left0 = [Vector(obj.location) for obj in left_group]
    right0 = [Vector(obj.location) for obj in right_group]

    left_dx = meta["left_closed_x"] - meta["left_open_x"]
    right_dx = meta["right_closed_x"] - meta["right_open_x"]

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

        for obj, base in zip(left_group, left0):
            obj.location = base + Vector((left_dx * t, 0.0, 0.0))
            obj.keyframe_insert(data_path="location", frame=frame)
            obj["pb_state"] = "open" if t == 0.0 else ("closed_tight" if t == 1.0 else "moving")

        for obj, base in zip(right_group, right0):
            obj.location = base + Vector((right_dx * t, 0.0, 0.0))
            obj.keyframe_insert(data_path="location", frame=frame)
            obj["pb_state"] = "open" if t == 0.0 else ("closed_tight" if t == 1.0 else "moving")


def animate_scene(scene, meta):
    if meta["kind"] == "x":
        animate_x(scene, meta["group"], meta["x0"], meta["x1"])
    elif meta["kind"] == "z":
        animate_z(scene, meta["group"], meta["z0"], meta["z1"])
    elif meta["kind"] == "two_door_x":
        animate_two_door_x(scene, meta)
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
