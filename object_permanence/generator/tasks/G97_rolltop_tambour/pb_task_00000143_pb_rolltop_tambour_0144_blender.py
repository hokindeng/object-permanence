# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_ROLLTOP_TAMBOUR_0144",
  "scene_kind": "rolltop_tambour",
  "prompt": "A box with a curved roll-top (tambour) cover sits open on a table with an object resting inside, in plain view. The curved cover slides forward along its curved track to close over the top and hide the object, holds, then retracts again to reveal the same object, unchanged. The box body stays in place; only the cover moves."
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


def lerp(a, b, t):
    return a + (b - a) * t


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
            mat.blend_method = "BLEND"
            mat.show_transparent_back = True
            mat.use_screen_refraction = True
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


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), roughness=0.84)
    MATS["gray"] = make_mat("mat_gray", (0.46, 0.46, 0.46), roughness=0.64)
    MATS["dark"] = make_mat("mat_dark", (0.18, 0.19, 0.21), roughness=0.76)
    MATS["light"] = make_mat("mat_light", (0.68, 0.69, 0.71), roughness=0.68)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.38, 0.06), roughness=0.28)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.92)
    MATS["slat"] = make_mat("mat_tambour_slat", (0.55, 0.36, 0.18), roughness=0.58)


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


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (10.0, 5.0, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 2.48, 1.62), (10.2, 0.08, 3.24), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.4, -4.2, 5.5))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 980
    key.data.size = 6.0

    bpy.ops.object.light_add(type="POINT", location=(3.4, -3.0, 3.0))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 150

    return scene


def setup_camera(scene, location, target, lens=32, ortho=False, ortho_scale=4.0):
    bpy.ops.object.camera_add(location=location)
    cam = bpy.context.object
    cam.name = "camera_main"
    cam.data.lens = lens
    cam.data.dof.use_dof = False
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho_scale
    look_at(cam, target)
    scene.camera = cam
    return cam


# =============================================================================
# 0144 rolltop tambour
#
# A box (base + four walls) sits on the table. Instead of a flat sliding lid,
# its cover is a TAMBOUR: a curved roll-top made of a row of many thin slats
# that together follow a smooth curved track. At the closed state the track
# runs from the box FRONT-top rim, up and over the top of the opening, curving
# down toward the box BACK. When the cover retracts, the whole slat assembly
# advances along that curved track (each slat rolls back over the top and down
# the rear), progressively uncovering the top opening and revealing a colored
# ball resting on the box inner floor. The box body and the ball never move.
#
# Track construction (a "wraparound" path parametrized by arc length s):
#   - A leading straight run over the top of the opening (front -> back), plus
#   - a quarter-circle bend at the back rim that turns the path downward, plus
#   - a trailing straight run down the back face of the box.
# Each slat occupies a fixed arc-offset along this path; advancing a single
# scalar `s0` (the arc position of the leading slat) slides the whole comb of
# slats along the curve. A slat's position + tilt are read off the path at its
# own arc coordinate, so the assembly bends smoothly around the rear corner
# with no clipping. This APPROXIMATES a real tambour convincingly.
# =============================================================================

# Box footprint (shared constants used by build + path helpers).
BASE_Z = 0.10
WALL_H = 1.08
WALL_T = 0.10
INNER_HALF = 0.60                      # inner half-width / half-depth
OUTER_HALF = INNER_HALF + WALL_T / 2.0  # 0.65 -> wall centerline

# Top opening surface height (top of the walls).
TOP_Z = BASE_Z + 0.05 + WALL_H

# The curved track lives a small clearance above the top rim so the tambour
# slats never clip the walls as they roll.
TRACK_CLEAR = 0.06
TRACK_TOP_Z = TOP_Z + TRACK_CLEAR

