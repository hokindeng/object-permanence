# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_THREE_DRAWERS_OBJECTS_ORDER_CUBE_BALL_PYRAMID_0059",
  "scene_kind": "three_drawers",
  "drawer_order": [
    "cube",
    "ball",
    "pyramid"
  ],
  "prompt": "Three supported drawers are open in the first frame. From left to right they contain cube, ball, and pyramid. The drawers slide fully into real empty cabinet cavities, the cabinet shifts slightly, and the drawers open again. Each object must remain in its original drawer."
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


# ----------------------------
# Utility
# ----------------------------

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


def lerp(a, b, t):
    return a + (b - a) * t


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def make_mat(name, color, roughness=0.55, metallic=0.0, alpha=1.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (color[0], color[1], color[2], alpha)

    try:
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            if "Base Color" in bsdf.inputs:
                bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], alpha)
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = roughness
            if "Metallic" in bsdf.inputs:
                bsdf.inputs["Metallic"].default_value = metallic
            if "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = alpha
    except Exception:
        pass

    return mat


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), roughness=0.85)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.92)

    MATS["cabinet"] = make_mat("mat_cabinet", (0.56, 0.57, 0.61), roughness=0.72)
    MATS["drawer"] = make_mat("mat_drawer", (0.76, 0.77, 0.80), roughness=0.68)
    MATS["rail"] = make_mat("mat_rail", (0.16, 0.18, 0.21), roughness=0.55)
    MATS["handle"] = make_mat("mat_handle", (0.10, 0.10, 0.11), roughness=0.4, metallic=0.2)

    MATS["orange"] = make_mat("mat_orange", (1.00, 0.45, 0.08), roughness=0.25)
    MATS["blue"] = make_mat("mat_blue", (0.18, 0.42, 0.95), roughness=0.35)
    MATS["yellow"] = make_mat("mat_yellow", (1.00, 0.78, 0.12), roughness=0.36)
    MATS["green"] = make_mat("mat_green", (0.22, 0.60, 0.32), roughness=0.65)
    MATS["black"] = make_mat("mat_black", (0.03, 0.03, 0.035), roughness=0.5)


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

    if material is not None:
        obj.data.materials.append(material)

    tag(
        obj,
        name,
        role,
        "dynamic_object" if is_dynamic else "static_solid",
        "cube",
        color_name,
        is_dynamic,
        solid=solid,
    )
    return obj


def add_ball(name, radius, location, material, color_name):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=48, ring_count=24)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, "contained_object", "dynamic_object", "sphere", color_name, True, solid=True, pb_radius=radius)
    return obj


def add_pyramid(name, size, location, material, color_name, yaw=0.0):
    bpy.ops.mesh.primitive_cone_add(
        vertices=3,
        radius1=size * 0.62,
        radius2=0.0,
        depth=size,
        location=location,
        rotation=(0.0, 0.0, yaw),
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, "contained_object", "dynamic_object", "triangular_pyramid", color_name, True, solid=True, pb_size=size)
    return obj


def add_text_label(name, text, location, size=0.16, parent=None):
    bpy.ops.object.text_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.body = str(text)
    obj.data.align_x = "CENTER"
    obj.data.align_y = "CENTER"
    obj.data.size = size
    obj.data.extrude = 0.003
    obj.data.materials.append(MATS["black"])
    if parent is not None:
        obj.parent = parent
    tag(obj, name, "label", "static_marker", "text", "black", False, solid=False)
    return obj


