# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "kind": "hinged_page",
  "variant": "three_shapes",
  "prompt": "Three objects are visible on a tabletop: an orange ball, a blue cube, and a yellow pyramid. A large opaque page-like panel is attached to a visible vertical hinge spine on the left. The page swings closed in the foreground, fully hiding the objects, then swings open again. The same three objects must reappear unchanged.",
  "item_id": "PB_HINGED_BOOK_PAGE_OCCLUDES_THREE_OBJECTS_0092"
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
    MATS["gray"] = make_mat("mat_gray", (0.62, 0.63, 0.66), 0.75)
    MATS["dark"] = make_mat("mat_dark", (0.18, 0.20, 0.24), 0.55)
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
    for k, v in extras.items():
        obj[k] = v


def add_cube(name, location, dimensions, material, role, color_name, is_dynamic=False, solid=True, rotation=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=rotation)
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
    bpy.ops.mesh.primitive_cone_add(vertices=3, radius1=size * 0.62, radius2=0.0, depth=size, location=location, rotation=(0.0, 0.0, math.radians(-30)))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, "target", "dynamic_object", "triangular_pyramid", color_name, True, solid=True)
    return obj


def add_cylinder_between(name, p1, p2, radius, material, role, color_name):
    p1 = Vector(p1)
    p2 = Vector(p2)
    diff = p2 - p1
    mid = (p1 + p2) / 2.0
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=diff.length, vertices=32, location=mid)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = diff.to_track_quat("Z", "Y").to_euler()
    obj.data.materials.append(material)
    tag(obj, name, role, "static_solid", "cylinder", color_name, False, solid=True)
    return obj


def make_root(name, loc=(0.0, 0.0, 0.0), role="dynamic_root"):
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=loc)
    root = bpy.context.object
    root.name = name
    tag(root, name, role, "dynamic_object", "empty", "gray", True, solid=False)
    return root


def parent_to_local(obj, parent, local_location):
    obj.parent = parent
    obj.location = local_location
    return obj


def setup_base(camera_loc=(0.0, -9.5, 3.8), target=(0.0, 0.0, 0.95), ortho=8.2):
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (15.0, 8.0, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.45, 1.85), (15.0, 0.08, 3.70), MATS["backdrop"], "background", "off_white")

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


def add_basic_objects(variant):
    if variant == "single_ball":
        add_ball("center_orange_ball", 0.22, (0.0, 0.28, 0.22), MATS["orange"], "orange")
    elif variant == "ball_cube":
        add_ball("left_orange_ball", 0.20, (-0.55, 0.28, 0.20), MATS["orange"], "orange")
        add_cube("right_blue_cube", (0.55, 0.28, 0.21), (0.42, 0.42, 0.42), MATS["blue"], "target_cube", "blue", is_dynamic=True)
    elif variant == "three_shapes":
        add_ball("orange_ball", 0.20, (-0.78, 0.28, 0.20), MATS["orange"], "orange")
        add_cube("blue_cube", (0.0, 0.28, 0.21), (0.42, 0.42, 0.42), MATS["blue"], "target_cube", "blue", is_dynamic=True)
        add_pyramid("yellow_pyramid", 0.50, (0.78, 0.28, 0.25), MATS["yellow"], "yellow")
    else:
        raise RuntimeError("Unknown variant: " + str(variant))


def build_hinged_page():
    scene = setup_base(ortho=8.4)
    add_basic_objects("three_shapes")

    y = -0.84
    hinge_x = -1.70
    hinge_z = 1.12
    panel_w = 3.40
    panel_h = 2.25

    add_cylinder_between("vertical_hinge_spine", (hinge_x, y, 0.02), (hinge_x, y, 2.38), 0.045, MATS["support"], "vertical_hinge_spine", "dark_gray")
    add_cube("hinge_top_socket", (hinge_x, y, 2.42), (0.22, 0.16, 0.10), MATS["support"], "hinge_socket", "dark_gray")
    add_cube("hinge_bottom_socket", (hinge_x, y, 0.02), (0.22, 0.16, 0.10), MATS["support"], "hinge_socket", "dark_gray")

    root = make_root("book_page_hinge_root", (hinge_x, y, hinge_z), "hinged_page_root")

    panel = add_cube("large_opaque_book_page", (0, 0, 0), (panel_w, 0.10, panel_h), MATS["screen"], "hinged_page_panel", "gray", is_dynamic=True)
    brace_top = add_cube("page_top_hinge_brace", (0, 0, 0), (0.42, 0.08, 0.08), MATS["support"], "hinge_brace", "dark_gray", is_dynamic=True)
    brace_bottom = add_cube("page_bottom_hinge_brace", (0, 0, 0), (0.42, 0.08, 0.08), MATS["support"], "hinge_brace", "dark_gray", is_dynamic=True)

    parent_to_local(panel, root, (panel_w / 2.0, 0.0, 0.0))
    parent_to_local(brace_top, root, (0.20, 0.0, panel_h / 2.0 - 0.12))
    parent_to_local(brace_bottom, root, (0.20, 0.0, -panel_h / 2.0 + 0.12))

    panel["pb_large_enough_to_fully_hide_targets"] = True
    panel["pb_connected_to_visible_hinge"] = True

    return scene, {"kind": "hinge_z", "root": root, "open_angle": math.radians(-78), "closed_angle": 0.0}


