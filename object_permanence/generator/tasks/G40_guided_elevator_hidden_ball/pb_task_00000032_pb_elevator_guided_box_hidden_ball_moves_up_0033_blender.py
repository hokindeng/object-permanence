# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_ELEVATOR_GUIDED_BOX_HIDDEN_BALL_MOVES_UP_0033",
  "scene_kind": "guided_elevator_hidden_ball",
  "prompt": "A gray elevator box is visibly attached to two fixed vertical guide rails by guide brackets. In the first frame the front door is open and an orange ball is visible inside the elevator box. The door closes, hiding the ball. Then the entire guided elevator box moves upward along the rails. At the end the door opens again, revealing that the same orange ball is still inside the box and has moved upward with it. The ball must not stay at the original height or fall through the elevator floor."
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


def ease_in_quad(t):
    t = clamp01(t)
    return t * t


def lerp(a, b, t):
    return a + (b - a) * t


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def make_mat(name, color, roughness=0.55, metallic=0.0, alpha=1.0, blend=None):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (color[0], color[1], color[2], alpha)
    try:
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            if "Base Color" in bsdf.inputs:
                bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], alpha)
            if "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = alpha
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = roughness
            if "Metallic" in bsdf.inputs:
                bsdf.inputs["Metallic"].default_value = metallic
    except Exception:
        pass

    if blend is None:
        blend = "BLEND" if alpha < 1.0 else "OPAQUE"
    try:
        mat.blend_method = blend
        mat.show_transparent_back = True
        mat.use_screen_refraction = alpha < 1.0
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


def add_cube(name, location, dimensions, material=None, role="static_solid", color_name="gray", is_dynamic=False, solid=True):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
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


def add_sphere(name, radius, location, material, color_name, role="target"):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object", "sphere", color_name, True, solid=True, pb_radius=radius)
    return obj


def add_oriented_box(name, center, length, width, height, direction, material, role, color_name, solid=True):
    direction = Vector(direction).normalized()
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.scale = (length / 2.0, width / 2.0, height / 2.0)
    obj.rotation_euler = direction.to_track_quat("X", "Z").to_euler()
    if material is not None:
        obj.data.materials.append(material)
    tag(obj, name, role, "static_solid" if solid else "non_solid_marker", "oriented_cube", color_name, False, solid=solid)
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
        scene.eevee.gtao_distance = 3
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


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor_warm", (0.82, 0.80, 0.75), roughness=0.82)
    MATS["gray"] = make_mat("mat_neutral_gray", (0.46, 0.46, 0.46), roughness=0.62)
    MATS["dark"] = make_mat("mat_dark_gray", (0.18, 0.18, 0.20), roughness=0.76)
    MATS["box"] = make_mat("mat_box_gray", (0.38, 0.39, 0.40), roughness=0.78)
    MATS["edge"] = make_mat("mat_light_edge", (0.62, 0.63, 0.64), roughness=0.68)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.38, 0.06), roughness=0.30)
    MATS["glass"] = make_mat("mat_transparent_glass", (0.50, 0.82, 1.0), roughness=0.08, alpha=0.34, blend="BLEND")
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (9.8, 4.8, 0.10), MATS["floor"], role="ground", color_name="warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 2.42, 1.60), (10.0, 0.08, 3.20), MATS["backdrop"], role="background", color_name="off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.8, -4.4, 5.5))
    key = bpy.context.object
    key.name = "large_softbox_light"
    key.data.energy = 950
    key.data.size = 6.0

    bpy.ops.object.light_add(type="POINT", location=(3.7, -2.8, 3.2))
    fill = bpy.context.object
    fill.name = "right_fill_light"
    fill.data.energy = 145

    return scene


def setup_camera(scene, location=(-0.65, -8.5, 1.75), target=(0.4, 0.0, 0.65), lens=31):
    bpy.ops.object.camera_add(location=location)
    camera = bpy.context.object
    camera.name = "camera_main"
    camera.data.lens = lens
    look_at(camera, target)
    camera.data.dof.use_dof = False
    scene.camera = camera


# ============================================================
# 0033 guided elevator
# ============================================================

