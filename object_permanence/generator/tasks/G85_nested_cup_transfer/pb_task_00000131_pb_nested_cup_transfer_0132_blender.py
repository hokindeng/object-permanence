# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_NESTED_CUP_TRANSFER_0132",
  "scene_kind": "nested_cup_transfer",
  "prompt": "A ball is shown, then a small opaque cup lowers over it. A larger opaque cup is then placed over the small cup (nesting them). The nested cups slide together to a new spot on the table and stop. The outer cup lifts, then the inner cup lifts, revealing the ball still inside - it travelled with the nested containers, not back to its original position."
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
    MATS["blue"] = make_mat("mat_blue", (0.15, 0.35, 0.90), roughness=0.36)
    MATS["yellow"] = make_mat("mat_yellow", (0.97, 0.85, 0.10), roughness=0.34)
    MATS["black"] = make_mat("mat_black", (0.03, 0.03, 0.035), roughness=0.78)
    MATS["cup"] = make_mat("mat_cup_red", (0.78, 0.10, 0.09), roughness=0.42)
    MATS["cup_outer"] = make_mat("mat_cup_blue", (0.13, 0.30, 0.82), roughness=0.42)
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
# scene 0132 nested cup transfer
# =============================================================================

# table top surface height (z of the table top face the cups sit on)
TABLE_TOP_Z = 0.45

# inner (small) opaque cup = wall cylinder + solid cap disk on top
INNER_RADIUS = 0.40
INNER_WALL_HEIGHT = 0.78
INNER_CAP = 0.07

# outer (larger) opaque cup = wall cylinder + solid cap disk on top.
# radius clearly bigger than the inner cup (no wall overlap / interpenetration),
# and tall enough that when it sits on the table it fully covers the inner cup
# with vertical clearance above the inner cap.
OUTER_RADIUS = 0.68
OUTER_WALL_HEIGHT = 1.02
OUTER_CAP = 0.07

# ball geometry (fits inside the inner cup with clearance)
BALL_RADIUS = 0.16

# start x-position where the ball is shown and the cups are first placed
START_X = -1.55
# destination x-position the nested pair slides to and stops
END_X = 1.55

# vertical lift heights used to raise a cup fully clear of what is under it
# (lift measured above the cup's resting position on the table).
INNER_LIFT = INNER_WALL_HEIGHT + INNER_CAP + 0.55
OUTER_LIFT = OUTER_WALL_HEIGHT + OUTER_CAP + 0.55


def _make_cup(prefix, radius, wall_height, cap_thick, x, material, color_name):
    """Build one upside-down opaque cup as a wall cylinder + a top cap disk.

    The cup's local base is the table top (z = TABLE_TOP_Z) at world x.
    Each part stores pb_rel_z (its z offset above the resting base).
    """
    parts = []

    wall = add_cylinder(
        f"{prefix}_wall",
        (x, 0.0, TABLE_TOP_Z + wall_height / 2.0),
        radius,
        wall_height,
        material=material,
        role="opaque_cup_wall",
        color_name=color_name,
        is_dynamic=True,
        solid=True,
        vertices=48,
    )
    wall["pb_rel_z"] = wall_height / 2.0
    parts.append(wall)

    cap = add_cylinder(
        f"{prefix}_cap",
        (x, 0.0, TABLE_TOP_Z + wall_height + cap_thick / 2.0),
        radius,
        cap_thick,
        material=material,
        role="opaque_cup_cap",
        color_name=color_name,
        is_dynamic=True,
        solid=True,
        vertices=48,
    )
    cap["pb_rel_z"] = wall_height + cap_thick / 2.0
    parts.append(cap)

    for p in parts:
        p["pb_base_x"] = x
        p["pb_is_cup_part"] = True

    return {"parts": parts, "base_x": x, "radius": radius}


def build_nested_cup_transfer():
    scene = build_base_scene()
    # front 3/4 view, slightly higher than G56 to read the nesting/lift clearly;
    # action spans x in [-1.55, 1.55]; camera off to the left-front.
    setup_camera(scene, location=(-3.4, -7.6, 3.55), target=(0.0, 0.0, 0.70), lens=34)

    # table the cups stand on (well within camera frame, no edge overhang)
    add_cube(
        "nested_cup_table",
        (0.0, 0.0, TABLE_TOP_Z - 0.09),
        (6.2, 2.6, 0.18),
        MATS["table"],
        role="table_surface",
        color_name="wood_brown",
    )

    # inner (small, red) cup and outer (larger, blue) cup, both start at START_X.
    inner_cup = _make_cup("inner_cup", INNER_RADIUS, INNER_WALL_HEIGHT, INNER_CAP, START_X, MATS["cup"], "red")
    outer_cup = _make_cup("outer_cup", OUTER_RADIUS, OUTER_WALL_HEIGHT, OUTER_CAP, START_X, MATS["cup_outer"], "blue")

    for p in inner_cup["parts"]:
        p["pb_cup_role"] = "inner"
    for p in outer_cup["parts"]:
        p["pb_cup_role"] = "outer"

    # the ball is shown on the table at START_X before any cup lowers over it
    ball = add_sphere(
        "hidden_ball",
        BALL_RADIUS,
        (START_X, 0.0, TABLE_TOP_Z + BALL_RADIUS),
        MATS["yellow"],
        "yellow",
    )
    ball["pb_inside_cup"] = True

    return {
        "scene": scene,
        "kind": "nested_cup_transfer",
        "inner_cup": inner_cup,
        "outer_cup": outer_cup,
        "ball": ball,
    }


