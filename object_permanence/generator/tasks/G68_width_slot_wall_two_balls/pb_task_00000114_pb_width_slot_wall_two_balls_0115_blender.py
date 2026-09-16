# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_WIDTH_SLOT_WALL_TWO_BALLS_0115",
  "scene_kind": "width_slot_wall_two_balls",
  "prompt": "A standing wall blocks a flat track, but it has a narrow vertical slot cut through its middle. A narrow ball rolls up and passes cleanly through the slot to the far side; a wide ball, too big for the slot, is stopped by the wall and comes to rest against it. Neither ball is ever suspended."
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
    # Wall body: mid gray, clearly opaque and solid so the slot reads as a true gap.
    MATS["wall"] = make_mat("mat_wall_gray", (0.52, 0.53, 0.56), roughness=0.70)
    # Near-black lining on the slot jambs so the vertical opening reads as a real
    # cut-through gap (dark contour framing the far side seen through it).
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
# Standing wall across the track with a REAL vertical slot
# ============================================================

def create_wall_with_vertical_slot(name, wall_y, wall_thick, wall_span_x, wall_height,
                                    slot_width, slot_bottom_z, slot_top_z):
    """Build an opaque standing wall (spanning X, thickness along Y, standing up in Z)
    at y=wall_y, with a REAL vertical slot cut through its middle. The slot is a
    genuine gap (not a painted stripe): the wall is assembled from a LEFT pillar and a
    RIGHT pillar with a gap of exactly slot_width between them, plus a top LINTEL above
    the slot so the opening is a bounded vertical channel. slot_bottom_z sits on the
    floor (=0) so a ball can roll straight through at track level. Returns a dict of the
    wall parts and slot geometry."""
    half_span = wall_span_x / 2.0
    half_slot = slot_width / 2.0
    wall_center_z = wall_height / 2.0

    # ---- LEFT pillar: from -half_span to -half_slot ----
    left_w = half_span - half_slot
    left_cx = -(half_slot + left_w / 2.0)
    left_pillar = add_cube(
        f"{name}_left_pillar",
        (left_cx, wall_y, wall_center_z),
        (left_w, wall_thick, wall_height),
        MATS["wall"],
        role="slot_wall_pillar",
        color_name="gray",
        solid=True,
    )

    # ---- RIGHT pillar: from +half_slot to +half_span ----
    right_w = half_span - half_slot
    right_cx = half_slot + right_w / 2.0
    right_pillar = add_cube(
        f"{name}_right_pillar",
        (right_cx, wall_y, wall_center_z),
        (right_w, wall_thick, wall_height),
        MATS["wall"],
        role="slot_wall_pillar",
        color_name="gray",
        solid=True,
    )

    # ---- TOP lintel: spans the slot above slot_top_z, closing the top of the gap ----
    lintel_h = wall_height - slot_top_z
    lintel_cz = slot_top_z + lintel_h / 2.0
    lintel = add_cube(
        f"{name}_top_lintel",
        (0.0, wall_y, lintel_cz),
        (slot_width, wall_thick, lintel_h),
        MATS["wall"],
        role="slot_wall_lintel",
        color_name="gray",
        solid=True,
    )

    # ---- Dark jamb linings on the two vertical slot edges so the opening reads as a
    # real deep cut-through, not a painted stripe. Thin dark plates flush with the
    # inner faces of the two pillars, slightly proud on both sides of the wall.
    jamb_thick = wall_thick + 0.03
    for sx, tag_side in ((-half_slot, "left"), (half_slot, "right")):
        jamb = add_cube(
            f"{name}_slot_jamb_{tag_side}",
            (sx, wall_y, (slot_bottom_z + slot_top_z) / 2.0),
            (0.02, jamb_thick, slot_top_z - slot_bottom_z),
            MATS["dark"],
            role="slot_jamb",
            color_name="near_black",
            solid=True,
        )
        jamb["pb_is_slot_jamb"] = True

    # ---- Dark lintel underside lining marking the top of the slot channel. ----
    top_lining = add_cube(
        f"{name}_slot_top_lining",
        (0.0, wall_y, slot_top_z),
        (slot_width, jamb_thick, 0.02),
        MATS["dark"],
        role="slot_top_lining",
        color_name="near_black",
        solid=True,
    )
    top_lining["pb_is_slot_lining"] = True

    for part in (left_pillar, right_pillar, lintel):
        part["pb_is_slot_wall"] = True
        part["pb_slot_width"] = float(slot_width)

    return {
        "left_pillar": left_pillar,
        "right_pillar": right_pillar,
        "lintel": lintel,
        "wall_y": wall_y,
        "wall_thick": wall_thick,
        "slot_width": slot_width,
        "slot_bottom_z": slot_bottom_z,
        "slot_top_z": slot_top_z,
        "left_inner_x": -half_slot,
        "right_inner_x": half_slot,
    }


# ============================================================
# 0115 width slot wall two balls
# ============================================================