def build_tall_pivot_sign():
    scene = setup_base(ortho=8.4)
    add_basic_objects(CASE["variant"])

    y = -0.84
    hinge_x = -1.78
    hinge_z = 1.12

    if CASE["variant"] == "single_ball":
        panel_w = 2.40
        panel_h = 2.25
    else:
        panel_w = 3.55
        panel_h = 2.35

    add_cylinder_between("side_pivot_post", (hinge_x, y, 0.02), (hinge_x, y, 2.48), 0.05, MATS["support"], "pivot_post", "dark_gray")
    add_cube("pivot_base_plate", (hinge_x, y, 0.04), (0.34, 0.22, 0.08), MATS["support"], "pivot_base", "dark_gray")

    root = make_root("tall_pivot_sign_root", (hinge_x, y, hinge_z), "pivot_sign_root")

    sign = add_cube("tall_wide_pivoting_signboard", (0, 0, 0), (panel_w, 0.10, panel_h), MATS["screen"], "pivoting_signboard", "gray", is_dynamic=True)
    brace = add_cube("sign_to_post_connector", (0, 0, 0), (0.46, 0.08, 0.10), MATS["support"], "sign_connector", "dark_gray", is_dynamic=True)

    parent_to_local(sign, root, (panel_w / 2.0, 0.0, 0.0))
    parent_to_local(brace, root, (0.22, 0.0, panel_h / 2.0 - 0.20))

    sign["pb_large_enough_to_fully_hide_targets"] = True
    sign["pb_connected_to_side_post"] = True

    return scene, {"kind": "hinge_z", "root": root, "open_angle": math.radians(-78), "closed_angle": 0.0}


def build_rolling_shutter():
    scene = setup_base(ortho=8.2)
    add_basic_objects("ball_cube")

    y = -0.84

    # Connected full frame.
    add_cube("left_shutter_guide_post", (-1.65, y, 1.42), (0.12, 0.16, 2.84), MATS["support"], "shutter_guide_post", "dark_gray")
    add_cube("right_shutter_guide_post", (1.65, y, 1.42), (0.12, 0.16, 2.84), MATS["support"], "shutter_guide_post", "dark_gray")
    add_cube("top_shutter_beam", (0.0, y, 2.88), (3.42, 0.16, 0.12), MATS["support"], "shutter_top_beam", "dark_gray")
    add_cube("bottom_shutter_beam", (0.0, y, 0.06), (3.42, 0.16, 0.12), MATS["support"], "shutter_bottom_beam", "dark_gray")

    group = [
        add_cube("large_rolling_shutter_panel", (0.0, y, 2.55), (2.82, 0.10, 1.78), MATS["screen"], "rolling_shutter_panel", "gray", is_dynamic=True),
        add_cube("left_shutter_slider", (-1.48, y, 2.55), (0.24, 0.18, 0.26), MATS["support"], "shutter_slider", "dark_gray", is_dynamic=True),
        add_cube("right_shutter_slider", (1.48, y, 2.55), (0.24, 0.18, 0.26), MATS["support"], "shutter_slider", "dark_gray", is_dynamic=True),
        add_cube("shutter_top_connector_bar", (0.0, y, 3.46), (2.70, 0.08, 0.08), MATS["support"], "shutter_connector", "dark_gray", is_dynamic=True),
    ]

    for obj in group:
        obj["pb_connected_to_side_rails"] = True
        obj["pb_large_enough_to_fully_hide_targets"] = True

    return scene, {"kind": "vertical_group", "group": group, "z_open": 2.55, "z_closed": 1.02}