def make_object(kind, prefix, floor_top_z, local_xy, parent):
    x, y = local_xy

    if kind == "ball":
        radius = 0.16
        obj = add_ball(
            f"{prefix}_orange_ball",
            radius,
            (x, y, floor_top_z + radius),
            MATS["orange"],
            "orange",
        )

    elif kind == "cube":
        size = 0.30
        obj = add_cube(
            f"{prefix}_blue_cube",
            (x, y, floor_top_z + size / 2.0),
            (size, size, size),
            MATS["blue"],
            "contained_object",
            "blue",
            is_dynamic=True,
            rotation=(0.0, 0.0, math.radians(18)),
        )
        obj["pb_size"] = size

    elif kind == "pyramid":
        size = 0.34
        obj = add_pyramid(
            f"{prefix}_yellow_pyramid",
            size,
            (x, y, floor_top_z + size / 2.0),
            MATS["yellow"],
            "yellow",
            yaw=math.radians(-20),
        )
        obj["pb_size"] = size

    else:
        raise RuntimeError(f"Unknown object kind: {kind}")

    obj.parent = parent
    obj["pb_kind_key"] = kind
    obj["pb_identity_preserved"] = True
    obj["pb_placed_after_drawer_geometry"] = True
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
        scene.eevee.gtao_distance = 3.0
        scene.eevee.gtao_factor = 1.2
    except Exception:
        pass

    if scene.world is None:
        scene.world = bpy.data.worlds.new("clean_world")
    scene.world.color = (1.0, 1.0, 1.0)

    try:
        scene.view_settings.view_transform = "Filmic"
        scene.view_settings.look = "Medium High Contrast"
    except Exception:
        pass


def setup_base(camera_scale, camera_loc, target):
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (10.0, 7.2, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.25, 1.9), (10.0, 0.08, 3.8), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.2, -4.2, 6.9))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 1150
    key.data.size = 6.0

    bpy.ops.object.light_add(type="POINT", location=(3.2, -1.8, 4.4))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 140

    bpy.ops.object.camera_add(location=camera_loc)
    cam = bpy.context.object
    cam.name = "camera_drawer_geometry_first"
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = camera_scale
    cam.data.dof.use_dof = False
    look_at(cam, target)
    scene.camera = cam

    return scene


# ----------------------------
# Cabinet / drawer geometry
# ----------------------------

def parent_to(obj, parent):
    obj.parent = parent
    return obj


def build_three_drawer_cabinet_frame(root):
    # Empty cavities, no solid front block.
    parent_to(add_cube("cabinet_bottom_board", (0.0, 0.10, 0.08), (3.65, 1.42, 0.10), MATS["cabinet"], "cabinet_bottom", "gray"), root)
    parent_to(add_cube("cabinet_top_board", (0.0, 0.10, 1.03), (3.65, 1.42, 0.12), MATS["cabinet"], "cabinet_top", "gray"), root)
    parent_to(add_cube("cabinet_back_wall", (0.0, 0.78, 0.55), (3.65, 0.10, 0.95), MATS["cabinet"], "cabinet_back", "gray"), root)

    parent_to(add_cube("cabinet_left_wall", (-1.86, 0.10, 0.55), (0.10, 1.42, 0.95), MATS["cabinet"], "cabinet_side", "gray"), root)
    parent_to(add_cube("cabinet_right_wall", (1.86, 0.10, 0.55), (0.10, 1.42, 0.95), MATS["cabinet"], "cabinet_side", "gray"), root)

    parent_to(add_cube("cabinet_divider_12", (-0.62, 0.10, 0.55), (0.07, 1.42, 0.95), MATS["cabinet"], "cabinet_divider", "gray"), root)
    parent_to(add_cube("cabinet_divider_23", (0.62, 0.10, 0.55), (0.07, 1.42, 0.95), MATS["cabinet"], "cabinet_divider", "gray"), root)

    root["pb_real_empty_drawer_cavities"] = True


def build_cubby_cabinet_frame(root):
    parent_to(add_cube("cubby_cabinet_bottom_board", (0.0, 0.12, 0.08), (3.08, 1.62, 0.10), MATS["cabinet"], "cabinet_bottom", "gray"), root)
    parent_to(add_cube("cubby_cabinet_top_board", (0.0, 0.12, 1.14), (3.08, 1.62, 0.12), MATS["cabinet"], "cabinet_top", "gray"), root)
    parent_to(add_cube("cubby_cabinet_back_wall", (0.0, 0.88, 0.62), (3.08, 0.10, 1.05), MATS["cabinet"], "cabinet_back", "gray"), root)
    parent_to(add_cube("cubby_cabinet_left_wall", (-1.56, 0.12, 0.62), (0.10, 1.62, 1.05), MATS["cabinet"], "cabinet_side", "gray"), root)
    parent_to(add_cube("cubby_cabinet_right_wall", (1.56, 0.12, 0.62), (0.10, 1.62, 1.05), MATS["cabinet"], "cabinet_side", "gray"), root)

    root["pb_real_empty_drawer_cavities"] = True


