# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_VAULT_SWING_DOOR_0163",
  "scene_kind": "vault_swing_door",
  "prompt": "A heavy round vault door on a side hinge is closed over the front of a safe. The door swings open about its hinge to reveal an object resting inside the safe, unchanged. The safe body does not move; only the door swings."
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
    MATS["safe_body"] = make_mat("mat_safe_body", (0.34, 0.36, 0.40), roughness=0.60, metallic=0.35)
    MATS["door"] = make_mat("mat_vault_door", (0.55, 0.57, 0.62), roughness=0.42, metallic=0.55)
    MATS["door_face"] = make_mat("mat_door_face", (0.62, 0.64, 0.68), roughness=0.38, metallic=0.6)


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
# 0163 bank-vault swing door
#
# A static box "safe" sits on the table. Its front face (toward the camera, -Y)
# has a circular opening. A thick ROUND door (a short cylinder, disk faces
# toward the camera, axis along Y) plugs that opening. The door is hinged on one
# VERTICAL edge (its right side, +X): the door's object origin is moved onto
# that vertical hinge line so a pure world-Z rotation swings it open about the
# hinge with no translation. The safe body NEVER moves; only the door swings.
#
# Clearance: the object inside (a ball) rests on the safe's inner floor, centred
# in the cavity. The door hinges outward toward the camera (-Y) and to the side,
# so its swept volume stays in front of / beside the opening and never enters the
# cavity where the ball rests. The opening radius is derived from the ball so the
# ball is fully revealed when the door is open.
# =============================================================================