def build_guided_elevator_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(2.75, -7.7, 2.25), target=(0.12, 0.0, 1.08), lens=32)

    # Static shaft / guide frame: rails are real vertical pillars, not just decoration.
    rail_x = 0.72
    rail_y = 0.34
    rail_h = 2.55
    rail_z = 1.38

    for sx, name in [(-rail_x, "left"), (rail_x, "right")]:
        add_cube(f"fixed_{name}_vertical_guide_rail", (sx, rail_y, rail_z), (0.08, 0.08, rail_h), MATS["edge"], role="fixed_guide_rail", color_name="light_gray")
        add_cube(f"fixed_{name}_front_guide_rail", (sx, -0.34, rail_z), (0.08, 0.08, rail_h), MATS["edge"], role="fixed_guide_rail", color_name="light_gray")

    add_cube("fixed_top_crossbeam_between_rails", (0.0, 0.0, 2.64), (1.58, 0.12, 0.10), MATS["edge"], role="fixed_elevator_frame", color_name="light_gray")
    add_cube("fixed_bottom_crossbeam_between_rails", (0.0, 0.0, 0.18), (1.58, 0.12, 0.10), MATS["edge"], role="fixed_elevator_frame", color_name="light_gray")

    base_x = 0.0
    base_y = 0.0
    bottom_z0 = 0.24
    box_w = 0.90
    box_d = 0.70
    box_h = 0.82
    wall_t = 0.07

    parts = []

    def moving_part(name, rel, dims, mat, role, color="gray"):
        obj = add_cube(
            name,
            (base_x + rel[0], base_y + rel[1], bottom_z0 + rel[2]),
            dims,
            mat,
            role=role,
            color_name=color,
            is_dynamic=True,
            solid=True,
        )
        obj["pb_rel_x"] = rel[0]
        obj["pb_rel_y"] = rel[1]
        obj["pb_rel_z"] = rel[2]
        obj["pb_moves_with_elevator_car"] = True
        parts.append(obj)
        return obj

    moving_part("guided_elevator_box_floor", (0, 0, 0), (box_w, box_d, wall_t), MATS["box"], "elevator_floor")
    moving_part("guided_elevator_back_wall", (0, box_d / 2, box_h / 2), (box_w, wall_t, box_h), MATS["box"], "elevator_wall")
    moving_part("guided_elevator_left_wall", (-box_w / 2, 0, box_h / 2), (wall_t, box_d, box_h), MATS["box"], "elevator_wall")
    moving_part("guided_elevator_right_wall", (box_w / 2, 0, box_h / 2), (wall_t, box_d, box_h), MATS["box"], "elevator_wall")
    moving_part("guided_elevator_roof", (0, 0, box_h), (box_w, box_d, wall_t), MATS["box"], "elevator_roof")

    # Visible guide shoes/brackets physically connect the moving box to the fixed rails,
    # so the box does not read as floating.
    for sx, side in [(-0.58, "left"), (0.58, "right")]:
        for zrel, level in [(0.22, "lower"), (0.66, "upper")]:
            shoe = moving_part(
                f"moving_{side}_{level}_guide_shoe_touching_rail",
                (sx, 0.34, zrel),
                (0.20, 0.16, 0.12),
                MATS["edge"],
                "moving_guide_shoe",
                "light_gray",
            )
            shoe["pb_attached_to_box_and_rides_on_fixed_rail"] = True

            bracket = moving_part(
                f"moving_{side}_{level}_box_to_rail_bracket",
                (sx * 0.82, 0.25, zrel),
                (0.20, 0.08, 0.08),
                MATS["edge"],
                "box_to_rail_bracket",
                "light_gray",
            )
            bracket["pb_visibly_connects_box_to_guide_rail"] = True

    door = moving_part(
        "guided_elevator_front_sliding_door",
        (0, -box_d / 2 - 0.04, box_h / 2),
        (box_w, wall_t, box_h),
        MATS["edge"],
        "elevator_sliding_door",
        "light_gray",
    )

    ball = add_sphere("orange_ball_inside_guided_elevator", 0.15, (0, -0.05, bottom_z0 + 0.22), MATS["orange"], "orange")
    ball["pb_rel_x"] = 0.0
    ball["pb_rel_y"] = -0.05
    ball["pb_rel_z"] = 0.22
    ball["pb_moves_with_elevator_box"] = True

    return {"scene": scene, "kind": "guided_elevator_hidden_ball", "parts": parts, "door": door, "ball": ball, "bottom_z0": bottom_z0}


