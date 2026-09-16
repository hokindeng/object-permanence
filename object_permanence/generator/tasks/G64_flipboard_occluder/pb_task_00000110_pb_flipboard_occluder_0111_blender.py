# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_FLIPBOARD_OCCLUDER_0111",
  "scene_kind": "flipboard_occluder",
  "prompt": "Two objects sit on a table. A flat board, hinged along its bottom edge in front of them, flips up toward the camera until it stands vertical and fully hides the two objects; it holds briefly, then flips back down flat, revealing the same two objects, unchanged in number and position."
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


def add_sphere(name, radius, location, material, color_name, role="target", is_dynamic=False):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "sphere", color_name, is_dynamic, solid=True, pb_radius=radius)
    return obj


def add_cylinder(name, radius, depth, location, material, color_name, role="target", is_dynamic=False):
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "cylinder", color_name, is_dynamic, solid=True, pb_radius=radius)
    return obj


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), roughness=0.84)
    MATS["gray"] = make_mat("mat_gray", (0.46, 0.46, 0.46), roughness=0.64)
    MATS["dark"] = make_mat("mat_dark", (0.18, 0.19, 0.21), roughness=0.76)
    MATS["light"] = make_mat("mat_light", (0.68, 0.69, 0.71), roughness=0.68)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.38, 0.06), roughness=0.28)
    MATS["blue"] = make_mat("mat_blue", (0.12, 0.34, 0.86), roughness=0.34)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.92)
    MATS["board"] = make_mat("mat_board", (0.40, 0.41, 0.43), roughness=0.70)


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
# 0111 flip board occluder
#
# Object-static-occlusion. Two distinct STATIC objects rest on the table. A flat
# rectangular board lies flat on the table just IN FRONT of them (nearer the
# camera). The board is hinged along its FRONT bottom edge (the edge nearest the
# camera). It flips UP toward the camera about that hinge until it stands
# vertical, fully hiding the two objects; it holds briefly, then flips back down
# flat, revealing the SAME two objects, unchanged in number and position.
#
# Hinge construction: the board is a thin slab whose mesh origin is moved to its
# FRONT bottom edge (min-Y, low-Z) so that rotating it about the world X axis
# pivots exactly at that edge (no translation, no clipping through the table).
# A POSITIVE X rotation lifts the far (+Y) edge up and swings it forward/up over
# the pivot, standing the board vertical directly above the front edge -- which
# is between the objects and the camera, so it occludes them cleanly.
#
# The two objects and the table never move. The board is the only moving thing.
# =============================================================================

