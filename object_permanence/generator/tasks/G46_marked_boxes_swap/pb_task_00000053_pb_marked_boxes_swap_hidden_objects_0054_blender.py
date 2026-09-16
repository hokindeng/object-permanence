# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_MARKED_BOXES_SWAP_HIDDEN_OBJECTS_0054",
  "scene_kind": "marked_boxes_swap",
  "prompt": "Two flat marked boxes are open in the first frame. Box A contains an orange ball, and box B contains a blue cube. The boxes close, cross over, and swap screen positions. When they open again, the orange ball must still be inside box A and the blue cube must still be inside box B."
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
    MATS["gray"] = make_mat("mat_gray", (0.62, 0.63, 0.66), roughness=0.68)
    MATS["dark"] = make_mat("mat_dark", (0.62, 0.63, 0.66), roughness=0.75)
    MATS["label"] = make_mat("mat_label", (0.04, 0.04, 0.04), roughness=0.5)
    MATS["red"] = make_mat("mat_red", (0.82, 0.08, 0.08), roughness=0.45)
    MATS["orange"] = make_mat("mat_orange", (1.00, 0.45, 0.08), roughness=0.25)
    MATS["blue"] = make_mat("mat_blue", (0.18, 0.42, 0.95), roughness=0.35)
    MATS["yellow"] = make_mat("mat_yellow", (1.00, 0.78, 0.12), roughness=0.36)
    MATS["green"] = make_mat("mat_green", (0.25, 0.62, 0.35), roughness=0.55)
    MATS["capsule"] = make_mat("mat_capsule", (0.55, 0.82, 1.00), roughness=0.15, alpha=0.55)


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
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "cube", color_name, is_dynamic, solid)
    return obj


def add_ball(name, radius, location, material, color_name):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=48, ring_count=24)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, "contained_object", "dynamic_object", "sphere", color_name, True, True, pb_radius=radius)
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
    tag(obj, name, "contained_object", "dynamic_object", "triangular_pyramid", color_name, True, True, pb_size=size)
    return obj


def add_text_label(name, text, location, size=0.22, parent=None):
    bpy.ops.object.text_add(location=location, rotation=(0.0, 0.0, 0.0))
    obj = bpy.context.object
    obj.name = name
    obj.data.body = str(text)
    obj.data.align_x = "CENTER"
    obj.data.align_y = "CENTER"
    obj.data.size = size
    obj.data.extrude = 0.004
    obj.data.materials.append(MATS["label"])
    if parent is not None:
        obj.parent = parent
    tag(obj, name, "label", "static_marker", "text", "black", False, solid=False)
    return obj


def make_object(kind, name_prefix, loc, parent=None):
    if kind == "ball":
        obj = add_ball(f"{name_prefix}_orange_ball", 0.16, (loc[0], loc[1], loc[2] + 0.16), MATS["orange"], "orange")
    elif kind == "cube":
        obj = add_cube(f"{name_prefix}_blue_cube", (loc[0], loc[1], loc[2] + 0.14), (0.28, 0.28, 0.28), MATS["blue"], "contained_object", "blue", is_dynamic=True, rotation=(0.0, 0.0, math.radians(18)))
    elif kind == "pyramid":
        obj = add_pyramid(f"{name_prefix}_yellow_pyramid", 0.32, (loc[0], loc[1], loc[2] + 0.16), MATS["yellow"], "yellow", yaw=math.radians(-20))
    else:
        raise RuntimeError("unknown object kind: " + str(kind))
    if parent is not None:
        obj.parent = parent
    obj["pb_kind_key"] = kind
    obj["pb_identity_preserved"] = True
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
        scene.view_settings.exposure = 0.0
        scene.view_settings.gamma = 1.0
    except Exception:
        pass


def setup_base(camera_scale=5.4, camera_loc=(0.0, -6.2, 6.6), target=(0.0, 0.0, 0.45)):
    scene = bpy.context.scene
    set_render(scene)
    build_materials()
    add_cube("large_floor_base", (0.0, 0.0, -0.05), (9.5, 6.8, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.05, 1.90), (9.5, 0.08, 3.80), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.0, -4.2, 6.4))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 1050
    key.data.size = 6.0

    bpy.ops.object.light_add(type="POINT", location=(3.2, -2.0, 4.2))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 145

    bpy.ops.object.camera_add(location=camera_loc)
    cam = bpy.context.object
    cam.name = "camera_main"
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = camera_scale
    cam.data.dof.use_dof = False
    look_at(cam, target)
    scene.camera = cam
    return scene


