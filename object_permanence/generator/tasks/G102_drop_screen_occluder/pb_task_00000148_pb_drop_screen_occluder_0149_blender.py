# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_DROP_SCREEN_OCCLUDER_0149",
  "scene_kind": "drop_screen_occluder",
  "kind": "drop_screen_occluder",
  "prompt": "A ball rolls at a constant speed along a straight rail from left to right. A solid opaque screen, held in vertical guides in front of the rail, drops straight down from above to fully block the view of the ball's mid-path and holds there while the ball passes hidden behind it; the screen then lifts back up and the ball is revealed on the far side, unchanged and still moving at the same steady speed. The ball never stops -- it reappears at a position consistent with continuous constant-velocity motion."
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
    return t * t * (3.0 - 2.0 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def make_mat(name, color, roughness=0.55, metallic=0.0, alpha=1.0):
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

    return mat


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), roughness=0.85)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.92)

    MATS["gray"] = make_mat("mat_gray", (0.62, 0.63, 0.66), roughness=0.75)
    MATS["housing"] = make_mat("mat_housing", (0.32, 0.33, 0.37), roughness=0.85)
    MATS["dark"] = make_mat("mat_dark", (0.18, 0.20, 0.24), roughness=0.55)
    MATS["support"] = make_mat("mat_support", (0.16, 0.18, 0.22), roughness=0.60)

    # Rolling ball: warm red so it reads clearly against the screen and backdrop.
    MATS["coin"] = make_mat("mat_ball", (0.90, 0.20, 0.16), roughness=0.35, metallic=0.0)
    # The dropping screen: a solid opaque slate panel.
    MATS["screen"] = make_mat("mat_screen", (0.30, 0.33, 0.40), roughness=0.70)
    MATS["frame"] = make_mat("mat_frame", (0.14, 0.15, 0.18), roughness=0.55)


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
        "dynamic_object" if is_dynamic else "static_solid",
        "cube",
        color_name,
        is_dynamic,
        solid=solid,
    )
    return obj


def add_cylinder(name, location, radius, depth, material, role, color_name, rotation=(0.0, 0.0, 0.0), is_dynamic=False, shape="cylinder", **extras):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, vertices=64, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    if material is not None:
        obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", shape, color_name, is_dynamic, solid=True, **extras)
    return obj


def add_ball(name, location, radius, material, role, color_name, is_dynamic=True, **extras):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=48, ring_count=24)
    obj = bpy.context.object
    obj.name = name
    if material is not None:
        obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "sphere", color_name, is_dynamic, solid=True, pb_radius=radius, **extras)
    return obj


def add_cylinder_between(name, p1, p2, radius, material, role, color_name):
    p1 = Vector(p1)
    p2 = Vector(p2)
    diff = p2 - p1
    length = diff.length
    mid = (p1 + p2) / 2.0

    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=length, vertices=24, location=mid)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = diff.to_track_quat("Z", "Y").to_euler()

    if material is not None:
        obj.data.materials.append(material)

    tag(obj, name, role, "static_solid", "cylinder", color_name, False, solid=True)
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
        scene.eevee.gtao_distance = 3.0
        scene.eevee.gtao_factor = 1.2
    except Exception:
        pass

    if scene.world is None:
        scene.world = bpy.data.worlds.new("clean_world")
    scene.world.color = (1.0, 1.0, 1.0)

    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Base Contrast"
    except Exception:
        try:
            scene.view_settings.view_transform = "Standard"
            scene.view_settings.look = "None"
        except Exception:
            pass


def setup_base(camera_loc, target, ortho_scale):
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (12.0, 8.0, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.55, 2.05), (12.0, 0.08, 4.1), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-2.8, -4.5, 6.4))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 600
    key.data.size = 7.0

    bpy.ops.object.light_add(type="POINT", location=(3.0, 1.8, 3.6))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 140

    bpy.ops.object.camera_add(location=camera_loc)
    cam = bpy.context.object
    cam.name = "camera_main"
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = ortho_scale
    look_at(cam, target)
    scene.camera = cam

    return scene


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


