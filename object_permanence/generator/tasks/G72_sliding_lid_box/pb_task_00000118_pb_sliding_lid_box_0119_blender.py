# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_SLIDING_LID_BOX_0119",
  "scene_kind": "sliding_lid_box",
  "prompt": "A closed box sits on a table. Its flat top lid slides off horizontally to one side, sliding clear of the box to reveal a ball resting inside. The box body stays in place; only the lid translates."
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
    MATS["lid"] = make_mat("mat_opaque_lid", (0.40, 0.41, 0.43), roughness=0.70)


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
# 0119 sliding lid box
#
# A closed gray box sits on the table. Its flat top lid does NOT rotate; it
# SLIDES horizontally in +X (to one side), like a matchbox cover / sliding
# tray lid, until it fully clears the box opening and reveals a colored ball
# resting inside on the box floor. The box body and the ball never move; only
# the lid translates.
#
# Slide construction: the lid is a thin flat slab that starts resting flush on
# top of the four walls, fully covering the opening. Animating its X location
# moves it sideways along a horizontal track. It is lifted a hair above the
# wall tops so it clears the wall rims cleanly with no clipping as it slides.
# =============================================================================

def build_sliding_lid_box():
    scene = build_base_scene()

    # Slightly elevated 3/4 view so the top opening reveal is legible: the
    # camera looks down INTO the cavity once the lid has slid clear, and the
    # closed lid clearly hides the ball at the start.
    setup_camera(
        scene,
        location=(1.05, -3.55, 3.35),
        target=(0.0, 0.05, 0.45),
        lens=40,
    )

    base_z = 0.10

    # Inner cavity spans roughly x in [-0.60, 0.60], y in [-0.60, 0.60].
    # Walls are 0.10 thick, 0.72 tall.
    wall_h = 0.72
    wall_t = 0.10
    inner_half = 0.60          # inner half-width / half-depth
    outer_half = inner_half + wall_t / 2.0  # 0.65 -> wall centerline
    wall_cz = base_z + 0.05 + wall_h / 2.0

    floor_top_z = base_z + 0.10  # top surface of the box inner floor

    # Box inner floor (a solid slab the object rests on)
    add_cube("box_inner_floor", (0.0, 0.0, base_z + 0.05),
             (2.0 * outer_half + wall_t, 2.0 * outer_half + wall_t, 0.10),
             MATS["gray"], "box_floor", "gray")

    add_cube("box_left_wall", (-outer_half, 0.0, wall_cz),
             (wall_t, 2.0 * outer_half + wall_t, wall_h), MATS["gray"], "box_wall", "gray")
    add_cube("box_right_wall", (outer_half, 0.0, wall_cz),
             (wall_t, 2.0 * outer_half + wall_t, wall_h), MATS["gray"], "box_wall", "gray")
    add_cube("box_front_wall", (0.0, -outer_half, wall_cz),
             (2.0 * outer_half + wall_t, wall_t, wall_h), MATS["gray"], "box_wall", "gray")
    add_cube("box_back_wall", (0.0, outer_half, wall_cz),
             (2.0 * outer_half + wall_t, wall_t, wall_h), MATS["gray"], "box_wall", "gray")

    # --- Sliding lid --------------------------------------------------------
    # The lid slab covers the full box top. It is a plain thin cube (origin at
    # its own center) so a pure X translation slides it sideways along a
    # horizontal track. It is seated a small gap ABOVE the wall tops so its
    # underside clears the wall rims cleanly as it slides -> no clipping.
    lid_top_z = base_z + 0.05 + wall_h            # top of the walls
    lid_thick = 0.08
    lid_span_x = 2.0 * outer_half + wall_t        # full top width incl. walls
    lid_depth = 2.0 * outer_half + wall_t         # full top depth incl. walls

    slide_gap = 0.02                              # clearance above wall rims
    lid_cz = lid_top_z + slide_gap + lid_thick / 2.0  # resting center height

    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.0, 0.0, lid_cz))
    lid = bpy.context.object
    lid.name = "sliding_top_lid"
    lid.dimensions = (lid_span_x, lid_depth, lid_thick)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    lid.data.materials.append(MATS["lid"])
    tag(lid, "sliding_top_lid", "sliding_lid", "dynamic_object", "cube", "dark_gray", True, solid=True)
    lid["pb_slides_horizontally"] = True

    # Closed X = 0 (lid centered, fully covering opening).
    # Fully-clear X: the lid must move far enough in +X that its trailing (-X)
    # edge passes the box's +X outer edge, so the opening is completely
    # uncovered. lid half-span = lid_span_x/2; box +X outer edge = outer_half +
    # wall_t/2. Add a small margin so the reveal reads as fully clear.
    lid_closed_x = 0.0
    lid_open_x = (lid_span_x / 2.0) + (outer_half + wall_t / 2.0) + 0.15

    # --- Object inside (clearly visible once the lid slides clear) -----------
    # A single clearly-colored ball, sized so it plainly fills the cavity and is
    # obvious to the viewer once revealed. It rests on the inner floor and never
    # moves. This is the ONE persistent object the reveal is about.
    ball_r = 0.28
    ball = add_sphere(
        "colored_ball_inside_box",
        ball_r,
        (0.0, 0.0, floor_top_z + ball_r),
        MATS["orange"],
        "orange",
    )
    ball["pb_visible_when_lid_open"] = True
    ball["pb_resting_inside_box"] = True

    return {
        "scene": scene,
        "kind": "sliding_lid_box",
        "lid": lid,
        "ball": ball,
        "base_z": base_z,
        "ball_r": ball_r,
        "floor_top_z": floor_top_z,
        "lid_cz": lid_cz,
        "lid_closed_x": lid_closed_x,
        "lid_open_x": lid_open_x,
    }


