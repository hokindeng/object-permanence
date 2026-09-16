# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_CONVEYOR_COVERED_BOXES_0133",
  "scene_kind": "conveyor_covered_boxes",
  "prompt": "Four identical opaque covers sit in a row on a conveyor belt; a ball is shown under one cover before it lowers. The conveyor advances, carrying all four covers along the belt to new positions. When it stops, the cover over the ball lifts to reveal the ball rode along with its cover - it did not stay at its original spot."
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


def add_cylinder(name, location, radius, depth, rotation=(0, 0, 0), material=None, role="static_solid", color_name="gray", is_dynamic=False, solid=True, vertices=48):
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
    MATS["gray"] = make_mat("mat_gray", (0.46, 0.46, 0.46), roughness=0.62)
    MATS["dark"] = make_mat("mat_dark_gray", (0.20, 0.20, 0.22), roughness=0.74)
    MATS["light"] = make_mat("mat_light_gray", (0.67, 0.68, 0.70), roughness=0.66)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.38, 0.06), roughness=0.30)
    MATS["red"] = make_mat("mat_red", (0.95, 0.03, 0.02), roughness=0.30)
    MATS["blue"] = make_mat("mat_blue", (0.15, 0.35, 0.90), roughness=0.36)
    MATS["yellow"] = make_mat("mat_yellow", (0.97, 0.85, 0.10), roughness=0.34)
    MATS["black"] = make_mat("mat_black", (0.03, 0.03, 0.035), roughness=0.78)
    MATS["cover"] = make_mat("mat_cover_teal", (0.09, 0.52, 0.55), roughness=0.44)
    MATS["belt"] = make_mat("mat_belt_dark", (0.14, 0.14, 0.16), roughness=0.68)
    MATS["belt_stripe"] = make_mat("mat_belt_stripe", (0.32, 0.33, 0.36), roughness=0.66)
    MATS["roller"] = make_mat("mat_roller_metal", (0.55, 0.56, 0.60), roughness=0.34, metallic=0.7)
    MATS["frame"] = make_mat("mat_frame_metal", (0.30, 0.31, 0.34), roughness=0.50, metallic=0.4)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (14.0, 6.0, 0.10), MATS["floor"], role="ground", color_name="warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 2.9, 1.62), (14.4, 0.08, 3.24), MATS["backdrop"], role="background", color_name="off_white")

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
# scene 0133 conveyor covered boxes
# =============================================================================

# belt top surface height (z of the belt slab top face the covers sit on)
BELT_TOP_Z = 0.55

# conveyor geometry (belt length/extent are derived from the cover procession
# below so the belt frames the actual motion instead of overrunning it)
BELT_WIDTH = 1.9             # along y
BELT_SLAB_THICK = 0.22       # thickness of the belt slab
ROLLER_RADIUS = 0.22
ROLLER_LENGTH = BELT_WIDTH + 0.18

# box-cover geometry (opaque box open at the bottom, sitting on the belt)
# built as 4 thin walls + a top lid so it is truly hollow underneath the ball
COVER_HALF = 0.44            # half-extent of the square footprint (x and y)
COVER_HEIGHT = 0.82          # standing height of the cover wall
COVER_WALL = 0.06            # wall thickness
COVER_LID = 0.07             # top lid thickness

# four cover start x-positions (evenly spaced on the belt), all at y = 0
COVER_START_X = [-3.3, -1.1, 1.1, 3.3]

# ball geometry
BALL_RADIUS = 0.16

# one belt step: how far the whole procession advances along +x.
# kept modest so the rightmost cover does not ride off the right end of the belt.
BELT_STEP = 1.6