# ---------------------------------------------------------------------
# Scene builders
# ---------------------------------------------------------------------

def build_marked_boxes_swap():
    scene = setup_base(camera_scale=4.6, camera_loc=(0.0, -5.7, 6.1), target=(0.0, 0.0, 0.30))

    roots = []
    for label, x, obj_kind in [("A", -0.85, "ball"), ("B", 0.85, "cube")]:
        bpy.ops.object.empty_add(type='PLAIN_AXES', location=(x, 0.0, 0.0))
        root = bpy.context.object
        root.name = f"box_{label}_root"
        tag(root, root.name, "marked_container", "dynamic_object", "empty", "gray", True, True, pb_container_label=label)

        tray = add_cube(f"box_{label}_base", (0.0, 0.0, 0.05), (1.15, 0.75, 0.08), MATS["gray"], "box_base", "gray")
        tray.parent = root
        add_text_label(f"box_{label}_label", label, (-0.42, 0.25, 0.13), size=0.28, parent=root)

        # Cover modeled as an open-bottom CAP (top + 4 side walls), tall enough to enclose
        # the contained object (ball top ~0.43 above the tray). Closing LOWERS the cap over
        # the object so it is hidden from every angle; opening RAISES it straight up. Because
        # the cap surrounds the object (open bottom, footprint clearance) it never passes
        # THROUGH the object.
        bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.0, 0.0, 0.0))
        cover = bpy.context.object
        cover.name = f"box_{label}_cover"
        cover.parent = root
        cover["pb_container_label"] = label
        tag(cover, cover.name, "box_cover", "dynamic_object", "empty", "dark_gray", True, True)
        cover_footprint_scale = DIVERSITY.get("cover_footprint_scale", 1.0)
        _CW, _CD, _CH, _WT, _SEAT = 1.15 * cover_footprint_scale, 0.75 * cover_footprint_scale, 0.52, 0.07, 0.09
        _walls = [
            # TOP panel NESTED inside the 4 side walls: footprint shrunk by 2*_WT in x & y so its
            # outer edges sit inside the walls (no coincident outer faces -> no z-fight black bar).
            # Object is small and centered (ball r=0.16 / cube halfdiag ~0.198), so the
            # shrunk top still fully covers it from above when the cap is lowered.
            (f"box_{label}_cover_top",   (0.0, 0.0, _SEAT + _CH),                (_CW - 2 * _WT, _CD - 2 * _WT, _WT)),
            (f"box_{label}_cover_front", (0.0, -(_CD / 2 - _WT / 2), _SEAT + _CH / 2), (_CW, _WT, _CH)),
            (f"box_{label}_cover_back",  (0.0,  (_CD / 2 - _WT / 2), _SEAT + _CH / 2), (_CW, _WT, _CH)),
            (f"box_{label}_cover_left",  (-(_CW / 2 - _WT / 2), 0.0, _SEAT + _CH / 2), (_WT, _CD - 2 * _WT, _CH)),
            (f"box_{label}_cover_right", ( (_CW / 2 - _WT / 2), 0.0, _SEAT + _CH / 2), (_WT, _CD - 2 * _WT, _CH)),
        ]
        for _wn, _wloc, _wdim in _walls:
            _w = add_cube(_wn, _wloc, _wdim, MATS["dark"], "box_cover", "dark_gray", is_dynamic=True)
            _w.parent = cover

        obj = make_object(obj_kind, f"box_{label}", (0.0, 0.0, 0.11), parent=root)
        obj["pb_container_label"] = label

        roots.append({"label": label, "root": root, "cover": cover, "object": obj, "start_x": x, "end_x": -x})

    return {"scene": scene, "kind": "marked_boxes_swap", "roots": roots}


