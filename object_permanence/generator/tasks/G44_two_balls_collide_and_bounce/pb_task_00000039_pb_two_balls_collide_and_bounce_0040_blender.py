# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_TWO_BALLS_COLLIDE_AND_BOUNCE_0040",
  "scene_kind": "two_balls_collide_and_bounce",
  "prompt": "A red ball rolls from left to right and a blue ball rolls from right to left on the same gray straight track. They collide near the center. After the collision the red ball should bounce back to the left and the blue ball should bounce back to the right. The two balls must not pass through each other, merge, disappear, or swap identities."
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


def add_cylinder(name, location, radius, depth, rotation=(0, 0, 0), material=None, role="static_solid", color_name="gray", is_dynamic=False, solid=True, vertices=32):
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


def add_oriented_box(name, center, length, width, height, direction, material, role, color_name, is_dynamic=False, solid=True):
    direction = Vector(direction).normalized()
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.scale = (length / 2.0, width / 2.0, height / 2.0)
    obj.rotation_euler = direction.to_track_quat("X", "Z").to_euler()
    if material is not None:
        obj.data.materials.append(material)
    tag(
        obj,
        name,
        role,
        "dynamic_object" if is_dynamic else ("static_solid" if solid else "non_solid_marker"),
        "oriented_cube",
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
    MATS["glass"] = make_mat("mat_glass", (0.50, 0.82, 1.0), roughness=0.08, alpha=0.32, blend="BLEND")
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
# scene 0036 ring track
# =============================================================================

def build_ring_track_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(0.0, -7.9, 3.00), target=(0.0, 0.0, 0.60), lens=32)

    radius = 1.55
    z = 0.18
    seg_count = 48
    pts = []

    for i in range(seg_count):
        th = 2.0 * math.pi * i / seg_count
        x = radius * math.cos(th)
        y = radius * math.sin(th)
        pts.append((x, y, z))
        add_cube(
            f"gray_ring_track_segment_{i:02d}",
            (x, y, z),
            (0.18, 0.34, 0.08),
            MATS["gray"],
            role="ring_track_segment",
            color_name="gray",
        )

    block = add_cube(
        "opaque_center_block",
        (0.0, 0.18, 0.72),
        (1.44, 1.44, 1.44),
        MATS["dark"],
        role="center_occluder",
        color_name="dark_gray",
    )
    block["pb_occludes_ball"] = True

    ball = add_sphere("orange_ball_on_ring_track", 0.16, (-1.2, -0.9, z + 0.18), MATS["orange"], "orange")
    return {"scene": scene, "kind": "ring_track_ball_behind_center_block", "ball": ball, "radius": radius, "track_z": z}


def animate_ring_track(objs, frame):
    ball = objs["ball"]
    r = objs["radius"]
    z = objs["track_z"]

    # start front-left, move clockwise, hide on far side, reappear right side
    th0 = math.radians(225.0)
    th1 = math.radians(20.0)
    t = (frame - FRAME_START) / float(FRAME_END - FRAME_START)
    theta = th0 + (th1 - th0) * t

    x = r * math.cos(theta)
    y = r * math.sin(theta)
    ball.location = (x, y, z + 0.18)
    ball.rotation_euler = (0.0, -8.0 * t, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)

    if y > 0.55:
        state = "occluded_behind_center_block"
    elif x < 0:
        state = "visible_before_occlusion"
    else:
        state = "visible_after_occlusion"
    ball["pb_state"] = state
    ball["pb_continues_behind_occluder"] = True


# =============================================================================
# scene 0037 drawer
# =============================================================================

