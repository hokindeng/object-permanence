# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_TWO_TIER_TRAPDOOR_CASCADE_0116",
  "scene_kind": "two_tier_trapdoor_cascade",
  "prompt": "A ball rests on an upper platform that has a hinged trapdoor. The trapdoor opens and the ball falls through onto a lower platform below, makes two small diminishing rebounds, and settles. That lower platform then opens its own trapdoor, and the ball falls again down to the floor, where it makes two smaller rebounds before settling. Each fall accelerates under gravity; the ball is never left suspended after a trapdoor opens."
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
    MATS["dark"] = make_mat("mat_dark_gray", (0.04, 0.04, 0.05), roughness=0.92)
    MATS["box"] = make_mat("mat_box_gray", (0.38, 0.39, 0.40), roughness=0.78)
    MATS["edge"] = make_mat("mat_light_edge", (0.62, 0.63, 0.64), roughness=0.68)
    MATS["trap"] = make_mat("mat_trapdoor", (0.52, 0.40, 0.30), roughness=0.66)
    MATS["hinge"] = make_mat("mat_hinge", (0.20, 0.20, 0.22), roughness=0.45, metallic=0.6)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.38, 0.06), roughness=0.30)
    MATS["red"] = make_mat("mat_red", (0.85, 0.12, 0.10), roughness=0.32)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (9.8, 4.8, 0.10), MATS["floor"], role="ground", color_name="warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 2.42, 1.90), (10.0, 0.08, 4.20), MATS["backdrop"], role="background", color_name="off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.8, -4.4, 6.2))
    key = bpy.context.object
    key.name = "large_softbox_light"
    key.data.energy = 1050
    key.data.size = 6.0

    bpy.ops.object.light_add(type="POINT", location=(3.7, -2.8, 3.6))
    fill = bpy.context.object
    fill.name = "right_fill_light"
    fill.data.energy = 165

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
# A platform with a REAL rectangular opening + a hinged trapdoor
# panel that covers it. The panel rotates open about a hinge edge.
# ============================================================