def animate_sliding_lid_box(objs):
    scene = objs["scene"]
    lid = objs["lid"]
    ball = objs["ball"]
    floor_top_z = objs["floor_top_z"]
    ball_r = objs["ball_r"]
    lid_cz = objs["lid_cz"]
    lid_closed_x = objs["lid_closed_x"]
    lid_open_x = objs["lid_open_x"]

    # The lid slides purely along the X axis at a constant height (lid_cz),
    # clearing the wall rims, and comes to rest fully off to one side so the
    # ball inside is revealed. The box body and the ball never move.
    #
    # Full OBJECT-PERMANENCE cycle that STARTS OPEN: object shown first, then
    # hidden as the lid slides ON, then revealed again as the lid slides OFF.
    #   Phase 1  f1  - f16   : OPEN, lid fully clear, ball visible (hold).
    #   Phase 2  f16 - f46   : lid SLIDES ON (toward closed), hiding the ball.
    #   Phase 3  f46 - f66   : hold CLOSED (ball hidden).
    #   Phase 4  f66 - f96   : lid SLIDES OFF again, revealing the SAME ball.
    #   Phase 5  f96 - f120  : hold OPEN, ball revealed unchanged.
    open_hold_end = 16
    close_end = 46
    closed_hold_end = 66
    reopen_end = 96

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= open_hold_end:
            lid_x = lid_open_x
            lid_state = "open_lid_clear_ball_visible"
            ball_state = "visible_inside_open_box"
        elif frame <= close_end:
            t = smooth01((frame - open_hold_end) / float(close_end - open_hold_end))
            lid_x = lerp(lid_open_x, lid_closed_x, t)
            lid_state = "lid_sliding_on_hiding_ball"
            ball_state = "being_hidden_as_lid_slides_on"
        elif frame <= closed_hold_end:
            lid_x = lid_closed_x
            lid_state = "closed_lid_covering_box_ball_hidden"
            ball_state = "hidden_inside_closed_box"
        elif frame <= reopen_end:
            t = smooth01((frame - closed_hold_end) / float(reopen_end - closed_hold_end))
            lid_x = lerp(lid_closed_x, lid_open_x, t)
            lid_state = "lid_sliding_off_revealing_ball"
            ball_state = "being_revealed_as_lid_slides_clear"
        else:
            lid_x = lid_open_x
            lid_state = "lid_slid_fully_clear_same_ball_revealed"
            ball_state = "revealed_resting_inside_open_box"

        # Pure horizontal X translation at constant height -> no clipping.
        lid.location = (lid_x, 0.0, lid_cz)
        lid.keyframe_insert(data_path="location", frame=frame)
        lid["pb_state"] = lid_state

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
    if kind == "sliding_lid_box":
        return build_sliding_lid_box()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(objs):
    kind = objs["kind"]
    if kind == "sliding_lid_box":
        return animate_sliding_lid_box(objs)
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

    # Input = closed box (ball hidden). Event = lid mid-slide (partial reveal).
    # Final = lid fully clear, ball revealed resting inside.
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