def build_drawer_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(2.8, -7.7, 2.25), target=(0.30, 0.0, 0.62), lens=32)

    base_z = 0.34

    # moving outer case
    moving = []

    def moving_case_part(name, rel, dims, mat, role, color="gray"):
        obj = add_cube(
            name,
            (rel[0], rel[1], base_z + rel[2]),
            dims,
            mat,
            role=role,
            color_name=color,
            is_dynamic=True,
            solid=True,
        )
        obj["pb_rel_x"] = rel[0]
        obj["pb_rel_y"] = rel[1]
        obj["pb_rel_z"] = rel[2]
        moving.append(obj)
        return obj

    moving_case_part("drawer_outer_bottom", (0.0, 0.0, 0.0), (1.66, 1.05, 0.10), MATS["light"], "drawer_outer_case")
    moving_case_part("drawer_outer_top", (0.0, 0.0, 0.60), (1.66, 1.05, 0.10), MATS["light"], "drawer_outer_case")
    moving_case_part("drawer_outer_left", (-0.78, 0.0, 0.30), (0.10, 1.05, 0.60), MATS["light"], "drawer_outer_case")
    moving_case_part("drawer_outer_right", (0.78, 0.0, 0.30), (0.10, 1.05, 0.60), MATS["light"], "drawer_outer_case")
    moving_case_part("drawer_outer_back", (0.0, 0.48, 0.30), (1.66, 0.10, 0.60), MATS["light"], "drawer_outer_case")

    # dynamic drawer
    drawer = []

    def drawer_part(name, rel, dims, mat, role, color="gray"):
        obj = add_cube(
            name,
            (rel[0], rel[1], base_z + rel[2]),
            dims,
            mat,
            role=role,
            color_name=color,
            is_dynamic=True,
            solid=True,
        )
        obj["pb_rel_x"] = rel[0]
        obj["pb_rel_y"] = rel[1]
        obj["pb_rel_z"] = rel[2]
        drawer.append(obj)
        return obj

    drawer_part("drawer_floor", (0.0, -0.38, 0.12), (1.24, 0.84, 0.08), MATS["gray"], "drawer_part")
    drawer_part("drawer_left_wall", (-0.57, -0.38, 0.30), (0.08, 0.84, 0.30), MATS["gray"], "drawer_part")
    drawer_part("drawer_right_wall", (0.57, -0.38, 0.30), (0.08, 0.84, 0.30), MATS["gray"], "drawer_part")
    drawer_part("drawer_back_wall", (0.0, 0.00, 0.30), (1.24, 0.08, 0.30), MATS["gray"], "drawer_part")
    drawer_front = drawer_part("drawer_front_panel", (0.0, -0.79, 0.30), (1.24, 0.08, 0.40), MATS["gray"], "drawer_front_panel")
    drawer_front["pb_drawer_front"] = True

    ball = add_sphere("orange_ball_inside_drawer", 0.14, (-0.12, -0.55, base_z + 0.24), MATS["orange"], "orange")
    ball["pb_inside_drawer"] = True

    return {"scene": scene, "kind": "drawer_closes_moves_hidden_ball", "moving": moving, "drawer": drawer, "ball": ball, "base_z": base_z}


def animate_drawer_scene(objs, frame):
    moving = objs["moving"]
    drawer = objs["drawer"]
    ball = objs["ball"]
    base_z = objs["base_z"]

    # drawer open -> close
    if frame <= 55:
        close_frac = smooth01((frame - FRAME_START) / 54.0)
        assembly_shift = 0.0
    else:
        close_frac = 1.0
        if frame <= 95:
            assembly_shift = 1.35 * smooth01((frame - 55) / 40.0)
        else:
            assembly_shift = 1.35

    if frame <= 95:
        reopen_frac = 0.0
    else:
        reopen_frac = smooth01((frame - 95) / 25.0)

    drawer_ext = (1.0 - close_frac) * 0.72 + reopen_frac * 0.72

    for obj in moving:
        x = obj.get("pb_rel_x", 0.0) + assembly_shift
        y = obj.get("pb_rel_y", 0.0)
        z = base_z + obj.get("pb_rel_z", 0.0)
        obj.location = (x, y, z)
        obj.keyframe_insert(data_path="location", frame=frame)
        obj["pb_state"] = "drawer_unit_moving_right" if frame > 55 else "drawer_unit_initial"

    for obj in drawer:
        x = obj.get("pb_rel_x", 0.0) + assembly_shift
        y = obj.get("pb_rel_y", 0.0) - drawer_ext
        z = base_z + obj.get("pb_rel_z", 0.0)
        obj.location = (x, y, z)
        obj.keyframe_insert(data_path="location", frame=frame)
        if frame <= 55:
            state = "closing"
        elif frame <= 95:
            state = "closed_hiding_ball"
        else:
            state = "opening_revealing_ball"
        obj["pb_state"] = state

    ball.location = (-0.12 + assembly_shift, -0.55 - drawer_ext, base_z + 0.24)
    ball.keyframe_insert(data_path="location", frame=frame)
    if frame <= 55:
        ball["pb_state"] = "visible_in_open_drawer" if drawer_ext > 0.10 else "becoming_hidden_in_closing_drawer"
    elif frame <= 95:
        ball["pb_state"] = "hidden_moving_with_closed_drawer"
    else:
        ball["pb_state"] = "visible_again_in_drawer_after_move"
    ball["pb_moves_with_drawer"] = True


