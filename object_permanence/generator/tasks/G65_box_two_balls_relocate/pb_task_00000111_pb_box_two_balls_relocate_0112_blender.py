# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_BOX_TWO_BALLS_RELOCATE_0112",
  "scene_kind": "box_two_balls_relocate",
  "prompt": "An open-topped box holds two balls, one red and one green. A lid closes over the box, hiding the balls; the box then slides across the table to a new position and comes to rest. The lid lifts to show both balls still inside the box - both still present, having travelled with the container rather than staying at the original spot."
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


# =============================================================================
# helpers
# =============================================================================

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


def add_cylinder(name, location, radius, depth, rotation=(0, 0, 0), material=None, role="static_solid", color_name="gray", is_dynamic=False, solid=True, vertices=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    if material is not None:
        obj.data.materials.append(material)
    tag(
        obj,
        name,
        role,
        "dynamic_object" if is_dynamic else ("static_solid" if solid else "non_solid_marker"),
        "cylinder",
        color_name,
        is_dynamic,
        solid=solid,
    )
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
    MATS["gray"] = make_mat("mat_gray", (0.46, 0.46, 0.46), roughness=0.62)
    MATS["dark"] = make_mat("mat_dark_gray", (0.20, 0.20, 0.22), roughness=0.74)
    MATS["light"] = make_mat("mat_light_gray", (0.67, 0.68, 0.70), roughness=0.66)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.38, 0.06), roughness=0.30)
    MATS["red"] = make_mat("mat_red", (0.95, 0.03, 0.02), roughness=0.30)
    MATS["green"] = make_mat("mat_green", (0.08, 0.72, 0.14), roughness=0.32)
    MATS["blue"] = make_mat("mat_blue", (0.15, 0.35, 0.90), roughness=0.36)
    MATS["yellow"] = make_mat("mat_yellow", (0.97, 0.85, 0.10), roughness=0.34)
    MATS["black"] = make_mat("mat_black", (0.03, 0.03, 0.035), roughness=0.78)
    MATS["box"] = make_mat("mat_box_tan", (0.62, 0.44, 0.24), roughness=0.58)
    MATS["lid"] = make_mat("mat_lid_brown", (0.48, 0.32, 0.16), roughness=0.54)
    MATS["table"] = make_mat("mat_table_wood", (0.55, 0.40, 0.26), roughness=0.70)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (10.0, 5.0, 0.10), MATS["floor"], role="ground", color_name="warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 2.48, 1.62), (10.2, 0.08, 3.24), MATS["backdrop"], role="background", color_name="off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.6, -4.3, 5.5))
    key = bpy.context.object
    key.name = "large_softbox_light"
    key.data.energy = 960
    key.data.size = 6.2

    bpy.ops.object.light_add(type="POINT", location=(3.6, -3.0, 3.0))
    fill = bpy.context.object
    fill.name = "fill_light"
    fill.data.energy = 145

    return scene


def setup_camera(scene, location, target, lens=31):
    bpy.ops.object.camera_add(location=location)
    cam = bpy.context.object
    cam.name = "camera_main"
    cam.data.lens = lens
    cam.data.dof.use_dof = False
    look_at(cam, target)
    scene.camera = cam
    return cam


# =============================================================================
# scene 0112 box with two balls relocates
# =============================================================================

# table top surface height (z of the table top face the box sits on)
TABLE_TOP_Z = 0.45

# box geometry (open-topped rectangular box = floor slab + 4 low walls)
BOX_INNER_HALF_X = 1.05       # inner half-extent in x (space for two balls side by side)
BOX_INNER_HALF_Y = 0.62       # inner half-extent in y
BOX_WALL_T = 0.10             # wall / floor slab thickness
BOX_WALL_H = 0.62             # wall height above the box floor top face
BOX_FLOOR_T = 0.10            # floor slab thickness

# ball geometry
BALL_RADIUS = 0.26
# lateral offsets of the two balls from the box center (must sit inside the walls)
BALL_DX = 0.52

# lid geometry (a flat slab that covers the whole open top)
LID_T = 0.10
LID_HALF_X = BOX_INNER_HALF_X + BOX_WALL_T   # covers walls too
LID_HALF_Y = BOX_INNER_HALF_Y + BOX_WALL_T

# resting x positions of the box center: start (left) and final (right)
BOX_START_X = -1.9
BOX_END_X = 1.9

# how high the lid hovers when fully open (well clear of the ball tops)
LID_OPEN_LIFT = BALL_RADIUS * 2.0 + 0.55


def _box_part_rel_z(kind):
    """Local z offset of a box part's center above the box base (table top)."""
    if kind == "floor":
        return BOX_FLOOR_T / 2.0
    if kind == "wall":
        return BOX_FLOOR_T + BOX_WALL_H / 2.0
    raise ValueError(kind)


