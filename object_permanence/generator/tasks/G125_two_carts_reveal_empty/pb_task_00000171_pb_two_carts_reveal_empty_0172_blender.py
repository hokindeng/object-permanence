# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_TWO_CARTS_REVEAL_EMPTY_0172",
  "scene_kind": "two_carts_reveal_empty",
  "prompt": "Two identical covered carts sit at opposite ends of a table. Both covers lift to display their contents: a ball is under the left cart, the right cart is empty. The covers close, and the two carts roll toward each other, cross past one another in the middle, and continue to the opposite ends, the ball riding with its cart. At the end, the cart that was always empty is uncovered to show it is still empty, implying the ball travelled with the other cart."
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
    MATS["cover"] = make_mat("mat_cover", (0.30, 0.58, 0.36), roughness=0.44)
    MATS["cart"] = make_mat("mat_cart_body", (0.42, 0.30, 0.20), roughness=0.60)
    MATS["wheel"] = make_mat("mat_wheel", (0.12, 0.12, 0.14), roughness=0.70)
    MATS["table"] = make_mat("mat_table_wood", (0.55, 0.40, 0.26), roughness=0.70)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (12.0, 6.0, 0.10), MATS["floor"], role="ground", color_name="warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 2.9, 1.9), (12.2, 0.08, 3.8), MATS["backdrop"], role="background", color_name="off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.6, -4.3, 5.5))
    key = bpy.context.object
    key.name = "large_softbox_light"
    key.data.energy = 980
    key.data.size = 6.2

    bpy.ops.object.light_add(type="POINT", location=(3.6, -3.0, 3.0))
    fill = bpy.context.object
    fill.name = "fill_light"
    fill.data.energy = 150

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
# scene 0172 two covered carts cross, empty cart revealed at the end
# =============================================================================

# table top surface height (z of the table top face the carts roll on)
TABLE_TOP_Z = 0.45

# the two carts start at opposite ends in x, and roll to swap ends. They travel at
# SLIGHTLY DIFFERENT DEPTHS (y) so they pass without colliding as they cross.
END_X = 2.35
LEFT_Y = -0.62          # left cart (holds ball) travels on the near lane
RIGHT_Y = 0.62          # right cart (empty) travels on the far lane

# cart geometry: a small wheeled body + an opaque box cover over the interior
CART_W = 0.92          # body width (x)
CART_D = 0.78          # body depth (y)
BODY_H = 0.16          # flat cart bed thickness
WHEEL_R = 0.11
CART_BASE_Z = TABLE_TOP_Z + 2.0 * WHEEL_R
COVER_W = 0.80
COVER_D = 0.66
COVER_H = 0.62         # opaque cover height
COVER_WALL = 0.055

# ball carried under the LEFT cart's cover
BALL_RADIUS = 0.24

# how high a cover lifts to reveal/display (fully clear of the interior)
COVER_REVEAL_LIFT = COVER_H + 0.55