# =============================================================================
# scene 0038 bucket
# =============================================================================

def build_bucket_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(2.55, -7.8, 2.35), target=(0.0, 0.0, 0.92), lens=32)

    bucket = []
    base_z = 0.18

    def bucket_part(name, rel, dims, mat, role, color="gray"):
        obj = add_cube(
            name,
            (rel[0], rel[1], base_z + rel[2]),
            dims,
            mat,
            role=role,
            color_name=color,
            is_dynamic=True,
            solid=True,
        )
        obj["pb_rel_x"] = rel[0]
        obj["pb_rel_y"] = rel[1]
        obj["pb_rel_z"] = rel[2]
        bucket.append(obj)
        return obj

    bucket_part("bucket_bottom", (0.0, 0.0, 0.0), (0.96, 0.96, 0.10), MATS["gray"], "bucket_body")
    bucket_part("bucket_left_wall", (-0.43, 0.0, 0.32), (0.10, 0.96, 0.64), MATS["gray"], "bucket_body")
    bucket_part("bucket_right_wall", (0.43, 0.0, 0.32), (0.10, 0.96, 0.64), MATS["gray"], "bucket_body")
    bucket_part("bucket_back_wall", (0.0, 0.43, 0.32), (0.96, 0.10, 0.64), MATS["gray"], "bucket_body")
    bucket_part("bucket_front_wall", (0.0, -0.43, 0.32), (0.96, 0.10, 0.64), MATS["gray"], "bucket_body")

    lid = add_cube(
        "bucket_lid",
        (0.0, 0.0, base_z + 0.70),
        (0.96, 0.96, 0.08),
        MATS["light"],
        role="bucket_lid",
        color_name="light_gray",
        is_dynamic=True,
        solid=True,
    )
    lid["pb_hinge_side"] = "back"
    lid["pb_rel_x"] = 0.0
    lid["pb_rel_y"] = 0.0
    lid["pb_rel_z"] = 0.70

    hook = add_cube("fixed_top_hook_block", (0.0, 0.0, 2.70), (0.24, 0.24, 0.14), MATS["dark"], role="fixed_hook", color_name="dark_gray")
    rope = add_cube("visible_lifting_rope", (0.0, 0.0, 1.55), (0.05, 0.05, 2.10), MATS["dark"], role="lifting_rope", color_name="dark_gray", is_dynamic=True, solid=True)
    rope["pb_is_visible_rope"] = True

    ball = add_sphere("orange_ball_inside_bucket", 0.15, (0.0, 0.0, base_z + 0.22), MATS["orange"], "orange")
    ball["pb_moves_with_bucket"] = True

    return {"scene": scene, "kind": "bucket_closes_and_lifts_hidden_ball", "bucket": bucket, "lid": lid, "rope": rope, "ball": ball, "base_z": base_z}


def animate_bucket_scene(objs, frame):
    bucket = objs["bucket"]
    lid = objs["lid"]
    rope = objs["rope"]
    ball = objs["ball"]
    base_z = objs["base_z"]

    if frame <= 30:
        lid_close = smooth01((frame - FRAME_START) / 29.0)
        lift = 0.0
    else:
        lid_close = 1.0
        if frame <= 90:
            lift = 1.12 * smooth01((frame - 30) / 60.0)
        else:
            lift = 1.12

    if frame <= 90:
        lid_open_end = 0.0
    else:
        lid_open_end = smooth01((frame - 90) / 30.0)

    for obj in bucket:
        x = obj.get("pb_rel_x", 0.0)
        y = obj.get("pb_rel_y", 0.0)
        z = base_z + obj.get("pb_rel_z", 0.0) + lift
        obj.location = (x, y, z)
        obj.keyframe_insert(data_path="location", frame=frame)
        obj["pb_state"] = "bucket_being_lifted" if lift > 0.0 else "bucket_on_floor"

    # lid open at frame1, closed mid, open again at end
    # use x rotation
    open_angle = math.radians(-95.0)
    mid_angle = open_angle * (1.0 - lid_close)
    final_angle = open_angle * lid_open_end
    angle = final_angle if frame > 90 else mid_angle

    lid.location = (0.0, 0.0, base_z + 0.70 + lift)
    lid.rotation_euler = (angle, 0.0, 0.0)
    lid.keyframe_insert(data_path="location", frame=frame)
    lid.keyframe_insert(data_path="rotation_euler", frame=frame)
    if frame <= 30:
        lid["pb_state"] = "closing"
    elif frame <= 90:
        lid["pb_state"] = "closed_hiding_ball"
    else:
        lid["pb_state"] = "opening_revealing_ball"

    # rope shortens as bucket rises
    rope_len = 2.10 - lift
    rope.location = (0.0, 0.0, 2.70 - rope_len / 2.0)
    rope.dimensions = (0.05, 0.05, max(0.30, rope_len))
    rope.keyframe_insert(data_path="location", frame=frame)
    rope.keyframe_insert(data_path="dimensions", frame=frame)
    rope["pb_state"] = "lifting_bucket"

    ball.location = (0.0, 0.0, base_z + 0.22 + lift)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball["pb_state"] = "visible_in_open_bucket" if (frame < 8 or frame > 110) else "hidden_inside_lifted_bucket"
    ball["pb_moves_with_bucket"] = True


