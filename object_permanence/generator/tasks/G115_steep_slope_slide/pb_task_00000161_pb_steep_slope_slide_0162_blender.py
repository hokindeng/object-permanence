# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_STEEP_SLOPE_SLIDE_0162",
  "scene_kind": "steep_slope_slide",
  "prompt": "A ball starts at the top of a steep ramp with a modest rightward push. It slides and rolls down the slope, accelerating under gravity, reaches the bottom, and continues rolling along the floor while gradually slowing to a stop. It is never suspended in the air."
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


def add_wedge(name, profile_xz, y_half, material=None, role="static_ramp", color_name="gray", solid=True):
    """Build a solid triangular-prism ramp resting on the floor. profile_xz is a
    triple of (x, z) points ((top_back), (toe), (back_bottom)) in the XZ plane;
    the prism is extruded in Y by +/- y_half. The (top_back -> toe) edge is the
    slide surface the ball rides on; the (top_back -> back_bottom) edge is the
    vertical back face and (back_bottom -> toe) is the base on the floor."""
    (ax, az), (bx, bz), (cx, cz) = profile_xz
    verts = [
        (ax, -y_half, az), (bx, -y_half, bz), (cx, -y_half, cz),
        (ax, y_half, az), (bx, y_half, bz), (cx, y_half, cz),
    ]
    faces = [
        (0, 2, 1),        # -Y triangle end cap
        (3, 4, 5),        # +Y triangle end cap
        (0, 1, 4, 3),     # top slide surface (top_back -> toe)
        (1, 2, 5, 4),     # base on the floor (toe -> back_bottom)
        (2, 0, 3, 5),     # vertical back face (back_bottom -> top_back)
    ]
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if material is not None:
        obj.data.materials.append(material)
    tag(obj, name, role, "static_solid" if solid else "non_solid_marker", "wedge", color_name, False, solid=solid)
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
    MATS["dark"] = make_mat("mat_dark_gray", (0.14, 0.14, 0.16), roughness=0.88)
    MATS["ramp"] = make_mat("mat_ramp", (0.74, 0.55, 0.35), roughness=0.70)
    MATS["ramp_track"] = make_mat("mat_ramp_track", (0.86, 0.73, 0.55), roughness=0.72)
    MATS["frame"] = make_mat("mat_frame", (0.40, 0.41, 0.43), roughness=0.62)
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
# 0162 steep slope slide
#
# A steep solid ramp (triangular wedge) rests on the floor, its high end on the
# left. A ball starts at the top of the slope with a modest rightward push. It
# slides/rolls DOWN the slope, accelerating under gravity, reaches the bottom,
# and then continues rolling along the flat floor in +X, decelerating (friction)
# until it comes to rest. The ball center rides exactly one radius above the
# slide surface (offset along the surface normal) and one radius above the floor,
# so it never penetrates the ramp and is never suspended in the air.
# ============================================================

