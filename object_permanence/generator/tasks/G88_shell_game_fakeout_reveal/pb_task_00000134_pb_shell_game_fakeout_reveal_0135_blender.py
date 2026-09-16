# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_SHELL_GAME_FAKEOUT_REVEAL_0135",
  "scene_kind": "shell_game_fakeout_reveal",
  "prompt": "Three identical opaque cups stand on a table; a ball is shown under one cup before it lowers. The cups slide through two position swaps. First one cup (not covering the ball) lifts to show it is EMPTY; then the cup actually covering the ball lifts to reveal the ball inside - it stayed with its cup through the swaps."
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
# scene 0135 shell game fakeout reveal
# =============================================================================

# table top surface height (z of the table top face the cups sit on)
TABLE_TOP_Z = 0.45

# Task-aware diversity values are sampled by the shared renderer from task.json.
# Defaults preserve the canonical scene when this script is run by itself.
_DIVERSITY = globals().get("DIVERSITY", {})

# cup geometry (upside-down cup = wall cylinder + solid cap disk on top)
CUP_RADIUS = float(_DIVERSITY.get("cup_radius", 0.42))
CUP_WALL_HEIGHT = 0.74
CUP_CAP = 0.07               # cap disk thickness on top of the wall

# slot world x-positions: left / middle / right
SLOT_SPACING = float(_DIVERSITY.get("slot_spacing", 1.7))
SLOT_X = [-SLOT_SPACING, 0.0, SLOT_SPACING]

# ball geometry
BALL_RADIUS = float(_DIVERSITY.get("ball_radius", 0.16))
BALL_START_SIDE = str(_DIVERSITY.get("ball_start_side", "left"))
BALL_CUP_INDEX = 0 if BALL_START_SIDE == "left" else 2

# During each swap both cups remain on the table and pass through opposite
# front/back lanes. Two lane offsets always exceed the largest cup diameter.
SHUFFLE_LANE_OFFSET = float(_DIVERSITY.get("shuffle_lane_offset", 0.55))
SHUFFLE_LANE_SIGN = int(_DIVERSITY.get("shuffle_lane_sign", 1))

# vertical lift for the reveal / initial show (lift fully clear of the ball)
CUP_REVEAL_LIFT = CUP_WALL_HEIGHT + CUP_CAP + 0.55


def _make_cup(prefix, slot_index, x):
    """Build one upside-down opaque cup as a wall cylinder + a top cap disk.

    The cup's local base is the slot center on the table top (z = TABLE_TOP_Z).
    Each part stores pb_rel_z (its z offset above the grounded base).
    """
    parts = []

    wall = add_cylinder(
        f"{prefix}_wall",
        (x, 0.0, TABLE_TOP_Z + CUP_WALL_HEIGHT / 2.0),
        CUP_RADIUS,
        CUP_WALL_HEIGHT,
        material=MATS["cup"],
        role="opaque_cup_wall",
        color_name="red",
        is_dynamic=True,
        solid=True,
        vertices=48,
    )
    wall["pb_rel_z"] = CUP_WALL_HEIGHT / 2.0
    parts.append(wall)

    cap = add_cylinder(
        f"{prefix}_cap",
        (x, 0.0, TABLE_TOP_Z + CUP_WALL_HEIGHT + CUP_CAP / 2.0),
        CUP_RADIUS,
        CUP_CAP,
        material=MATS["cup"],
        role="opaque_cup_cap",
        color_name="red",
        is_dynamic=True,
        solid=True,
        vertices=48,
    )
    cap["pb_rel_z"] = CUP_WALL_HEIGHT + CUP_CAP / 2.0
    parts.append(cap)

    for p in parts:
        p["pb_slot_index"] = slot_index
        p["pb_base_x"] = x
        p["pb_is_cup_part"] = True

    return {"parts": parts, "slot_index": slot_index, "base_x": x}


