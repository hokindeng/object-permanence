# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_LOOP_THE_LOOP_OCCLUDED_0122",
  "scene_kind": "ball_behind_rotating_billboard",
  "kind": "ball_behind_rotating_billboard",
  "prompt": "A ball rolls from left to right at a steady speed while remaining in contact with the top of a straight raised rail. In front of the rail, a large opaque billboard mounted at its center on a vertical post rotates clockwise as viewed from above, turning from edge-on to broadside and then edge-on again. When the ball passes behind the broadside panel, it becomes fully hidden for a moment, then reappears on the right and continues at the same speed. The same ball preserves its identity, color, size, and continuous motion throughout."
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
            mat.blend_method = "HASHED"
            mat.show_transparent_back = False
            mat.use_screen_refraction = False
        except Exception:
            pass
        try:
            mat.surface_render_method = "DITHERED"
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
    MATS["track"] = make_mat("mat_track", (0.55, 0.56, 0.60), roughness=0.45, metallic=0.3)

    MATS["red"] = make_mat("mat_red", (0.92, 0.18, 0.18), roughness=0.28)
    MATS["blue"] = make_mat("mat_blue", (0.16, 0.36, 0.95), roughness=0.28)
    MATS["yellow"] = make_mat("mat_yellow", (0.98, 0.78, 0.15), roughness=0.28)
    MATS["orange"] = make_mat("mat_orange", (0.97, 0.45, 0.10), roughness=0.28)
    MATS["glass"] = make_mat("mat_glass", (0.60, 0.80, 1.0), roughness=0.08, alpha=0.24, transparent=True)


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


def add_sphere(name, radius, location, material, color_name, role="target", is_dynamic=True):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=48, ring_count=24)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)

    tag(
        obj,
        name,
        role,
        "dynamic_object" if is_dynamic else "static_solid",
        "sphere",
        color_name,
        is_dynamic,
        solid=True,
        pb_radius=radius,
    )
    return obj


def add_cylinder(name, location, radius, depth, material, role, color_name, rotation=(0.0, 0.0, 0.0), is_dynamic=False):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, vertices=24, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    if material is not None:
        obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "cylinder", color_name, is_dynamic, solid=True)
    return obj


def add_torus(name, location, major_radius, minor_radius, material, role, color_name, rotation=(0.0, 0.0, 0.0), solid=True, **extras):
    bpy.ops.mesh.primitive_torus_add(
        location=location,
        major_radius=major_radius,
        minor_radius=minor_radius,
        major_segments=64,
        minor_segments=16,
    )
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = rotation
    if material is not None:
        obj.data.materials.append(material)
    tag(obj, name, role, "static_solid", "torus", color_name, False, solid=solid, **extras)
    return obj


def add_oriented_box(name, location, dimensions, material, role, color_name, rotation=(0.0, 0.0, 0.0), is_dynamic=False, solid=True):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.rotation_euler = rotation

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
# 00000121  ball_behind_rotating_billboard  (Cluster: Baillargeonian Occlusion)
# =============================================================================


PANEL_W = 1.95   # billboard panel width (X, when broadside)