def build_steep_slope_slide_scene():
    scene = build_base_scene()
    # Front / three-quarter view so the whole steep slope, the descent, and the
    # roll-out along the floor are all visible.
    setup_camera(scene, location=(-0.6, -9.6, 3.1), target=(0.5, 0.0, 1.05), lens=29)

    BALL_R = 0.24

    # Ball-CENTER endpoints. On the slope the center travels this straight line;
    # its bottom z equals the floor rest height (BALL_R), so the transition onto
    # the floor is smooth (no dip / no hop).
    C_top = Vector((-2.20, 0.0, 2.40))
    C_bot = Vector((0.80, 0.0, BALL_R))

    slope_vec = C_bot - C_top
    slope_len = slope_vec.length
    d_hat = slope_vec.normalized()
    # Upward surface normal (perpendicular to the slope in the XZ plane).
    n_hat = Vector((-d_hat.z, 0.0, d_hat.x)).normalized()

    # Slide SURFACE points (one radius below the ball center along the normal).
    S_top = C_top - n_hat * BALL_R
    S_bot = C_bot - n_hat * BALL_R

    # Extend the slide line downhill to the floor (z = 0) to get the ramp toe.
    if abs(d_hat.z) > 1e-6:
        k_toe = S_top.z / (-d_hat.z)
    else:
        k_toe = 0.0
    toe = S_top + d_hat * k_toe   # z ~= 0 on the floor

    # Build the solid triangular wedge ramp resting on the floor.
    profile = [
        (S_top.x, S_top.z),   # top_back  (high, left)
        (toe.x, 0.0),         # toe       (on the floor, right)
        (S_top.x, 0.0),       # back_bot  (on the floor, below top_back)
    ]
    add_wedge(
        "steep_ramp_wedge",
        profile,
        y_half=0.85,
        material=MATS["ramp"],
        role="steep_ramp",
        color_name="warm_wood",
        solid=True,
    )

    # A brighter narrow track strip laid flush on the slide surface as a visual
    # cue for the slope face (thin slab centered on the slide line).
    strip_center = (S_top + S_bot) / 2.0 + n_hat * 0.012
    strip_ang = math.atan2(-d_hat.z, d_hat.x)   # slope pitch about Y
    strip = add_cube(
        "ramp_track_strip",
        (strip_center.x, 0.0, strip_center.z),
        (slope_len * 0.98, 0.55, 0.02),
        MATS["ramp_track"],
        role="ramp_track",
        color_name="pale",
        solid=False,
    )
    strip.rotation_euler = (0.0, strip_ang, 0.0)

    # --- Ball, resting at the top of the slope -------------------------------
    ball = add_sphere(
        "orange_ball_sliding_down_slope",
        BALL_R,
        (C_top.x, C_top.y, C_top.z),
        MATS["orange"],
        "orange",
        # Keep "slides" out of this ball's role: it contains "lid", and
        # render.py's is_target() matches apparatus keywords by substring, so
        # the target ball would be classed as rig apparatus and repainted muted.
        role="ball_descends_steep_slope",
    )
    ball["pb_expected_behavior"] = "slide_down_slope_then_roll_out_on_floor_to_rest"

    return {
        "scene": scene,
        "kind": "steep_slope_slide",
        "ball": ball,
        "ball_r": BALL_R,
        "C_top": C_top,
        "C_bot": C_bot,
        "slope_len": slope_len,
    }


def animate_steep_slope_slide(objs, frame):
    ball = objs["ball"]
    ball_r = objs["ball_r"]
    C_top = objs["C_top"]
    C_bot = objs["C_bot"]
    slope_len = objs["slope_len"]

    # Timeline:
    #   Phase 0 (1..HOLD_END): ball poised at the top of the slope.
    #   Phase 1 (HOLD_END..SLOPE_END): slide down the slope. Distance along the
    #     slope = slope_len * ((1-c) t^2 + c t): a modest initial (rightward)
    #     velocity c plus constant acceleration, so velocity grows monotonically.
    #   Phase 2 (SLOPE_END..FLOOR_END): roll along the floor in +X, carrying the
    #     slope-exit velocity and decelerating (constant friction) to a stop.
    #   Phase 3 (after FLOOR_END): at rest on the floor.
    HOLD_END = 6
    SLOPE_END = 54
    c = 0.35                       # initial rightward velocity fraction (modest)
    n_slope = SLOPE_END - HOLD_END

    # Velocity (units/frame) at the bottom of the slope, carried onto the floor.
    v_join = slope_len * (2.0 - c) / float(n_slope)
    D_f = 2.4                      # roll-out distance on the floor before stopping
    a_f = v_join * v_join / (2.0 * D_f)     # constant floor deceleration
    n_floor = max(1, int(round(v_join / a_f)))
    FLOOR_END = SLOPE_END + n_floor

    if frame <= HOLD_END:
        pos = C_top.copy()
        s_dist = 0.0
        state = "poised_at_top_of_slope"
    elif frame <= SLOPE_END:
        tau = (frame - HOLD_END) / float(n_slope)
        s_frac = (1.0 - c) * tau * tau + c * tau
        pos = C_top + (C_bot - C_top) * s_frac
        s_dist = slope_len * s_frac
        state = "sliding_down_slope"
    else:
        m = min(frame, FLOOR_END) - SLOPE_END
        q = v_join * m - 0.5 * a_f * m * m
        q = max(0.0, min(D_f, q))
        pos = C_bot + Vector((1.0, 0.0, 0.0)) * q
        s_dist = slope_len + q
        state = "rolling_on_floor" if frame < FLOOR_END else "at_rest_on_floor"

    ball.location = (pos.x, 0.0, pos.z)
    # Rolling: rolls forward in +X, so it spins negatively about Y; angle = arc/R.
    ball.rotation_euler = (0.0, -s_dist / ball_r, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball["pb_state"] = state
    ball["pb_never_suspended"] = True
    ball["pb_never_passes_through_ramp"] = True


# ============================================================
# Build / animate dispatch
# ============================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "steep_slope_slide":
        return build_steep_slope_slide_scene()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "steep_slope_slide":
            animate_steep_slope_slide(objs, frame)
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
