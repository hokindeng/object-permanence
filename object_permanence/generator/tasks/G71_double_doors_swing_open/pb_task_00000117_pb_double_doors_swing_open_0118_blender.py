# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_DOUBLE_DOORS_SWING_OPEN_0118",
  "scene_kind": "double_doors_swing_open",
  "prompt": "A closed box sits on a table with two front doors meeting in the middle. The two doors swing open outward on their side hinges — the left door to the left, the right door to the right — revealing an object resting inside the box. The box itself does not move; only the doors open."
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


def make_mat(name, color, roughness=0.55, metallic=0.0, alpha=1.0, transparent=False):
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

    if transparent:
        try:
            mat.blend_method = "BLEND"
            mat.show_transparent_back = True
            mat.use_screen_refraction = True
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


def add_sphere(name, radius, location, material, color_name, role="target"):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object", "sphere", color_name, True, solid=True, pb_radius=radius)
    return obj


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), roughness=0.84)
    MATS["gray"] = make_mat("mat_gray", (0.46, 0.46, 0.46), roughness=0.64)
    MATS["dark"] = make_mat("mat_dark", (0.18, 0.19, 0.21), roughness=0.76)
    MATS["light"] = make_mat("mat_light", (0.68, 0.69, 0.71), roughness=0.68)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.38, 0.06), roughness=0.28)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.92)
    MATS["door"] = make_mat("mat_opaque_door", (0.40, 0.41, 0.43), roughness=0.70)


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


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (10.0, 5.0, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 2.48, 1.62), (10.2, 0.08, 3.24), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.4, -4.2, 5.5))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 980
    key.data.size = 6.0

    bpy.ops.object.light_add(type="POINT", location=(3.4, -3.0, 3.0))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 150

    return scene


def setup_camera(scene, location, target, lens=32, ortho=False, ortho_scale=4.0):
    bpy.ops.object.camera_add(location=location)
    cam = bpy.context.object
    cam.name = "camera_main"
    cam.data.lens = lens
    cam.data.dof.use_dof = False
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho_scale
    look_at(cam, target)
    scene.camera = cam
    return cam


# =============================================================================
# 0118 double doors swing open
#
# A closed box sits on the table. Its FRONT face is a pair of doors that meet
# in the middle. The two doors swing open OUTWARD on their side hinges: the
# left door pivots about its LEFT (outer) vertical edge and swings to the left,
# the right door pivots about its RIGHT (outer) vertical edge and swings to the
# right. This reveals a colored ball resting inside the box. The box body (its
# floor, back wall, side walls and top) never moves.
#
# Hinge construction: each door is a thin vertical slab whose mesh origin is
# moved to its OUTER vertical edge, so a pure world Z rotation about that edge
# pivots exactly at the box side (no translation, no clipping through the side
# walls). The left door rotates -Z (opening its inner edge forward/left away
# from the box front), the right door rotates +Z (mirror), so both fronts open
# outward toward the camera and clear each other completely.
# =============================================================================