def build_theater_curtain():
    scene = setup_base(ortho=8.6)
    add_basic_objects("three_shapes")

    y = -0.84

    add_cube("left_curtain_post", (-2.05, y, 1.25), (0.10, 0.14, 2.50), MATS["support"], "curtain_post", "dark_gray")
    add_cube("right_curtain_post", (2.05, y, 1.25), (0.10, 0.14, 2.50), MATS["support"], "curtain_post", "dark_gray")
    add_cube("top_curtain_rail", (0.0, y, 2.52), (4.20, 0.14, 0.10), MATS["support"], "curtain_top_rail", "dark_gray")

    left_group = [
        add_cube("left_curtain_panel", (-1.65, y, 1.08), (1.30, 0.08, 2.10), MATS["screen"], "left_curtain_panel", "gray", is_dynamic=True),
        add_cube("left_curtain_carrier_a", (-1.95, y, 2.22), (0.18, 0.16, 0.12), MATS["support"], "curtain_carrier", "dark_gray", is_dynamic=True),
        add_cube("left_curtain_carrier_b", (-1.35, y, 2.22), (0.18, 0.16, 0.12), MATS["support"], "curtain_carrier", "dark_gray", is_dynamic=True),
        add_cube("left_curtain_hanger_a", (-1.95, y, 2.08), (0.05, 0.05, 0.20), MATS["support"], "curtain_hanger", "dark_gray", is_dynamic=True),
        add_cube("left_curtain_hanger_b", (-1.35, y, 2.08), (0.05, 0.05, 0.20), MATS["support"], "curtain_hanger", "dark_gray", is_dynamic=True),
    ]

    right_group = [
        add_cube("right_curtain_panel", (1.65, y, 1.08), (1.30, 0.08, 2.10), MATS["screen"], "right_curtain_panel", "gray", is_dynamic=True),
        add_cube("right_curtain_carrier_a", (1.35, y, 2.22), (0.18, 0.16, 0.12), MATS["support"], "curtain_carrier", "dark_gray", is_dynamic=True),
        add_cube("right_curtain_carrier_b", (1.95, y, 2.22), (0.18, 0.16, 0.12), MATS["support"], "curtain_carrier", "dark_gray", is_dynamic=True),
        add_cube("right_curtain_hanger_a", (1.35, y, 2.08), (0.05, 0.05, 0.20), MATS["support"], "curtain_hanger", "dark_gray", is_dynamic=True),
        add_cube("right_curtain_hanger_b", (1.95, y, 2.08), (0.05, 0.05, 0.20), MATS["support"], "curtain_hanger", "dark_gray", is_dynamic=True),
    ]

    for obj in left_group + right_group:
        obj["pb_connected_to_top_rail"] = True
        obj["pb_curtains_overlap_when_closed"] = True

    return scene, {
        "kind": "curtain_groups",
        "left": left_group,
        "right": right_group,
        "left_open_x": -1.65,
        "right_open_x": 1.65,
        "left_closed_x": -0.32,
        "right_closed_x": 0.32,
    }


def build_top_hinged_flap():
    scene = setup_base(ortho=8.2)
    add_basic_objects("ball_cube")

    y = -0.84

    add_cube("left_flap_frame_post", (-1.65, y, 1.20), (0.10, 0.14, 2.40), MATS["support"], "flap_frame_post", "dark_gray")
    add_cube("right_flap_frame_post", (1.65, y, 1.20), (0.10, 0.14, 2.40), MATS["support"], "flap_frame_post", "dark_gray")
    add_cylinder_between("top_horizontal_hinge_rod", (-1.65, y, 2.42), (1.65, y, 2.42), 0.045, MATS["support"], "top_hinge_rod", "dark_gray")

    root = make_root("top_hinged_flap_root", (0.0, y, 2.42), "top_hinged_flap_root")

    flap = add_cube("large_top_hinged_front_flap", (0, 0, 0), (3.20, 0.10, 2.10), MATS["screen"], "top_hinged_flap", "gray", is_dynamic=True)
    left_connector = add_cube("left_flap_hinge_connector", (0, 0, 0), (0.18, 0.08, 0.10), MATS["support"], "flap_connector", "dark_gray", is_dynamic=True)
    right_connector = add_cube("right_flap_hinge_connector", (0, 0, 0), (0.18, 0.08, 0.10), MATS["support"], "flap_connector", "dark_gray", is_dynamic=True)

    parent_to_local(flap, root, (0.0, 0.0, -1.05))
    parent_to_local(left_connector, root, (-1.20, 0.0, -0.08))
    parent_to_local(right_connector, root, (1.20, 0.0, -0.08))

    flap["pb_connected_to_top_hinge"] = True
    flap["pb_large_enough_to_fully_hide_targets"] = True

    return scene, {"kind": "hinge_x", "root": root, "open_angle": math.radians(-78), "closed_angle": 0.0}


