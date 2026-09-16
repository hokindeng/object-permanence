# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_CONVEYOR_EDGE_FALL_0142",
  "scene_kind": "conveyor_edge_fall",
  "prompt": "A ball rides along a conveyor belt toward the end of the belt. When it reaches the edge, it rolls off and falls into a bin (a lower catch floor) below. It accelerates as it falls and is never suspended in the air."
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
    MATS["dark"] = make_mat("mat_dark_gray", (0.14, 0.14, 0.16), roughness=0.88)
    MATS["belt"] = make_mat("mat_belt", (0.20, 0.21, 0.24), roughness=0.70)
    MATS["stripe"] = make_mat("mat_stripe", (0.90, 0.82, 0.20), roughness=0.55)
    MATS["roller"] = make_mat("mat_roller", (0.55, 0.56, 0.58), roughness=0.35, metallic=0.6)
    MATS["frame"] = make_mat("mat_frame", (0.40, 0.41, 0.43), roughness=0.62)
    MATS["box"] = make_mat("mat_box_gray", (0.38, 0.39, 0.40), roughness=0.78)
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
# Horizontal conveyor belt (slab + end rollers + surface stripes)
# ============================================================

def create_conveyor_belt(name, belt_start_x, belt_end_x, belt_y, belt_top_z, belt_width, belt_thick):
    """Build a horizontal conveyor belt: a long dark slab (the belt top surface),
    two metallic end rollers at each end, a support frame under it, and a few bright
    surface stripes on the belt top as a motion cue. belt_top_z is the top surface z
    (where the ball rides). Returns a dict of key objects."""
    belt_len = belt_end_x - belt_start_x
    belt_cx = (belt_start_x + belt_end_x) / 2.0
    slab_center_z = belt_top_z - belt_thick / 2.0

    slab = add_cube(
        f"{name}_belt_slab",
        (belt_cx, belt_y, slab_center_z),
        (belt_len, belt_width, belt_thick),
        MATS["belt"],
        role="conveyor_belt_surface",
        color_name="dark_gray",
        solid=True,
    )
    slab["pb_is_conveyor_belt"] = True
    slab["pb_belt_top_z"] = float(belt_top_z)
    slab["pb_belt_end_x"] = float(belt_end_x)

    # Two metallic cylinder rollers spanning the belt width at each end, axis along Y.
    roller_r = belt_thick * 0.75
    roller_z = belt_top_z - roller_r
    for rx, tagn in ((belt_start_x, "start"), (belt_end_x, "end")):
        add_cylinder(
            f"{name}_roller_{tagn}",
            (rx, belt_y, roller_z),
            roller_r,
            belt_width + 0.06,
            MATS["roller"],
            role="conveyor_roller",
            color_name="metal_gray",
            solid=True,
            rotation=(math.radians(90.0), 0.0, 0.0),
            vertices=32,
        )

    # Support frame: two side rails and two legs so the belt is clearly supported
    # (never floating). Rails run under the belt along X on each side.
    rail_top_z = belt_top_z - belt_thick - 0.02
    for sy in (-belt_width / 2.0 + 0.05, belt_width / 2.0 - 0.05):
        add_cube(
            f"{name}_rail_{'n' if sy > 0 else 's'}",
            (belt_cx, belt_y + sy, rail_top_z - 0.06),
            (belt_len + 0.1, 0.08, 0.12),
            MATS["frame"],
            role="conveyor_rail",
            color_name="gray",
            solid=True,
        )

    leg_h = belt_top_z - belt_thick - 0.18
    leg_z = leg_h / 2.0
    for lx in (belt_start_x + 0.35, belt_end_x - 0.35):
        for sy in (-belt_width / 2.0 + 0.06, belt_width / 2.0 - 0.06):
            add_cube(
                f"{name}_leg_{lx > belt_cx and 'e' or 'w'}_{'n' if sy > 0 else 's'}",
                (lx, belt_y + sy, leg_z),
                (0.12, 0.12, leg_h),
                MATS["edge"],
                role="conveyor_leg",
                color_name="light_gray",
                solid=True,
            )

    # A few bright surface stripes across the belt as a motion cue. They are thin,
    # lie flush on the belt top, and are animated to translate toward the end edge.
    stripes = []
    stripe_top_z = belt_top_z + 0.006
    n_stripes = 4
    for i in range(n_stripes):
        sx = belt_start_x + belt_len * (i + 0.5) / float(n_stripes)
        st = add_cube(
            f"{name}_stripe_{i}",
            (sx, belt_y, stripe_top_z),
            (0.14, belt_width - 0.10, 0.012),
            MATS["stripe"],
            role="conveyor_stripe",
            color_name="yellow",
            solid=False,
        )
        st["pb_is_motion_cue"] = True
        stripes.append(st)

    return {
        "slab": slab,
        "stripes": stripes,
        "belt_start_x": belt_start_x,
        "belt_end_x": belt_end_x,
        "belt_y": belt_y,
        "belt_top_z": belt_top_z,
        "belt_len": belt_len,
        "belt_width": belt_width,
        "stripe_top_z": stripe_top_z,
        "n_stripes": n_stripes,
    }