def create_platform_with_trapdoor(name, center, plate_size, plate_thick, opening_w, opening_d, top_z,
                                   hinge_side=+1, leg_base_z=0.0):
    """Build a gray square platform (a flat plate) on four legs with a REAL
    rectangular opening punched through its middle (boolean DIFFERENCE), plus a
    hinged rectangular trapdoor PANEL that sits flush in the opening and can be
    rotated open about a hinge edge.

    center=(cx,cy); top_z is the platform TOP surface z.
    opening_w = opening size along X (the gap the ball drops through)
    opening_d = opening size along Y
    hinge_side = +1 -> hinge on +X edge of opening (panel swings down toward +X)
                -1 -> hinge on -X edge.

    Returns dict with 'plate', 'panel', and hinge pivot info.
    """
    cx, cy = center[0], center[1]
    plate_center_z = top_z - plate_thick / 2.0

    body = add_cube(
        name,
        (cx, cy, plate_center_z),
        (plate_size, plate_size, plate_thick),
        MATS["gray"],
        role="platform_with_trapdoor",
        color_name="gray",
        solid=True,
    )
    body["pb_has_trapdoor_opening"] = True
    body["pb_opening_w"] = float(opening_w)
    body["pb_opening_d"] = float(opening_d)
    body["pb_opening_center_z"] = float(top_z)

    # Rectangular cutter punches a real opening straight down through the plate.
    cutter = add_cube(
        f"{name}_opening_cutter",
        (cx, cy, plate_center_z),
        (opening_w, opening_d, plate_thick * 4.0),
        None,
        role="cutter",
        solid=False,
    )
    mod = body.modifiers.new(name="opening_boolean", type="BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    bpy.context.view_layer.objects.active = body
    body.select_set(True)
    try:
        bpy.ops.object.modifier_apply(modifier=mod.name)
    except Exception:
        pass
    try:
        bpy.data.objects.remove(cutter, do_unlink=True)
    except ReferenceError:
        pass

    # A dark rim around the opening so the gap reads as a real hole with a crisp
    # dark contour (hollow ring: difference the interior out, like the plate).
    rim = add_cube(
        f"{name}_opening_rim",
        (cx, cy, plate_center_z),
        (opening_w + 0.10, opening_d + 0.10, plate_thick + 0.012),
        MATS["dark"],
        role="opening_rim",
        color_name="near_black",
        solid=False,
    )
    rim_cutter = add_cube(
        f"{name}_rim_cutter",
        (cx, cy, plate_center_z),
        (opening_w, opening_d, plate_thick + 0.5),
        None,
        role="cutter",
        solid=False,
    )
    rmod = rim.modifiers.new(name="rim_hollow", type="BOOLEAN")
    rmod.operation = "DIFFERENCE"
    rmod.object = rim_cutter
    bpy.context.view_layer.objects.active = rim
    rim.select_set(True)
    try:
        bpy.ops.object.modifier_apply(modifier=rmod.name)
    except Exception:
        pass
    try:
        bpy.data.objects.remove(rim_cutter, do_unlink=True)
    except ReferenceError:
        pass
    rim["pb_is_opening_rim"] = True

    # ---- Hinged trapdoor PANEL ----
    # The panel fills the opening. Its rotation pivot is the hinge edge (one X-edge
    # of the opening). We place the panel mesh so its own origin sits on the hinge
    # edge; then rotating about Y swings the free edge down.
    panel_thick = plate_thick * 0.9
    hinge_x = cx + hinge_side * (opening_w / 2.0)
    panel_center_z = top_z - panel_thick / 2.0
    # Panel spans from hinge edge toward the opposite edge. Build it centered, then
    # move origin to hinge edge via delta offset in the location math at animate time.
    panel = add_cube(
        f"{name}_trapdoor_panel",
        (cx, cy, panel_center_z),
        (opening_w * 0.98, opening_d * 0.98, panel_thick),
        MATS["trap"],
        role="trapdoor_panel",
        color_name="brown",
        solid=True,
    )
    # Move the panel's ORIGIN to the hinge edge so rotation swings about that edge.
    # We do this by setting the mesh data offset: shift geometry so origin is at hinge.
    dx = -(hinge_x - cx)  # geometry offset relative to origin placed at hinge_x
    for v in panel.data.vertices:
        v.co.x += dx
    panel.location = (hinge_x, cy, panel_center_z)
    panel["pb_is_trapdoor_panel"] = True
    panel["pb_hinge_x"] = float(hinge_x)
    panel["pb_hinge_side"] = int(hinge_side)
    panel["pb_panel_rest_z"] = float(panel_center_z)

    # A small dark hinge bar along the hinge edge (decorative depth cue).
    hinge_bar = add_cube(
        f"{name}_hinge_bar",
        (hinge_x, cy, top_z - 0.008),
        (0.06, opening_d * 0.98, 0.05),
        MATS["hinge"],
        role="hinge_bar",
        color_name="dark_metal",
        solid=True,
    )
    hinge_bar["pb_is_hinge"] = True

    # Four legs supporting the plate down to leg_base_z (floor, or the tier below).
    leg_h = (top_z - plate_thick) - leg_base_z
    if leg_h > 0.02:
        leg_z = leg_base_z + leg_h / 2.0
        inset = plate_size / 2.0 - 0.18
        for sx in (-inset, inset):
            for sy in (-inset, inset):
                add_cube(
                    f"{name}_leg_{('n' if sy > 0 else 's')}{('e' if sx > 0 else 'w')}",
                    (cx + sx, cy + sy, leg_z),
                    (0.12, 0.12, leg_h),
                    MATS["edge"],
                    role="platform_leg",
                    color_name="light_gray",
                    solid=True,
                )

    return {
        "plate": body,
        "panel": panel,
        "hinge_x": hinge_x,
        "hinge_side": hinge_side,
        "opening_w": opening_w,
        "opening_d": opening_d,
        "top_z": top_z,
        "panel_thick": panel_thick,
    }


# ============================================================
# 0116 two tier trapdoor cascade
# ============================================================

def build_two_tier_trapdoor_cascade_scene():
    scene = build_base_scene()
    # Front/side 3/4 camera set low enough to see BOTH tiers and both falls clearly.
    setup_camera(scene, location=(-1.0, -7.6, 2.8), target=(0.0, 0.0, 1.55), lens=32)

    UPPER_TOP_Z = 2.85
    LOWER_TOP_Z = 1.45
    FLOOR_Z = 0.0

    plate_size = 2.4
    plate_thick = 0.12
    OPENING_W = 1.05  # wide opening along X (ball drops through here)
    OPENING_D = 1.05

    BALL_R = 0.34  # clearly narrower than the opening -> passes cleanly, no clipping

    # Upper platform: hinge on +X edge -> panel swings open toward +X / downward.
    upper = create_platform_with_trapdoor(
        "upper_platform_with_trapdoor",
        (0.0, 0.0),
        plate_size,
        plate_thick,
        OPENING_W,
        OPENING_D,
        UPPER_TOP_Z,
        hinge_side=+1,
        leg_base_z=LOWER_TOP_Z,
    )

    # Lower platform: offset legs so they don't sit under the upper opening. Hinge on
    # -X edge so the two trapdoors swing to opposite sides (visually distinct).
    lower = create_platform_with_trapdoor(
        "lower_platform_with_trapdoor",
        (0.0, 0.0),
        plate_size,
        plate_thick,
        OPENING_W,
        OPENING_D,
        LOWER_TOP_Z,
        hinge_side=-1,
    )

    # The ball starts resting on the upper platform surface, offset in -X so it sits
    # ON the solid part of the platform (NOT over the opening) before the trapdoor
    # opens, then rolls onto the trapdoor center as it begins to open.
    ball_rest_x = 0.0
    ball = add_sphere(
        "cascade_ball",
        BALL_R,
        (ball_rest_x, 0.0, UPPER_TOP_Z + BALL_R),
        MATS["orange"],
        "orange",
        role="cascading_ball",
    )
    ball["pb_expected_behavior"] = "falls_through_two_trapdoors_to_floor"

    return {
        "scene": scene,
        "kind": "two_tier_trapdoor_cascade",
        "ball": ball,
        "upper": upper,
        "lower": lower,
        "upper_top_z": UPPER_TOP_Z,
        "lower_top_z": LOWER_TOP_Z,
        "floor_z": FLOOR_Z,
        "ball_r": BALL_R,
    }


def swing_panel(panel, open01, hinge_side):
    """Rotate the trapdoor panel about its hinge edge by up to ~95 degrees.
    open01 in [0,1]. Panel origin sits on the hinge edge, so a Y-rotation swings the
    free edge DOWNWARD below the platform (a real trapdoor drops open), so the panel
    hangs below the plate and never blocks or clips the falling ball."""
    max_angle = math.radians(115.0)
    # A real trapdoor opens DOWNWARD: the free edge swings below the platform.
    # hinge on +X edge (free geom in -X): rotate -Y drops the -X free edge downward.
    # hinge on -X edge (free geom in +X): rotate +Y drops the +X free edge downward.
    ang = max_angle * open01 * (-1.0 if hinge_side > 0 else 1.0)
    panel.rotation_euler = (0.0, ang, 0.0)


def damped_rebound_height(frame, contact_frame, first_end, second_end,
                          first_height, second_height):
    """Two nonnegative half-sine rebounds with exact contact/settle endpoints."""
    if frame <= contact_frame:
        return 0.0
    if frame <= first_end:
        u = (frame - contact_frame) / float(first_end - contact_frame)
        return first_height * math.sin(math.pi * u)
    if frame <= second_end:
        u = (frame - first_end) / float(second_end - first_end)
        return second_height * math.sin(math.pi * u)
    return 0.0


def animate_two_tier_trapdoor_cascade(objs, frame):
    ball = objs["ball"]
    upper = objs["upper"]
    lower = objs["lower"]
    upper_top_z = objs["upper_top_z"]
    lower_top_z = objs["lower_top_z"]
    floor_z = objs["floor_z"]
    ball_r = objs["ball_r"]

    upper_panel = upper["panel"]
    lower_panel = lower["panel"]

    # ---- Timeline ----
    # 1..18   : ball rests on upper platform (trapdoors shut).
    # 18..30  : UPPER trapdoor swings open; the ball begins falling as soon as
    #            the supporting panel starts moving away on the next frame.
    # After release the landing frame is derived from the drop height and one
    # shared gravity constant rather than chosen independently.
    # 72..84  : LOWER trapdoor swings open and immediately releases the ball.
    # The second landing is derived the same way and is followed by two smaller
    # rebounds before frame 120.
    upper_open_start = 18
    upper_open_end = 30
    fall1_start = upper_open_start
    pause_end = 72
    lower_open_start = 72
    lower_open_end = 84
    fall2_start = lower_open_start

    ball_x = 0.0
    z_on_upper = upper_top_z + ball_r
    z_on_lower = lower_top_z + ball_r
    z_on_floor = floor_z + ball_r
    fall_acceleration = 0.018
    fall1_end = fall1_start + int(math.ceil(math.sqrt(
        2.0 * (z_on_upper - z_on_lower) / fall_acceleration
    )))
    fall2_end = fall2_start + int(math.ceil(math.sqrt(
        2.0 * (z_on_lower - z_on_floor) / fall_acceleration
    )))

    # ---- Upper trapdoor panel ----
    if frame <= upper_open_start:
        u_open = 0.0
    elif frame <= upper_open_end:
        u_open = smooth01((frame - upper_open_start) / float(upper_open_end - upper_open_start))
    else:
        u_open = 1.0
    swing_panel(upper_panel, u_open, upper["hinge_side"])
    upper_panel.keyframe_insert(data_path="rotation_euler", frame=frame)

    # ---- Lower trapdoor panel ----
    if frame <= lower_open_start:
        l_open = 0.0
    elif frame <= lower_open_end:
        l_open = smooth01((frame - lower_open_start) / float(lower_open_end - lower_open_start))
    else:
        l_open = 1.0
    swing_panel(lower_panel, l_open, lower["hinge_side"])
    lower_panel.keyframe_insert(data_path="rotation_euler", frame=frame)

    # ---- Ball ----
    if frame <= fall1_start:
        bz = z_on_upper
        state = "resting_on_upper_platform"
    elif frame <= fall1_end:
        dt = frame - fall1_start
        bz = max(z_on_lower, z_on_upper - 0.5 * fall_acceleration * dt * dt)
        state = "falling_through_upper_trapdoor"
    elif frame <= pause_end:
        bounce = damped_rebound_height(
            frame, fall1_end, fall1_end + 10, fall1_end + 20,
            first_height=0.90 * ball_r,
            second_height=0.35 * ball_r,
        )
        bz = z_on_lower + bounce
        state = "rebounding_on_lower_platform" if bounce > 0.0 else "resting_on_lower_platform"
    elif frame <= fall2_start:
        bz = z_on_lower
        state = "resting_on_lower_platform"
    elif frame <= fall2_end:
        dt = frame - fall2_start
        bz = max(z_on_floor, z_on_lower - 0.5 * fall_acceleration * dt * dt)
        state = "falling_through_lower_trapdoor"
    else:
        bounce = damped_rebound_height(
            frame, fall2_end, fall2_end + 12, fall2_end + 24,
            first_height=0.80 * ball_r,
            second_height=0.30 * ball_r,
        )
        bz = z_on_floor + bounce
        state = "rebounding_on_floor" if bounce > 0.0 else "settled_on_floor"

    ball.location = (ball_x, 0.0, bz)
    # The motion is vertical, so do not add unexplained spin while the ball rests.
    ball.rotation_euler = (0.0, 0.0, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball["pb_state"] = state
    ball["pb_never_suspended"] = True


# ============================================================
# Build / animate dispatch
# ============================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "two_tier_trapdoor_cascade":
        return build_two_tier_trapdoor_cascade_scene()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "two_tier_trapdoor_cascade":
            animate_two_tier_trapdoor_cascade(objs, frame)
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