def build_theater_curtain():
    scene = setup_base(camera_scale=4.8, camera_loc=(0.0, -5.9, 5.8), target=(0.0, 0.0, 0.35))

    add_cube("stage_platform", (0.0, 0.0, 0.05), (3.6, 1.4, 0.08), MATS["gray"], "stage", "gray")
    make_object("ball", "stage_left", (-0.85, 0.0, 0.10))
    make_object("cube", "stage_middle", (0.0, 0.0, 0.10))
    make_object("pyramid", "stage_right", (0.85, 0.0, 0.10))

    curtain = add_cube("opaque_red_stage_curtain", (0.0, 1.25, 0.58), (3.9, 1.25, 0.12), MATS["red"], "moving_occluder", "red", is_dynamic=True)
    curtain["pb_occludes_static_objects"] = True
    return {"scene": scene, "kind": "theater_curtain", "curtain": curtain}


def build_sliding_window_row():
    scene = setup_base(camera_scale=5.2, camera_loc=(0.0, -6.2, 6.0), target=(0.0, 0.0, 0.35))

    add_cube("rear_object_table", (0.0, 0.0, 0.05), (3.8, 1.2, 0.08), MATS["gray"], "table", "gray")
    make_object("ball", "row_01", (-1.05, 0.0, 0.10))
    make_object("cube", "row_02", (0.0, 0.0, 0.10))
    make_object("pyramid", "row_03", (1.05, 0.0, 0.10))

    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(-1.05, -0.02, 0.0))
    mask_root = bpy.context.object
    mask_root.name = "sliding_window_mask_root"
    tag(mask_root, mask_root.name, "moving_window_mask", "dynamic_object", "empty", "dark_gray", True)

    # Four panels around a central window. Window center follows mask_root.
    for name, loc, dims in [
        ("mask_left_bar", (-0.72, 0.0, 0.58), (0.70, 1.35, 0.12)),
        ("mask_right_bar", (0.72, 0.0, 0.58), (0.70, 1.35, 0.12)),
        ("mask_top_bar", (0.0, 0.47, 0.58), (0.75, 0.38, 0.12)),
        ("mask_bottom_bar", (0.0, -0.47, 0.58), (0.75, 0.38, 0.12)),
    ]:
        bar = add_cube(name, loc, dims, MATS["dark"], "opaque_mask_part", "dark_gray", is_dynamic=True)
        bar.parent = mask_root

    mask_root["pb_window_reveal_order"] = ["ball", "cube", "pyramid"]
    return {"scene": scene, "kind": "sliding_window_row", "mask_root": mask_root}


def build_locker_permutation():
    scene = setup_base(camera_scale=5.3, camera_loc=(0.0, -6.2, 6.2), target=(0.0, 0.0, 0.45))

    order = CASE["locker_order"]

    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.0, 0.0, 0.0))
    cabinet_root = bpy.context.object
    cabinet_root.name = "locker_cabinet_root"
    tag(cabinet_root, cabinet_root.name, "locker_cabinet", "dynamic_object", "empty", "gray", True)

    xs = [-1.05, 0.0, 1.05]
    doors = []
    for i, (x, kind) in enumerate(zip(xs, order), start=1):
        cell = add_cube(f"locker_{i}_cell_body", (x, 0.0, 0.22), (0.88, 0.88, 0.42), MATS["gray"], "locker_cell", "gray")
        cell.parent = cabinet_root
        add_text_label(f"locker_{i}_number", str(i), (x, 0.32, 0.48), size=0.23, parent=cabinet_root)

        obj = make_object(kind, f"locker_{i}", (x, -0.06, 0.45), parent=cabinet_root)
        obj["pb_locker_index"] = i
        obj["pb_locker_order"] = order

        door = add_cube(f"locker_{i}_door", (x, -0.82, 0.72), (0.88, 0.88, 0.10), MATS["dark"], "locker_door", "dark_gray", is_dynamic=True)
        door.parent = cabinet_root
        door["pb_locker_index"] = i
        doors.append(door)

    return {"scene": scene, "kind": "locker_permutation", "cabinet_root": cabinet_root, "doors": doors, "order": order}