def build_double_doors_swing_open():
    scene = build_base_scene()

    # Front, slightly elevated view so the camera looks at the front doors and,
    # once open, straight into the cavity at the ball resting inside.
    setup_camera(
        scene,
        location=(0.0, -3.75, 2.05),
        target=(0.0, 0.10, 0.55),
        lens=40,
    )

    base_z = 0.10

    # Inner cavity spans roughly x in [-0.60, 0.60], y in [-0.60, 0.60].
    # Walls are 0.10 thick, 0.90 tall (taller so the doors read clearly).
    wall_h = 0.90
    wall_t = 0.10
    inner_half = 0.60          # inner half-width / half-depth
    outer_half = inner_half + wall_t / 2.0  # 0.65 -> wall centerline
    wall_cz = base_z + 0.05 + wall_h / 2.0

    floor_top_z = base_z + 0.10  # top surface of the box inner floor

    # Box inner floor (a solid slab the object rests on)
    add_cube("box_inner_floor", (0.0, 0.0, base_z + 0.05),
             (2.0 * outer_half + wall_t, 2.0 * outer_half + wall_t, 0.10),
             MATS["gray"], "box_floor", "gray")

    # Left / right side walls and the BACK wall. The FRONT face is left open for
    # the two doors. A slim top slab caps the box (leaving the full front open).
    add_cube("box_left_wall", (-outer_half, 0.0, wall_cz),
             (wall_t, 2.0 * outer_half + wall_t, wall_h), MATS["gray"], "box_wall", "gray")
    add_cube("box_right_wall", (outer_half, 0.0, wall_cz),
             (wall_t, 2.0 * outer_half + wall_t, wall_h), MATS["gray"], "box_wall", "gray")
    add_cube("box_back_wall", (0.0, outer_half, wall_cz),
             (2.0 * outer_half + wall_t, wall_t, wall_h), MATS["gray"], "box_wall", "gray")

    box_top_z = base_z + 0.05 + wall_h            # top of the walls
    top_thick = 0.10
    add_cube("box_top", (0.0, 0.0, box_top_z + top_thick / 2.0),
             (2.0 * outer_half + wall_t, 2.0 * outer_half + wall_t, top_thick),
             MATS["gray"], "box_top", "gray")

    # --- Front double doors -------------------------------------------------
    # The two doors together cover the full front opening. Each door spans half
    # the front width and the full inner height; they meet at x = 0 (the middle)
    # when closed. Each door's OBJECT ORIGIN is placed on its OUTER vertical
    # edge so a pure Z rotation swings it outward about the box side.
    #
    # Front face is at y = -front_y (front outer face of the box).
    front_y = outer_half + wall_t / 2.0           # 0.70, front outer plane
    door_thick = 0.06
    door_h = wall_h                               # match wall height
    door_cz = base_z + 0.05 + door_h / 2.0        # center height of the doors
    # The front opening spans x in [-front_y, +front_y] = [-0.70, 0.70]. Each of
    # the two doors covers exactly half of it, so each door is `front_y` wide
    # (0.70) and they meet at x = 0 (the middle) when closed. `door_w` is the
    # full width of one door; the outer-edge origin is `door_w` from the middle.
    door_w = front_y                               # 0.70, width of one door

    # Outer edges (hinge lines) sit at the box's left/right outer front corners.
    left_hinge_x = -front_y                       # -0.70 (left door outer edge)
    right_hinge_x = front_y                        # +0.70 (right door outer edge)
    # Front face of the doors sits just in front of the box front plane so the
    # closed doors clearly cover the opening without z-fighting the box.
    door_y = -(front_y + door_thick / 2.0)         # front face of closed doors

    # LEFT DOOR: origin at its LEFT (outer) edge. Build centered, then shift
    # verts so geometry extends in +X from the origin (origin at left edge).
    bpy.ops.mesh.primitive_cube_add(size=1, location=(left_hinge_x, door_y, door_cz))
    left_door = bpy.context.object
    left_door.name = "left_front_door"
    left_door.dimensions = (door_w, door_thick, door_h)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    lmesh = left_door.data
    for v in lmesh.vertices:
        v.co.x += door_w / 2.0   # geometry extends from left-edge origin toward +X (inner edge at x=0)
    lmesh.update()
    left_door.data.materials.append(MATS["door"])
    tag(left_door, "left_front_door", "hinged_door", "dynamic_object", "cube", "dark_gray", True, solid=True)
    left_door["pb_hinge_at_left_edge"] = True

    # RIGHT DOOR: origin at its RIGHT (outer) edge. Build centered, then shift
    # verts so geometry extends in -X from the origin (origin at right edge).
    bpy.ops.mesh.primitive_cube_add(size=1, location=(right_hinge_x, door_y, door_cz))
    right_door = bpy.context.object
    right_door.name = "right_front_door"
    right_door.dimensions = (door_w, door_thick, door_h)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    rmesh = right_door.data
    for v in rmesh.vertices:
        v.co.x -= door_w / 2.0   # geometry extends from right-edge origin toward -X (inner edge at x=0)
    rmesh.update()
    right_door.data.materials.append(MATS["door"])
    tag(right_door, "right_front_door", "hinged_door", "dynamic_object", "cube", "dark_gray", True, solid=True)
    right_door["pb_hinge_at_right_edge"] = True

    # --- Object inside (revealed as the doors open) --------------------------
    # A single clearly-colored ball resting on the inner floor. It never moves.
    ball_r = 0.34
    ball = add_sphere(
        "colored_ball_inside_box",
        ball_r,
        (0.0, 0.0, floor_top_z + ball_r),
        MATS["orange"],
        "orange",
    )
    ball["pb_visible_when_doors_open"] = True
    ball["pb_resting_inside_box"] = True

    return {
        "scene": scene,
        "kind": "double_doors_swing_open",
        "left_door": left_door,
        "right_door": right_door,
        "ball": ball,
        "base_z": base_z,
        "ball_r": ball_r,
        "floor_top_z": floor_top_z,
    }