def build_shell_game_fakeout_reveal():
    scene = build_base_scene()
    # front 3/4 view; cups span x in [-1.7, 1.7]; camera off to the left-front
    setup_camera(scene, location=(-3.4, -7.6, 3.05), target=(0.0, 0.0, 0.70), lens=34)

    # table the cups stand on (well within camera frame, no edge overhang)
    add_cube(
        "shell_game_table",
        (0.0, 0.0, TABLE_TOP_Z - 0.09),
        (6.2, 2.6, 0.18),
        MATS["table"],
        role="table_surface",
        color_name="wood_brown",
    )

    # three identical opaque cups, one per slot
    cups = []
    cups.append(_make_cup("cup_L", 0, SLOT_X[0]))
    cups.append(_make_cup("cup_M", 1, SLOT_X[1]))
    cups.append(_make_cup("cup_R", 2, SLOT_X[2]))

    # The ball starts under either edge cup; its identity is tracked through both swaps.
    ball_cup = cups[BALL_CUP_INDEX]
    ball = add_sphere(
        "hidden_ball",
        BALL_RADIUS,
        (ball_cup["base_x"], 0.0, TABLE_TOP_Z + BALL_RADIUS),
        MATS["yellow"],
        "yellow",
    )
    ball["pb_inside_cup"] = True

    return {
        "scene": scene,
        "kind": "shell_game_fakeout_reveal",
        "cups": cups,
        "ball": ball,
        "ball_cup": ball_cup,
    }


def _place_cup(cup, x, lift, frame, y=0.0):
    """Place a whole cup (wall + cap) at world x with vertical lift above table."""
    for p in cup["parts"]:
        z = TABLE_TOP_Z + p["pb_rel_z"] + lift
        p.location = (x, y, z)
        p.keyframe_insert(data_path="location", frame=frame)


def _swap_positions(moving_cup, ground_cup, t, frame):
    """Animate one position swap of two cups across frame-fraction t in [0,1].

    Both cups remain on the table. They use opposite front/back lanes during the
    crossing, which preserves a realistic tabletop shuffle without lifting.
    """
    g_from = ground_cup["base_x"]
    g_to = moving_cup["base_x"]
    m_from = moving_cup["base_x"]
    m_to = ground_cup["base_x"]

    s = smooth01(t)

    lane = SHUFFLE_LANE_SIGN * SHUFFLE_LANE_OFFSET * math.sin(math.pi * clamp01(t))

    # both cups slide flat on opposite lanes, preserving clearance at the crossing
    gx = lerp(g_from, g_to, s)
    _place_cup(ground_cup, gx, 0.0, frame, y=lane)
    mx = lerp(m_from, m_to, s)
    _place_cup(moving_cup, mx, 0.0, frame, y=-lane)

    # commit the new slot bookkeeping at the end of the swap
    if t >= 1.0:
        ground_cup["base_x"], moving_cup["base_x"] = g_to, m_to
        gi = ground_cup["slot_index"]
        mi = moving_cup["slot_index"]
        ground_cup["slot_index"], moving_cup["slot_index"] = mi, gi
        for p in ground_cup["parts"]:
            p["pb_base_x"] = ground_cup["base_x"]
            p["pb_slot_index"] = ground_cup["slot_index"]
        for p in moving_cup["parts"]:
            p["pb_base_x"] = moving_cup["base_x"]
            p["pb_slot_index"] = moving_cup["slot_index"]


def _pick_empty_cup(cups, ball_cup):
    """Return a cup that does NOT hold the ball, nearest to the ball_cup's slot
    (a convincing near-miss fakeout). Deterministic by current slot index."""
    empties = [c for c in cups if c is not ball_cup]
    empties.sort(key=lambda c: abs(c["slot_index"] - ball_cup["slot_index"]))
    return empties[0]