def build_nested_capsule_carrier():
    scene = setup_base(camera_scale=5.3, camera_loc=(0.0, -6.0, 6.1), target=(0.0, 0.0, 0.35))

    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(-1.25, 0.0, 0.0))
    capsule_root = bpy.context.object
    capsule_root.name = "small_capsule_root"
    tag(capsule_root, capsule_root.name, "inner_capsule_container", "dynamic_object", "empty", "blue", True)

    cap_base = add_cube("capsule_base", (0.0, 0.0, 0.08), (0.82, 0.55, 0.10), MATS["capsule"], "capsule_base", "transparent_blue", is_dynamic=True)
    cap_base.parent = capsule_root
    cap_lid = add_cube("capsule_lid", (0.0, -0.65, 0.38), (0.82, 0.55, 0.08), MATS["dark"], "capsule_lid", "dark_gray", is_dynamic=True)
    cap_lid.parent = capsule_root
    ball = make_object("ball", "capsule_inner", (0.0, 0.0, 0.13), parent=capsule_root)
    ball["pb_nested_inside_capsule"] = True

    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(1.10, 0.0, 0.0))
    carrier_root = bpy.context.object
    carrier_root.name = "outer_carrier_root"
    tag(carrier_root, carrier_root.name, "outer_carrier", "dynamic_object", "empty", "gray", True)

    carrier_base = add_cube("carrier_base", (0.0, 0.0, 0.06), (1.65, 1.05, 0.10), MATS["gray"], "carrier_base", "gray", is_dynamic=True)
    carrier_base.parent = carrier_root
    slot = add_cube("carrier_marked_slot", (0.0, 0.0, 0.14), (0.95, 0.65, 0.06), MATS["green"], "carrier_slot", "green", is_dynamic=True)
    slot.parent = carrier_root
    carrier_cover = add_cube("carrier_cover", (0.0, -1.20, 0.65), (1.75, 1.10, 0.10), MATS["dark"], "carrier_cover", "dark_gray", is_dynamic=True)
    carrier_cover.parent = carrier_root
    add_text_label("carrier_slot_label", "SLOT", (0.0, 0.0, 0.22), size=0.18, parent=carrier_root)

    return {
        "scene": scene,
        "kind": "nested_capsule_carrier",
        "capsule_root": capsule_root,
        "capsule_lid": cap_lid,
        "carrier_root": carrier_root,
        "carrier_cover": carrier_cover,
        "ball": ball,
    }


def build_numbered_cubbies():
    scene = setup_base(camera_scale=6.1, camera_loc=(0.0, -6.8, 6.6), target=(0.0, 0.0, 0.35))

    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.0, 0.0, 0.0))
    tray_root = bpy.context.object
    tray_root.name = "numbered_cubby_tray_root"
    tag(tray_root, tray_root.name, "numbered_cubby_tray", "dynamic_object", "empty", "gray", True)

    cell = 0.68
    start = -cell
    idx = 1
    objects = {2: "ball", 5: "cube", 8: "pyramid"}
    for row in range(3):
        for col in range(3):
            x = start + col * cell
            y = cell - row * cell
            base = add_cube(f"cubby_{idx}_base", (x, y, 0.06), (cell * 0.92, cell * 0.92, 0.08), MATS["gray"], "numbered_cubby_cell", "gray", is_dynamic=True)
            base.parent = tray_root
            add_text_label(f"cubby_{idx}_number", str(idx), (x - 0.20, y + 0.20, 0.15), size=0.16, parent=tray_root)

            if idx in objects:
                obj = make_object(objects[idx], f"cubby_{idx}", (x, y, 0.12), parent=tray_root)
                obj["pb_cubby_number"] = idx

            idx += 1

    panel = add_cube("opaque_cubby_cover_panel", (0.0, -2.25, 0.70), (2.35, 2.35, 0.12), MATS["dark"], "opaque_cover_panel", "dark_gray", is_dynamic=True)
    panel.parent = tray_root

    return {"scene": scene, "kind": "numbered_cubbies", "tray_root": tray_root, "panel": panel}


# ---------------------------------------------------------------------
# Animation
# ---------------------------------------------------------------------

