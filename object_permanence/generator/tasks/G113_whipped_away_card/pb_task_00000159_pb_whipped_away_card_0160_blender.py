# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_WHIPPED_AWAY_CARD_0160",
  "scene_kind": "whipped_away_card",
  "prompt": "A ball rests on a thin flat card that bridges the mouth of a cup. The card is flicked out sideways fast; the ball, left unsupported, drops straight down into the cup below. Nothing remains suspended."
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


def add_cylinder(name, location, radius, depth, material=None, role="static_solid", color_name="gray", is_dynamic=False, solid=True, rotation=(0.0, 0.0, 0.0), vertices=48):
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
    MATS["gray"] = make_mat("mat_neutral_gray", (0.46, 0.46, 0.46), roughness=0.62)
    MATS["dark"] = make_mat("mat_dark_gray", (0.18, 0.18, 0.20), roughness=0.76)
    MATS["cup"] = make_mat("mat_cup", (0.30, 0.52, 0.70), roughness=0.55)
    MATS["card"] = make_mat("mat_card", (0.92, 0.90, 0.84), roughness=0.60)
    MATS["edge"] = make_mat("mat_light_edge", (0.62, 0.63, 0.64), roughness=0.68)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.38, 0.06), roughness=0.30)
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
# 0160 whipped-away support card
#
# A cup stands on the floor. A thin flat card bridges the cup's mouth and a
# ball rests on the card, its center one radius above the card top. The card
# is flicked sideways (fast, ease-in) fully clear of the cup mouth; the instant
# its trailing edge clears the ball's x the ball loses support and free-falls
# straight down (constant gravity acceleration, distance ~ t^2) into the cup,
# coming to rest on the cup's inner floor. x is held constant so the ball drops
# straight down; the card is pulled in +X (away from the drop path) so it never
# intersects the falling ball.
# ============================================================

def build_whipped_away_card_scene():
    scene = build_base_scene()
    # Three-quarter view so the card on the cup mouth, the sideways pull, and the
    # ball dropping into the cup are all visible.
    setup_camera(scene, location=(-1.0, -8.0, 2.35), target=(0.15, 0.0, 0.95), lens=33)

    BALL_R = 0.24

    # --- Cup (open-top hollow cylinder built from a floor disk + wall ring) ---
    # The cup mouth must be wide enough for the ball to drop cleanly inside.
    CUP_CX = 0.0
    CUP_CY = 0.0
    CUP_INNER_R = BALL_R + 0.16      # inner radius, ball clears wall by 0.16
    CUP_WALL_T = 0.06
    CUP_OUTER_R = CUP_INNER_R + CUP_WALL_T
    CUP_BASE_Z = 0.0                 # cup sits on the floor
    CUP_FLOOR_T = 0.08
    CUP_HEIGHT = 0.95                # outer wall height
    cup_floor_top = CUP_BASE_Z + CUP_FLOOR_T   # inner floor surface (ball rests here)
    cup_mouth_z = CUP_BASE_Z + CUP_HEIGHT      # top of the cup wall / card level

    # Cup inner floor (solid disk the ball lands on).
    add_cylinder(
        "cup_inner_floor",
        (CUP_CX, CUP_CY, CUP_BASE_Z + CUP_FLOOR_T / 2.0),
        CUP_INNER_R,
        CUP_FLOOR_T,
        MATS["cup"],
        role="cup_floor",
        color_name="blue",
        solid=True,
        vertices=48,
    )
    # Cup wall ring: an outer solid cylinder is visually the cup body; the hollow
    # interior is implied (the ball drops into the top opening and rests on the
    # inner floor). Model the wall as four arc segments? Simpler + robust: a thin
    # tall outer shell built as a torus-like ring using a large cylinder minus is
    # not available without bmesh ops here, so build the wall as an annular ring
    # approximated by a ring of tall thin panels around the rim.
    n_panels = 24
    wall_cz = CUP_BASE_Z + CUP_HEIGHT / 2.0
    ring_r = CUP_INNER_R + CUP_WALL_T / 2.0
    for i in range(n_panels):
        ang = 2.0 * math.pi * i / n_panels
        px = CUP_CX + ring_r * math.cos(ang)
        py = CUP_CY + ring_r * math.sin(ang)
        seg_w = 2.0 * math.pi * ring_r / n_panels + 0.01
        panel = add_cube(
            f"cup_wall_seg_{i}",
            (px, py, wall_cz),
            (CUP_WALL_T, seg_w, CUP_HEIGHT),
            MATS["cup"],
            role="cup_wall",
            color_name="blue",
            solid=True,
        )
        panel.rotation_euler = (0.0, 0.0, ang)

    # --- Card bridging the cup mouth (thin flat slab, ball rests on it) -------
    CARD_T = 0.03
    CARD_LEN_X = 2.0 * CUP_OUTER_R + 1.4    # extends well past the mouth in +X so it can slide out
    CARD_W_Y = 2.0 * CUP_OUTER_R + 0.20
    card_top_z = cup_mouth_z + CARD_T / 2.0
    # Card is centered on the cup at rest; it will translate in +X to clear the mouth.
    card = add_cube(
        "support_card_on_cup_mouth",
        (CUP_CX, CUP_CY, cup_mouth_z + CARD_T / 2.0),
        (CARD_LEN_X, CARD_W_Y, CARD_T),
        MATS["card"],
        role="support_card",
        color_name="cream",
        is_dynamic=True,
        solid=True,
    )
    card["pb_supports_ball_initially"] = True

    # --- Ball resting on the card, over the cup center -----------------------
    card_surface_z = cup_mouth_z + CARD_T
    ball = add_sphere(
        "orange_ball_on_card",
        BALL_R,
        (CUP_CX, CUP_CY, card_surface_z + BALL_R),
        MATS["orange"],
        "orange",
        role="ball_drops_into_cup_when_card_pulled",
    )
    ball["pb_expected_behavior"] = "free_fall_into_cup_after_card_pulled"

    return {
        "scene": scene,
        "kind": "whipped_away_card",
        "card": card,
        "ball": ball,
        "ball_r": BALL_R,
        "cup_cx": CUP_CX,
        "cup_cy": CUP_CY,
        "cup_inner_r": CUP_INNER_R,
        "cup_outer_r": CUP_OUTER_R,
        "cup_floor_top": cup_floor_top,
        "cup_mouth_z": cup_mouth_z,
        "card_surface_z": card_surface_z,
        "card_len_x": CARD_LEN_X,
    }


