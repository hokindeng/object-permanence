# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_LIMBO_HEIGHT_BAR_0136",
  "scene_kind": "limbo_height_bar",
  "prompt": "A horizontal bar is held up on two posts at a set height above a flat track, leaving a gap underneath. A short object rolls along the track and passes cleanly UNDER the bar to the far side; a tall object, taller than the gap, is stopped by the bar and comes to rest against it. Neither object is ever suspended."
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
    MATS["gray"] = make_mat("mat_neutral_gray", (0.66, 0.66, 0.68), roughness=0.62)
    # Posts: mid gray uprights that clearly hold the bar aloft.
    MATS["post"] = make_mat("mat_post_gray", (0.52, 0.53, 0.56), roughness=0.70)
    # Bar: darker so the horizontal limbo bar reads distinctly against the posts.
    MATS["bar"] = make_mat("mat_bar_dark", (0.30, 0.31, 0.34), roughness=0.66)
    MATS["dark"] = make_mat("mat_dark_gray", (0.05, 0.05, 0.06), roughness=0.92)
    MATS["box"] = make_mat("mat_box_gray", (0.38, 0.39, 0.40), roughness=0.78)
    MATS["edge"] = make_mat("mat_light_edge", (0.62, 0.63, 0.64), roughness=0.68)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.38, 0.06), roughness=0.30)
    MATS["red"] = make_mat("mat_red", (0.85, 0.12, 0.10), roughness=0.32)
    MATS["glass"] = make_mat("mat_transparent_glass", (0.50, 0.82, 1.0), roughness=0.08, alpha=0.34, blend="BLEND")
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (9.8, 7.6, 0.10), MATS["floor"], role="ground", color_name="warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.9, 1.60), (10.0, 0.08, 3.20), MATS["backdrop"], role="background", color_name="off_white")

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
# Limbo gate: two vertical posts holding a horizontal bar aloft,
# leaving a clear gap of height GAP_H underneath.
# ============================================================

def create_limbo_bar(name, gate_y, gap_height, bar_thick, span_x, post_side,
                      post_cross, post_top_z):
    """Build a limbo-style gate straddling the track at y=gate_y. Two vertical POSTS
    stand just outside the two lanes (at +/-span_x/2) and rise from the floor up to
    post_top_z. A horizontal BAR is laid across the top of the posts so that its
    UNDERSIDE sits at height gap_height above the floor, leaving a clear gap of height
    gap_height for a short object to roll under. The bar spans X (along the posts),
    with its thickness in Z (bar_thick) and depth along Y (post_cross). Returns a dict
    of the parts and gate geometry. The gap underneath is a genuine open channel: a
    short object passes clean under, a tall object hits the bar."""
    half_span = span_x / 2.0
    bar_bottom_z = gap_height
    bar_center_z = bar_bottom_z + bar_thick / 2.0
    bar_top_z = bar_bottom_z + bar_thick

    parts = {}

    # ---- Two vertical posts, one outside each lane, rising to post_top_z ----
    for sx, side in ((-half_span, "left"), (half_span, "right")):
        post = add_cube(
            f"{name}_post_{side}",
            (sx, gate_y, post_top_z / 2.0),
            (post_cross, post_cross, post_top_z),
            MATS["post"],
            role="limbo_post",
            color_name="gray",
            solid=True,
        )
        post["pb_is_limbo_post"] = True
        parts[f"post_{side}"] = post

    # ---- Horizontal bar across the top, underside at gap_height ----
    # It spans slightly beyond the inner faces of the posts so it visibly rests on them.
    bar_len = span_x + post_cross
    bar = add_cube(
        f"{name}_cross_bar",
        (0.0, gate_y, bar_center_z),
        (bar_len, post_cross, bar_thick),
        MATS["bar"],
        role="limbo_cross_bar",
        color_name="dark_gray",
        solid=True,
    )
    bar["pb_is_limbo_bar"] = True
    bar["pb_gap_height"] = float(gap_height)
    parts["bar"] = bar

    parts.update({
        "gate_y": gate_y,
        "gap_height": gap_height,
        "bar_thick": bar_thick,
        "bar_bottom_z": bar_bottom_z,
        "bar_top_z": bar_top_z,
        "post_cross": post_cross,
        "half_span": half_span,
    })
    return parts