def build_width_slot_wall_two_balls_scene():
    scene = build_base_scene()
    # 3/4 elevated camera placed on the NEAR side and offset to the left, aimed at
    # the slot, so we look THROUGH the vertical slot to the far side of the wall and
    # the opening clearly reads as a real gap (far floor visible through it).
    setup_camera(scene, location=(-3.2, -7.4, 3.1), target=(0.0, 0.6, 0.55), lens=35)

    WALL_Y = 0.6
    WALL_THICK = 0.30
    WALL_SPAN_X = 5.2
    WALL_HEIGHT = 2.6
    SLOT_WIDTH = 0.70            # the gate width
    SLOT_BOTTOM_Z = 0.0          # slot reaches the floor -> ball rolls through at track level
    SLOT_TOP_Z = 1.7

    wall = create_wall_with_vertical_slot(
        "slot_wall",
        WALL_Y,
        WALL_THICK,
        WALL_SPAN_X,
        WALL_HEIGHT,
        SLOT_WIDTH,
        SLOT_BOTTOM_Z,
        SLOT_TOP_Z,
    )

    # Ball radii chosen relative to slot half-width so the physics is unambiguous:
    # narrow ball diameter (2*0.28=0.56) < SLOT_WIDTH (0.70) -> passes through.
    # wide ball  diameter (2*0.52=1.04) > SLOT_WIDTH (0.70) -> stopped by the wall.
    NARROW_R = 0.28
    WIDE_R = 0.52

    # Narrow ball starts on the NEAR side (low Y), centered on the slot, rolls in +Y
    # through the slot to the FAR side.
    narrow = add_sphere(
        "narrow_orange_ball_passes_slot",
        NARROW_R,
        (0.0, -3.2, NARROW_R),
        MATS["orange"],
        "orange",
        role="narrow_ball_passes_through_slot",
    )
    narrow["pb_narrower_than_slot"] = True
    narrow["pb_expected_behavior"] = "rolls_through_slot_to_far_side"

    # Wide ball also on the near side, on a parallel lane offset in X so the two balls
    # never collide; it rolls in +Y and is stopped against the wall (cannot fit slot).
    wide = add_sphere(
        "wide_red_ball_blocked_by_wall",
        WIDE_R,
        (-1.7, -3.2, WIDE_R),
        MATS["red"],
        "red",
        # The role name must not contain "wall": render.py's is_target() would
        # then classify this scored ball as rig apparatus and repaint it a
        # muted tone.
        role="wide_ball_blocked_by_slot",
    )
    wide["pb_wider_than_slot"] = True
    wide["pb_expected_behavior"] = "stopped_by_wall_rests_against_it"

    return {
        "scene": scene,
        "kind": "width_slot_wall_two_balls",
        "narrow": narrow,
        "wide": wide,
        "wall": wall,
        "wall_y": WALL_Y,
        "wall_thick": WALL_THICK,
        "slot_width": SLOT_WIDTH,
        "narrow_r": NARROW_R,
        "wide_r": WIDE_R,
        "narrow_lane_x": 0.0,
        "wide_lane_x": -1.7,
    }


def animate_width_slot_wall_two_balls(objs, frame):
    narrow = objs["narrow"]
    wide = objs["wide"]
    wall_y = objs["wall_y"]
    wall_thick = objs["wall_thick"]
    narrow_r = objs["narrow_r"]
    wide_r = objs["wide_r"]
    narrow_lane_x = objs["narrow_lane_x"]
    wide_lane_x = objs["wide_lane_x"]

    near_y = -3.2

    # ---- NARROW BALL (lane x=0, centered on slot) ----
    # Rolls in +Y from the near side, passes cleanly THROUGH the slot, continues to
    # the far side and comes to rest. Y goes monotonically forward; z stays at radius
    # (rolling on the floor the whole time) so it is never suspended.
    narrow_start_y = near_y
    narrow_end_y = wall_y + 2.4          # well past the wall on the far side
    narrow_roll_start = 1
    narrow_roll_end = 70

    t_n = smooth01((frame - narrow_roll_start) / float(narrow_roll_end - narrow_roll_start))
    ny = lerp(narrow_start_y, narrow_end_y, t_n)
    if ny < wall_y - 0.05:
        n_state = "rolling_in_near_side_toward_slot"
    elif ny <= wall_y + 0.05:
        n_state = "passing_through_slot"
    elif frame < narrow_roll_end:
        n_state = "rolling_out_far_side"
    else:
        n_state = "at_rest_far_side"
    narrow.location = (narrow_lane_x, ny, narrow_r)
    # Roll about X axis for +Y motion (forward rolling).
    narrow.rotation_euler = (0.20 * frame, 0.0, 0.0)
    narrow.keyframe_insert(data_path="location", frame=frame)
    narrow.keyframe_insert(data_path="rotation_euler", frame=frame)
    narrow["pb_state"] = n_state
    narrow["pb_never_suspended"] = True

    # ---- WIDE BALL (lane x=-1.7) ----
    # Rolls in +Y from the near side and is STOPPED by the wall: it can never enter the
    # slot (too wide) and even off to the side it meets the solid pillar face. It comes
    # to rest with its surface just touching the near face of the wall. Never suspended.
    wall_near_face = wall_y - wall_thick / 2.0
    wide_rest_y = wall_near_face - wide_r          # sphere surface touches wall face
    wide_start_y = near_y
    wide_roll_start = 8
    wide_roll_end = 60

    t_w = smooth01((frame - wide_roll_start) / float(wide_roll_end - wide_roll_start))
    wy = lerp(wide_start_y, wide_rest_y, t_w)
    wy = min(wy, wide_rest_y)
    if frame <= wide_roll_start:
        w_state = "waiting_near_side"
    elif wy < wide_rest_y - 0.02:
        w_state = "rolling_in_near_side_toward_wall"
    else:
        w_state = "stopped_resting_against_wall"
    wide.location = (wide_lane_x, wy, wide_r)
    wide.rotation_euler = (0.16 * frame, 0.0, 0.0)
    wide.keyframe_insert(data_path="location", frame=frame)
    wide.keyframe_insert(data_path="rotation_euler", frame=frame)
    wide["pb_state"] = w_state
    wide["pb_rests_against_wall"] = bool(wy >= wide_rest_y - 0.02)
    wide["pb_never_suspended"] = True


# ============================================================
# Build / animate dispatch
# ============================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "width_slot_wall_two_balls":
        return build_width_slot_wall_two_balls_scene()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "width_slot_wall_two_balls":
            animate_width_slot_wall_two_balls(objs, frame)
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