def build_ball_behind_rotating_billboard():
    # A ball rolls at a steady speed along a straight rail. A large opaque billboard
    # panel stands on a vertical post IN FRONT of the rail (between the camera and the
    # ball) and rotates about the post. As it turns broadside it fully hides the ball
    # for a moment; as it turns edge-on the ball is revealed, continuing at the same
    # speed. The occlusion is GEOMETRIC (the panel really blocks the camera's line of
    # sight), so the ball is genuinely hidden, never deleted, and reappears unchanged.
    scene = setup_base(
        camera_loc=(0.0, -7.8, 2.9),
        target=(0.0, 0.15, 0.55),
        ortho_scale=8.8,
    )

    ball_radius = 0.24
    track_center_z = 0.045
    track_thickness = 0.09
    track_top_z = track_center_z + track_thickness / 2.0
    ball_z = track_top_z + ball_radius

    # Straight rail the ball rolls along (X axis) -- a low flat track.
    add_cube("ball_track_rail", (0.0, 0.0, track_center_z), (7.4, 0.46, track_thickness),
             MATS["track"], "track", "steel_gray")

    # --- Rotating billboard: vertical post + flat opaque panel -----------------
    post_y = -0.98                      # IN FRONT of the ball plane (toward camera)
    post_h = 2.0
    add_cylinder("billboard_post", (0.0, post_y, post_h / 2.0), 0.06, post_h,
                 MATS["support"], "billboard_post", "dark_gray")

    panel_t, panel_h = 0.09, 1.55
    panel_cz = 0.10 + panel_h / 2.0
    # The panel origin is its center == the post axis, so a Z-rotation spins it about
    # the post. At angle 0 the wide face (spanning X) is broadside to the camera and
    # covers the ball; at +/-90 deg it is edge-on (thin) and reveals the ball.
    panel = add_oriented_box(
        "billboard_panel",
        (0.0, post_y, panel_cz),
        (PANEL_W, panel_t, panel_h),
        MATS["housing"],
        "rotating_occluder_billboard",
        "gray",
        rotation=(0.0, 0.0, 0.0),
        solid=True,
    )
    panel["pb_is_rotating_occluder"] = True

    # --- The ball at its start (far -X end of the rail) ------------------------
    x_start, x_end = -3.25, 3.25
    ball = add_sphere("billboard_ball", ball_radius, (x_start, 0.0, ball_z),
                      MATS["orange"], "orange")
    ball["pb_path"] = "rolls_straight_briefly_hidden_behind_rotating_billboard_reappears_same"
    ball["pb_can_disappear"] = False

    return scene, {
        "ball": ball,
        "panel": panel,
        "ball_radius": ball_radius,
        "ball_z": ball_z,
        "x_start": x_start,
        "x_end": x_end,
    }


def animate_ball_behind_rotating_billboard(scene, meta):
    ball = meta["ball"]
    panel = meta["panel"]
    radius = meta["ball_radius"]
    x_start = meta["x_start"]
    x_end = meta["x_end"]
    ball_z = meta["ball_z"]

    rest_frames = 6
    roll_end = FRAME_END - 6                          # steady roll rest..roll_end
    center_frame = (rest_frames + roll_end) // 2      # ball at rail center here

    # Panel angular speed: broadside (0 deg) exactly at center_frame, reaching edge-on
    # (+/-90 deg) ~20 frames either side. Positive-to-negative Z rotation is clockwise
    # when viewed from above, matching the prompt and making the sweep unambiguous.
    deg_per_frame = 4.5
    max_deg = 90.0

    def panel_angle_deg(frame):
        return max(-max_deg, min(max_deg, -deg_per_frame * (frame - center_frame)))

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        # --- Ball: steady constant-velocity roll (permanence: reappears on time) ---
        if frame <= rest_frames:
            t = 0.0
        elif frame >= roll_end:
            t = 1.0
        else:
            t = (frame - rest_frames) / float(roll_end - rest_frames)
        bx = x_start + (x_end - x_start) * t
        ball.location = (bx, 0.0, ball_z)
        ball.rotation_euler = (0.0, (bx - x_start) / radius, 0.0)
        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)

        # --- Billboard: rotate about the post (vertical Z axis) ---
        ang = panel_angle_deg(frame)
        panel.rotation_euler = (0.0, 0.0, math.radians(ang))
        panel.keyframe_insert(data_path="rotation_euler", frame=frame)
        panel["pb_angle_deg"] = float(ang)

        # Geometrically hidden when the panel is near broadside AND the ball lies
        # within the panel's projected X-coverage (the ball is behind the panel).
        covered_half = 0.5 * PANEL_W * math.cos(math.radians(ang))
        hidden = (abs(ang) < 42.0) and (abs(bx) < covered_half)
        ball["pb_state"] = "hidden_behind_rotating_billboard" if hidden else "visible_rolling_on_rail"
        ball["pb_occluded"] = bool(hidden)

    scene.frame_set(FRAME_START)


# =============================================================================
# Dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE.get("scene_kind", CASE.get("kind"))

    if kind == "ball_behind_rotating_billboard":
        return build_ball_behind_rotating_billboard()

    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(scene, meta):
    kind = CASE.get("scene_kind", CASE.get("kind"))

    if kind == "ball_behind_rotating_billboard":
        return animate_ball_behind_rotating_billboard(scene, meta)

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