def build_rails(root, prefix, x_center, width, y_center, depth, z):
    parent_to(add_cube(f"{prefix}_left_rail", (x_center - width / 2.0 + 0.04, y_center, z), (0.055, depth, 0.045), MATS["rail"], "drawer_rail", "dark_gray"), root)
    parent_to(add_cube(f"{prefix}_right_rail", (x_center + width / 2.0 - 0.04, y_center, z), (0.055, depth, 0.045), MATS["rail"], "drawer_rail", "dark_gray"), root)


def create_open_drawer(root, prefix, x_center, y_open, z_center, width, depth):
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(x_center, y_open, 0.0))
    drawer = bpy.context.object
    drawer.name = f"{prefix}_drawer_root"
    drawer.parent = root
    tag(drawer, drawer.name, "drawer_container", "dynamic_object", "empty", "gray", True)

    floor_thick = 0.045
    side_thick = 0.045
    side_h = 0.18
    front_h = 0.075

    floor_z = z_center
    floor_top_z = floor_z + floor_thick / 2.0

    parent_to(add_cube(f"{prefix}_floor", (0.0, 0.0, floor_z), (width, depth, floor_thick), MATS["drawer"], "drawer_floor", "gray", is_dynamic=True), drawer)
    parent_to(add_cube(f"{prefix}_left_side", (-width / 2.0 + side_thick / 2.0, 0.0, floor_top_z + side_h / 2.0), (side_thick, depth, side_h), MATS["drawer"], "drawer_side", "gray", is_dynamic=True), drawer)
    parent_to(add_cube(f"{prefix}_right_side", (width / 2.0 - side_thick / 2.0, 0.0, floor_top_z + side_h / 2.0), (side_thick, depth, side_h), MATS["drawer"], "drawer_side", "gray", is_dynamic=True), drawer)
    parent_to(add_cube(f"{prefix}_back_wall", (0.0, depth / 2.0 - side_thick / 2.0, floor_top_z + side_h / 2.0), (width, side_thick, side_h), MATS["drawer"], "drawer_back", "gray", is_dynamic=True), drawer)

    # Low front lip: visible object remains above it.
    parent_to(add_cube(f"{prefix}_front_lip", (0.0, -depth / 2.0 + side_thick / 2.0, floor_top_z + front_h / 2.0), (width, side_thick, front_h), MATS["drawer"], "drawer_front_lip", "gray", is_dynamic=True), drawer)

    # Solid front panel, but placed low/outside drawer content.
    parent_to(add_cube(f"{prefix}_front_panel", (0.0, -depth / 2.0 - 0.06, floor_top_z + 0.07), (width + 0.05, 0.08, 0.14), MATS["cabinet"], "drawer_front_panel", "gray", is_dynamic=True), drawer)
    parent_to(add_cube(f"{prefix}_handle", (0.0, -depth / 2.0 - 0.115, floor_top_z + 0.065), (0.18, 0.045, 0.045), MATS["handle"], "drawer_handle", "black", is_dynamic=True), drawer)

    drawer["pb_floor_top_z"] = float(floor_top_z)
    drawer["pb_open_tray"] = True
    drawer["pb_drawer_fits_cavity"] = True
    return drawer, floor_top_z


def add_drawer_front_label(drawer, text, prefix, width, depth, floor_top_z):
    # Label is on front outside face, never through the object.
    label = add_text_label(
        f"{prefix}_front_label",
        text,
        (0.0, -depth / 2.0 - 0.17, floor_top_z + 0.10),
        size=0.16,
        parent=drawer,
    )
    label["pb_not_inside_drawer_content_area"] = True
    return label


# ----------------------------
# Scene builders
# ----------------------------