# --- conveyor extent derived from the cover procession -----------------------
# The covers occupy from the leftmost cover's start face to the rightmost cover's
# FINAL face (after advancing +BELT_STEP). We size and center the belt/rollers/
# frame rails to frame exactly that span with an equal margin on each end, so the
# belt is not left shifted (with a stub of empty belt jutting past the
# covers) and the rightmost cover stays fully supported on the belt at its final
# position instead of overhanging the +x (right) end into empty space.
BELT_MARGIN = 0.5
BELT_LEFT_X = min(COVER_START_X) - COVER_HALF - BELT_MARGIN
BELT_RIGHT_X = max(COVER_START_X) + BELT_STEP + COVER_HALF + BELT_MARGIN
BELT_LENGTH = BELT_RIGHT_X - BELT_LEFT_X
BELT_CENTER_X = 0.5 * (BELT_LEFT_X + BELT_RIGHT_X)

# vertical lift for the reveal / initial show (fully clear of the ball)
COVER_REVEAL_LIFT = COVER_HEIGHT + 0.55


def _make_cover(prefix, index, x):
    """Build one opaque box-cover (open bottom) as four walls + a top lid.

    The cover's local base is the belt top (z = BELT_TOP_Z). Each part stores
    pb_rel_x / pb_rel_y (offsets from the cover center) and pb_rel_z (z offset
    above the belt top when resting) so the whole cover can be moved rigidly.
    """
    parts = []
    wall_h = COVER_HEIGHT
    inner = COVER_HALF - COVER_WALL / 2.0

    # +x wall and -x wall (span in y)
    for sx in (+1.0, -1.0):
        w = add_cube(
            f"{prefix}_wall_x{'p' if sx > 0 else 'm'}",
            (x + sx * inner, 0.0, BELT_TOP_Z + wall_h / 2.0),
            (COVER_WALL, 2.0 * COVER_HALF, wall_h),
            MATS["cover"],
            role="opaque_cover_wall",
            color_name="teal",
            is_dynamic=True,
            solid=True,
        )
        w["pb_rel_x"] = sx * inner
        w["pb_rel_y"] = 0.0
        w["pb_rel_z"] = wall_h / 2.0
        parts.append(w)

    # +y wall and -y wall (span in x, inset so corners do not double-overlap)
    for sy in (+1.0, -1.0):
        w = add_cube(
            f"{prefix}_wall_y{'p' if sy > 0 else 'm'}",
            (x, sy * inner, BELT_TOP_Z + wall_h / 2.0),
            (2.0 * (COVER_HALF - COVER_WALL), COVER_WALL, wall_h),
            MATS["cover"],
            role="opaque_cover_wall",
            color_name="teal",
            is_dynamic=True,
            solid=True,
        )
        w["pb_rel_x"] = 0.0
        w["pb_rel_y"] = sy * inner
        w["pb_rel_z"] = wall_h / 2.0
        parts.append(w)

    # top lid
    lid = add_cube(
        f"{prefix}_lid",
        (x, 0.0, BELT_TOP_Z + wall_h + COVER_LID / 2.0),
        (2.0 * COVER_HALF, 2.0 * COVER_HALF, COVER_LID),
        MATS["cover"],
        role="opaque_cover_lid",
        color_name="teal",
        is_dynamic=True,
        solid=True,
    )
    lid["pb_rel_x"] = 0.0
    lid["pb_rel_y"] = 0.0
    lid["pb_rel_z"] = wall_h + COVER_LID / 2.0
    parts.append(lid)

    for p in parts:
        p["pb_cover_index"] = index
        p["pb_base_x"] = x
        p["pb_is_cover_part"] = True

    return {"parts": parts, "index": index, "base_x": x}