# =============================================================================
# scene 0039 three tunnels
# =============================================================================

def build_three_tunnel_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(0.0, -8.2, 2.20), target=(0.40, 0.0, 0.72), lens=31)

    ys = [0.70, 0.0, -0.70]
    for i, y in enumerate(ys):
        add_cube(
            f"parallel_track_{i+1}",
            (0.0, y, 0.06),
            (8.8, 0.28, 0.08),
            MATS["gray"],
            role="parallel_track",
            color_name="gray",
        )

    tunnel = add_cube(
        "wide_opaque_tunnel_structure",
        (0.60, 0.0, 0.70),
        (1.90, 2.30, 1.40),
        MATS["dark"],
        role="wide_tunnel",
        color_name="dark_gray",
    )
    tunnel["pb_occludes_three_balls"] = True

    red = add_sphere("red_ball_top_track", 0.14, (-2.8, ys[0], 0.22), MATS["red"], "red")
    blue = add_sphere("blue_ball_middle_track", 0.14, (-2.8, ys[1], 0.22), MATS["blue"], "blue")
    yellow = add_sphere("yellow_ball_bottom_track", 0.14, (-2.8, ys[2], 0.22), MATS["yellow"], "yellow")

    return {"scene": scene, "kind": "three_balls_parallel_tunnels_identity", "balls": [red, blue, yellow], "ys": ys}


def animate_three_tunnel_scene(objs, frame):
    balls = objs["balls"]
    ys = objs["ys"]

    x = lerp(-2.8, 3.0, (frame - FRAME_START) / float(FRAME_END - FRAME_START))
    names = ["top", "middle", "bottom"]
    colors = ["red", "blue", "yellow"]

    for ball, y, name, color in zip(balls, ys, names, colors):
        ball.location = (x, y, 0.22)
        ball.rotation_euler = (0.0, -0.10 * frame, 0.0)
        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)
        if -0.35 <= x <= 1.55:
            state = f"hidden_inside_{name}_tunnel_path"
        elif x < -0.35:
            state = f"visible_before_tunnel_{name}"
        else:
            state = f"visible_after_tunnel_{name}"
        ball["pb_state"] = state
        ball["pb_identity_color"] = color
        ball["pb_must_not_swap_lanes"] = True


# =============================================================================
# scene 0040 collision
# =============================================================================

def build_collision_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(0.0, -8.0, 2.05), target=(0.0, 0.0, 0.46), lens=31)
    ball_radius = 0.16 * DIVERSITY.get("ball_radius_scale", 1.0)
    ball_z = 0.08 + ball_radius

    add_cube("straight_collision_track", (0.0, 0.0, 0.06), (8.4, 0.32, 0.08), MATS["gray"], role="collision_track", color_name="gray")
    red = add_sphere("red_ball_left", ball_radius, (-2.70, 0.0, ball_z), MATS["red"], "red")
    blue = add_sphere("blue_ball_right", ball_radius, (2.70, 0.0, ball_z), MATS["blue"], "blue")
    return {"scene": scene, "kind": "two_balls_collide_and_bounce", "red": red, "blue": blue}