def animate_marked_boxes_swap(objs):
    scene = objs["scene"]
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 25:
            close_t = smooth01((frame - 1) / 24.0)
            swap_t = 0.0
            open_t = 0.0
        elif frame <= 85:
            close_t = 1.0
            swap_t = smooth01((frame - 25) / 60.0)
            open_t = 0.0
        else:
            close_t = 1.0
            swap_t = 1.0
            open_t = smooth01((frame - 85) / 35.0)

        for r in objs["roots"]:
            x = lerp(r["start_x"], r["end_x"], swap_t)
            # Route the boxes around one another in depth.  A 1.45 arc gives more than one
            # full box depth (the boxes are 0.75 deep) of separation throughout every frame
            # whose x footprints overlap, and makes the two bypass lanes unmistakable on camera.
            SWAP_DEPTH_ARC = 1.45
            arc_dir = math.copysign(1.0, r["start_x"])
            y_off = arc_dir * SWAP_DEPTH_ARC * math.sin(math.pi * swap_t)
            # Cap LOWERS to seat over the object (close) and RAISES straight up (open). The
            # open-bottom cap surrounds the object with footprint clearance, so vertical
            # motion never intersects it -- and when seated it fully occludes it.
            cover_lift_open = 0.78          # cap bottom well clear of the object (top ~0.43) when open
            cover_z = lerp(cover_lift_open, 0.0, close_t)
            if open_t > 0:
                cover_z = lerp(0.0, cover_lift_open, open_t)

            r["root"].location = (x, y_off, 0.0)
            r["cover"].location = (0.0, 0.0, cover_z)   # vertical lift; open bottom never clips the object
            r["root"].keyframe_insert(data_path="location", frame=frame)
            r["cover"].keyframe_insert(data_path="location", frame=frame)

            r["object"]["pb_state"] = "hidden_in_marked_box" if cover_z < 0.30 else "visible_in_marked_box"
            r["object"]["pb_container_label"] = r["label"]

    scene.frame_set(FRAME_START)