def animate_shell_game_fakeout_reveal(objs, frame):
    cups = objs["cups"]
    ball = objs["ball"]
    ball_cup = objs["ball_cup"]

    cup_L, cup_M, cup_R = cups[0], cups[1], cups[2]
    first_swap_cup = cup_M
    second_swap_cup = cup_R if ball_cup is cup_L else cup_L

    # ---- phase windows ----
    # f1-14   : left cup (ball_cup) starts raised (ball shown), lowers to hide ball
    # f18-48  : swap 1, slots 0<->1  (cup_M arcs over grounded ball_cup at slot 0)
    # f54-84  : swap 2, slots 1<->2  (cup_R arcs over grounded ball_cup at slot 1)
    # f90-102 : FAKEOUT - a cup that does NOT hold the ball lifts (empty table),
    #           then lowers back onto the table
    # f108-120: the ball-carrying cup lifts to REVEAL the ball inside

    def rest_all():
        # every cup resting on the table at its current base_x
        for c in cups:
            _place_cup(c, c["base_x"], 0.0, frame)

    if frame <= 14:
        # cup_L raised at start (ball visible), lowers over the ball to hide it
        rest_all()
        t = (frame - FRAME_START) / 13.0
        lift = CUP_REVEAL_LIFT * (1.0 - smooth01(t))
        _place_cup(ball_cup, ball_cup["base_x"], lift, frame)
        ball_cup["parts"][0]["pb_state"] = "lowering_to_hide_ball"

    elif frame < 18:
        rest_all()

    elif frame <= 48:
        # swap 1: slots 0<->1. ball_cup (cup_L) at slot 0 stays grounded; cup_M arcs over it.
        rest_all()  # cup_R untouched at slot 2
        t = (frame - 18) / 30.0
        _swap_positions(moving_cup=first_swap_cup, ground_cup=ball_cup, t=t, frame=frame)

    elif frame < 54:
        rest_all()

    elif frame <= 84:
        # swap 2: slots 1<->2. after swap 1 ball_cup (cup_L) is at slot 1; it stays
        # grounded, and cup_R (at slot 2) arcs over it.
        rest_all()  # cup_M untouched (now at slot 0)
        t = (frame - 54) / 30.0
        _swap_positions(moving_cup=second_swap_cup, ground_cup=ball_cup, t=t, frame=frame)

    elif frame < 90:
        rest_all()

    elif frame <= 102:
        # FAKEOUT: lift an EMPTY cup (one that does NOT hold the ball) to show the
        # bare table beneath it, then lower it back down. sin() gives up-then-down
        # over the window (0 at the ends, peak at mid) so it ends resting again.
        rest_all()
        empty_cup = _pick_empty_cup(cups, ball_cup)
        t = (frame - 90) / 12.0
        lift = CUP_REVEAL_LIFT * math.sin(math.pi * clamp01(t))
        _place_cup(empty_cup, empty_cup["base_x"], lift, frame)
        empty_cup["parts"][0]["pb_state"] = "fakeout_lift_shows_empty_table"

    elif frame < 108:
        rest_all()

    else:
        # final reveal: ball_cup lifts off the ball (it stayed with its cup)
        rest_all()
        t = (frame - 108) / 12.0
        lift = CUP_REVEAL_LIFT * smooth01(t)
        _place_cup(ball_cup, ball_cup["base_x"], lift, frame)
        ball_cup["parts"][0]["pb_state"] = "lifting_to_reveal_ball"

    # ball: hidden after f14, always pinned to the ball_cup's LIVE world x.
    # _place_cup has already moved the ball_cup's parts for THIS frame, so read
    # the actual current wall x rather than base_x (base_x only updates at the end
    # of a swap, which would leave the ball frozen at the old slot while the cup
    # slides through it). The ball rides at the live x/y centre of its container
    # every frame and never returns to its original world position.
    if frame <= 14:
        bx = ball_cup["base_x"]
        by = 0.0
    else:
        bx = ball_cup["parts"][0].location.x
        by = ball_cup["parts"][0].location.y
    ball.location = (bx, by, TABLE_TOP_Z + BALL_RADIUS)
    ball.keyframe_insert(data_path="location", frame=frame)

    if frame <= 8:
        ball["pb_state"] = "visible_under_raised_left_cup"
    elif frame <= 106:
        ball["pb_state"] = "hidden_moving_with_its_cup"
    else:
        ball["pb_state"] = "revealed_under_its_cup_after_empty_fakeout"
    ball["pb_moves_with_container"] = True
    ball["pb_no_teleport_back_to_origin"] = True


# =============================================================================
# dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "shell_game_fakeout_reveal":
        return build_shell_game_fakeout_reveal()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "shell_game_fakeout_reveal":
            animate_shell_game_fakeout_reveal(objs, frame)
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