# Back / front outer faces of the box (Y).
BACK_Y = OUTER_HALF + WALL_T / 2.0     # +Y outer face of the back wall
FRONT_Y = -(OUTER_HALF + WALL_T / 2.0)  # -Y outer face of the front wall
# Back face plane (where the trailing straight run lies), pushed just outside
# the back wall so descending slats clear it.
BACK_FACE_Y = BACK_Y + 0.08

# Bend geometry at the rear top corner: a quarter circle of radius R whose
# center sits inboard of the back rim so the path turns cleanly from
# horizontal (over the top) to vertical (down the back face). A larger radius
# makes the rear roll-over read clearly on camera.
BEND_R = 0.34
BEND_CX = BACK_FACE_Y - BEND_R         # makes bend end tangent to the rear run
BEND_CZ = TRACK_TOP_Z - BEND_R         # center Z of the bend circle

# Arc-length breakpoints along the path (measured from the FRONT rim = s0).
#   segment A: straight top run from front rim to start of bend.
#   segment B: quarter-circle bend (length = R * pi/2).
#   segment C: straight run down the back face, all the way down to the table
#              so retracted slats visibly PILE DOWN behind the box.
SEG_A_LEN = (BEND_CX - FRONT_Y)        # horizontal top run length
SEG_B_LEN = BEND_R * (math.pi / 2.0)   # quarter circle
SEG_C_LEN = (BEND_CZ - (BASE_Z + 0.05))      # bend endpoint down to near table
PATH_LEN = SEG_A_LEN + SEG_B_LEN + SEG_C_LEN


def path_point(s):
    """Return (y, z, tilt) at arc-length s measured from the front top rim.

    tilt = rotation about the X axis (radians). tilt 0 => slat lies flat
    (horizontal, spanning Y); tilt -pi/2 => slat stands vertical against the
    back face. The path goes: flat over the top (A) -> quarter bend (B) ->
    vertical down the back (C).
    """
    s = max(0.0, min(PATH_LEN, s))

    if s <= SEG_A_LEN:
        # Straight top run: y advances from front rim toward the bend start.
        y = FRONT_Y + s
        z = TRACK_TOP_Z
        tilt = 0.0
        return y, z, tilt

    if s <= SEG_A_LEN + SEG_B_LEN:
        # Quarter-circle bend around (BEND_CX, BEND_CZ). Parametrize by angle
        # a in [0, pi/2]: a=0 at top of the arc, a=pi/2 at the back face.
        a = (s - SEG_A_LEN) / BEND_R
        y = BEND_CX + BEND_R * math.sin(a)
        z = BEND_CZ + BEND_R * math.cos(a)
        tilt = -a
        return y, z, tilt

    # Straight vertical run down the back face.
    d = s - (SEG_A_LEN + SEG_B_LEN)
    y = BACK_FACE_Y
    # Continue from the exact endpoint of the quarter bend. Starting this run
    # at TRACK_TOP_Z caused each rear slat to jump upward by BEND_R and flicker.
    z = BEND_CZ - d
    z = max(BASE_Z + 0.05, z)
    tilt = -(math.pi / 2.0)
    return y, z, tilt


