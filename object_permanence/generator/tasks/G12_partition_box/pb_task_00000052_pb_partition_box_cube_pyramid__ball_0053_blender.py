# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_PARTITION_BOX_CUBE_PYRAMID__BALL_0053",
  "prompt": "A rectangular box is seen from a top-down view. The top lid is open in the first frame. Inside the box there is one internal partition creating two compartments. On one side of the partition there are a blue cube and a yellow regular triangular pyramid. On the other side there is an orange ball. The lid closes, the whole box rotates 90 degrees, and then the lid opens again. All three objects must still exist, preserve identity, color, size, and count, and remain separated by the partition.",
  "left_group": [
    "cube",
    "pyramid"
  ],
  "right_group": [
    "ball"
  ]
}""")
ITEM_ID = CASE["item_id"]

FPS = 24
FRAME_START = 1
FRAME_END = 120

LID_CLOSE_END = 26
ROTATE_START = 36
ROTATE_END = 92
LID_REOPEN_START = 98

BOX_ROT_DEG = 90.0

BOX_INNER_X = 2.35
BOX_INNER_Y = 1.42
BOX_WALL_THICK = 0.08
BOX_WALL_H = 0.58
BOX_BASE_H = 0.08
BOX_TOP_Z = BOX_BASE_H + BOX_WALL_H
LID_THICK = 0.05

PARTITION_THICK = 0.07
PARTITION_H = 0.54

OBJECT_BASE_Z = BOX_BASE_H + 0.02

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

OUT_DIR = os.path.join(PROJECT_ROOT, "permanence_blender_outputs", ITEM_ID)
FRAMES_DIR = os.path.join(OUT_DIR, "frames")
SCENE_FILE = os.path.join(OUT_DIR, f"{ITEM_ID}_scene.blend")
TASK_JSON_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_task.json")

INPUT_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_input_frame_01.png")
OPTIONAL_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_event_frame_02.png")
OPTIONAL_FRAME_02B_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_final_frame_02B.png")


OBJECT_LIBRARY = {
    "ball": {
        "kind": "ball",
        "name": "inner_orange_ball",
        "color_name": "orange",
        "material": "orange",
        "size": 0.18,
    },
    "cube": {
        "kind": "cube",
        "name": "inner_blue_cube",
        "color_name": "blue",
        "material": "blue",
        "size": 0.28,
    },
    "pyramid": {
        "kind": "triangular_pyramid",
        "name": "inner_yellow_pyramid",
        "color_name": "yellow",
        "material": "yellow",
        "size": 0.30,
    },
}

# Two slots in left compartment, one slot in right compartment
LEFT_SLOTS = [
    (-0.62, -0.18, 0.0),
    (-0.34,  0.22, 18.0),
]
RIGHT_SLOT = (0.52, 0.02, -18.0)


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
        "dynamic_object" if is_dynamic else ("static_solid" if solid else "non_solid_marker"),
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


def add_triangular_pyramid(name, size, location, material, color_name, rotation=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_cone_add(
        vertices=3,
        radius1=size * 0.62,
        radius2=0.0,
        depth=size,
        location=location,
        rotation=rotation,
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, "contained_object", "dynamic_object", "triangular_pyramid", color_name, True, solid=True, pb_size=size)
    return obj


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), roughness=0.85)
    MATS["box"] = make_mat("mat_box", (0.66, 0.67, 0.70), roughness=0.70)
    MATS["lid"] = make_mat("mat_lid", (0.58, 0.60, 0.64), roughness=0.62)
    MATS["partition"] = make_mat("mat_partition", (0.50, 0.52, 0.56), roughness=0.72)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.92)
    MATS["orange"] = make_mat("mat_orange", (1.00, 0.45, 0.08), roughness=0.25)
    MATS["blue"] = make_mat("mat_blue", (0.18, 0.42, 0.95), roughness=0.35)
    MATS["yellow"] = make_mat("mat_yellow", (1.00, 0.78, 0.12), roughness=0.36)


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
        scene.view_settings.exposure = 0.0
        scene.view_settings.gamma = 1.0
    except Exception:
        pass


def build_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (8.0, 6.0, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 2.70, 1.80), (8.0, 0.08, 3.60), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-2.6, -3.8, 6.3))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 1000
    key.data.size = 5.8

    bpy.ops.object.light_add(type="POINT", location=(2.8, -1.8, 4.1))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 130

    bpy.ops.object.camera_add(location=(0.0, -5.8, 6.6))
    cam = bpy.context.object
    cam.name = "camera_partitioned_rotating_box_hidden_objects"
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 4.9
    cam.data.dof.use_dof = False
    look_at(cam, (0.0, 0.0, 0.54))
    scene.camera = cam

    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.0, 0.0, 0.0))
    box_root = bpy.context.object
    box_root.name = "box_root"

    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.0, BOX_INNER_Y / 2.0 + BOX_WALL_THICK / 2.0, BOX_TOP_Z))
    lid_hinge = bpy.context.object
    lid_hinge.name = "box_lid_hinge"
    lid_hinge.parent = box_root

    base = add_cube("box_base", (0.0, 0.0, BOX_BASE_H / 2.0), (BOX_INNER_X + 2 * BOX_WALL_THICK, BOX_INNER_Y + 2 * BOX_WALL_THICK, BOX_BASE_H), MATS["box"], "container_base", "gray")
    base.parent = box_root

    left_wall = add_cube("box_left_wall", (-(BOX_INNER_X + BOX_WALL_THICK) / 2.0, 0.0, BOX_BASE_H + BOX_WALL_H / 2.0), (BOX_WALL_THICK, BOX_INNER_Y + 2 * BOX_WALL_THICK, BOX_WALL_H), MATS["box"], "container_wall", "gray")
    left_wall.parent = box_root

    right_wall = add_cube("box_right_wall", ((BOX_INNER_X + BOX_WALL_THICK) / 2.0, 0.0, BOX_BASE_H + BOX_WALL_H / 2.0), (BOX_WALL_THICK, BOX_INNER_Y + 2 * BOX_WALL_THICK, BOX_WALL_H), MATS["box"], "container_wall", "gray")
    right_wall.parent = box_root

    front_wall = add_cube("box_front_wall", (0.0, -(BOX_INNER_Y + BOX_WALL_THICK) / 2.0, BOX_BASE_H + BOX_WALL_H / 2.0), (BOX_INNER_X, BOX_WALL_THICK, BOX_WALL_H), MATS["box"], "container_wall", "gray")
    front_wall.parent = box_root

    back_wall = add_cube("box_back_wall", (0.0, (BOX_INNER_Y + BOX_WALL_THICK) / 2.0, BOX_BASE_H + BOX_WALL_H / 2.0), (BOX_INNER_X, BOX_WALL_THICK, BOX_WALL_H), MATS["box"], "container_wall", "gray")
    back_wall.parent = box_root

    partition = add_cube(
        "inner_partition_wall",
        (0.0, 0.0, BOX_BASE_H + PARTITION_H / 2.0),
        (PARTITION_THICK, BOX_INNER_Y, PARTITION_H),
        MATS["partition"],
        "container_partition",
        "dark_gray",
        is_dynamic=False,
        solid=True,
    )
    partition.parent = box_root
    partition["pb_partition_divides_box"] = True

    lid_panel = add_cube(
        "box_top_lid",
        (0.0, -BOX_INNER_Y / 2.0, LID_THICK / 2.0),
        (BOX_INNER_X + 0.02, BOX_INNER_Y + 0.02, LID_THICK),
        MATS["lid"],
        "container_lid",
        "dark_gray",
        is_dynamic=True,
    )
    lid_panel.parent = lid_hinge
    lid_panel.location = (0.0, -BOX_INNER_Y / 2.0, LID_THICK / 2.0)
    lid_panel.rotation_euler = (0.0, 0.0, 0.0)

    tag(box_root, "box_root", "container", "dynamic_object", "empty", "gray", True, solid=True)
    tag(lid_hinge, "box_lid_hinge", "container_lid_hinge", "dynamic_object", "empty", "gray", True, solid=True)

    inner_objects = []

    left_group = CASE["left_group"]
    right_group = CASE["right_group"]

    for idx, obj_key in enumerate(left_group):
        spec = OBJECT_LIBRARY[obj_key]
        lx, ly, yaw_deg = LEFT_SLOTS[idx]
        yaw = math.radians(yaw_deg)

        if spec["kind"] == "ball":
            radius = float(spec["size"])
            obj = add_ball(
                spec["name"],
                radius,
                (lx, ly, OBJECT_BASE_Z + radius),
                MATS[spec["material"]],
                spec["color_name"],
            )
        elif spec["kind"] == "cube":
            size = float(spec["size"])
            obj = add_cube(
                spec["name"],
                (lx, ly, OBJECT_BASE_Z + size / 2.0),
                (size, size, size),
                MATS[spec["material"]],
                "contained_object",
                spec["color_name"],
                is_dynamic=True,
                rotation=(0.0, 0.0, yaw),
            )
            obj["pb_size"] = size
        elif spec["kind"] == "triangular_pyramid":
            size = float(spec["size"])
            obj = add_triangular_pyramid(
                spec["name"],
                size,
                (lx, ly, OBJECT_BASE_Z + size / 2.0),
                MATS[spec["material"]],
                spec["color_name"],
                rotation=(0.0, 0.0, yaw),
            )
        else:
            raise RuntimeError("Unknown object kind: " + str(spec["kind"]))

        obj.parent = box_root
        obj["pb_compartment_side"] = "left"
        inner_objects.append(obj)

    for obj_key in right_group:
        spec = OBJECT_LIBRARY[obj_key]
        rx, ry, yaw_deg = RIGHT_SLOT
        yaw = math.radians(yaw_deg)

        if spec["kind"] == "ball":
            radius = float(spec["size"])
            obj = add_ball(
                spec["name"],
                radius,
                (rx, ry, OBJECT_BASE_Z + radius),
                MATS[spec["material"]],
                spec["color_name"],
            )
        elif spec["kind"] == "cube":
            size = float(spec["size"])
            obj = add_cube(
                spec["name"],
                (rx, ry, OBJECT_BASE_Z + size / 2.0),
                (size, size, size),
                MATS[spec["material"]],
                "contained_object",
                spec["color_name"],
                is_dynamic=True,
                rotation=(0.0, 0.0, yaw),
            )
            obj["pb_size"] = size
        elif spec["kind"] == "triangular_pyramid":
            size = float(spec["size"])
            obj = add_triangular_pyramid(
                spec["name"],
                size,
                (rx, ry, OBJECT_BASE_Z + size / 2.0),
                MATS[spec["material"]],
                spec["color_name"],
                rotation=(0.0, 0.0, yaw),
            )
        else:
            raise RuntimeError("Unknown object kind: " + str(spec["kind"]))

        obj.parent = box_root
        obj["pb_compartment_side"] = "right"
        inner_objects.append(obj)

    return {
        "scene": scene,
        "box_root": box_root,
        "lid_hinge": lid_hinge,
        "partition": partition,
        "inner_objects": inner_objects,
    }


def lid_open_angle_rad(frame):
    if frame <= LID_CLOSE_END:
        t = smooth01((frame - FRAME_START) / float(max(1, LID_CLOSE_END - FRAME_START)))
        return lerp(math.radians(-110.0), 0.0, t)

    if frame < LID_REOPEN_START:
        return 0.0

    t = smooth01((frame - LID_REOPEN_START) / float(max(1, FRAME_END - LID_REOPEN_START)))
    return lerp(0.0, math.radians(-110.0), t)


def box_rotation_z_rad(frame):
    if frame <= ROTATE_START:
        return 0.0
    if frame >= ROTATE_END:
        return math.radians(BOX_ROT_DEG)
    t = smooth01((frame - ROTATE_START) / float(max(1, ROTATE_END - ROTATE_START)))
    return lerp(0.0, math.radians(BOX_ROT_DEG), t)


def animate_scene(objs):
    scene = objs["scene"]
    box_root = objs["box_root"]
    lid_hinge = objs["lid_hinge"]
    inner_objects = objs["inner_objects"]
    partition = objs["partition"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        rot_z = box_rotation_z_rad(frame)
        box_root.location = (0.0, 0.0, 0.0)
        box_root.rotation_euler = (0.0, 0.0, rot_z)

        lid_angle = lid_open_angle_rad(frame)
        lid_hinge.rotation_euler = (lid_angle, 0.0, 0.0)

        box_root.keyframe_insert(data_path="location", frame=frame)
        box_root.keyframe_insert(data_path="rotation_euler", frame=frame)
        lid_hinge.keyframe_insert(data_path="rotation_euler", frame=frame)

        if frame <= LID_CLOSE_END:
            lid_state = "closing"
        elif frame < LID_REOPEN_START:
            lid_state = "closed"
        else:
            lid_state = "reopening"

        if frame < ROTATE_START:
            box_state = "before_rotation"
        elif frame <= ROTATE_END:
            box_state = "rotating_ninety_degrees"
        else:
            box_state = "rotation_complete"

        box_root["pb_state"] = box_state
        lid_hinge["pb_state"] = lid_state
        partition["pb_state"] = "fixed_divider_inside_box"

        for obj in inner_objects:
            if lid_state == "closed" and frame >= ROTATE_START:
                obj["pb_state"] = "hidden_inside_closed_rotating_partitioned_box"
            elif lid_state == "closed":
                obj["pb_state"] = "hidden_inside_closed_partitioned_box"
            elif lid_state == "closing":
                obj["pb_state"] = "still_visible_while_lid_closes"
            else:
                obj["pb_state"] = "visible_after_lid_reopens"

            obj["pb_identity_preserved"] = True
            obj["pb_moves_with_box"] = True
            obj["pb_partition_preserved"] = True
            obj["pb_box_rotation_deg"] = math.degrees(rot_z)

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
    print("left_group:", CASE["left_group"])
    print("right_group:", CASE["right_group"])
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
