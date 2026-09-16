# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_PICKET_FENCE_FLICKER_0148",
  "scene_kind": "picket_fence_flicker",
  "kind": "picket_fence_flicker",
  "prompt": "A ball rolls at a steady speed along a straight rail behind a row of evenly spaced vertical posts. As it passes behind each post it is briefly hidden, then reappears in the gap between posts — the same ball, moving at the same speed — and rolls on past the last post."
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

    # Rolling ball: warm red so it reads clearly against the gray posts.
    MATS["coin"] = make_mat("mat_ball", (0.90, 0.20, 0.16), roughness=0.35, metallic=0.0)
    MATS["coin_rim"] = make_mat("mat_post", (0.40, 0.42, 0.47), roughness=0.70)


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
# 00000147  picket_fence_flicker  (Cluster: Baillargeonian Occlusion)
# =============================================================================
#
# A ball rolls at CONSTANT speed left->right along a straight flat rail. A row
# of N tall thin vertical POSTS stands in a plane BETWEEN the camera and the
# ball (nearer the camera in -y). As the ball passes behind each post it is
# briefly hidden; in the gaps between posts it reappears. It is never deleted
# -- only occluded by the geometry of the posts (real geometric occlusion, no
# hide_render trickery). The ball rolls on past the last post at the far right.
# =============================================================================


def _fence_params():
    z_track_top = 0.62
    track_thick = 0.16
    ball_radius = 0.30
    x_span = 3.35            # ball travels from -x_span to +x_span
    n_posts = 5
    post_w = 0.46            # post thickness (x): wide enough for solid occlusion
    post_depth = 0.22        # post depth (y)
    post_h = 1.9             # tall enough to fully cover the ball
    return {
        "z_track_top": z_track_top,
        "track_thick": track_thick,
        "ball_radius": ball_radius,
        "x_span": x_span,
        "n_posts": n_posts,
        "post_w": post_w,
        "post_depth": post_depth,
        "post_h": post_h,
    }


def build_picket_fence_flicker_scene():
    # Nearly head-on, slightly raised front view so the picket row reads as a
    # foreground fence and the ball is clearly seen flickering through the gaps.
    scene = setup_base(
        camera_loc=(0.0, -9.0, 2.4),
        target=(0.0, 0.55, 1.0),
        ortho_scale=8.6,
    )

    P = _fence_params()
    z_top = P["z_track_top"]
    track_thick = P["track_thick"]
    ball_radius = P["ball_radius"]
    x_span = P["x_span"]
    n_posts = P["n_posts"]
    post_w = P["post_w"]
    post_depth = P["post_depth"]
    post_h = P["post_h"]

    ball_z = z_top + ball_radius
    z_slab_c = z_top - track_thick / 2.0

    # The ball rolls along the rail at rail_y; the posts stand nearer the camera.
    rail_y = 0.55
    post_y = rail_y - (ball_radius + post_depth / 2.0 + 0.28)  # clearly in front of the ball

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

    # ---- Row of tall thin opaque posts (between camera and the ball) ---------
    # Evenly spaced across the travel span. Post centers are inset so the ball
    # is visible before the first and after the last post. A thin rail cap +
    # base ground the posts so they read as a picket fence, not floating slabs.
    post_bottom_z = z_top - 0.01
    post_cz = post_bottom_z + post_h / 2.0
    first_x = -x_span + 0.55
    last_x = x_span - 0.55
    spacing = (last_x - first_x) / (n_posts - 1)
    post_xs = [first_x + i * spacing for i in range(n_posts)]
    for i, px in enumerate(post_xs):
        add_cube(
            "picket_post_%02d" % i,
            (px, post_y, post_cz),
            (post_w, post_depth, post_h),
            MATS["coin_rim"], "occluder_post", "gray",
        )
    # Top rail connecting the pickets (thin, above the ball's occlusion band so
    # it does not add extra hiding, purely reads as a fence).
    add_cube(
        "picket_top_rail",
        (0.0, post_y, post_bottom_z + post_h + 0.06),
        (2.0 * x_span + 0.4, post_depth + 0.02, 0.10),
        MATS["housing"], "fence_rail", "gray",
    )

    # ---- The rolling ball ----------------------------------------------------
    ball = add_ball(
        "rolling_ball",
        (-x_span, rail_y, ball_z),
        ball_radius,
        MATS["coin"], "target", "red",
        is_dynamic=True,
    )
    ball["pb_path"] = "left_to_right_behind_row_of_posts_repeated_flicker_occlusion"
    ball["pb_can_disappear"] = False

    return scene, {
        "ball": ball,
        "ball_radius": ball_radius,
        "ball_z": ball_z,
        "rail_y": rail_y,
        "x_span": x_span,
        "post_xs": post_xs,
        "post_w": post_w,
    }


def animate_picket_fence_flicker(scene, meta):
    ball = meta["ball"]
    radius = meta["ball_radius"]
    ball_z = meta["ball_z"]
    rail_y = meta["rail_y"]
    x_span = meta["x_span"]
    post_xs = meta["post_xs"]
    post_w = meta["post_w"]

    # Constant-speed roll from -x_span to +x_span across the full clip. The
    # ball is occluded purely by the post geometry sitting between it and the
    # camera; we do NOT hide the ball, so occlusion is genuinely geometric.
    rest_frames = 6
    move_frames = float(FRAME_END - rest_frames)
    speed = (2.0 * x_span) / (move_frames / FPS)

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= rest_frames:
            s = 0.0
        else:
            t = (frame - rest_frames) / FPS
            s = min(2.0 * x_span, speed * t)

        xb = -x_span + s
        ball.location = (xb, rail_y, ball_z)
        # No-slip rolling spin about the y axis (top of ball moves +x forward).
        ball.rotation_euler = (0.0, -s / radius, 0.0)

        # Semantic tag: is the ball currently behind a post (from camera view)?
        behind_post = any(abs(xb - px) <= (post_w / 2.0 + radius) for px in post_xs)

        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)

        if behind_post:
            ball["pb_state"] = "hidden_behind_post"
        elif xb >= post_xs[-1]:
            ball["pb_state"] = "past_last_post_visible"
        else:
            ball["pb_state"] = "visible_in_gap_between_posts"
        ball["pb_occluded"] = bool(behind_post)
        ball["pb_pos_x"] = float(xb)

    scene.frame_set(FRAME_START)


# =============================================================================
# Dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE.get("scene_kind", CASE.get("kind"))

    if kind == "picket_fence_flicker":
        return build_picket_fence_flicker_scene()

    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(scene, meta):
    kind = CASE.get("scene_kind", CASE.get("kind"))

    if kind == "picket_fence_flicker":
        return animate_picket_fence_flicker(scene, meta)

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