def build_rolltop_tambour():
    scene = build_base_scene()

    # Steep 3/4 view looking down into the cavity. The walls are 1.08 high
    # (raised for the tambour track) and the ball sits at z 0.15-0.71,
    # so a camera lower than about 55 degrees sees only the front wall: from the
    # previous (1.15, -3.60, 3.55) the ball was never in frame. From here the
    # ball is visible with the cover open, and the closed cover on top hides it.
    setup_camera(
        scene,
        location=(0.90, -2.70, 5.60),
        target=(0.0, 0.05, 0.45),
        lens=55,
    )

    base_z = BASE_Z
    wall_h = WALL_H
    wall_t = WALL_T
    outer_half = OUTER_HALF
    wall_cz = base_z + 0.05 + wall_h / 2.0
    floor_top_z = base_z + 0.10  # top surface of the box inner floor

    # Box inner floor (a solid slab the object rests on).
    add_cube("box_inner_floor", (0.0, 0.0, base_z + 0.05),
             (2.0 * outer_half + wall_t, 2.0 * outer_half + wall_t, 0.10),
             MATS["gray"], "box_floor", "gray")

    # Four static walls (the box body never moves).
    add_cube("box_left_wall", (-outer_half, 0.0, wall_cz),
             (wall_t, 2.0 * outer_half + wall_t, wall_h), MATS["gray"], "box_wall", "gray")
    add_cube("box_right_wall", (outer_half, 0.0, wall_cz),
             (wall_t, 2.0 * outer_half + wall_t, wall_h), MATS["gray"], "box_wall", "gray")
    add_cube("box_front_wall", (0.0, -outer_half, wall_cz),
             (2.0 * outer_half + wall_t, wall_t, wall_h), MATS["gray"], "box_wall", "gray")
    add_cube("box_back_wall", (0.0, outer_half, wall_cz),
             (2.0 * outer_half + wall_t, wall_t, wall_h), MATS["gray"], "box_wall", "gray")

    # --- Tambour cover: a comb of thin slats along the curved path ----------
    # The slats span the box in X (across the opening width). Each slat is a
    # thin cube; its origin is its own center, so a slat is placed at a path
    # point and tilted about X to follow the curve. A fixed per-slat arc gap
    # keeps the comb rigid: advancing s0 (leading-slat arc position) slides the
    # whole assembly along the path.
    slat_span_x = 2.0 * outer_half + wall_t   # spans full opening width incl. walls
    slat_thick = 0.06                          # radial thickness of a slat
    slat_gap = 0.16                            # arc spacing; diversity scales it x0.84-1.16
    # Slat length follows the gap so the seam stays 0.03 at every gap scale. A
    # fixed 0.13 left 0.056 seams at gap x1.16: the closed cover became a comb
    # you could see the ball through, i.e. no longer an occluder.
    slat_len_along = slat_gap - 0.03           # slat extent along the travel (Y-ish)
    n_slats = 9                                # comb spans ~ the whole top run

    slats = []
    for i in range(n_slats):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0.0, 0.0, TRACK_TOP_Z))
        s = bpy.context.object
        s.name = f"tambour_slat_{i:02d}"
        # Local dims: X = across opening, Y = along travel, Z = thickness.
        s.dimensions = (slat_span_x, slat_len_along, slat_thick)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        s.data.materials.append(MATS["slat"])
        tag(s, s.name, "tambour_slat", "dynamic_object", "cube", "wood_brown", True, solid=True)
        s["pb_tambour_arc_offset"] = i * slat_gap
        s["pb_part_of_cover"] = True
        slats.append(s)

    # Closed state: the leading (index 0) slat sits at the FRONT top rim
    # (arc s = 0) and the comb extends back along the top run, so the row of
    # slats fully covers the top opening front-to-back. s0_closed is the arc
    # position of the leading slat.
    s0_closed = 0.0
    # Open state: advance the whole comb so the LEADING slat is fully past the
    # end of the top run (into the rear bend) and the rest of the comb drapes
    # around the corner and PILES DOWN the back face all the way toward the
    # table. This fully uncovers the top opening (ball revealed) while the whole
    # comb still rides the curve contiguously -- the trailing slat's arc stays
    # just below PATH_LEN so nothing clamps/piles up or disappears.
    cover_arc_span = (n_slats - 1) * slat_gap
    s0_open = min(PATH_LEN - cover_arc_span - 0.01, SEG_A_LEN + 0.03)

    # --- Object inside (clearly visible once the cover retracts) ------------
    ball_r = 0.28
    ball = add_sphere(
        "colored_ball_inside_box",
        ball_r,
        (0.0, 0.0, floor_top_z + ball_r),
        MATS["orange"],
        "orange",
    )
    ball["pb_visible_when_cover_open"] = True
    ball["pb_resting_inside_box"] = True

    return {
        "scene": scene,
        "kind": "rolltop_tambour",
        "slats": slats,
        "ball": ball,
        "base_z": base_z,
        "ball_r": ball_r,
        "floor_top_z": floor_top_z,
        "slat_gap": slat_gap,
        "n_slats": n_slats,
        "s0_closed": s0_closed,
        "s0_open": s0_open,
    }