def build_box_two_balls_relocate():
    scene = build_base_scene()
    # front 3/4 view; the box travels across x in [-1.9, 1.9]
    # Keep both balls visible over the front wall even for the lowest randomized
    # orbit viewpoint.
    setup_camera(scene, location=(0.0, -7.8, 5.8), target=(0.0, 0.0, 0.55), lens=38)

    # table the box stands on
    add_cube(
        "relocate_table",
        (0.0, 0.0, TABLE_TOP_Z - 0.09),
        (7.2, 2.8, 0.18),
        MATS["table"],
        role="table_surface",
        color_name="wood_brown",
    )

    x0 = BOX_START_X
    parts = []

    # box floor slab
    floor = add_cube(
        "box_floor",
        (x0, 0.0, TABLE_TOP_Z + _box_part_rel_z("floor")),
        (2.0 * (BOX_INNER_HALF_X + BOX_WALL_T), 2.0 * (BOX_INNER_HALF_Y + BOX_WALL_T), BOX_FLOOR_T),
        MATS["box"],
        role="container_floor",
        color_name="tan",
        is_dynamic=True,
    )
    floor["pb_rel_x"] = 0.0
    floor["pb_rel_z"] = _box_part_rel_z("floor")
    parts.append(floor)

    wall_z = TABLE_TOP_Z + _box_part_rel_z("wall")

    # +x wall (far right side of box)
    wpx = add_cube(
        "box_wall_px",
        (x0 + BOX_INNER_HALF_X + BOX_WALL_T / 2.0, 0.0, wall_z),
        (BOX_WALL_T, 2.0 * (BOX_INNER_HALF_Y + BOX_WALL_T), BOX_WALL_H),
        MATS["box"],
        role="container_wall",
        color_name="tan",
        is_dynamic=True,
    )
    wpx["pb_rel_x"] = BOX_INNER_HALF_X + BOX_WALL_T / 2.0
    wpx["pb_rel_z"] = _box_part_rel_z("wall")
    parts.append(wpx)

    # -x wall
    wnx = add_cube(
        "box_wall_nx",
        (x0 - (BOX_INNER_HALF_X + BOX_WALL_T / 2.0), 0.0, wall_z),
        (BOX_WALL_T, 2.0 * (BOX_INNER_HALF_Y + BOX_WALL_T), BOX_WALL_H),
        MATS["box"],
        role="container_wall",
        color_name="tan",
        is_dynamic=True,
    )
    wnx["pb_rel_x"] = -(BOX_INNER_HALF_X + BOX_WALL_T / 2.0)
    wnx["pb_rel_z"] = _box_part_rel_z("wall")
    parts.append(wnx)

    # +y wall (back)
    wpy = add_cube(
        "box_wall_py",
        (x0, BOX_INNER_HALF_Y + BOX_WALL_T / 2.0, wall_z),
        (2.0 * BOX_INNER_HALF_X, BOX_WALL_T, BOX_WALL_H),
        MATS["box"],
        role="container_wall",
        color_name="tan",
        is_dynamic=True,
    )
    wpy["pb_rel_x"] = 0.0
    wpy["pb_rel_z"] = _box_part_rel_z("wall")
    parts.append(wpy)

    # -y wall (front, camera-facing) -- kept low enough (same height) so balls
    # are clearly visible over it from the 3/4 camera before the lid closes
    wny = add_cube(
        "box_wall_ny",
        (x0, -(BOX_INNER_HALF_Y + BOX_WALL_T / 2.0), wall_z),
        (2.0 * BOX_INNER_HALF_X, BOX_WALL_T, BOX_WALL_H),
        MATS["box"],
        role="container_wall",
        color_name="tan",
        is_dynamic=True,
    )
    wny["pb_rel_x"] = 0.0
    wny["pb_rel_z"] = _box_part_rel_z("wall")
    parts.append(wny)

    box = {"parts": parts, "base_x": x0}

    # the lid: flat slab covering the open top. Its resting (closed) z sits just
    # on top of the walls. It starts OPEN (lifted) so the balls are visible.
    lid_closed_z = TABLE_TOP_Z + BOX_FLOOR_T + BOX_WALL_H + LID_T / 2.0
    lid = add_cube(
        "box_lid",
        (x0, 0.0, lid_closed_z + LID_OPEN_LIFT),
        (2.0 * LID_HALF_X, 2.0 * LID_HALF_Y, LID_T),
        MATS["lid"],
        role="container_lid",
        color_name="brown",
        is_dynamic=True,
    )
    lid["pb_rel_x"] = 0.0
    lid["pb_closed_z"] = lid_closed_z

    # two balls resting on the box floor top face, side by side in x
    ball_z = TABLE_TOP_Z + BOX_FLOOR_T + BALL_RADIUS
    ball_red = add_sphere(
        "ball_red",
        BALL_RADIUS,
        (x0 - BALL_DX, 0.0, ball_z),
        MATS["red"],
        "red",
    )
    ball_red["pb_rel_x"] = -BALL_DX
    ball_red["pb_inside_container"] = True

    ball_green = add_sphere(
        "ball_green",
        BALL_RADIUS,
        (x0 + BALL_DX, 0.0, ball_z),
        MATS["green"],
        "green",
    )
    ball_green["pb_rel_x"] = BALL_DX
    ball_green["pb_inside_container"] = True

    return {
        "scene": scene,
        "kind": "box_two_balls_relocate",
        "box": box,
        "lid": lid,
        "balls": [ball_red, ball_green],
    }