# ============================================================
# 0142 conveyor edge fall
# ============================================================

def build_conveyor_edge_fall_scene():
    scene = build_base_scene()
    # Side / three-quarter camera so the ride along the belt, the end edge, and the
    # fall into the bin below are all visible.
    setup_camera(scene, location=(-1.0, -8.2, 2.6), target=(0.9, 0.0, 0.9), lens=32)

    BELT_TOP_Z = 1.65
    BELT_START_X = -3.0
    BELT_END_X = 1.7
    BELT_Y = 0.0
    BELT_WIDTH = 1.2
    BELT_THICK = 0.16

    belt = create_conveyor_belt(
        "conveyor",
        BELT_START_X,
        BELT_END_X,
        BELT_Y,
        BELT_TOP_Z,
        BELT_WIDTH,
        BELT_THICK,
    )

    BALL_R = 0.34

    # Bin (a lower catch floor) below and just past the belt end edge, so the ball
    # that rolls off the end lands inside it. Built as a floor plus low walls.
    BIN_FLOOR_Z = 0.30  # catch floor top surface height
    BIN_CX = BELT_END_X + 0.55
    BIN_CY = BELT_Y
    BIN_SIZE_X = 1.7
    BIN_SIZE_Y = 1.6

    catch = add_cube(
        "lower_catch_floor_bin_bottom",
        (BIN_CX, BIN_CY, BIN_FLOOR_Z - 0.05),
        (BIN_SIZE_X, BIN_SIZE_Y, 0.10),
        MATS["box"],
        role="lower_catch_floor",
        color_name="gray",
        solid=True,
    )
    catch["pb_is_lower_catch_floor"] = True

    wall_h = 0.45
    wall_z = BIN_FLOOR_Z + wall_h / 2.0
    # Far wall (+X), back wall (+Y) and front wall (-Y). Leave the belt-facing side
    # (-X) low/open so the incoming ball's arc into the bin stays visible.
    add_cube("bin_wall_far", (BIN_CX + BIN_SIZE_X / 2.0, BIN_CY, wall_z),
             (0.10, BIN_SIZE_Y, wall_h), MATS["frame"], role="bin_wall", color_name="gray", solid=True)
    add_cube("bin_wall_back", (BIN_CX, BIN_CY + BIN_SIZE_Y / 2.0, wall_z),
             (BIN_SIZE_X, 0.10, wall_h), MATS["frame"], role="bin_wall", color_name="gray", solid=True)
    add_cube("bin_wall_front", (BIN_CX, BIN_CY - BIN_SIZE_Y / 2.0, wall_z - 0.10),
             (BIN_SIZE_X, 0.10, wall_h - 0.20), MATS["frame"], role="bin_wall", color_name="gray", solid=True)

    ball = add_sphere(
        "orange_ball_on_conveyor",
        BALL_R,
        (BELT_START_X + 0.5, BELT_Y, BELT_TOP_Z + BALL_R),
        MATS["orange"],
        "orange",
        role="ball_rides_conveyor_then_falls",
    )
    ball["pb_expected_behavior"] = "rides_belt_then_falls_off_edge_into_bin"

    # Landing x: settle inside the bin, just past the belt end edge.
    land_x = BELT_END_X + 0.35

    return {
        "scene": scene,
        "kind": "conveyor_edge_fall",
        "ball": ball,
        "belt": belt,
        "belt_top_z": BELT_TOP_Z,
        "belt_start_x": BELT_START_X,
        "belt_end_x": BELT_END_X,
        "belt_y": BELT_Y,
        "ball_r": BALL_R,
        "bin_floor_z": BIN_FLOOR_Z,
        "land_x": land_x,
    }