def _make_cart(prefix, start_x, lane_y, mat_cover):
    """Build one covered cart: a flat bed with 4 wheels + a box cover on top.

    Parts store pb_rel = (dx, dy, dz) offsets from the cart's bed-center reference
    point at (x, lane_y, CART_BASE_Z). The whole cart is repositioned each frame by
    setting a single reference x and re-deriving all part positions. All rig parts
    carry apparatus-keyword roles so render.py recolors them a muted gray."""
    parts = []
    # The wheel bottoms are tangent to the table and the bed bottom is tangent to
    # the wheel tops.  Keeping this as one shared reference prevents the cart from
    # sinking into the tabletop when it moves.
    bed_ref_z = CART_BASE_Z

    # cart bed (role has "platform" -> apparatus/gray)
    bed = add_cube(f"{prefix}_bed", (start_x, lane_y, bed_ref_z + BODY_H / 2.0),
                   (CART_W, CART_D, BODY_H), MATS["cart"], role="cart_bed_platform",
                   color_name="wood_brown", is_dynamic=True)
    bed["pb_rel"] = (0.0, 0.0, BODY_H / 2.0)
    parts.append(bed)

    # 4 wheels (thin cylinders, axle along y); "wheel" -> apparatus/gray
    for sx, sy, nm in [(-1, -1, "wfl"), (1, -1, "wfr"), (-1, 1, "wbl"), (1, 1, "wbr")]:
        wx = sx * (CART_W / 2.0 - 0.10)
        wy = sy * (CART_D / 2.0 - 0.02)
        w = add_cylinder(f"{prefix}_{nm}", (start_x + wx, lane_y + wy, bed_ref_z - WHEEL_R),
                         WHEEL_R, 0.06, rotation=(math.radians(90.0), 0.0, 0.0),
                         material=MATS["wheel"], role="cart_wheel", color_name="black",
                         is_dynamic=True, vertices=24)
        w["pb_rel"] = (wx, wy, -WHEEL_R)
        parts.append(w)

    # A real hollow five-panel cover, rather than a solid cube occupying the same
    # volume as the ball.  Every panel uses the same vertical lift and therefore
    # stays visible and rigid while the cart rolls.
    cover_parts = []
    cover_specs = [
        ("roof", (0.0, 0.0, BODY_H + COVER_H - COVER_WALL / 2.0),
         (COVER_W, COVER_D, COVER_WALL)),
        ("left_wall", (-(COVER_W - COVER_WALL) / 2.0, 0.0,
                       BODY_H + (COVER_H - COVER_WALL) / 2.0),
         (COVER_WALL, COVER_D, COVER_H - COVER_WALL)),
        ("right_wall", ((COVER_W - COVER_WALL) / 2.0, 0.0,
                        BODY_H + (COVER_H - COVER_WALL) / 2.0),
         (COVER_WALL, COVER_D, COVER_H - COVER_WALL)),
        ("front_wall", (0.0, -(COVER_D - COVER_WALL) / 2.0,
                        BODY_H + (COVER_H - COVER_WALL) / 2.0),
         (COVER_W - 2.0 * COVER_WALL, COVER_WALL, COVER_H - COVER_WALL)),
        ("back_wall", (0.0, (COVER_D - COVER_WALL) / 2.0,
                       BODY_H + (COVER_H - COVER_WALL) / 2.0),
         (COVER_W - 2.0 * COVER_WALL, COVER_WALL, COVER_H - COVER_WALL)),
    ]
    for suffix, rel, dims in cover_specs:
        panel = add_cube(
            f"{prefix}_cover_{suffix}",
            (start_x + rel[0], lane_y + rel[1], bed_ref_z + rel[2]),
            dims,
            mat_cover,
            role="cart_cover",
            color_name="green",
            is_dynamic=True,
        )
        panel["pb_rel"] = rel
        panel["pb_is_cover"] = True
        cover_parts.append(panel)
        parts.append(panel)
    cover = cover_parts[0]

    for p in parts:
        p["pb_is_cart_part"] = True
        p["pb_lane_y"] = lane_y

    return {"parts": parts, "cover": cover, "lane_y": lane_y, "start_x": start_x}


def build_two_carts_reveal_empty():
    scene = build_base_scene()
    # front 3/4 view; carts span x in [-2.35, 2.35]; camera off to the left-front
    setup_camera(scene, location=(-3.0, -8.2, 3.0), target=(0.0, 0.0, 0.75), lens=33)

    # table the carts roll on (wide enough for the full travel)
    add_cube(
        "cart_table",
        (0.0, 0.0, TABLE_TOP_Z - 0.09),
        (7.6, 2.8, 0.18),
        MATS["table"],
        role="table_surface",
        color_name="wood_brown",
    )

    # LEFT cart (holds the ball) starts at -END_X on the near lane;
    # RIGHT cart (identical, EMPTY) starts at +END_X on the far lane.
    left_cart = _make_cart("cart_L", -END_X, LEFT_Y, MATS["cover"])
    right_cart = _make_cart("cart_R", END_X, RIGHT_Y, MATS["cover"])

    # ball lives under the LEFT cart's cover (vivid target; no apparatus role)
    ball = add_sphere(
        "shown_ball",
        BALL_RADIUS,
        (-END_X, LEFT_Y, CART_BASE_Z + BODY_H + BALL_RADIUS),
        MATS["yellow"],
        "yellow",
        role="shown_ball",
    )
    ball["pb_inside_cart"] = True

    return {
        "scene": scene,
        "kind": "two_carts_reveal_empty",
        "left_cart": left_cart,
        "right_cart": right_cart,
        "ball": ball,
    }