def animate_whipped_away_card(objs, frame):
    card = objs["card"]
    ball = objs["ball"]
    ball_r = objs["ball_r"]
    cup_cx = objs["cup_cx"]
    cup_cy = objs["cup_cy"]
    cup_outer_r = objs["cup_outer_r"]
    cup_floor_top = objs["cup_floor_top"]
    card_surface_z = objs["card_surface_z"]
    card_len_x = objs["card_len_x"]

    card_cz = card.location.z

    # --- Card: hold, then flick sideways (+X) FAST with ease-in acceleration ---
    # The card must be pulled fully clear of the cup mouth. The support is
    # considered removed once the card's trailing (-X) edge passes the ball's x
    # (cup center). We drive the card so it clears within a few frames of the
    # pull start; the ball's free-fall starts exactly at that removal frame.
    HOLD_END = 24
    PULL_DUR = 14.0
    # Distance so the card's -X trailing edge (starts at -card_len_x/2, centered
    # at cup_cx) clears +cup_outer_r: shift >= card_len_x/2 + cup_outer_r.
    PULL_DIST = card_len_x / 2.0 + cup_outer_r + 0.20

    if frame <= HOLD_END:
        card_shift = 0.0
        card_state = "bridging_cup_mouth_supporting_ball"
    else:
        t = ease_in_quad((frame - HOLD_END) / PULL_DUR)
        card_shift = PULL_DIST * t
        card_state = "flicked_out_sideways" if t < 0.98 else "removed_clear_of_mouth"

    card.location = (cup_cx + card_shift, cup_cy, card_cz)
    card.keyframe_insert(data_path="location", frame=frame)
    card["pb_state"] = card_state

    # Frame at which the card trailing edge clears the ball's x (cup center).
    # trailing edge x = cup_cx - card_len_x/2 + card_shift; clears when >= cup_cx.
    # => card_shift >= card_len_x/2. Solve for the frame using the ease curve.
    clear_shift = card_len_x / 2.0
    # ease_in_quad: shift = PULL_DIST * ((f-HOLD_END)/PULL_DUR)^2
    # (f-HOLD_END)/PULL_DUR = sqrt(clear_shift/PULL_DIST)
    frac_clear = math.sqrt(min(1.0, clear_shift / PULL_DIST))
    fall_start = HOLD_END + frac_clear * PULL_DUR

    # --- Ball: rest on card, then pure vertical free-fall into the cup --------
    rest_z = card_surface_z + ball_r
    land_z = cup_floor_top + ball_r
    # Prompt free-fall: land early so the accelerating drop is fast (a larger
    # implied gravity constant), not a slow float into the cup.
    LAND_FRAME = 52
    G_FALL = 2.0 * (rest_z - land_z) / float((LAND_FRAME - fall_start) ** 2)

    if frame <= fall_start:
        z = rest_z
        state = "resting_supported_on_card"
    else:
        df = frame - fall_start
        z = max(land_z, rest_z - 0.5 * G_FALL * df * df)
        state = "free_falling_into_cup" if z > land_z + 0.01 else "settled_on_cup_floor"

    ball.location = (cup_cx, cup_cy, z)
    ball.rotation_euler = (0.0, 0.0, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball["pb_state"] = state
    ball["pb_does_not_fall_before_card_removed"] = bool(frame <= fall_start)
    ball["pb_falls_after_support_removed"] = bool(frame > fall_start)


# ============================================================
# Build / animate dispatch
# ============================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "whipped_away_card":
        return build_whipped_away_card_scene()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "whipped_away_card":
            animate_whipped_away_card(objs, frame)
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