def animate_conveyor_edge_fall(objs, frame):
    ball = objs["ball"]
    belt = objs["belt"]
    belt_top_z = objs["belt_top_z"]
    belt_start_x = objs["belt_start_x"]
    belt_end_x = objs["belt_end_x"]
    belt_y = objs["belt_y"]
    ball_r = objs["ball_r"]
    bin_floor_z = objs["bin_floor_z"]
    land_x = objs["land_x"]

    ball_x0 = belt_start_x + 0.5
    ride_z = belt_top_z + ball_r
    land_z = bin_floor_z + ball_r

    # Phase 1 (frames 1..ride_end): ride along the belt at CONSTANT speed toward the
    #   end edge. The ball center reaches the end edge (belt_end_x) at ride_end.
    # Phase 2 (ride_end..land_frame): free-fall off the edge. Horizontal motion keeps
    #   the pre-edge speed (projectile), vertical drop uses ease-in quad so the
    #   per-frame drop GROWS (constant downward acceleration). Lands in the bin.
    # Phase 3 (after land_frame): settled on the bin catch floor.
    ride_start = 1
    ride_end = 66
    fall_frames = 14
    land_frame = ride_end + fall_frames

    # Horizontal belt velocity (units/frame) that the ball carries off the edge.
    vx_per_frame = (belt_end_x - ball_x0) / float(ride_end - ride_start)

    if frame <= ride_end:
        # Constant-speed ride (linear in frame -> constant horizontal velocity).
        t = (frame - ride_start) / float(ride_end - ride_start)
        t = clamp01(t)
        bx = lerp(ball_x0, belt_end_x, t)
        bz = ride_z
        state = "riding_conveyor_toward_edge"
    else:
        # Projectile off the edge: the horizontal velocity is PRESERVED (constant
        # vx, so x keeps increasing every frame — the ball flies OUT, it does not
        # drop straight down), while z accelerates under gravity (ease-in quad, so
        # the per-frame drop grows). Together this is a parabolic arc that clears
        # the edge by a short distance before landing in the bin below.
        df = min(frame, land_frame) - ride_end
        bx = belt_end_x + vx_per_frame * df
        ft = clamp01(df / float(fall_frames))
        bz = lerp(ride_z, land_z, ease_in_quad(ft))
        bz = max(land_z, bz)
        state = "falling_off_edge_into_bin" if bz > land_z + 0.01 else "settled_in_bin"

    ball.location = (bx, belt_y, bz)
    # Rolling spin about Y while riding; keep spinning through the fall.
    ball.rotation_euler = (0.0, -0.20 * frame, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball["pb_state"] = state
    ball["pb_never_suspended"] = True

    # Belt surface stripes translate toward the end edge as a motion cue, wrapping
    # back to the belt start (looping conveyor surface). They stay flush on the belt.
    stripes = belt["stripes"]
    n = belt["n_stripes"]
    belt_len = belt["belt_len"]
    stripe_top_z = belt["stripe_top_z"]
    # Same speed as the ball's ride: full belt length over the ride duration.
    speed_per_frame = belt_len / float(ride_end - ride_start)
    for i, st in enumerate(stripes):
        base_x = belt_start_x + belt_len * (i + 0.5) / float(n)
        adv = speed_per_frame * (frame - 1)
        sx = belt_start_x + ((base_x - belt_start_x + adv) % belt_len)
        st.location = (sx, belt_y, stripe_top_z)
        st.keyframe_insert(data_path="location", frame=frame)


# ============================================================
# Build / animate dispatch
# ============================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "conveyor_edge_fall":
        return build_conveyor_edge_fall_scene()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "conveyor_edge_fall":
            animate_conveyor_edge_fall(objs, frame)
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