def animate_guided_elevator(objs, frame):
    parts = objs["parts"]
    door = objs["door"]
    ball = objs["ball"]
    bottom_z0 = objs["bottom_z0"]

    if frame <= 30:
        lift = 0.0
        door_closed = smooth01(frame / 30.0)
    elif frame <= 84:
        lift = smooth01((frame - 30) / 54.0) * 1.08
        door_closed = 1.0
    else:
        lift = 1.08
        door_closed = 1.0 - smooth01((frame - 84) / 36.0)

    for obj in parts:
        rx = obj.get("pb_rel_x", 0.0)
        ry = obj.get("pb_rel_y", 0.0)
        rz = obj.get("pb_rel_z", 0.0)

        if obj == door:
            # open means shifted left; closed means centered.
            side_shift = -0.70 * (1.0 - door_closed)
            obj.location = (rx + side_shift, ry, bottom_z0 + rz + lift)
            obj["pb_state"] = "open" if door_closed < 0.1 else ("closed_hiding_ball" if door_closed > 0.9 else "sliding_closed_or_open")
        else:
            obj.location = (rx, ry, bottom_z0 + rz + lift)
            obj["pb_state"] = "guided_elevator_car_moving_up" if lift > 0.0 else "guided_elevator_car_initial"

        obj["pb_elevator_lift_z"] = float(lift)
        obj.keyframe_insert(data_path="location", frame=frame)

    ball.location = (ball.get("pb_rel_x", 0.0), ball.get("pb_rel_y", 0.0), bottom_z0 + ball.get("pb_rel_z", 0.22) + lift)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball["pb_state"] = "visible_inside_open_guided_elevator" if door_closed < 0.15 else "hidden_inside_guided_elevator"
    ball["pb_moves_with_elevator_box"] = True
    ball["pb_not_left_at_original_height"] = bool(lift > 0.0)


# ============================================================
# 0035 trapdoor
# ============================================================

def build_trapdoor_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(2.55, -7.8, 2.20), target=(0.15, 0.0, 0.82), lens=32)

    deck_z = 0.95
    hole_x = 0.0
    trap_len = 0.82
    deck_len = 3.0
    deck_w = 0.72
    deck_t = 0.10

    add_cube("left_fixed_deck_before_trapdoor", (-0.95, 0, deck_z), (1.10, deck_w, deck_t), MATS["gray"], role="fixed_deck", color_name="gray")
    add_cube("right_fixed_deck_after_trapdoor", (0.95, 0, deck_z), (1.10, deck_w, deck_t), MATS["gray"], role="fixed_deck", color_name="gray")

    hole_marker = add_cube("dark_opening_under_trapdoor", (hole_x, 0, deck_z - 0.065), (trap_len, deck_w + 0.06, 0.035), MATS["dark"], role="trapdoor_opening", color_name="dark_gray", solid=False)
    hole_marker["pb_is_opening_below_trapdoor"] = True

    hinge_x = trap_len / 2.0
    hinge_z = deck_z + deck_t / 2.0
    hinge = add_cube("right_trapdoor_hinge", (hinge_x, 0, hinge_z + 0.02), (0.10, deck_w + 0.12, 0.08), MATS["edge"], role="hinge", color_name="light_gray")

    trapdoor = add_cube("closed_trapdoor_panel", (0, 0, deck_z), (trap_len, deck_w, deck_t), MATS["gray"], role="trapdoor_panel", color_name="gray", is_dynamic=True, solid=True)
    trapdoor["pb_hinge_x"] = hinge_x
    trapdoor["pb_supports_ball_initially"] = True

    latch = add_cube("left_retracting_latch_pin", (-hinge_x, 0, deck_z + 0.02), (0.16, deck_w + 0.16, 0.09), MATS["edge"], role="support_latch_pin", color_name="light_gray", is_dynamic=True, solid=True)
    latch["pb_latch_holds_trapdoor_closed"] = True

    ball = add_sphere("orange_ball_on_trapdoor", 0.16, (-0.16, 0, deck_z + 0.16 + 0.07), MATS["orange"], "orange")
    ball["pb_expected_behavior"] = "fall_only_after_trapdoor_opens"

    return {"scene": scene, "kind": "trapdoor_opens_ball_falls", "trapdoor": trapdoor, "latch": latch, "ball": ball, "hinge_x": hinge_x, "deck_z": deck_z, "trap_len": trap_len}


