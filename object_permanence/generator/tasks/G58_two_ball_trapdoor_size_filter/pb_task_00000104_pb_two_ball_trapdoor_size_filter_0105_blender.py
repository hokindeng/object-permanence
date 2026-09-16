# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_TWO_BALL_TRAPDOOR_SIZE_FILTER_0105",
  "scene_kind": "two_ball_trapdoor_size_filter",
  "prompt": "A small ball and a large ball roll onto a gray platform with a circular hole in the middle. The small ball, narrower than the hole, falls straight through into the space below; the large ball, wider than the hole, cannot pass and comes to rest on the platform. Neither object stays suspended without support."
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
    # Lighter platform so the dark hole reads with strong contrast against it.
    MATS["gray"] = make_mat("mat_neutral_gray", (0.66, 0.66, 0.68), roughness=0.62)
    # Near-black shaft interior so the opening reads as a deep, dark hole.
    MATS["dark"] = make_mat("mat_dark_gray", (0.04, 0.04, 0.05), roughness=0.92)
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
# Platform with a real circular hole + dark rim
# ============================================================

def create_square_platform_with_circular_hole(name, center, plate_size, plate_thick, hole_radius, top_z):
    """Build a gray square platform (a flat plate) on four legs, with a REAL circular
    hole punched through its middle (boolean DIFFERENCE), and a dark rim ring around
    the hole edge. center=(cx,cy); top_z is the platform top surface z. Returns the
    plate body object."""
    cx, cy = center[0], center[1]
    plate_center_z = top_z - plate_thick / 2.0

    body = add_cube(
        name,
        (cx, cy, plate_center_z),
        (plate_size, plate_size, plate_thick),
        MATS["gray"],
        role="platform_with_hole",
        color_name="gray",
        solid=True,
    )
    body["pb_has_circular_hole"] = True
    body["pb_hole_radius"] = float(hole_radius)
    body["pb_hole_center_z"] = float(top_z)

    # Vertical cylindrical cutter punches a circular hole straight down through the plate.
    bpy.ops.mesh.primitive_cylinder_add(
        radius=hole_radius,
        depth=plate_thick * 4.0,
        location=(cx, cy, plate_center_z),
        rotation=(0.0, 0.0, 0.0),
        vertices=48,
    )
    cutter = bpy.context.object
    cutter.name = f"{name}_hole_cutter"

    mod = body.modifiers.new(name="hole_boolean", type="BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter

    bpy.context.view_layer.objects.active = body
    body.select_set(True)
    try:
        bpy.ops.object.modifier_apply(modifier=mod.name)
    except Exception:
        pass

    # Remove ONLY the cutter object directly (selection-delete can drop the body).
    try:
        bpy.data.objects.remove(cutter, do_unlink=True)
    except ReferenceError:
        pass

    # ---- Make the opening read as a REAL hole, not a painted disk. ----
    # 1) A deep, near-black cylindrical SHAFT wall hanging below the hole so the
    #    eye sees DOWN into a dark tube (true depth cue). Open at the bottom so the
    #    small ball can fall through and land on the catch floor below.
    shaft_top = top_z - plate_thick
    shaft_height = 0.92  # reach most of the way down toward the lower catch floor
    shaft_z = shaft_top - shaft_height / 2.0
    shaft = add_cylinder(
        f"{name}_dark_shaft",
        (cx, cy, shaft_z),
        hole_radius - 0.005,
        shaft_height,
        MATS["dark"],
        role="hole_shaft",
        color_name="near_black",
        solid=False,
        vertices=48,
    )
    shaft["pb_is_hole_shaft"] = True
    # Hollow out the shaft into a thin-walled TUBE (boolean difference) so the small
    # ball stays visible passing down INSIDE the dark well instead of vanishing into
    # a solid dark plug. Thin walls (~0.03) keep the dark contour while leaving the
    # interior open all the way down.
    bpy.ops.mesh.primitive_cylinder_add(
        radius=hole_radius - 0.035,
        depth=shaft_height + 0.4,
        location=(cx, cy, shaft_z),
        rotation=(0.0, 0.0, 0.0),
        vertices=48,
    )
    shaft_cutter = bpy.context.object
    shaft_cutter.name = f"{name}_shaft_cutter"
    smod = shaft.modifiers.new(name="shaft_hollow", type="BOOLEAN")
    smod.operation = "DIFFERENCE"
    smod.object = shaft_cutter
    bpy.context.view_layer.objects.active = shaft
    shaft.select_set(True)
    try:
        bpy.ops.object.modifier_apply(modifier=smod.name)
    except Exception:
        pass
    try:
        bpy.data.objects.remove(shaft_cutter, do_unlink=True)
    except ReferenceError:
        pass

    # 2) A thin near-black RING flush at the top edge of the hole, giving a crisp
    #    dark contour where the light platform meets the opening. It MUST be hollow
    #    (inner radius = hole edge) so it forms a lip around the opening instead of
    #    capping it with a solid disk, which would read as a gray plug and make the hole
    #    look filled. Boolean-difference its centre out, like the shaft.
    rim = add_cylinder(
        f"{name}_dark_rim",
        (cx, cy, top_z - plate_thick / 2.0),
        hole_radius + 0.055,
        plate_thick + 0.012,
        MATS["dark"],
        role="hole_rim",
        color_name="near_black",
        solid=False,
        vertices=48,
    )
    bpy.ops.mesh.primitive_cylinder_add(
        radius=hole_radius,
        depth=(plate_thick + 0.012) + 0.5,
        location=(cx, cy, top_z - plate_thick / 2.0),
        rotation=(0.0, 0.0, 0.0),
        vertices=48,
    )
    rim_cutter = bpy.context.object
    rim_cutter.name = f"{name}_rim_cutter"
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
    rim["pb_is_hole_rim"] = True

    # 3) A dark disk at the BOTTOM of the shaft (deep down, not at the mouth) so the
    #    shaft reads as a dark well with a black floor far below. Placed low so it
    #    never hides the small ball as it drops through the opening; the ball stays
    #    visible against the dark walls all the way down.
    rim_inner = add_cylinder(
        f"{name}_dark_opening_marker",
        (cx, cy, shaft_top - shaft_height + 0.04),
        hole_radius - 0.01,
        0.02,
        MATS["dark"],
        role="hole_opening",
        color_name="near_black",
        solid=False,
        vertices=48,
    )
    rim_inner["pb_is_opening_below_platform"] = True

    # Four legs supporting the plate.
    leg_h = top_z - plate_thick
    leg_z = leg_h / 2.0
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

    return body


# ============================================================
# 0105 two ball trapdoor size filter
# ============================================================

def build_two_ball_trapdoor_size_filter_scene():
    scene = build_base_scene()
    # Elevated, more top-down 3/4 camera so the circular hole reads as an OPENING
    # looking down into the shaft, not a flat painted disk. Higher Z + closer Y,
    # aimed at the hole, so we see the small ball drop INTO the opening.
    setup_camera(scene, location=(0.5, -4.8, 6.8), target=(0.0, 0.10, 0.55), lens=35)

    PLATFORM_TOP_Z = 1.05
    HOLE_R = 0.46
    # Both balls begin and finish on one continuous tabletop: the plate is wide enough
    # to reach well past their start positions at x = ±2.6, so neither ever floats.
    plate_size = 6.2
    plate_thick = 0.10
    LOWER_FLOOR_Z = PLATFORM_TOP_Z - 1.0  # lower catch floor ~1.0 below platform

    plate = create_square_platform_with_circular_hole(
        "gray_platform_with_circular_hole",
        (0.0, 0.0),
        plate_size,
        plate_thick,
        HOLE_R,
        PLATFORM_TOP_Z,
    )

    # Lower catch floor that the small ball settles on after falling through.
    catch = add_cube(
        "lower_catch_floor",
        (0.0, 0.0, LOWER_FLOOR_Z - 0.04),
        (1.6, 1.6, 0.08),
        MATS["box"],
        role="lower_catch_floor",
        color_name="gray",
        solid=True,
    )
    catch["pb_is_lower_catch_floor"] = True

    SMALL_R = 0.26  # < HOLE_R -> falls through
    LARGE_R = 0.64  # > HOLE_R -> rests on platform

    # Small ball rolls in from the LEFT.
    small = add_sphere(
        "small_orange_ball_narrower_than_hole",
        SMALL_R,
        (-2.6, 0.0, PLATFORM_TOP_Z + SMALL_R),
        MATS["orange"],
        "orange",
        role="small_ball_falls_through",
    )
    small["pb_narrower_than_hole"] = True
    small["pb_expected_behavior"] = "falls_straight_through_hole"

    # Large ball rolls in from the RIGHT.
    large = add_sphere(
        "large_red_ball_wider_than_hole",
        LARGE_R,
        (2.6, 0.0, PLATFORM_TOP_Z + LARGE_R),
        MATS["red"],
        "red",
        # role must not contain any APPARATUS_ROLES keyword ("platform" etc.) --
        # render.py:is_target() would classify the TARGET ball as rig apparatus
        # and repaint it gray while the SSG still records it as red.
        role="large_ball_blocked_by_hole",
    )
    large["pb_wider_than_hole"] = True
    large["pb_expected_behavior"] = "cannot_pass_rests_on_platform"

    return {
        "scene": scene,
        "kind": "two_ball_trapdoor_size_filter",
        "small": small,
        "large": large,
        "plate": plate,
        "platform_top_z": PLATFORM_TOP_Z,
        "lower_floor_z": LOWER_FLOOR_Z,
        "hole_r": HOLE_R,
        "small_r": SMALL_R,
        "large_r": LARGE_R,
    }


def animate_two_ball_trapdoor_size_filter(objs, frame):
    small = objs["small"]
    large = objs["large"]
    platform_top_z = objs["platform_top_z"]
    lower_floor_z = objs["lower_floor_z"]
    small_r = objs["small_r"]
    large_r = objs["large_r"]

    # ---- SMALL BALL (from LEFT) ----
    # Phase 1: accelerate toward the hole while still supported by its rim.
    # Phase 2: cross the unsupported rim and immediately enter free fall while
    #          preserving horizontal motion; there is no hold at the hole centre.
    # Phase 3: settle on lower catch floor.
    small_x0 = -2.6
    small_roll_start = 1
    small_roll_end = 36
    small_rest_top_z = platform_top_z + small_r
    small_land_z = lower_floor_z + small_r
    small_release_x = -math.sqrt(max(0.0, objs["hole_r"] ** 2 - small_r ** 2))
    small_fall_start = small_roll_end
    small_land_frame = 64

    if frame <= small_roll_end:
        t = ease_in_quad((frame - small_roll_start) / float(small_roll_end - small_roll_start))
        sx = lerp(small_x0, small_release_x, t)
        sz = small_rest_top_z
        s_state = "rolling_in_from_left_toward_hole"
    else:
        # Continue the incoming horizontal velocity for three frames as the ball
        # clears the rim, then fall vertically through the centre of the opening.
        sx = lerp(small_release_x, 0.0, min(1.0, (frame - small_fall_start) / 3.0))
        # Pure free fall: ease-in quad on the drop distance -> constant acceleration.
        ft = ease_in_quad((frame - small_fall_start) / float(small_land_frame - small_fall_start))
        sz = lerp(small_rest_top_z, small_land_z, ft)
        sz = max(small_land_z, sz)
        s_state = "falling_through_hole" if sz > small_land_z + 0.01 else "settled_on_lower_floor"

    small.location = (sx, 0.0, sz)
    small.rotation_euler = (0.0, -0.16 * frame, 0.0)
    small.keyframe_insert(data_path="location", frame=frame)
    small.keyframe_insert(data_path="rotation_euler", frame=frame)
    small["pb_state"] = s_state
    small["pb_never_suspended"] = True

    # ---- LARGE BALL (from RIGHT) ----
    # Staggered frames 40-78: rolls in from the right and comes to REST on the platform
    # over the hole (cannot pass). Never suspended.
    large_x0 = 2.6
    large_rest_x = 0.0
    large_roll_start = 40
    large_roll_end = 78
    large_top_z = platform_top_z + large_r  # rests on platform surface (sits over hole)

    if frame <= large_roll_start:
        lx = large_x0
        l_state = "waiting_at_right"
    elif frame <= large_roll_end:
        t = smooth01((frame - large_roll_start) / float(large_roll_end - large_roll_start))
        lx = lerp(large_x0, large_rest_x, t)
        l_state = "rolling_in_from_right_toward_hole"
    else:
        lx = large_rest_x
        l_state = "resting_on_platform_over_hole_cannot_pass"

    large.location = (lx, 0.0, large_top_z)
    large.rotation_euler = (0.0, -0.12 * frame, 0.0)
    large.keyframe_insert(data_path="location", frame=frame)
    large.keyframe_insert(data_path="rotation_euler", frame=frame)
    large["pb_state"] = l_state
    large["pb_rests_on_platform"] = bool(frame > large_roll_end)
    large["pb_never_suspended"] = True


# ============================================================
# Build / animate dispatch
# ============================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "two_ball_trapdoor_size_filter":
        return build_two_ball_trapdoor_size_filter_scene()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "two_ball_trapdoor_size_filter":
            animate_two_ball_trapdoor_size_filter(objs, frame)
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