def animate_collision_scene(objs, frame):
    red = objs["red"]
    blue = objs["blue"]
    ball_radius = 0.16 * DIVERSITY.get("ball_radius_scale", 1.0)
    ball_z = 0.08 + ball_radius

    contact_red_x = -(ball_radius + 0.01)
    contact_blue_x = ball_radius + 0.01

    if frame <= 60:
        t = (frame - FRAME_START) / 59.0
        rx = lerp(-2.70, contact_red_x, t)
        bx = lerp(2.70, contact_blue_x, t)
        red_state = "approaching_collision_from_left"
        blue_state = "approaching_collision_from_right"
    else:
        t = (frame - 60) / 60.0
        rx = lerp(contact_red_x, -2.45, t)
        bx = lerp(contact_blue_x, 2.45, t)
        red_state = "bounced_back_to_left"
        blue_state = "bounced_back_to_right"

    red.location = (rx, 0.0, ball_z)
    blue.location = (bx, 0.0, ball_z)
    red.rotation_euler = (0.0, -0.12 * frame, 0.0)
    blue.rotation_euler = (0.0, 0.12 * frame, 0.0)
    red.keyframe_insert(data_path="location", frame=frame)
    blue.keyframe_insert(data_path="location", frame=frame)
    red.keyframe_insert(data_path="rotation_euler", frame=frame)
    blue.keyframe_insert(data_path="rotation_euler", frame=frame)
    red["pb_state"] = red_state
    blue["pb_state"] = blue_state
    red["pb_no_overlap_with_other_ball"] = True
    blue["pb_no_overlap_with_other_ball"] = True


# =============================================================================
# scene 0041 first ball passes second blocked
# =============================================================================

def build_gate_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(0.0, -8.0, 2.10), target=(0.45, 0.0, 0.55), lens=31)

    add_cube("straight_gate_track", (0.0, 0.0, 0.06), (10.0, 0.32, 0.08), MATS["gray"], role="gate_track", color_name="gray")
    gate = add_cube(
        "dropping_gate_barrier",
        (0.92, 0.0, 1.55),
        (0.16, 0.72, 0.98),
        MATS["dark"],
        role="dropping_gate",
        color_name="dark_gray",
        is_dynamic=True,
        solid=True,
    )
    first = add_sphere("first_orange_ball", 0.14, (-2.60, 0.0, 0.22), MATS["orange"], "orange")
    second = add_sphere("second_orange_ball", 0.14, (-4.95, 0.0, 0.22), MATS["orange"], "orange")
    first["pb_order"] = 1
    second["pb_order"] = 2
    return {"scene": scene, "kind": "first_ball_passes_second_blocked_by_gate", "gate": gate, "first": first, "second": second}


def animate_gate_scene(objs, frame):
    gate = objs["gate"]
    first = objs["first"]
    second = objs["second"]

    # gate open high, then drop
    if frame <= 40:
        gz = 1.55
    elif frame <= 65:
        gz = lerp(1.55, 0.55, smooth01((frame - 40) / 25.0))
    else:
        gz = 0.55

    gate.location = (0.92, 0.0, gz)
    gate.keyframe_insert(data_path="location", frame=frame)
    gate["pb_state"] = "open_high" if frame <= 40 else ("dropping" if frame <= 65 else "closed_blocking")

    # first ball always passes
    fx = lerp(-2.60, 4.25, (frame - FRAME_START) / float(FRAME_END - FRAME_START))
    first.location = (fx, 0.0, 0.22)
    first.rotation_euler = (0.0, -0.11 * frame, 0.0)
    first.keyframe_insert(data_path="location", frame=frame)
    first.keyframe_insert(data_path="rotation_euler", frame=frame)
    first["pb_state"] = "passed_open_gate" if fx > 1.1 else "approaching_open_gate"

    # second ball blocked
    raw_sx = lerp(-4.95, 1.2, (frame - FRAME_START) / float(FRAME_END - FRAME_START))
    stop_x = 0.92 - 0.08 - 0.14 - 0.01
    sx = min(raw_sx, stop_x)
    second.location = (sx, 0.0, 0.22)
    second.rotation_euler = (0.0, -0.10 * frame, 0.0)
    second.keyframe_insert(data_path="location", frame=frame)
    second.keyframe_insert(data_path="rotation_euler", frame=frame)
    second["pb_state"] = "blocked_by_closed_gate" if raw_sx >= stop_x and frame >= 65 else "approaching_gate"
    second["pb_must_not_pass_gate"] = True