def build_scene():
    kind = CASE["kind"]
    if kind == "hinged_page":
        return build_hinged_page()
    if kind == "tall_pivot_sign":
        return build_tall_pivot_sign()
    if kind == "rolling_shutter":
        return build_rolling_shutter()
    if kind == "theater_curtain":
        return build_theater_curtain()
    if kind == "top_hinged_flap":
        return build_top_hinged_flap()
    raise RuntimeError("Unknown kind: " + str(kind))


def animate_scene(scene, meta):
    kind = meta["kind"]

    if kind == "hinge_z":
        root = meta["root"]
        for frame in range(FRAME_START, FRAME_END + 1):
            scene.frame_set(frame)

            if frame <= 18:
                a = meta["open_angle"]
            elif frame <= 48:
                t = (frame - 18) / 30.0
                a = meta["open_angle"] + (meta["closed_angle"] - meta["open_angle"]) * t
            elif frame <= 82:
                a = meta["closed_angle"]
            elif frame <= 112:
                t = (frame - 82) / 30.0
                a = meta["closed_angle"] + (meta["open_angle"] - meta["closed_angle"]) * t
            else:
                a = meta["open_angle"]

            root.rotation_euler = (0.0, 0.0, a)
            root.keyframe_insert(data_path="rotation_euler", frame=frame)
            root["pb_motion"] = "visible_vertical_hinge_rotation"

    elif kind == "vertical_group":
        group = meta["group"]
        loc0 = [Vector(o.location) for o in group]
        dz_closed = meta["z_closed"] - meta["z_open"]

        for frame in range(FRAME_START, FRAME_END + 1):
            scene.frame_set(frame)

            if frame <= 18:
                dz = 0.0
            elif frame <= 45:
                t = (frame - 18) / 27.0
                dz = dz_closed * t
            elif frame <= 82:
                dz = dz_closed
            elif frame <= 112:
                t = (frame - 82) / 30.0
                dz = dz_closed * (1.0 - t)
            else:
                dz = 0.0

            for obj, base in zip(group, loc0):
                obj.location = base + Vector((0.0, 0.0, dz))
                obj.keyframe_insert(data_path="location", frame=frame)
                obj["pb_motion"] = "connected_vertical_guided_motion"

    elif kind == "curtain_groups":
        left = meta["left"]
        right = meta["right"]
        left_base = [Vector(o.location) for o in left]
        right_base = [Vector(o.location) for o in right]

        left_dx_closed = meta["left_closed_x"] - meta["left_open_x"]
        right_dx_closed = meta["right_closed_x"] - meta["right_open_x"]

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

            for obj, base in zip(left, left_base):
                obj.location = base + Vector((left_dx_closed * t, 0.0, 0.0))
                obj.keyframe_insert(data_path="location", frame=frame)
                obj["pb_motion"] = "curtain_slides_on_top_rail"

            for obj, base in zip(right, right_base):
                obj.location = base + Vector((right_dx_closed * t, 0.0, 0.0))
                obj.keyframe_insert(data_path="location", frame=frame)
                obj["pb_motion"] = "curtain_slides_on_top_rail"

    elif kind == "hinge_x":
        root = meta["root"]
        for frame in range(FRAME_START, FRAME_END + 1):
            scene.frame_set(frame)

            if frame <= 18:
                a = meta["open_angle"]
            elif frame <= 48:
                t = (frame - 18) / 30.0
                a = meta["open_angle"] + (meta["closed_angle"] - meta["open_angle"]) * t
            elif frame <= 82:
                a = meta["closed_angle"]
            elif frame <= 112:
                t = (frame - 82) / 30.0
                a = meta["closed_angle"] + (meta["open_angle"] - meta["closed_angle"]) * t
            else:
                a = meta["open_angle"]

            root.rotation_euler = (a, 0.0, 0.0)
            root.keyframe_insert(data_path="rotation_euler", frame=frame)
            root["pb_motion"] = "top_hinged_flap_rotation"

    else:
        raise RuntimeError("Unknown animation kind: " + str(kind))

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