def animate_theater_curtain(objs):
    scene = objs["scene"]
    curtain = objs["curtain"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 35:
            t = smooth01((frame - 1) / 34.0)
            y = lerp(1.25, 0.0, t)
        elif frame <= 85:
            y = 0.0
        else:
            t = smooth01((frame - 85) / 35.0)
            y = lerp(0.0, 1.25, t)

        curtain.location = (0.0, y, 0.58)
        curtain.keyframe_insert(data_path="location", frame=frame)
        curtain["pb_state"] = "covering_stage_objects" if abs(y) < 0.2 else "stage_objects_visible"

    scene.frame_set(FRAME_START)


def animate_sliding_window_row(objs):
    scene = objs["scene"]
    mask_root = objs["mask_root"]
    positions = [(-1.05, 1, 35), (0.0, 36, 70), (1.05, 71, 105)]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 35:
            t = smooth01((frame - 1) / 34.0)
            x = lerp(-1.05, -1.05, t)
            reveal = "ball"
        elif frame <= 70:
            t = smooth01((frame - 35) / 35.0)
            x = lerp(-1.05, 0.0, t)
            reveal = "cube"
        elif frame <= 105:
            t = smooth01((frame - 70) / 35.0)
            x = lerp(0.0, 1.05, t)
            reveal = "pyramid"
        else:
            x = 1.05
            reveal = "pyramid"

        mask_root.location = (x, -0.02, 0.0)
        mask_root.keyframe_insert(data_path="location", frame=frame)
        mask_root["pb_current_window_reveals"] = reveal
        mask_root["pb_reveal_order"] = ["ball", "cube", "pyramid"]

    scene.frame_set(FRAME_START)


def animate_locker_permutation(objs):
    scene = objs["scene"]
    root = objs["cabinet_root"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 28:
            close_t = smooth01((frame - 1) / 27.0)
            move_t = 0.0
            open_t = 0.0
        elif frame <= 88:
            close_t = 1.0
            move_t = smooth01((frame - 28) / 60.0)
            open_t = 0.0
        else:
            close_t = 1.0
            move_t = 1.0
            open_t = smooth01((frame - 88) / 32.0)

        root.location = (lerp(0.0, 1.55, move_t), 0.0, 0.0)
        root.keyframe_insert(data_path="location", frame=frame)

        for d in objs["doors"]:
            y_closed = -0.02
            y_open = -0.82
            y = lerp(y_open, y_closed, close_t)
            if open_t > 0:
                y = lerp(y_closed, y_open, open_t)
            d.location = (d.location.x, y, 0.72)
            d.keyframe_insert(data_path="location", frame=frame)
            d["pb_state"] = "closed" if y > -0.25 else "open"

        root["pb_locker_order"] = objs["order"]

    scene.frame_set(FRAME_START)


def animate_nested_capsule_carrier(objs):
    scene = objs["scene"]
    cap_root = objs["capsule_root"]
    cap_lid = objs["capsule_lid"]
    carrier = objs["carrier_root"]
    cover = objs["carrier_cover"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 20:
            cap_close = smooth01((frame - 1) / 19.0)
        else:
            cap_close = 1.0

        if frame <= 20:
            cap_move = 0.0
        elif frame <= 55:
            cap_move = smooth01((frame - 20) / 35.0)
        else:
            cap_move = 1.0

        if frame <= 55:
            carrier_close = 0.0
        elif frame <= 75:
            carrier_close = smooth01((frame - 55) / 20.0)
        else:
            carrier_close = 1.0

        if frame <= 75:
            carrier_move = 0.0
        elif frame <= 98:
            carrier_move = smooth01((frame - 75) / 23.0)
        else:
            carrier_move = 1.0

        if frame <= 98:
            reopen = 0.0
        else:
            reopen = smooth01((frame - 98) / 22.0)

        cap_x = lerp(-1.25, 1.10, cap_move) + lerp(0.0, 0.80, carrier_move)
        carrier_x = 1.10 + lerp(0.0, 0.80, carrier_move)

        cap_root.location = (cap_x, 0.0, 0.0)
        carrier.location = (carrier_x, 0.0, 0.0)

        cap_lid.location = (0.0, lerp(-0.65, 0.0, cap_close), 0.38)
        if reopen > 0:
            cap_lid.location = (0.0, lerp(0.0, -0.65, reopen), 0.38)

        cover.location = (0.0, lerp(-1.20, 0.0, carrier_close), 0.65)
        if reopen > 0:
            cover.location = (0.0, lerp(0.0, -1.20, reopen), 0.65)

        for obj in [cap_root, carrier, cap_lid, cover]:
            obj.keyframe_insert(data_path="location", frame=frame)

        objs["ball"]["pb_state"] = "inside_capsule"
        objs["ball"]["pb_nested_container_identity_preserved"] = True

    scene.frame_set(FRAME_START)


def animate_numbered_cubbies(objs):
    scene = objs["scene"]
    root = objs["tray_root"]
    panel = objs["panel"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 30:
            cover_t = smooth01((frame - 1) / 29.0)
            rot_t = 0.0
            open_t = 0.0
        elif frame <= 88:
            cover_t = 1.0
            rot_t = smooth01((frame - 30) / 58.0)
            open_t = 0.0
        else:
            cover_t = 1.0
            rot_t = 1.0
            open_t = smooth01((frame - 88) / 32.0)

        root.rotation_euler = (0.0, 0.0, lerp(0.0, math.radians(90), rot_t))
        root.keyframe_insert(data_path="rotation_euler", frame=frame)

        panel_y = lerp(-2.25, 0.0, cover_t)
        if open_t > 0:
            panel_y = lerp(0.0, 2.25, open_t)
        panel.location = (0.0, panel_y, 0.70)
        panel.keyframe_insert(data_path="location", frame=frame)

        root["pb_state"] = "covered_and_rotating" if cover_t >= 1.0 and open_t == 0.0 else "visible_or_revealing"
        panel["pb_covers_numbered_cubbies"] = True

    scene.frame_set(FRAME_START)


def build_scene():
    k = CASE["scene_kind"]
    if k == "marked_boxes_swap":
        return build_marked_boxes_swap()
    if k == "theater_curtain":
        return build_theater_curtain()
    if k == "sliding_window_row":
        return build_sliding_window_row()
    if k == "locker_permutation":
        return build_locker_permutation()
    if k == "nested_capsule_carrier":
        return build_nested_capsule_carrier()
    if k == "numbered_cubbies":
        return build_numbered_cubbies()
    raise RuntimeError("Unknown scene_kind: " + str(k))


def animate_scene(objs):
    k = objs["kind"]
    if k == "marked_boxes_swap":
        return animate_marked_boxes_swap(objs)
    if k == "theater_curtain":
        return animate_theater_curtain(objs)
    if k == "sliding_window_row":
        return animate_sliding_window_row(objs)
    if k == "locker_permutation":
        return animate_locker_permutation(objs)
    if k == "nested_capsule_carrier":
        return animate_nested_capsule_carrier(objs)
    if k == "numbered_cubbies":
        return animate_numbered_cubbies(objs)
    raise RuntimeError("Unknown kind: " + str(k))


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
    if "locker_order" in CASE:
        print("locker_order:", CASE["locker_order"])
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