def animate_trapdoor(objs, frame):
    trapdoor = objs["trapdoor"]
    latch = objs["latch"]
    ball = objs["ball"]
    hinge_x = objs["hinge_x"]
    deck_z = objs["deck_z"]
    trap_len = objs["trap_len"]

    # Latch retracts first.
    if frame <= 34:
        latch_shift = 0.0
    elif frame <= 50:
        latch_shift = -0.80 * smooth01((frame - 34) / 16.0)
    else:
        latch_shift = -0.80

    latch.location = (-hinge_x + latch_shift, 0, deck_z + 0.02)
    latch.keyframe_insert(data_path="location", frame=frame)
    latch["pb_state"] = "holding_trapdoor_closed" if frame <= 34 else ("retracting" if frame <= 50 else "removed")

    # Trapdoor opens after latch retracts.
    if frame <= 50:
        angle = 0.0
        door_state = "closed_supporting_ball"
    else:
        t = smooth01((frame - 50) / 38.0)
        angle = math.radians(-72.0) * t
        door_state = "opening_downward_after_latch_removed" if t < 0.98 else "open_downward"

    # Rotate panel around right hinge.
    center_vec_x = -trap_len / 2.0
    center_x = hinge_x + center_vec_x * math.cos(angle)
    center_z = deck_z - center_vec_x * math.sin(angle)
    trapdoor.location = (center_x, 0, center_z)
    trapdoor.rotation_euler = (0.0, angle, 0.0)
    trapdoor.keyframe_insert(data_path="location", frame=frame)
    trapdoor.keyframe_insert(data_path="rotation_euler", frame=frame)
    trapdoor["pb_state"] = door_state
    trapdoor["pb_support_removed"] = bool(frame > 50)

    # Ball supported until door opens, then falls with slight forward motion.
    if frame <= 50:
        x = -0.16
        z = deck_z + 0.23
        state = "resting_supported_on_closed_trapdoor"
    else:
        t = (frame - 50) / 56.0
        x = -0.16 + 0.36 * clamp01(t)
        z = max(0.16, deck_z + 0.23 - 1.12 * ease_in_quad(t))
        state = "falling_through_open_trapdoor" if z > 0.18 else "landed_on_floor_after_fall"

    ball.location = (x, 0, z)
    ball.rotation_euler = (0.0, -0.15 * frame, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball["pb_state"] = state
    ball["pb_does_not_fall_before_latch_removed"] = bool(frame <= 50)
    ball["pb_falls_after_support_removed"] = bool(frame > 50)


# ============================================================
# 0036 transparent trough
# ============================================================

def build_transparent_trough_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(1.75, -7.7, 2.05), target=(0.0, 0.0, 0.95), lens=33)

    start = Vector((-2.35, 0.0, 1.35))
    end = Vector((1.85, 0.0, 0.55))
    direction = (end - start).normalized()
    length = (end - start).length
    center = (start + end) * 0.5

    # Transparent trough: bottom + two side walls + visible edge rods.
    bottom = add_oriented_box("transparent_trough_bottom_plate", center, length, 0.56, 0.06, direction, MATS["glass"], "transparent_trough_bottom", "transparent_blue", solid=True)
    bottom["pb_transparent"] = True
    bottom["pb_solid"] = True

    side_offset = Vector((0, 0.31, 0))
    left_wall = add_oriented_box("transparent_trough_left_side_wall", center + side_offset, length, 0.06, 0.42, direction, MATS["glass"], "transparent_trough_side_wall", "transparent_blue", solid=True)
    right_wall = add_oriented_box("transparent_trough_right_side_wall", center - side_offset, length, 0.06, 0.42, direction, MATS["glass"], "transparent_trough_side_wall", "transparent_blue", solid=True)
    left_wall["pb_transparent"] = True
    right_wall["pb_transparent"] = True

    # End wall is perpendicular to the channel direction and blocks the ball.
    cap_center = end + direction * 0.05 + Vector((0, 0, 0.12))
    end_wall = add_oriented_box("transparent_end_wall_blocker", cap_center, 0.10, 0.70, 0.58, direction, MATS["glass"], "transparent_end_wall", "transparent_blue", solid=True)
    end_wall["pb_transparent"] = True
    end_wall["pb_solid"] = True
    end_wall["pb_blocks_ball"] = True

    # Light edge rods make the transparent geometry readable.
    add_oriented_box("light_edge_left_top_rail", center + side_offset + Vector((0, 0, 0.23)), length, 0.035, 0.035, direction, MATS["edge"], "visible_trough_edge", "light_gray")
    add_oriented_box("light_edge_right_top_rail", center - side_offset + Vector((0, 0, 0.23)), length, 0.035, 0.035, direction, MATS["edge"], "visible_trough_edge", "light_gray")
    add_oriented_box("light_edge_end_wall_top", cap_center + Vector((0, 0, 0.30)), 0.10, 0.76, 0.035, direction, MATS["edge"], "visible_end_wall_edge", "light_gray")

    ball_start = start + direction * 0.42 + Vector((0, 0, 0.22))
    ball = add_sphere("orange_ball_inside_transparent_trough", 0.15, ball_start, MATS["orange"], "orange")
    ball["pb_inside_transparent_trough"] = True

    return {"scene": scene, "kind": "transparent_trough_end_wall_blocks_ball", "ball": ball, "start": start, "end": end, "direction": direction}