def build_vault_swing_door():
    scene = build_base_scene()

    # Slightly off-axis front view so the round door face, its side hinge, the
    # swing-open arc, and the revealed ball inside all read clearly.
    setup_camera(
        scene,
        location=(-2.6, -3.9, 1.85),
        target=(0.1, 0.0, 0.75),
        lens=40,
    )

    base_z = 0.10

    # --- Ball first: cavity clearances DERIVED from the ball -----------------
    ball_r = 0.24
    side_gap = 0.26          # min gap from ball surface to cavity walls
    back_gap = 0.22

    wall_t = 0.12
    cavity_half = ball_r + side_gap                 # inner half-width/height of cavity
    door_r = cavity_half + 0.06                     # round door radius (covers opening)
    door_thick = 0.16                               # THICK round door

    # --- Safe body (static box with a cavity opening on the front face) ------
    # Build the safe as a set of walls (back, top, bottom, left, right) forming a
    # cubic cavity open on the front (-Y) face. The round door plugs that front.
    safe_cx = 0.0
    inner_floor_top = base_z + 0.05 + wall_t        # top surface of the inner floor slab
    cavity_h = 2.0 * cavity_half                    # inner height of cavity
    cavity_w = 2.0 * cavity_half                    # inner width of cavity
    cavity_depth = 2.0 * ball_r + back_gap + 0.10   # inner depth (Y)

    # Cavity spans:  x in [-cavity_half, cavity_half]
    #                z in [inner_floor_top, inner_floor_top + cavity_h]
    #                y (depth) from front opening (y = front_y) back to +Y
    front_y = -cavity_depth / 2.0                   # front opening plane (toward camera)
    back_y = cavity_depth / 2.0

    cavity_cz = inner_floor_top + cavity_h / 2.0

    # Inner floor slab (ball rests on this).
    add_cube("safe_inner_floor", (safe_cx, 0.0, base_z + 0.05 + wall_t / 2.0),
             (cavity_w + 2.0 * wall_t, cavity_depth + wall_t, wall_t),
             MATS["safe_body"], "safe_body", "dark_gray")
    # Back wall.
    add_cube("safe_back_wall", (safe_cx, back_y + wall_t / 2.0, cavity_cz),
             (cavity_w + 2.0 * wall_t, wall_t, cavity_h + wall_t),
             MATS["safe_body"], "safe_body", "dark_gray")
    # Top wall.
    add_cube("safe_top_wall", (safe_cx, 0.0, inner_floor_top + cavity_h + wall_t / 2.0),
             (cavity_w + 2.0 * wall_t, cavity_depth + wall_t, wall_t),
             MATS["safe_body"], "safe_body", "dark_gray")
    # Left wall (-X).
    add_cube("safe_left_wall", (-cavity_half - wall_t / 2.0, 0.0, cavity_cz),
             (wall_t, cavity_depth + wall_t, cavity_h),
             MATS["safe_body"], "safe_body", "dark_gray")
    # Right wall (+X, hinge side).
    add_cube("safe_right_wall", (cavity_half + wall_t / 2.0, 0.0, cavity_cz),
             (wall_t, cavity_depth + wall_t, cavity_h),
             MATS["safe_body"], "safe_body", "dark_gray")

    # A front bezel/frame around the circular opening (four thin bars around the
    # square face leaving the round opening clear) so the safe front reads as a
    # solid face with a round door set into it. Kept thin and outside door_r.
    face_y = front_y - 0.02
    bezel_out = cavity_half + wall_t
    # top & bottom bezel bars
    add_cube("safe_front_bezel_top", (safe_cx, face_y, inner_floor_top + cavity_h + wall_t / 2.0),
             (2.0 * bezel_out, 0.06, wall_t), MATS["safe_body"], "safe_face", "dark_gray")
    add_cube("safe_front_bezel_bottom", (safe_cx, face_y, base_z + 0.05 + wall_t / 2.0),
             (2.0 * bezel_out, 0.06, wall_t), MATS["safe_body"], "safe_face", "dark_gray")
    add_cube("safe_front_bezel_left", (-cavity_half - wall_t / 2.0, face_y, cavity_cz),
             (wall_t, 0.06, cavity_h + wall_t), MATS["safe_body"], "safe_face", "dark_gray")
    add_cube("safe_front_bezel_right", (cavity_half + wall_t / 2.0, face_y, cavity_cz),
             (wall_t, 0.06, cavity_h + wall_t), MATS["safe_body"], "safe_face", "dark_gray")

    # --- Round vault door (thick cylinder, hinged on its RIGHT vertical edge) --
    # Cylinder default axis is Z; rotate 90deg about X so its axis lies along Y
    # (disk faces the camera). Center it over the opening, its front just in front
    # of the face plane. Then move the object ORIGIN onto the right vertical hinge
    # line (x = +hinge_x) so a pure Z rotation pivots at that edge.
    door_center_x = safe_cx
    door_center_z = cavity_cz
    # The bezel occupies y=[face_y-0.03, face_y+0.03]. Keep the door's rear face
    # another 0.01 toward the camera so its rim never shares/intersects the gray
    # frame volume at the fully closed pose.
    bezel_front_y = face_y - 0.03
    door_frame_clearance = 0.01
    door_center_y = bezel_front_y - door_frame_clearance - door_thick / 2.0
    hinge_x = door_r + 0.02                          # vertical hinge line just right of the door rim

    bpy.ops.mesh.primitive_cylinder_add(
        vertices=48,
        radius=door_r,
        depth=door_thick,
        location=(door_center_x, door_center_y, door_center_z),
        rotation=(math.radians(90.0), 0.0, 0.0),
    )
    door = bpy.context.object
    door.name = "vault_round_door"
    door.data.materials.append(MATS["door"])
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    # Move the object origin onto the vertical hinge line (x = hinge_x) while the
    # geometry keeps its world position: shift mesh verts by -(hinge_x - center_x)
    # in X and set the object location's x to hinge_x. Equivalent: offset verts so
    # that rotating the object about its own +Z axis pivots at the hinge line.
    dx = door_center_x - hinge_x
    mesh = door.data
    for v in mesh.vertices:
        v.co.x += dx
    mesh.update()
    door.location = (hinge_x, door_center_y, door_center_z)
    tag(door, "vault_round_door", "vault_door", "dynamic_object", "cylinder", "steel", True, solid=True)
    door["pb_hinge_at_right_vertical_edge"] = True

    # A small door handle/wheel on the door face for realism (child-follows door
    # via the same rotation applied in animate). Kept as a separate tagged cube
    # offset to the door face; it shares the door's hinge pivot.
    handle = add_cube("vault_door_handle", (door_center_x - door_r * 0.35, door_center_y - door_thick / 2.0 - 0.04, door_center_z),
                      (0.10, 0.08, 0.10), MATS["door_face"], "vault_door_handle", "steel", is_dynamic=True, solid=True)
    # store handle rest offset relative to the hinge line for co-rotation
    handle["pb_rel_x"] = (door_center_x - door_r * 0.35) - hinge_x
    handle["pb_rel_y"] = door_center_y - door_thick / 2.0 - 0.04
    handle["pb_rel_z"] = door_center_z

    # --- Object inside (revealed when the door swings open) ------------------
    ball = add_sphere(
        "colored_ball_inside_safe",
        ball_r,
        (safe_cx, (front_y + back_y) / 2.0 + 0.05, inner_floor_top + ball_r),
        MATS["orange"],
        "orange",
    )
    ball["pb_visible_when_vault_open"] = True
    ball["pb_resting_inside_safe"] = True

    return {
        "scene": scene,
        "kind": "vault_swing_door",
        "door": door,
        "handle": handle,
        "ball": ball,
        "hinge_x": hinge_x,
        "door_center_z": door_center_z,
        "door_center_y": door_center_y,
    }