def write_task_json(task):
    with open(TASK_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(task, f, indent=2, ensure_ascii=False)


def save_scene():
    bpy.ops.wm.save_as_mainfile(filepath=SCENE_FILE)


# =============================================================================
# 00000148  drop_screen_occluder  (Cluster: Baillargeonian Occlusion)
# =============================================================================
#
# A ball rolls at CONSTANT speed left->right along a straight flat rail. A solid
# opaque SCREEN panel is held in a pair of vertical guides that stand IN FRONT of
# the rail (between the camera and the ball, at y < rail_y). The screen starts
# RAISED clear above the lane (ball visible, approaching). It then DROPS straight
# down along the guides to fully block the view of the ball's mid-path, HOLDS
# there briefly while the ball -- still moving at the same steady speed -- passes
# hidden behind it, then LIFTS back up. The ball is revealed on the far side,
# unchanged, at a position/time consistent with continuous constant-velocity
# motion; it never stopped.
#
# Occlusion is genuine geometry: the screen is a solid opaque wall sitting between
# the camera and the ball, so the ball is hidden purely because the screen is in
# the way (no hide_render trickery). While down, the screen fully covers the
# ball's height across the mid-span of the lane.
# =============================================================================


def _screen_params():
    z_track_top = 0.62
    track_thick = 0.16
    ball_radius = 0.30
    x_span = 4.1              # ball travels from -x_span to +x_span
    screen_half_x = 1.9      # screen covers x in [-screen_half_x, +screen_half_x]
    screen_t = 0.12          # thickness of the screen panel in y
    screen_h = 1.55          # screen height (fully covers the ball's height)
    return {
        "z_track_top": z_track_top,
        "track_thick": track_thick,
        "ball_radius": ball_radius,
        "x_span": x_span,
        "screen_half_x": screen_half_x,
        "screen_t": screen_t,
        "screen_h": screen_h,
    }


def build_drop_screen_occluder_scene():
    # Nearly head-on, slightly raised front view so the screen reads as a
    # foreground panel and the ball is clearly seen rolling behind it.
    scene = setup_base(
        camera_loc=(0.0, -9.0, 2.4),
        target=(0.0, 0.55, 1.0),
        ortho_scale=9.4,
    )

    P = _screen_params()
    z_top = P["z_track_top"]
    track_thick = P["track_thick"]
    ball_radius = P["ball_radius"]
    x_span = P["x_span"]
    screen_half_x = P["screen_half_x"]
    screen_t = P["screen_t"]
    screen_h = P["screen_h"]

    ball_z = z_top + ball_radius
    z_slab_c = z_top - track_thick / 2.0

    # The ball rolls along the rail at rail_y; the screen stands nearer the
    # camera (smaller y) so it occludes the ball as the ball passes behind it.
    rail_y = 0.55
    screen_y = rail_y - (ball_radius + screen_t / 2.0 + 0.32)

    # ---- Flat horizontal track slab -----------------------------------------
    track_len = 2.0 * x_span + 1.6
    track_width = 1.2
    add_cube(
        "ball_track_slab",
        (0.0, rail_y, z_slab_c),
        (track_len, track_width, track_thick),
        MATS["gray"], "track", "gray",
    )

    # Low guide rails flanking the lane.
    rail_radius = 0.045
    rail_lift = z_top + rail_radius
    rail_x0 = -x_span - 0.8
    rail_x1 = x_span + 0.8
    for side, dy in [("front", rail_y - (ball_radius + 0.16)), ("back", rail_y + (ball_radius + 0.16))]:
        add_cylinder_between(
            "rail_%s" % side,
            (rail_x0, dy, rail_lift),
            (rail_x1, dy, rail_lift),
            rail_radius, MATS["dark"], "track_rail", "dark_gray",
        )

    # Support legs under the track (nothing suspended).
    for sx in (-x_span - 0.4, 0.0, x_span + 0.4):
        add_cube(
            "track_leg_%d" % int(round(sx * 10)),
            (sx, rail_y, z_slab_c / 2.0),
            (0.22, track_width - 0.2, max(0.1, z_slab_c)),
            MATS["support"], "track_support", "dark_gray",
        )

    # ---- Vertical guide frame the screen slides in --------------------------
    # Two tall guide posts flank the covered span, plus a top header, so the
    # screen reads as a panel that rides straight up and down in a track. The
    # frame is static; only the screen translates in z.
    down_cz = (z_top - 0.02) + screen_h / 2.0        # bottom edge on the track top
    up_cz = down_cz + 2.55                           # raised fully clear of the lane
    post_h = (up_cz + screen_h / 2.0) - (z_top - 0.02) + 0.20
    post_cz = (z_top - 0.02) + post_h / 2.0
    guide_w = 0.14
    # Exact prismatic fit: each guide's inner face is tangent to one vertical
    # edge of the screen.  Because the panel animation changes only Z, this
    # zero-gap lateral fit is preserved throughout the full drop/lift cycle.
    post_x = screen_half_x + guide_w / 2.0
    for sx, nm in ((-post_x, "left"), (post_x, "right")):
        guide = add_cube(
            "screen_guide_%s" % nm,
            (sx, screen_y, post_cz),
            (guide_w, screen_t + 0.18, post_h),
            MATS["frame"], "screen_guide", "dark_gray",
        )
        inner_face_x = sx + guide_w / 2.0 if sx < 0.0 else sx - guide_w / 2.0
        screen_edge_x = -screen_half_x if sx < 0.0 else screen_half_x
        guide["pb_inner_face_x"] = float(inner_face_x)
        guide["pb_screen_edge_x"] = float(screen_edge_x)
        guide["pb_lateral_clearance"] = float(abs(inner_face_x - screen_edge_x))
    header_z = (z_top - 0.02) + post_h + 0.02
    add_cube(
        "screen_guide_header",
        (0.0, screen_y, header_z),
        (2.0 * post_x + guide_w, screen_t + 0.18, 0.16),
        MATS["frame"], "screen_guide", "dark_gray",
    )

    # ---- The dropping screen (the true occluder) ----------------------------
    # A single solid opaque panel spanning x in [-screen_half_x, +screen_half_x]
    # and tall enough to fully cover the ball's height. Built at the RAISED
    # position; the animation lowers/raises it in z.
    screen = add_cube(
        "drop_screen",
        (0.0, screen_y, up_cz),
        (2.0 * screen_half_x, screen_t, screen_h),
        MATS["screen"], "occluder_screen", "slate",
        is_dynamic=True,
    )
    screen["pb_motion"] = "drops_down_to_cover_then_lifts_to_reveal"
    screen["pb_fixed_plane_y"] = screen_y
    screen["pb_foreground_depth_separated_from_target"] = True
    screen["pb_guided_edges_remain_tangent"] = True
    screen["pb_lateral_guide_clearance"] = 0.0

    # ---- The rolling ball ----------------------------------------------------
    ball = add_ball(
        "rolling_ball",
        (-x_span, rail_y, ball_z),
        ball_radius,
        MATS["coin"], "target", "red",
        is_dynamic=True,
    )
    ball["pb_path"] = "left_to_right_constant_velocity_behind_dropping_screen"
    ball["pb_can_disappear"] = False

    return scene, {
        "ball": ball,
        "ball_radius": ball_radius,
        "ball_z": ball_z,
        "rail_y": rail_y,
        "x_span": x_span,
        "screen": screen,
        "screen_y": screen_y,
        "screen_half_x": screen_half_x,
        "down_cz": down_cz,
        "up_cz": up_cz,
    }


def animate_drop_screen_occluder(scene, meta):
    ball = meta["ball"]
    radius = meta["ball_radius"]
    ball_z = meta["ball_z"]
    rail_y = meta["rail_y"]
    x_span = meta["x_span"]
    screen = meta["screen"]
    screen_y = meta["screen_y"]
    screen_half_x = meta["screen_half_x"]
    down_cz = meta["down_cz"]
    up_cz = meta["up_cz"]

    # The ball moves at a strictly CONSTANT velocity across the whole clip -- it
    # never rests and never changes speed. It is occluded purely by the solid
    # screen sitting between it and the camera (we do NOT hide the ball).
    total = float(FRAME_END - FRAME_START)

    # Screen timeline (down01: 1.0 = fully DOWN/covering, 0.0 = fully UP/clear).
    #   1-22   : up (ball approaching, visible)
    #   22-40  : screen drops straight down to cover
    #   40-76  : hold down (ball passes hidden behind the screen)
    #   76-92  : screen lifts while the ball crosses the screen's right half
    #   92-120 : up (same ball is clearly visible continuing on the far side)
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        # Constant-velocity roll from -x_span to +x_span.
        u = (frame - FRAME_START) / total
        xb = -x_span + (2.0 * x_span) * u
        ball.location = (xb, rail_y, ball_z)
        # No-slip rolling spin about the y axis (top of ball moves +x forward).
        ball.rotation_euler = (0.0, -(xb + x_span) / radius, 0.0)
        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)

        if frame <= 22:
            down01 = 0.0
            scr_state = "screen_up_ball_visible"
        elif frame <= 40:
            down01 = smooth01((frame - 22) / 18.0)
            scr_state = "screen_dropping_to_cover"
        elif frame <= 76:
            down01 = 1.0
            scr_state = "screen_down_ball_hidden"
        elif frame <= 92:
            down01 = 1.0 - smooth01((frame - 76) / 16.0)
            scr_state = "screen_lifting_to_reveal"
        else:
            down01 = 0.0
            scr_state = "screen_up_same_ball_revealed"

        cz = lerp(up_cz, down_cz, down01)
        screen.location = (0.0, screen_y, cz)
        screen.keyframe_insert(data_path="location", frame=frame)
        screen["pb_state"] = scr_state

        # Semantic tag: is the ball geometrically behind the screen span AND the
        # screen low enough to actually hide it?
        behind_span = abs(xb) <= (screen_half_x + radius)
        hidden = behind_span and down01 > 0.85
        if hidden:
            ball["pb_state"] = "hidden_behind_screen"
        elif xb > screen_half_x:
            ball["pb_state"] = "past_screen_visible"
        else:
            ball["pb_state"] = "approaching_screen_visible"
        ball["pb_occluded"] = bool(hidden)
        ball["pb_pos_x"] = float(xb)

    scene.frame_set(FRAME_START)


# =============================================================================
# Dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE.get("scene_kind", CASE.get("kind"))

    if kind == "drop_screen_occluder":
        return build_drop_screen_occluder_scene()

    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(scene, meta):
    kind = CASE.get("scene_kind", CASE.get("kind"))

    if kind == "drop_screen_occluder":
        return animate_drop_screen_occluder(scene, meta)

    raise RuntimeError("Unknown scene_kind: " + str(kind))


def main():
    ensure_dirs()
    clear_scene()

    scene, meta = build_scene_by_kind()
    animate_scene_by_kind(scene, meta)

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

    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, 60, OPTIONAL_FRAME_PATH)
    render_png(scene, 120, OPTIONAL_FRAME_02B_PATH)
    render_animation(scene)
    write_task_json(task)
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("scene_kind:", CASE.get("scene_kind"))
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