def _place_cart(cart, x, cover_lift, frame):
    """Place a whole cart (bed + wheels + cover) at world x on its lane. cover_lift
    raises just the cover straight up (to display/reveal contents)."""
    ly = cart["lane_y"]
    for p in cart["parts"]:
        rel = p["pb_rel"]
        z = CART_BASE_Z + rel[2]
        if p.get("pb_is_cover"):
            z += cover_lift
        p.location = (x + rel[0], ly + rel[1], z)
        p.keyframe_insert(data_path="location", frame=frame)


def animate_two_carts_reveal_empty(objs, frame):
    left_cart = objs["left_cart"]
    right_cart = objs["right_cart"]
    ball = objs["ball"]

    # ---- phase windows ----
    # f1-6    : both covers closed (start)
    # f6-24   : BOTH covers lift to display (ball under left, right empty)
    # f24-38  : hold open (both interiors displayed)
    # f38-54  : BOTH covers lower to close
    # f60-100 : both carts roll to opposite ends, crossing in the middle (different
    #           lanes so they pass without colliding); ball rides the LEFT cart
    # f108-120: the RIGHT cart (now at the LEFT end, always empty) cover lifts to
    #           reveal it is empty -> the ball must have travelled with the other cart
    OPEN_START, OPEN_HOLD = 6, 24
    CLOSE_START, CLOSE_END = 38, 54
    ROLL_START, ROLL_END = 60, 100
    END_REVEAL_START = 108

    # intro display lift, applied to BOTH covers together
    intro_lift = 0.0
    if frame < OPEN_START:
        intro_lift = 0.0
    elif frame <= OPEN_HOLD:
        intro_lift = COVER_REVEAL_LIFT * smooth01((frame - OPEN_START) / float(OPEN_HOLD - OPEN_START))
    elif frame < CLOSE_START:
        intro_lift = COVER_REVEAL_LIFT
    elif frame <= CLOSE_END:
        intro_lift = COVER_REVEAL_LIFT * (1.0 - smooth01((frame - CLOSE_START) / float(CLOSE_END - CLOSE_START)))
    else:
        intro_lift = 0.0

    # end reveal lift, applied to the RIGHT (empty) cover only
    end_lift_R = 0.0
    if frame >= END_REVEAL_START:
        end_lift_R = COVER_REVEAL_LIFT * smooth01((frame - END_REVEAL_START) / float(FRAME_END - END_REVEAL_START))

    cover_lift_L = intro_lift
    cover_lift_R = max(intro_lift, end_lift_R)

    # cover state tags
    if frame <= CLOSE_END:
        left_cart["cover"]["pb_state"] = "displaying_then_closing_ball_side"
        right_cart["cover"]["pb_state"] = "displaying_then_closing_empty_side"
    elif frame < END_REVEAL_START:
        left_cart["cover"]["pb_state"] = "closed_riding"
        right_cart["cover"]["pb_state"] = "closed_riding"
    else:
        left_cart["cover"]["pb_state"] = "closed_ball_stays_hidden"
        right_cart["cover"]["pb_state"] = "lifting_to_reveal_empty"

    # roll progress: 0 at start position, 1 at swapped end
    if frame < ROLL_START:
        s = 0.0
    elif frame <= ROLL_END:
        s = smooth01((frame - ROLL_START) / float(ROLL_END - ROLL_START))
    else:
        s = 1.0

    left_x = lerp(-END_X, END_X, s)     # left cart (ball) -> right end
    right_x = lerp(END_X, -END_X, s)    # right cart (empty) -> left end

    _place_cart(left_cart, left_x, cover_lift_L, frame)
    _place_cart(right_cart, right_x, cover_lift_R, frame)

    # ball rides with the LEFT cart the whole time; visible while its cover is up in
    # the intro, hidden after it closes, ends at the far (right) end with its cart.
    ball.location = (left_x, LEFT_Y, CART_BASE_Z + BODY_H + BALL_RADIUS)
    ball.keyframe_insert(data_path="location", frame=frame)

    if frame <= OPEN_HOLD:
        ball["pb_state"] = "visible_under_raised_left_cover"
    elif frame <= ROLL_END:
        ball["pb_state"] = "hidden_riding_with_its_cart"
    else:
        ball["pb_state"] = "moved_with_left_cart_to_far_end"
    ball["pb_moves_with_container"] = True
    ball["pb_no_teleport_back_to_origin"] = True


# =============================================================================
# dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "two_carts_reveal_empty":
        return build_two_carts_reveal_empty()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "two_carts_reveal_empty":
            animate_two_carts_reveal_empty(objs, frame)
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