def place_slats(slats, s0):
    """Position + tilt every slat given the leading-slat arc position s0."""
    for s in slats:
        offset = s["pb_tambour_arc_offset"]
        y, z, tilt = path_point(s0 + offset)
        s.location = (0.0, y, z)
        s.rotation_euler = (tilt, 0.0, 0.0)


def animate_rolltop_tambour(objs):
    scene = objs["scene"]
    slats = objs["slats"]
    ball = objs["ball"]
    floor_top_z = objs["floor_top_z"]
    ball_r = objs["ball_r"]
    s0_closed = objs["s0_closed"]
    s0_open = objs["s0_open"]

    # Object-permanence cycle that STARTS OPEN: the ball is plainly visible in the
    # open box, then the tambour cover slides FORWARD along the curve to close over
    # the top (hiding the ball), holds shut, then retracts again to reveal the same
    # ball. open01 = 1 => fully open (s0_open), 0 => fully closed (s0_closed).
    #   Phase 1  f1   - f6    : OPEN, cover retracted, ball visible (hold).
    #   Phase 2  f6   - f57   : cover CLOSES forward along the curve (ball hidden).
    #   Phase 3  f57  - f63   : hold CLOSED (ball hidden); the 60/60 split falls here.
    #   Phase 4  f63  - f114  : cover RETRACTS again, revealing the same ball.
    #   Phase 5  f114 - f120  : hold OPEN, ball shown.
    close_start, close_end = 6, 57
    hold_end = 63
    reopen_end = 114

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= close_start:
            open01 = 1.0
            cover_state = "open_cover_retracted_ball_visible"
            ball_state = "visible_inside_open_box"
        elif frame <= close_end:
            open01 = 1.0 - smooth01((frame - close_start) / float(close_end - close_start))
            cover_state = "cover_closing_forward_over_box"
            ball_state = "being_hidden_as_cover_closes"
        elif frame <= hold_end:
            open01 = 0.0
            cover_state = "closed_cover_covering_box_ball_hidden"
            ball_state = "hidden_inside_closed_box"
        elif frame <= reopen_end:
            open01 = smooth01((frame - hold_end) / float(reopen_end - hold_end))
            cover_state = "cover_retracting_along_curve_revealing_ball"
            ball_state = "being_revealed_as_cover_retracts"
        else:
            open01 = 1.0
            cover_state = "cover_fully_retracted_same_ball_revealed"
            ball_state = "revealed_resting_inside_open_box"

        s0 = lerp(s0_closed, s0_open, open01)

        # Advance the whole tambour comb along the curved track (no clipping:
        # every slat rides the path a clearance above the rim / outside the
        # back face).
        place_slats(slats, s0)
        for s in slats:
            s.keyframe_insert(data_path="location", frame=frame)
            s.keyframe_insert(data_path="rotation_euler", frame=frame)
            s["pb_state"] = cover_state

        # The box body and the object never move.
        ball.location = (0.0, 0.0, floor_top_z + ball_r)
        ball.keyframe_insert(data_path="location", frame=frame)
        ball["pb_state"] = ball_state
        ball["pb_must_remain_inside_box"] = True
        ball["pb_same_object_throughout"] = True

    scene.frame_set(FRAME_START)


# =============================================================================
# dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "rolltop_tambour":
        return build_rolltop_tambour()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(objs):
    kind = objs["kind"]
    if kind == "rolltop_tambour":
        return animate_rolltop_tambour(objs)
    raise RuntimeError("Unknown kind: " + str(kind))


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
    animate_scene_by_kind(objs)

    # Input = closed curved cover (ball hidden). Event = cover mid-retract
    # (partial reveal). Final = cover fully retracted, ball revealed inside.
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