def build_three_drawers():
    scene = setup_base(
        camera_scale=6.45,
        camera_loc=(0.0, -3.6, 9.0),
        target=(0.0, -0.15, 0.52),
    )

    order = CASE["drawer_order"]

    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.0, 0.0, 0.0))
    root = bpy.context.object
    root.name = "three_drawer_cabinet_root"
    tag(root, root.name, "drawer_cabinet", "dynamic_object", "empty", "gray", True)

    build_three_drawer_cabinet_frame(root)

    drawer_width = 0.82
    drawer_depth = 0.84
    drawer_floor_z = 0.26

    y_open = -0.98
    y_closed = 0.10  # fits fully inside cavity: [0.10-0.42, 0.10+0.42] = [-0.32, 0.52]

    xs = [-1.20, 0.0, 1.20]
    drawers = []

    for idx, (x, kind) in enumerate(zip(xs, order), start=1):
        build_rails(root, f"drawer_{idx}", x, width=0.90, y_center=0.10, depth=1.22, z=0.25)
        drawer, floor_top_z = create_open_drawer(root, f"drawer_{idx}", x, y_open, drawer_floor_z, drawer_width, drawer_depth)
        make_object(kind, f"drawer_{idx}", floor_top_z, (0.0, -0.05), drawer)
        add_drawer_front_label(drawer, str(idx), f"drawer_{idx}", drawer_width, drawer_depth, floor_top_z)

        drawer["pb_open_y"] = y_open
        drawer["pb_closed_y"] = y_closed
        drawer["pb_drawer_index"] = idx
        drawers.append(drawer)

    return {
        "scene": scene,
        "kind": "three_drawers",
        "root": root,
        "drawers": drawers,
        "y_open": y_open,
        "y_closed": y_closed,
        "order": order,
    }


def build_numbered_cubby_drawer():
    scene = setup_base(
        camera_scale=6.85,
        camera_loc=(0.0, -2.9, 9.7),
        target=(0.0, -0.12, 0.50),
    )

    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.0, 0.0, 0.0))
    root = bpy.context.object
    root.name = "numbered_cubby_cabinet_root"
    tag(root, root.name, "numbered_cubby_cabinet", "dynamic_object", "empty", "gray", True)

    build_cubby_cabinet_frame(root)

    drawer_width = 2.30
    drawer_depth = 1.20
    drawer_floor_z = 0.25

    y_open = -1.08
    y_closed = 0.05  # fully inside cavity: [-0.55, 0.65]

    build_rails(root, "cubby_drawer", 0.0, width=2.45, y_center=0.12, depth=1.36, z=0.25)
    drawer, floor_top_z = create_open_drawer(root, "numbered_cubby", 0.0, y_open, drawer_floor_z, drawer_width, drawer_depth)

    cell = 0.58
    start_x = -cell
    start_y = 0.30
    object_cells = {2: "ball", 5: "cube", 8: "pyramid"}

    idx = 1
    for row in range(3):
        for col in range(3):
            x = start_x + col * cell
            y = start_y - row * cell

            # Thin cell plate, not a box that buries objects.
            plate = add_cube(
                f"cubby_cell_{idx}_thin_plate",
                (x, y, floor_top_z + 0.018),
                (0.50, 0.50, 0.030),
                MATS["drawer"],
                "cubby_cell_plate",
                "gray",
                is_dynamic=True,
            )
            plate.parent = drawer

            # Number label is in the rear-left corner, not through the object center.
            label = add_text_label(
                f"cubby_cell_{idx}_corner_number",
                str(idx),
                (x - 0.18, y + 0.18, floor_top_z + 0.065),
                size=0.105,
                parent=drawer,
            )
            label["pb_label_in_corner_not_through_object"] = True

            if idx in object_cells:
                obj = make_object(object_cells[idx], f"cubby_{idx}", floor_top_z + 0.030, (x, y), drawer)
                obj["pb_cubby_number"] = idx

            idx += 1

    drawer["pb_open_y"] = y_open
    drawer["pb_closed_y"] = y_closed
    return {
        "scene": scene,
        "kind": "numbered_cubby_drawer",
        "root": root,
        "drawer": drawer,
        "y_open": y_open,
        "y_closed": y_closed,
    }