def animate_vault_swing_door(objs):
    scene = objs["scene"]
    door = objs["door"]
    handle = objs["handle"]
    ball = objs["ball"]
    hinge_x = objs["hinge_x"]
    door_center_y = objs["door_center_y"]
    door_center_z = objs["door_center_z"]

    # The door rotates about its right vertical hinge edge (origin moved there),
    # so a pure world-Z rotation swings it open with no translation and no
    # movement of the static safe body. START-OPEN cycle (object visible first):
    #   Phase 1  f1   - f14  : hold fully OPEN (ball clearly visible inside).
    #   Phase 2  f14  - f44  : door swings CLOSED, hiding the ball.
    #   Phase 3  f44  - f78  : hold fully CLOSED (ball hidden).
    #   Phase 4  f78  - f108 : door swings OPEN again, re-revealing the SAME ball.
    #   Phase 5  f108 - f120 : hold fully OPEN, ball revealed inside.
    #
    # Positive Z rotation swings the door's -X rim toward the camera (-Y) and out
    # to the side, away from the cavity, so the swept door never enters the safe
    # interior where the ball rests.
    closed = math.radians(0.0)
    open_ang = math.radians(105.0)     # swing well clear of the opening
    hold_open_start = 14               # f1..14 open
    close_end = 44                     # swing closed 14..44
    hold_closed_end = 78               # closed 44..78
    open_end2 = 108                    # swing open again 78..108 (then hold open)

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= hold_open_start:
            open01 = 1.0
            door_state = "open_door_swung_clear"
            ball_state = "revealed_resting_inside_safe"
        elif frame <= close_end:
            open01 = 1.0 - smooth01((frame - hold_open_start) / float(close_end - hold_open_start))
            door_state = "swinging_closed_about_vertical_hinge"
            ball_state = "being_hidden_as_door_closes"
        elif frame <= hold_closed_end:
            open01 = 0.0
            door_state = "closed_plugging_opening"
            ball_state = "hidden_inside_closed_safe"
        elif frame <= open_end2:
            open01 = smooth01((frame - hold_closed_end) / float(open_end2 - hold_closed_end))
            door_state = "swinging_open_about_vertical_hinge"
            ball_state = "being_revealed_as_door_opens"
        else:
            open01 = 1.0
            door_state = "open_door_swung_clear"
            ball_state = "revealed_resting_inside_safe"

        theta = lerp(closed, open_ang, open01)

        door.rotation_euler = (0.0, 0.0, theta)
        door.keyframe_insert(data_path="rotation_euler", frame=frame)
        door["pb_state"] = door_state

        # Handle co-rotates with the door about the same hinge line.
        rx = handle["pb_rel_x"]
        ry = handle["pb_rel_y"]
        c = math.cos(theta)
        s = math.sin(theta)
        hx = hinge_x + (rx * c - (ry - door_center_y) * s)
        hy = door_center_y + (rx * s + (ry - door_center_y) * c)
        handle.location = (hx, hy, door_center_z)
        handle.rotation_euler = (0.0, 0.0, theta)
        handle.keyframe_insert(data_path="location", frame=frame)
        handle.keyframe_insert(data_path="rotation_euler", frame=frame)
        handle["pb_state"] = door_state

        # Safe body and ball never move.
        ball.keyframe_insert(data_path="location", frame=frame)
        ball["pb_state"] = ball_state
        ball["pb_must_remain_inside_safe"] = True
        ball["pb_same_object_throughout"] = True

    scene.frame_set(FRAME_START)


# =============================================================================
# dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "vault_swing_door":
        return build_vault_swing_door()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(objs):
    kind = objs["kind"]
    if kind == "vault_swing_door":
        return animate_vault_swing_door(objs)
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

    # Input = closed vault (ball hidden). Event = mid-swing. Final = fully open,
    # ball revealed resting inside the static safe.
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