# ============================================================
# 0136 limbo height bar
# ============================================================

def build_limbo_height_bar_scene():
    scene = build_base_scene()
    # 3/4 elevated camera on the NEAR side, offset left, aimed just under the bar so
    # the gap between the track and the bar underside clearly reads as open space
    # (far floor visible through it). Angled low enough to see the gap edge-on.
    setup_camera(scene, location=(-3.2, -7.4, 2.2), target=(0.0, 0.6, 0.55), lens=35)

    GATE_Y = 0.6
    GAP_HEIGHT = 0.62           # the HEIGHT gate: clear gap under the bar
    BAR_THICK = 0.26
    SPAN_X = 4.4                # posts sit at +/-2.2, outside both lanes
    POST_CROSS = 0.24
    POST_TOP_Z = GAP_HEIGHT + BAR_THICK  # posts rise exactly to bar top

    gate = create_limbo_bar(
        "limbo_gate",
        GATE_Y,
        GAP_HEIGHT,
        BAR_THICK,
        SPAN_X,
        POST_CROSS,
        POST_CROSS,
        POST_TOP_Z,
    )

    # Object heights chosen relative to GAP_HEIGHT so the physics is unambiguous:
    # short puck total height (2*0.24=0.48) < GAP_HEIGHT (0.62) -> passes under.
    # tall cylinder total height (0.98) > GAP_HEIGHT (0.62) -> stopped by the bar.
    SHORT_R = 0.24
    SHORT_H = 0.38              # a low puck lying on its round side, rolling
    TALL_R = 0.22
    TALL_H = 0.98              # a tall standing cylinder, taller than the gap

    # The short puck is modeled as a cylinder lying on its side (axis along X) so it
    # rolls forward in +Y. Once its axis is horizontal, its vertical extent is
    # the circular radius SHORT_R, not half of its axial depth SHORT_H. Therefore
    # the centre must sit at z=SHORT_R for exact tangency with the floor.
    short_roll_radius = SHORT_R
    short = add_cylinder(
        "short_orange_puck_passes_under",
        (1.1, -3.2, short_roll_radius),
        SHORT_R,
        SHORT_H,
        MATS["orange"],
        role="target_short_object_passes_under_bar",
        color_name="orange",
        is_dynamic=True,
        solid=True,
        rotation=(0.0, math.radians(90.0), 0.0),  # axis along X -> rolls in +Y
    )
    short["pb_shorter_than_gap"] = True
    short["pb_object_height"] = float(2.0 * SHORT_R)
    short["pb_expected_behavior"] = "rolls_under_bar_to_far_side"

    # The tall object is a standing cylinder (axis vertical) on a PARALLEL lane offset
    # in X so it never collides with the short puck. It rolls/slides in +Y and is
    # stopped when its front meets the bar (it is taller than the gap). It rests upright
    # against the bar. Its center height is TALL_H/2 (base on the floor).
    tall = add_cylinder(
        "tall_red_cylinder_blocked_by_bar",
        (-1.1, -3.2, TALL_H / 2.0),
        TALL_R,
        TALL_H,
        MATS["red"],
        role="target_tall_object_stopped_by_bar",
        color_name="red",
        is_dynamic=True,
        solid=True,
        rotation=(0.0, 0.0, 0.0),  # axis vertical -> stands tall
    )
    tall["pb_taller_than_gap"] = True
    tall["pb_object_height"] = float(TALL_H)
    tall["pb_expected_behavior"] = "stopped_by_bar_rests_against_it"

    return {
        "scene": scene,
        "kind": "limbo_height_bar",
        "short": short,
        "tall": tall,
        "gate": gate,
        "gate_y": GATE_Y,
        "gap_height": GAP_HEIGHT,
        "bar_bottom_z": gate["bar_bottom_z"],
        "short_roll_radius": short_roll_radius,
        "short_r": SHORT_R,
        "short_h": SHORT_H,
        "tall_r": TALL_R,
        "tall_h": TALL_H,
        "short_lane_x": 1.1,
        "tall_lane_x": -1.1,
    }