# =============================================================================
# scene 0042 transparent cup
# =============================================================================

def build_transparent_cup_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(2.6, -7.8, 2.15), target=(0.35, 0.0, 0.42), lens=32)

    add_cube("flat_surface_for_transparent_cup", (0.0, 0.0, 0.04), (8.0, 2.8, 0.08), MATS["gray"], role="flat_surface", color_name="gray")

    cup_parts = []

    def cup_part(name, rel, dims, role):
        obj = add_cube(
            name,
            (rel[0], rel[1], rel[2]),
            dims,
            MATS["glass"],
            role=role,
            color_name="transparent_blue",
            is_dynamic=True,
            solid=True,
        )
        obj["pb_rel_x"] = rel[0]
        obj["pb_rel_y"] = rel[1]
        obj["pb_rel_z"] = rel[2]
        obj["pb_transparent"] = True
        obj["pb_solid"] = True
        cup_parts.append(obj)
        return obj

    # open-bottom cup
    cup_part("transparent_cup_top", (-1.20, 0.0, 0.90), (1.00, 1.00, 0.08), "transparent_cup_part")
    cup_part("transparent_cup_left_wall", (-1.62, 0.0, 0.48), (0.08, 1.00, 0.84), "transparent_cup_part")
    cup_part("transparent_cup_right_wall", (-0.78, 0.0, 0.48), (0.08, 1.00, 0.84), "transparent_cup_part")
    cup_part("transparent_cup_back_wall", (-1.20, 0.42, 0.48), (1.00, 0.08, 0.84), "transparent_cup_part")
    cup_part("transparent_cup_front_wall", (-1.20, -0.42, 0.48), (1.00, 0.08, 0.84), "transparent_cup_part")

    ball = add_sphere("orange_ball_inside_transparent_cup", 0.16, (-1.20, 0.0, 0.20), MATS["orange"], "orange")
    ball["pb_inside_transparent_cup"] = True

    return {"scene": scene, "kind": "transparent_cup_traps_ball_and_moves", "cup_parts": cup_parts, "ball": ball}


def animate_transparent_cup_scene(objs, frame):
    cup_parts = objs["cup_parts"]
    ball = objs["ball"]

    shift = lerp(0.0, 2.25, (frame - FRAME_START) / float(FRAME_END - FRAME_START))

    for obj in cup_parts:
        x = obj.get("pb_rel_x", 0.0) + shift
        y = obj.get("pb_rel_y", 0.0)
        z = obj.get("pb_rel_z", 0.0)
        obj.location = (x, y, z)
        obj.keyframe_insert(data_path="location", frame=frame)
        obj["pb_state"] = "transparent_cup_sliding_right"

    # keep ball inside, moving with cup
    ball.location = (-1.20 + shift, 0.0, 0.20)
    ball.rotation_euler = (0.0, -0.10 * frame, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball["pb_state"] = "moving_inside_transparent_cup"
    ball["pb_must_not_pass_transparent_walls"] = True


# =============================================================================
# dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "ring_track_ball_behind_center_block":
        return build_ring_track_scene()
    if kind == "drawer_closes_moves_hidden_ball":
        return build_drawer_scene()
    if kind == "bucket_closes_and_lifts_hidden_ball":
        return build_bucket_scene()
    if kind == "three_balls_parallel_tunnels_identity":
        return build_three_tunnel_scene()
    if kind == "two_balls_collide_and_bounce":
        return build_collision_scene()
    if kind == "first_ball_passes_second_blocked_by_gate":
        return build_gate_scene()
    if kind == "transparent_cup_traps_ball_and_moves":
        return build_transparent_cup_scene()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "ring_track_ball_behind_center_block":
            animate_ring_track(objs, frame)
        elif kind == "drawer_closes_moves_hidden_ball":
            animate_drawer_scene(objs, frame)
        elif kind == "bucket_closes_and_lifts_hidden_ball":
            animate_bucket_scene(objs, frame)
        elif kind == "three_balls_parallel_tunnels_identity":
            animate_three_tunnel_scene(objs, frame)
        elif kind == "two_balls_collide_and_bounce":
            animate_collision_scene(objs, frame)
        elif kind == "first_ball_passes_second_blocked_by_gate":
            animate_gate_scene(objs, frame)
        elif kind == "transparent_cup_traps_ball_and_moves":
            animate_transparent_cup_scene(objs, frame)
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