def _place_box(box, x, frame):
    """Place all box parts (floor + 4 walls) at world center x on the table."""
    for p in box["parts"]:
        p.location = (x + p["pb_rel_x"], p.location.y, p.location.z)
        p.keyframe_insert(data_path="location", frame=frame)


def animate_box_two_balls_relocate(objs, frame):
    box = objs["box"]
    lid = objs["lid"]
    balls = objs["balls"]

    lid_closed_z = lid["pb_closed_z"]
    ball_z = TABLE_TOP_Z + BOX_FLOOR_T + BALL_RADIUS

    # ---- phase windows ----
    # f1-12    : both balls visible, lid held OPEN (lifted above the box)
    # f16-34   : lid lowers to close the box (hides the balls)
    # f40-92   : the whole box (+ lid + both balls) slides in x to the new spot
    # f98-116  : lid lifts to reveal both balls still inside at the new location

    box_x = box["base_x"]     # current box world center x (default = resting)
    lid_lift = 0.0            # current lid lift above its closed z

    if frame <= 12:
        # opening state: lid fully open, box at start
        box_x = BOX_START_X
        lid_lift = LID_OPEN_LIFT

    elif frame <= 34:
        # lid lowers to close (box stays at start)
        box_x = BOX_START_X
        t = (frame - 16) / 18.0
        lid_lift = LID_OPEN_LIFT * (1.0 - smooth01(t))

    elif frame < 40:
        box_x = BOX_START_X
        lid_lift = 0.0

    elif frame <= 92:
        # slide the whole closed box across the table to the new position
        t = (frame - 40) / 52.0
        box_x = lerp(BOX_START_X, BOX_END_X, smooth01(t))
        lid_lift = 0.0
        if frame >= 92:
            box["base_x"] = BOX_END_X

    elif frame < 98:
        box_x = BOX_END_X
        box["base_x"] = BOX_END_X
        lid_lift = 0.0

    else:
        # final reveal: box at rest at the new spot, lid lifts open
        box_x = BOX_END_X
        box["base_x"] = BOX_END_X
        t = (frame - 98) / 18.0
        lid_lift = LID_OPEN_LIFT * smooth01(t)

    # place the box body (floor + walls)
    _place_box(box, box_x, frame)

    # place the lid: rides with the box in x, sits at closed_z + current lift
    lid.location = (box_x + lid["pb_rel_x"], lid.location.y, lid_closed_z + lid_lift)
    lid.keyframe_insert(data_path="location", frame=frame)

    # balls: ALWAYS pinned to the box's LIVE world center x (offset constant),
    # so they travel exactly with the container and never clip the walls or stay
    # behind at the original spot. Read box_x directly (the live position for THIS
    # frame), not a stale base_x that only updates at the end of the slide.
    for b in balls:
        b.location = (box_x + b["pb_rel_x"], 0.0, ball_z)
        b.keyframe_insert(data_path="location", frame=frame)

    # bookkeeping / state tags
    if frame <= 12:
        state = "visible_in_open_box_at_start"
    elif frame <= 34:
        state = "being_covered_by_lid"
    elif frame <= 92:
        state = "hidden_traveling_with_the_box"
    elif frame < 98:
        state = "hidden_box_at_rest_new_position"
    else:
        state = "revealed_still_inside_box_at_new_position"

    for b in balls:
        b["pb_state"] = state
        b["pb_moves_with_container"] = True
        b["pb_no_teleport_back_to_origin"] = True
    lid["pb_state"] = state


# =============================================================================
# dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "box_two_balls_relocate":
        return build_box_two_balls_relocate()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "box_two_balls_relocate":
            animate_box_two_balls_relocate(objs, frame)
        else:
            raise RuntimeError("Unknown kind: " + str(kind))
    scene.frame_set(FRAME_START)


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