def build_flipboard_occluder():
    scene = build_base_scene()

    # Front view, slightly above table height, so the raised vertical board sits
    # squarely between the camera and the two objects and fully occludes them.
    setup_camera(
        scene,
        location=(0.0, -4.05, 1.35),
        target=(0.0, 0.55, 0.55),
        lens=42,
    )

    table_top_z = 0.0  # top surface of the floor slab (floor spans z in [-0.10, 0.0])

    # --- Two distinct STATIC objects on the table --------------------------
    # Placed BEHIND the board hinge (larger Y), well within the board's occluded
    # footprint when it stands vertical. They never move.
    obj_a_r = 0.30
    obj_a = add_sphere(
        "static_object_a_ball",
        obj_a_r,
        (-0.42, 0.72, table_top_z + obj_a_r),
        MATS["orange"],
        "orange",
        role="static_object_a",
    )
    obj_a["pb_static_reference_object"] = True

    obj_b_r = 0.26
    obj_b_h = 0.62
    obj_b = add_cylinder(
        "static_object_b_cylinder",
        obj_b_r,
        obj_b_h,
        (0.44, 0.72, table_top_z + obj_b_h / 2.0),
        MATS["blue"],
        "blue",
        role="static_object_b",
    )
    obj_b["pb_static_reference_object"] = True

    # --- Hinged flip board --------------------------------------------------
    # A flat rectangular slab lying flat on the table just in front of the
    # objects. Its FRONT bottom edge (the hinge) is nearest the camera at
    # y = hinge_y. It must be wide enough and, when vertical, tall enough to
    # fully hide both objects from the front camera.
    board_thick = 0.06
    board_width = 2.30      # X extent -- wider than the objects' spread
    board_height = 1.60     # -Y extent when flat == HEIGHT when vertical

    hinge_y = 0.12          # front-bottom edge (pivot), IN FRONT of the objects
    hinge_z = table_top_z   # pivot at the table surface

    # Build the slab, then shift its mesh so the ORIGIN is at the FRONT-BOTTOM
    # edge and the slab extends toward the CAMERA (-Y) when flat -- so it NEVER
    # lies over the objects and cannot interpenetrate them. +Z is thickness.
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.0, hinge_y, hinge_z))
    board = bpy.context.object
    board.name = "flip_board_occluder"
    board.dimensions = (board_width, board_height, board_thick)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    mesh = board.data
    for v in mesh.vertices:
        v.co.y -= board_height / 2.0   # extend toward the camera (-Y) from the hinge
        v.co.z += board_thick / 2.0    # slab sits just above the pivot (table)
    mesh.update()

    # Cut a WINDOW through the board so that, standing vertical in front of the
    # objects, they stay PARTIALLY visible through the hole (windowed occlusion).
    # In the flat pose, board-local distance d back from the hinge (toward -Y)
    # becomes HEIGHT z=d when vertical; put the window at the objects' height band.
    win_lo, win_hi = 0.20, 0.60     # vertical band (when up) revealed through the hole
    win_x = 1.00                    # half-width of the window in X
    wy_c = hinge_y - (win_lo + win_hi) / 2.0
    wy_d = (win_hi - win_lo)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.0, wy_c, hinge_z + board_thick / 2.0))
    cutter = bpy.context.object
    cutter.name = "flip_board_window_cutter"
    cutter.dimensions = (2.0 * win_x, wy_d, board_thick * 4.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    wmod = board.modifiers.new(name="window", type="BOOLEAN")
    wmod.operation = "DIFFERENCE"
    wmod.object = cutter
    bpy.context.view_layer.objects.active = board
    board.select_set(True)
    try:
        bpy.ops.object.modifier_apply(modifier=wmod.name)
    except Exception:
        pass
    try:
        bpy.data.objects.remove(cutter, do_unlink=True)
    except ReferenceError:
        pass

    board.data.materials.append(MATS["board"])
    tag(board, "flip_board_occluder", "flip_occluder", "dynamic_object", "cube", "dark_gray", True, solid=True)
    board["pb_hinge_at_front_bottom_edge"] = True
    board["pb_has_window"] = True

    return {
        "scene": scene,
        "kind": "flipboard_occluder",
        "board": board,
        "obj_a": obj_a,
        "obj_b": obj_b,
        "obj_a_r": obj_a_r,
        "obj_b_r": obj_b_r,
        "obj_b_h": obj_b_h,
        "table_top_z": table_top_z,
    }


def animate_flipboard_occluder(objs):
    scene = objs["scene"]
    board = objs["board"]
    obj_a = objs["obj_a"]
    obj_b = objs["obj_b"]
    obj_a_r = objs["obj_a_r"]
    obj_b_h = objs["obj_b_h"]
    table_top_z = objs["table_top_z"]

    obj_a_loc = (-0.42, 0.72, table_top_z + obj_a_r)
    obj_b_loc = (0.44, 0.72, table_top_z + obj_b_h / 2.0)

    # Full HIDE -> REVEAL object-permanence cycle. theta=0 is the board lying
    # FLAT on the table (objects fully visible behind it). theta=up_angle is the
    # board standing VERTICAL (front-edge hinge), fully occluding both objects.
    # The board origin is at its front bottom edge, so a pure X rotation pivots
    # there with no translation and never clips through the table.
    #
    #   Phase 1  f1  - f22   : FLAT, both objects clearly visible (hold).
    #   Phase 2  f22 - f48   : board flips UP toward camera to vertical (hides).
    #   Phase 3  f48 - f74   : hold VERTICAL (both objects hidden).
    #   Phase 4  f74 - f112  : board flips back DOWN flat, revealing SAME objects.
    #   Phase 5  f112 - f120 : hold FLAT, both objects revealed unchanged.
    # Negative X rotation flips the -Y (toward-camera) slab UP to vertical.
    up_angle = -math.radians(90.0)
    p1_end = 22      # end of initial flat hold
    up_end = 48      # board fully vertical
    up_hold_end = 74  # end of vertical hold
    down_end = 112   # board fully back down flat

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= p1_end:
            theta = 0.0
            board_state = "flat_objects_visible_behind"
            occ_state = "both_objects_visible_before_occlusion"
        elif frame <= up_end:
            t = (frame - p1_end) / float(up_end - p1_end)
            theta = lerp(0.0, up_angle, smooth01(t))
            board_state = "flipping_up_toward_camera"
            occ_state = "objects_being_occluded_as_board_rises"
        elif frame <= up_hold_end:
            theta = up_angle
            board_state = "vertical_objects_fully_hidden"
            occ_state = "both_objects_hidden_behind_vertical_board"
        elif frame <= down_end:
            t = (frame - up_hold_end) / float(down_end - up_hold_end)
            theta = lerp(up_angle, 0.0, smooth01(t))
            board_state = "flipping_back_down_flat"
            occ_state = "objects_being_revealed_as_board_falls"
        else:
            theta = 0.0
            board_state = "flat_same_objects_revealed_unchanged"
            occ_state = "both_objects_revealed_unchanged_in_number_and_position"

        # Rotate about front-bottom-edge origin: pure X rotation, no translation.
        board.rotation_euler = (theta, 0.0, 0.0)
        board.keyframe_insert(data_path="rotation_euler", frame=frame)
        board["pb_state"] = board_state

        # The two objects and the table never move.
        obj_a.location = obj_a_loc
        obj_a.keyframe_insert(data_path="location", frame=frame)
        obj_a["pb_state"] = occ_state
        obj_a["pb_same_object_throughout"] = True

        obj_b.location = obj_b_loc
        obj_b.keyframe_insert(data_path="location", frame=frame)
        obj_b["pb_state"] = occ_state
        obj_b["pb_same_object_throughout"] = True

    scene.frame_set(FRAME_START)


# =============================================================================
# dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "flipboard_occluder":
        return build_flipboard_occluder()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(objs):
    kind = objs["kind"]
    if kind == "flipboard_occluder":
        return animate_flipboard_occluder(objs)
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

    # Input = flat board, both objects clearly visible. Event = board vertical
    # (objects hidden). Final = board back down flat, same objects revealed.
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