def animate_double_doors_swing_open(objs):
    scene = objs["scene"]
    left_door = objs["left_door"]
    right_door = objs["right_door"]
    ball = objs["ball"]
    floor_top_z = objs["floor_top_z"]
    ball_r = objs["ball_r"]

    # The two doors swing OUTWARD on their side hinges to reveal the ball
    # resting inside, and back to CLOSED (meeting at the middle) to hide it. The
    # box body and the ball never move.
    #
    # Each door's origin is on its OUTER vertical edge, so a pure Z rotation
    # pivots exactly at the box side with no translation. To swing the door
    # front OUTWARD toward the camera (-Y) and away from the box:
    #   - LEFT door (geometry extends +X, i.e. toward the middle): a NEGATIVE
    #     Z rotation carries its inner edge toward -Y/-X, swinging the door to
    #     the LEFT and forward, clearing the front opening.
    #   - RIGHT door (geometry extends -X): a POSITIVE Z rotation is the mirror,
    #     swinging the door to the RIGHT and forward.
    # ~105 degrees so both doors fully clear the front and each other.
    open_angle = math.radians(105.0)
    left_closed, left_open = 0.0, -open_angle
    right_closed, right_open = 0.0, open_angle

    # Full OBJECT-PERMANENCE cycle that STARTS OPEN: the object is shown first,
    # then hidden, then revealed again as the same object. t=1 -> doors OPEN,
    # t=0 -> doors CLOSED.
    #   Phase 1  f1  - f16   : OPEN, object clearly visible inside (hold).
    #   Phase 2  f16 - f46   : doors swing CLOSED, hiding the object.
    #   Phase 3  f46 - f66   : hold CLOSED (object hidden).
    #   Phase 4  f66 - f96   : doors swing OPEN again, revealing the SAME object.
    #   Phase 5  f96 - f120  : hold OPEN, object revealed unchanged.
    open_hold_end = 16
    close_end = 46
    closed_hold_end = 66
    reopen_end = 96

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= open_hold_end:
            t = 1.0
            door_state = "open_object_visible_before_hiding"
            ball_state = "visible_inside_open_box"
        elif frame <= close_end:
            t = 1.0 - smooth01((frame - open_hold_end) / float(close_end - open_hold_end))
            door_state = "doors_swinging_closed_hiding_object"
            ball_state = "being_hidden_as_doors_close"
        elif frame <= closed_hold_end:
            t = 0.0
            door_state = "closed_doors_meet_in_middle_object_hidden"
            ball_state = "hidden_inside_closed_box"
        elif frame <= reopen_end:
            t = smooth01((frame - closed_hold_end) / float(reopen_end - closed_hold_end))
            door_state = "doors_swinging_open_outward_revealing_object"
            ball_state = "being_revealed_as_doors_reopen"
        else:
            t = 1.0
            door_state = "doors_fully_open_same_object_revealed"
            ball_state = "revealed_resting_inside_open_box"

        l_theta = lerp(left_closed, left_open, t)
        r_theta = lerp(right_closed, right_open, t)

        # Pure Z rotation about each door's outer-edge origin: no translation.
        left_door.rotation_euler = (0.0, 0.0, l_theta)
        left_door.keyframe_insert(data_path="rotation_euler", frame=frame)
        left_door["pb_state"] = door_state

        right_door.rotation_euler = (0.0, 0.0, r_theta)
        right_door.keyframe_insert(data_path="rotation_euler", frame=frame)
        right_door["pb_state"] = door_state

        # The box body and the object never move.
        ball.location = (0.0, 0.0, floor_top_z + ball_r)
        ball.keyframe_insert(data_path="location", frame=frame)
        ball["pb_state"] = ball_state
        ball["pb_must_remain_inside_box"] = True
        ball["pb_same_object_throughout"] = True

    scene.frame_set(FRAME_START)


# =============================================================================
# dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "double_doors_swing_open":
        return build_double_doors_swing_open()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(objs):
    kind = objs["kind"]
    if kind == "double_doors_swing_open":
        return animate_double_doors_swing_open(objs)
    raise RuntimeError("Unknown kind: " + str(kind))


# =============================================================================
# output
# =============================================================================

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

    objs = build_scene_by_kind()
    scene = objs["scene"]
    animate_scene_by_kind(objs)

    # Input = closed doors (object hidden). Event = doors partly open. Final =
    # doors fully open, object revealed resting inside.
    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, 60, OPTIONAL_FRAME_PATH)
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