def _place_cup(cup, x, lift, frame):
    """Place a whole cup (wall + cap) at world x with vertical lift above table."""
    for p in cup["parts"]:
        z = TABLE_TOP_Z + p["pb_rel_z"] + lift
        p.location = (x, 0.0, z)
        p.keyframe_insert(data_path="location", frame=frame)


def animate_nested_cup_transfer(objs, frame):
    inner_cup = objs["inner_cup"]
    outer_cup = objs["outer_cup"]
    ball = objs["ball"]

    # ---- phase windows ----
    # f1-10   : ball shown; both cups held high, clear of the ball
    # f11-26  : inner (small) cup lowers over the ball, hiding it
    # f30-46  : outer (larger) cup lowers over the inner cup, nesting them
    # f52-92  : nested pair slides together from START_X to END_X, then stops
    # f98-108 : outer cup lifts off
    # f112-120: inner cup lifts off, revealing the ball still inside

    # defaults: both cups raised high, resting positions computed per phase
    inner_x = inner_cup["base_x"]
    outer_x = outer_cup["base_x"]
    inner_lift = INNER_LIFT
    outer_lift = OUTER_LIFT
    slide_x = START_X

    if frame <= 10:
        # ball shown; both cups held clear above the table (inner low-ish, outer higher)
        inner_lift = INNER_LIFT
        outer_lift = OUTER_LIFT

    elif frame <= 26:
        # inner cup lowers over the ball
        t = (frame - 10) / 16.0
        inner_lift = INNER_LIFT * (1.0 - smooth01(t))
        outer_lift = OUTER_LIFT
        inner_cup["parts"][0]["pb_state"] = "lowering_over_ball"

    elif frame < 30:
        inner_lift = 0.0
        outer_lift = OUTER_LIFT

    elif frame <= 46:
        # outer cup lowers over the (grounded) inner cup, nesting them concentrically
        t = (frame - 30) / 16.0
        inner_lift = 0.0
        outer_lift = OUTER_LIFT * (1.0 - smooth01(t))
        outer_cup["parts"][0]["pb_state"] = "lowering_over_inner_cup"

    elif frame < 52:
        inner_lift = 0.0
        outer_lift = 0.0

    elif frame <= 92:
        # nested pair slides together in x to the new spot, both grounded
        t = (frame - 52) / 40.0
        slide_x = lerp(START_X, END_X, smooth01(t))
        inner_x = slide_x
        outer_x = slide_x
        inner_lift = 0.0
        outer_lift = 0.0
        outer_cup["parts"][0]["pb_state"] = "sliding_nested_to_new_spot"
        # bookkeeping: commit new resting x at end of the slide
        if t >= 1.0:
            for p in inner_cup["parts"]:
                p["pb_base_x"] = END_X
            for p in outer_cup["parts"]:
                p["pb_base_x"] = END_X
            inner_cup["base_x"] = END_X
            outer_cup["base_x"] = END_X

    elif frame < 98:
        inner_x = END_X
        outer_x = END_X
        inner_lift = 0.0
        outer_lift = 0.0

    elif frame <= 108:
        # outer cup lifts off (inner cup + ball remain grounded at END_X)
        t = (frame - 98) / 10.0
        inner_x = END_X
        outer_x = END_X
        inner_lift = 0.0
        outer_lift = OUTER_LIFT * smooth01(t)
        outer_cup["parts"][0]["pb_state"] = "lifting_off_inner_cup"

    elif frame < 112:
        inner_x = END_X
        outer_x = END_X
        inner_lift = 0.0
        outer_lift = OUTER_LIFT

    else:
        # inner cup lifts off, revealing the ball still inside at END_X
        t = (frame - 112) / 8.0
        inner_x = END_X
        outer_x = END_X
        inner_lift = INNER_LIFT * smooth01(t)
        outer_lift = OUTER_LIFT
        inner_cup["parts"][0]["pb_state"] = "lifting_to_reveal_ball"

    _place_cup(inner_cup, inner_x, inner_lift, frame)
    _place_cup(outer_cup, outer_x, outer_lift, frame)

    # ball: shown at START_X until the inner cup has hidden it (f<=26 window end),
    # then pinned every frame to the inner cup's LIVE world x so it rides exactly
    # with its container and never teleports back to START_X. Reading the actual
    # current wall x (not base_x) keeps the ball glued to the cup while the nested
    # pair slides through, avoiding any stale-coordinate clipping.
    if frame <= 26:
        bx = START_X
    else:
        bx = inner_cup["parts"][0].location.x
    ball.location = (bx, 0.0, TABLE_TOP_Z + BALL_RADIUS)
    ball.keyframe_insert(data_path="location", frame=frame)

    if frame <= 10:
        ball["pb_state"] = "visible_before_cups_lower"
    elif frame <= 112:
        ball["pb_state"] = "hidden_moving_with_nested_cups"
    else:
        ball["pb_state"] = "revealed_at_new_spot_moved_with_containers"
    ball["pb_moves_with_container"] = True
    ball["pb_no_teleport_back_to_origin"] = True


# =============================================================================
# dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "nested_cup_transfer":
        return build_nested_cup_transfer()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "nested_cup_transfer":
            animate_nested_cup_transfer(objs, frame)
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