def build_conveyor_covered_boxes():
    scene = build_base_scene()
    # front 3/4 view so the whole belt procession from left to right is legible
    setup_camera(scene, location=(-4.6, -8.2, 3.7), target=(1.0, 0.0, 0.75), lens=30)

    # conveyor belt: a long dark slab the covers ride on, centered on the
    # cover procession so it frames the motion (no empty belt overrun on either end)
    add_cube(
        "conveyor_belt_slab",
        (BELT_CENTER_X, 0.0, BELT_TOP_Z - BELT_SLAB_THICK / 2.0),
        (BELT_LENGTH, BELT_WIDTH, BELT_SLAB_THICK),
        MATS["belt"],
        role="conveyor_surface",
        color_name="dark_gray",
    )

    # a couple of surface stripes for flavor / to read belt motion (they ride with
    # the belt step so the surface texture visibly advances with the covers).
    # Distribute them across the belt but keep them inside [BELT_LEFT_X, BELT_RIGHT_X]
    # even after advancing +BELT_STEP so no stripe rides off the right end.
    stripes = []
    n_stripes = 5
    stripe_lo = BELT_LEFT_X + 0.4
    stripe_hi = BELT_RIGHT_X - BELT_STEP - 0.4
    stripe_x0 = [stripe_lo + (stripe_hi - stripe_lo) * i / (n_stripes - 1) for i in range(n_stripes)]
    for i, sx in enumerate(stripe_x0):
        st = add_cube(
            f"belt_stripe_{i}",
            (sx, 0.0, BELT_TOP_Z + 0.004),
            (0.18, BELT_WIDTH - 0.10, 0.02),
            MATS["belt_stripe"],
            role="belt_marking",
            color_name="gray",
            is_dynamic=True,
            solid=False,
        )
        st["pb_base_x"] = sx
        st["pb_is_belt_stripe"] = True
        stripes.append(st)

    # end rollers (cylinders lying across the belt) for conveyor flavor,
    # placed at the actual belt ends so the belt visibly terminates at them
    for sx, nm in ((BELT_LEFT_X, "roller_left"), (BELT_RIGHT_X, "roller_right")):
        add_cylinder(
            nm,
            (sx, 0.0, BELT_TOP_Z - BELT_SLAB_THICK / 2.0),
            ROLLER_RADIUS,
            ROLLER_LENGTH,
            rotation=(math.pi / 2.0, 0.0, 0.0),
            material=MATS["roller"],
            role="conveyor_roller",
            color_name="metal_gray",
            is_dynamic=False,
            solid=True,
            vertices=40,
        )

    # side frame rails under the belt for a grounded, supported look; centered on
    # and slightly shorter than the belt so they terminate just inside the rollers
    for sy in (+1.0, -1.0):
        add_cube(
            f"belt_frame_rail_{'p' if sy > 0 else 'm'}",
            (BELT_CENTER_X, sy * (BELT_WIDTH / 2.0 + 0.05), BELT_TOP_Z - BELT_SLAB_THICK - 0.14),
            (BELT_LENGTH - 0.4, 0.10, 0.30),
            MATS["frame"],
            role="conveyor_frame",
            color_name="dark_gray",
        )

    # four identical opaque covers evenly spaced on the belt
    covers = []
    for i, x in enumerate(COVER_START_X):
        covers.append(_make_cover(f"cover_{i}", i, x))

    # the ball lives under cover index 1 (second from the left)
    ball_cover_index = 1
    ball_cover = covers[ball_cover_index]
    ball = add_sphere(
        "hidden_ball",
        BALL_RADIUS,
        (ball_cover["base_x"], 0.0, BELT_TOP_Z + BALL_RADIUS),
        MATS["yellow"],
        "yellow",
    )
    ball["pb_inside_cover"] = True

    return {
        "scene": scene,
        "kind": "conveyor_covered_boxes",
        "covers": covers,
        "stripes": stripes,
        "ball": ball,
        "ball_cover": ball_cover,
        "ball_cover_index": ball_cover_index,
    }


def _place_cover(cover, x, lift, frame):
    """Place a whole cover (walls + lid) at world x with vertical lift above belt."""
    for p in cover["parts"]:
        px = x + p["pb_rel_x"]
        py = p["pb_rel_y"]
        pz = BELT_TOP_Z + p["pb_rel_z"] + lift
        p.location = (px, py, pz)
        p.keyframe_insert(data_path="location", frame=frame)