def animate_transparent_trough(objs, frame):
    ball = objs["ball"]
    start = objs["start"]
    end = objs["end"]
    direction = objs["direction"]

    path_start = start + direction * 0.42 + Vector((0, 0, 0.22))
    path_stop = end - direction * 0.22 + Vector((0, 0, 0.22))

    if frame <= 88:
        t = smooth01((frame - FRAME_START) / 87.0)
        pos = path_start.lerp(path_stop, t)
        state = "rolling_down_inside_transparent_trough"
    else:
        pos = path_stop
        state = "stopped_by_transparent_end_wall"

    ball.location = pos
    ball.rotation_euler = (0.0, -0.11 * frame, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball["pb_state"] = state
    ball["pb_blocked_by_transparent_end_wall"] = bool(frame > 88)
    ball["pb_does_not_pass_through_transparent_wall"] = True


# ============================================================
# Build / animate dispatch
# ============================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "guided_elevator_hidden_ball":
        return build_guided_elevator_scene()
    if kind == "trapdoor_opens_ball_falls":
        return build_trapdoor_scene()
    if kind == "transparent_trough_end_wall_blocks_ball":
        return build_transparent_trough_scene()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "guided_elevator_hidden_ball":
            animate_guided_elevator(objs, frame)
        elif kind == "trapdoor_opens_ball_falls":
            animate_trapdoor(objs, frame)
        elif kind == "transparent_trough_end_wall_blocks_ball":
            animate_transparent_trough(objs, frame)
        else:
            raise RuntimeError("Unknown kind: " + str(kind))

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
        "reference_completion_video": None,
        "scene_file": f"{ITEM_ID}_scene.blend",
    }
    with open(TASK_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(task, f, indent=2, ensure_ascii=False)


def save_scene():
    bpy.ops.wm.save_as_mainfile(filepath=SCENE_FILE)


def main():
    ensure_dirs()
    clear_scene()
    objs = build_scene_by_kind()
    scene = objs["scene"]
    animate_scene(objs)

    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, 72, OPTIONAL_FRAME_PATH)
    render_png(scene, 120, OPTIONAL_FRAME_02B_PATH)

    render_animation(scene)
    write_task_json()
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("scene_kind:", CASE["scene_kind"])
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