def animate_limbo_height_bar(objs, frame):
    short = objs["short"]
    tall = objs["tall"]
    gate_y = objs["gate_y"]
    short_roll_radius = objs["short_roll_radius"]
    tall_r = objs["tall_r"]
    tall_h = objs["tall_h"]
    short_lane_x = objs["short_lane_x"]
    tall_lane_x = objs["tall_lane_x"]

    near_y = -3.2

    # ---- SHORT PUCK (lane x=+1.1) ----
    # Rolls in +Y from the near side, passes cleanly UNDER the bar, continues to the
    # far side and comes to rest. Y goes monotonically forward; z stays at its rolling
    # radius (on the floor the whole time) so it is never suspended.
    short_start_y = near_y
    short_end_y = gate_y + 2.4          # well past the gate on the far side
    short_roll_start = 1
    short_roll_end = 70

    t_s = smooth01((frame - short_roll_start) / float(short_roll_end - short_roll_start))
    sy = lerp(short_start_y, short_end_y, t_s)
    if sy < gate_y - 0.05:
        s_state = "rolling_in_near_side_toward_gap"
    elif sy <= gate_y + 0.05:
        s_state = "passing_under_bar"
    elif frame < short_roll_end:
        s_state = "rolling_out_far_side"
    else:
        s_state = "at_rest_far_side"
    short.location = (short_lane_x, sy, short_roll_radius)
    # Cylinder axis is along X (rotated 90deg about Y). Rolling forward in +Y is a
    # rotation about the X axis; keep the base 90deg-about-Y orientation on Y/Z.
    short.rotation_euler = (0.22 * frame, math.radians(90.0), 0.0)
    short.keyframe_insert(data_path="location", frame=frame)
    short.keyframe_insert(data_path="rotation_euler", frame=frame)
    short["pb_state"] = s_state
    short["pb_never_suspended"] = True

    # ---- TALL CYLINDER (lane x=-1.1) ----
    # Rolls/slides in +Y from the near side and is STOPPED by the bar: it is taller than
    # the gap, so its top meets the bar and it comes to rest with its front just touching
    # the near edge of the bar. Base stays on the floor -> never suspended.
    gate = objs["gate"]
    bar_near_face = gate_y - gate["post_cross"] / 2.0
    tall_rest_y = bar_near_face - tall_r          # cylinder surface touches bar near face
    tall_start_y = near_y
    tall_roll_start = 8
    tall_roll_end = 60

    t_t = smooth01((frame - tall_roll_start) / float(tall_roll_end - tall_roll_start))
    ty = lerp(tall_start_y, tall_rest_y, t_t)
    ty = min(ty, tall_rest_y)
    if frame <= tall_roll_start:
        t_state = "waiting_near_side"
    elif ty < tall_rest_y - 0.02:
        t_state = "rolling_in_near_side_toward_bar"
    else:
        t_state = "stopped_resting_against_bar"
    tall.location = (tall_lane_x, ty, tall_h / 2.0)
    # Standing cylinder sliding forward: spin about its vertical axis for a rolling
    # read while it advances; stays upright (base on floor) the whole time.
    tall.rotation_euler = (0.0, 0.0, 0.14 * frame)
    tall.keyframe_insert(data_path="location", frame=frame)
    tall.keyframe_insert(data_path="rotation_euler", frame=frame)
    tall["pb_state"] = t_state
    tall["pb_rests_against_bar"] = bool(ty >= tall_rest_y - 0.02)
    tall["pb_never_suspended"] = True


# ============================================================
# Build / animate dispatch
# ============================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "limbo_height_bar":
        return build_limbo_height_bar_scene()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "limbo_height_bar":
            animate_limbo_height_bar(objs, frame)
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