# ----------------------------
# Animation
# ----------------------------

def animate_three_drawers(objs):
    scene = objs["scene"]
    root = objs["root"]
    drawers = objs["drawers"]
    y_open = objs["y_open"]
    y_closed = objs["y_closed"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 32:
            close_t = smooth01((frame - FRAME_START) / 31.0)
            move_t = 0.0
            open_t = 0.0
        elif frame <= 82:
            close_t = 1.0
            move_t = smooth01((frame - 32) / 50.0)
            open_t = 0.0
        else:
            close_t = 1.0
            move_t = 1.0
            open_t = smooth01((frame - 82) / 38.0)

        # Small movement only; never flies out of frame.
        root.location = (lerp(0.0, 0.30, move_t), 0.0, 0.0)
        root.keyframe_insert(data_path="location", frame=frame)

        for drawer in drawers:
            y = lerp(y_open, y_closed, close_t)
            if open_t > 0:
                y = lerp(y_closed, y_open, open_t)

            drawer.location = (drawer.location.x, y, 0.0)
            drawer.keyframe_insert(data_path="location", frame=frame)

            if y > y_closed - 0.05:
                drawer["pb_state"] = "fully_inside_real_empty_cavity"
            else:
                drawer["pb_state"] = "open_supported_drawer"

    scene.frame_set(FRAME_START)


def animate_numbered_cubby_drawer(objs):
    scene = objs["scene"]
    root = objs["root"]
    drawer = objs["drawer"]
    y_open = objs["y_open"]
    y_closed = objs["y_closed"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 34:
            close_t = smooth01((frame - FRAME_START) / 33.0)
            rot_t = 0.0
            open_t = 0.0
        elif frame <= 88:
            close_t = 1.0
            rot_t = smooth01((frame - 34) / 54.0)
            open_t = 0.0
        else:
            close_t = 1.0
            rot_t = 1.0
            open_t = smooth01((frame - 88) / 32.0)

        y = lerp(y_open, y_closed, close_t)
        if open_t > 0:
            y = lerp(y_closed, y_open, open_t)

        drawer.location = (drawer.location.x, y, 0.0)
        drawer.keyframe_insert(data_path="location", frame=frame)

        root.rotation_euler = (0.0, 0.0, lerp(0.0, math.radians(90.0), rot_t))
        root.keyframe_insert(data_path="rotation_euler", frame=frame)

        if y > y_closed - 0.05:
            drawer["pb_state"] = "fully_inside_real_empty_cavity"
        else:
            drawer["pb_state"] = "open_supported_numbered_drawer"

    scene.frame_set(FRAME_START)


def build_scene():
    if CASE["scene_kind"] == "three_drawers":
        return build_three_drawers()
    if CASE["scene_kind"] == "numbered_cubby_drawer":
        return build_numbered_cubby_drawer()
    raise RuntimeError("Unknown scene_kind: " + str(CASE["scene_kind"]))


def animate_scene(objs):
    if objs["kind"] == "three_drawers":
        return animate_three_drawers(objs)
    if objs["kind"] == "numbered_cubby_drawer":
        return animate_numbered_cubby_drawer(objs)
    raise RuntimeError("Unknown kind: " + str(objs["kind"]))


# ----------------------------
# Output
# ----------------------------

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
        "scene_file": f"{ITEM_ID}_scene.blend",
    }

    with open(TASK_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(task, f, indent=2, ensure_ascii=False)


def save_scene():
    bpy.ops.wm.save_as_mainfile(filepath=SCENE_FILE)


def main():
    ensure_dirs()
    clear_scene()

    objs = build_scene()
    scene = objs["scene"]
    animate_scene(objs)

    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, 60, OPTIONAL_FRAME_PATH)
    render_png(scene, 120, OPTIONAL_FRAME_02B_PATH)

    render_animation(scene)
    write_task_json()
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("scene_kind:", CASE["scene_kind"])
    if "drawer_order" in CASE:
        print("drawer_order:", CASE["drawer_order"])
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