def _place_stripe(stripe, x, frame):
    stripe.location = (x, 0.0, BELT_TOP_Z + 0.004)
    stripe.keyframe_insert(data_path="location", frame=frame)


def animate_conveyor_covered_boxes(objs, frame):
    covers = objs["covers"]
    stripes = objs["stripes"]
    ball = objs["ball"]
    ball_cover = objs["ball_cover"]

    # ---- phase windows ----
    # f1-14   : ball-cover starts raised (ball shown), lowers to hide the ball
    # f18-24  : settle
    # f28-96  : conveyor advances; ALL covers + belt stripes translate +BELT_STEP
    # f100-116: the cover over the ball lifts to reveal the ball at the new spot

    def rest_covers(advance):
        for c in covers:
            _place_cover(c, c["base_x"] + advance, 0.0, frame)

    def rest_stripes(advance):
        for st in stripes:
            _place_stripe(st, st["pb_base_x"] + advance, frame)

    if frame <= 14:
        # ball-cover raised at start (ball visible), lowers over the ball to hide it
        rest_covers(0.0)
        rest_stripes(0.0)
        t = (frame - FRAME_START) / 13.0
        lift = COVER_REVEAL_LIFT * (1.0 - smooth01(t))
        _place_cover(ball_cover, ball_cover["base_x"], lift, frame)
        ball_cover["parts"][0]["pb_state"] = "lowering_to_hide_ball"
        advance = 0.0

    elif frame < 28:
        # brief settle, everything resting at start positions
        rest_covers(0.0)
        rest_stripes(0.0)
        advance = 0.0

    elif frame <= 96:
        # conveyor advances: every cover AND the belt stripes translate together
        # along +x by BELT_STEP with a single smooth ease (starts/stops gently)
        t = (frame - 28) / 68.0
        advance = BELT_STEP * smooth01(t)
        rest_covers(advance)
        rest_stripes(advance)

    elif frame < 100:
        rest_covers(BELT_STEP)
        rest_stripes(BELT_STEP)
        advance = BELT_STEP

    else:
        # final reveal: the ball-cover (now BELT_STEP further along +x) lifts off
        rest_covers(BELT_STEP)
        rest_stripes(BELT_STEP)
        t = (frame - 100) / 16.0
        lift = COVER_REVEAL_LIFT * smooth01(t)
        _place_cover(ball_cover, ball_cover["base_x"] + BELT_STEP, lift, frame)
        ball_cover["parts"][0]["pb_state"] = "lifting_to_reveal_ball"
        advance = BELT_STEP

    # ball: hidden after f14, always pinned to the ball_cover's LIVE world x.
    # _place_cover has already moved the ball_cover's parts for THIS frame, so read
    # the actual current lid x (minus its rel_x, which is 0 for the lid) rather than
    # base_x, so the ball rides exactly with its container every advancing frame and
    # ends up at the new belt position - it never stays at its original spot.
    if frame <= 14:
        bx = ball_cover["base_x"]
    else:
        lid = ball_cover["parts"][-1]
        bx = lid.location.x - lid["pb_rel_x"]
    ball.location = (bx, 0.0, BELT_TOP_Z + BALL_RADIUS)
    ball.keyframe_insert(data_path="location", frame=frame)

    if frame <= 8:
        ball["pb_state"] = "visible_under_raised_cover"
    elif frame <= 98:
        ball["pb_state"] = "hidden_riding_with_its_cover_on_belt"
    else:
        ball["pb_state"] = "revealed_at_new_belt_position_moved_with_cover"
    ball["pb_moves_with_container"] = True
    ball["pb_no_stay_at_origin"] = True


# =============================================================================
# dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "conveyor_covered_boxes":
        return build_conveyor_covered_boxes()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "conveyor_covered_boxes":
            animate_conveyor_covered_boxes(objs, frame)
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
