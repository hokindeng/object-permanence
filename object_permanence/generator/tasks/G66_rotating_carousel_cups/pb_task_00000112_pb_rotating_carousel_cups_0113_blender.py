# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_ROTATING_CAROUSEL_CUPS_0113",
  "scene_kind": "rotating_carousel_cups",
  "prompt": "Three identical opaque cups stand on a round turntable; a ball is shown under the front cup before it lowers over the ball. The turntable then rotates 180 degrees, carrying all three cups around with it. When it stops, the cup that began at the front is now at the back; that cup lifts to reveal the ball still under it - the ball moved with its cup rotationally, rather than staying at the original front position."
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
    MATS["cup"] = make_mat("mat_cup_red", (0.78, 0.10, 0.09), roughness=0.42)
    MATS["table"] = make_mat("mat_table_wood", (0.55, 0.40, 0.26), roughness=0.70)
    MATS["turntable"] = make_mat("mat_turntable", (0.30, 0.32, 0.36), roughness=0.55)
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
# scene 0113 rotating carousel of cups
# =============================================================================

# table top surface height (z the turntable sits on)
TABLE_TOP_Z = 0.45

# turntable disc that sits on the table; cups stand on the disc top
TURNTABLE_RADIUS = 2.05
TURNTABLE_THICK = 0.14
# top face of the turntable disc = the surface the cups (and ball) rest on
DISC_TOP_Z = TABLE_TOP_Z + TURNTABLE_THICK

# turntable center (world x,y); rotation happens about the vertical axis here
CENTER = (0.0, 0.0)

# cup geometry (upside-down cup = wall cylinder + solid cap disk on top)
CUP_RADIUS = 0.42
CUP_WALL_HEIGHT = 0.74
CUP_CAP = 0.07               # cap disk thickness on top of the wall

# radial distance of each cup from the turntable center
CUP_ORBIT_RADIUS = 1.30

# the three cups sit 120 degrees apart on the disc.
# angle 0 (measured from +Y toward +X) = FRONT position (nearest camera at -Y).
# we use the convention: world x = center_x + r*sin(theta), y = center_y - r*cos(theta)
# so theta=0 -> (0, -r) = front (toward camera), theta=180 -> (0, +r) = back.
CUP_START_ANGLES_DEG = [0.0, 120.0, 240.0]   # front, back-right, back-left

# ball geometry
BALL_RADIUS = 0.16

# vertical lift for the reveal / initial show (lift fully clear of the ball)
CUP_REVEAL_LIFT = CUP_WALL_HEIGHT + CUP_CAP + 0.55

# total rotation of the whole assembly, in radians (180 degrees)
TOTAL_ROTATION = math.pi


def _orbit_xy(angle_rad):
    """World (x, y) of a cup at the given orbit angle around the turntable center."""
    cx, cy = CENTER
    x = cx + CUP_ORBIT_RADIUS * math.sin(angle_rad)
    y = cy - CUP_ORBIT_RADIUS * math.cos(angle_rad)
    return x, y


def _make_cup(prefix, cup_index, angle_rad):
    """Build one upside-down opaque cup as a wall cylinder + a top cap disk.

    The cup's local base is its orbit position on the disc top (z = DISC_TOP_Z).
    Each part stores pb_rel_z (its z offset above the disc-top base).
    The cup's orbit angle is tracked in pb_angle (radians).
    """
    x, y = _orbit_xy(angle_rad)
    parts = []

    wall = add_cylinder(
        f"{prefix}_wall",
        (x, y, DISC_TOP_Z + CUP_WALL_HEIGHT / 2.0),
        CUP_RADIUS,
        CUP_WALL_HEIGHT,
        material=MATS["cup"],
        role="opaque_cup_wall",
        color_name="red",
        is_dynamic=True,
        solid=True,
        vertices=48,
    )
    wall["pb_rel_z"] = CUP_WALL_HEIGHT / 2.0
    parts.append(wall)

    cap = add_cylinder(
        f"{prefix}_cap",
        (x, y, DISC_TOP_Z + CUP_WALL_HEIGHT + CUP_CAP / 2.0),
        CUP_RADIUS,
        CUP_CAP,
        material=MATS["cup"],
        role="opaque_cup_cap",
        color_name="red",
        is_dynamic=True,
        solid=True,
        vertices=48,
    )
    cap["pb_rel_z"] = CUP_WALL_HEIGHT + CUP_CAP / 2.0
    parts.append(cap)

    for p in parts:
        p["pb_cup_index"] = cup_index
        p["pb_start_angle"] = angle_rad
        p["pb_is_cup_part"] = True

    return {"parts": parts, "cup_index": cup_index, "start_angle": angle_rad}


def build_rotating_carousel_cups():
    scene = build_base_scene()
    # slightly elevated 3/4 view so the turntable rotation reads clearly.
    # cups orbit at radius 1.3 around origin; camera off to the left-front, raised.
    # The final reveal happens on the far side of the carousel.  An elevated
    # view keeps the revealed ball above the nearer cups for every camera orbit.
    setup_camera(scene, location=(-3.9, -7.4, 6.6), target=(0.0, 0.0, 0.55), lens=40)

    # supporting table the turntable rests on
    add_cube(
        "carousel_table",
        (0.0, 0.0, TABLE_TOP_Z - 0.09),
        (6.6, 3.4, 0.18),
        MATS["table"],
        role="table_surface",
        color_name="wood_brown",
    )

    # round turntable disc; the whole assembly rotates about its vertical axis
    turntable = add_cylinder(
        "turntable_disc",
        (CENTER[0], CENTER[1], TABLE_TOP_Z + TURNTABLE_THICK / 2.0),
        TURNTABLE_RADIUS,
        TURNTABLE_THICK,
        material=MATS["turntable"],
        role="turntable",
        color_name="slate_gray",
        is_dynamic=True,
        solid=True,
        vertices=64,
    )
    turntable["pb_is_turntable"] = True
    turntable["pb_angle"] = 0.0

    # three identical opaque cups, 120 degrees apart on the disc
    cups = []
    cups.append(_make_cup("cup_F", 0, math.radians(CUP_START_ANGLES_DEG[0])))   # FRONT, holds the ball
    cups.append(_make_cup("cup_B", 1, math.radians(CUP_START_ANGLES_DEG[1])))
    cups.append(_make_cup("cup_C", 2, math.radians(CUP_START_ANGLES_DEG[2])))

    # the ball lives under the front cup (cup_F) at the start
    fx, fy = _orbit_xy(math.radians(CUP_START_ANGLES_DEG[0]))
    ball = add_sphere(
        "hidden_ball",
        BALL_RADIUS,
        (fx, fy, DISC_TOP_Z + BALL_RADIUS),
        MATS["yellow"],
        "yellow",
    )
    ball["pb_inside_cup"] = True

    # cup that carries the ball, tracked by id (cup_F) through the rotation
    ball_cup = cups[0]

    return {
        "scene": scene,
        "kind": "rotating_carousel_cups",
        "turntable": turntable,
        "cups": cups,
        "ball": ball,
        "ball_cup": ball_cup,
    }


def _place_cup(cup, extra_angle, lift, frame):
    """Place a whole cup (wall + cap) rotated by extra_angle about the turntable
    center, with an optional vertical lift above the disc top."""
    angle = cup["start_angle"] + extra_angle
    x, y = _orbit_xy(angle)
    for p in cup["parts"]:
        z = DISC_TOP_Z + p["pb_rel_z"] + lift
        p.location = (x, y, z)
        p.keyframe_insert(data_path="location", frame=frame)
        # spin each cup about its own axis so its orientation follows the disc
        p.rotation_euler = (0.0, 0.0, extra_angle)
        p.keyframe_insert(data_path="rotation_euler", frame=frame)


def _place_turntable(turntable, extra_angle, frame):
    turntable.rotation_euler = (0.0, 0.0, extra_angle)
    turntable.keyframe_insert(data_path="rotation_euler", frame=frame)
    turntable["pb_angle"] = extra_angle


def _current_cup_xy(cup, extra_angle):
    """LIVE world (x, y) of a cup after being rotated by extra_angle this frame."""
    return _orbit_xy(cup["start_angle"] + extra_angle)


def animate_rotating_carousel_cups(objs, frame):
    turntable = objs["turntable"]
    cups = objs["cups"]
    ball = objs["ball"]
    ball_cup = objs["ball_cup"]

    cup_F, cup_B, cup_C = cups[0], cups[1], cups[2]

    # ---- phase windows ----
    # f1-14   : front cup (ball_cup) starts raised (ball shown), lowers to hide ball
    # f18-30  : settle (assembly at rest, extra_angle = 0)
    # f30-96  : turntable rotates 180 degrees, carrying all cups + hidden ball
    # f100-120: the ball-carrying cup (now at the BACK) lifts to reveal the ball

    ROT_START = 30
    ROT_END = 96

    # rotation of the whole assembly at this frame
    if frame < ROT_START:
        extra_angle = 0.0
    elif frame <= ROT_END:
        t = (frame - ROT_START) / float(ROT_END - ROT_START)
        extra_angle = TOTAL_ROTATION * smooth01(t)
    else:
        extra_angle = TOTAL_ROTATION

    # turntable disc follows the same rotation
    _place_turntable(turntable, extra_angle, frame)

    # place all three cups at the current rotation (default lift 0)
    lift_F = 0.0

    if frame <= 14:
        # front cup (ball_cup) raised at start (ball visible), lowers over the ball
        t = (frame - FRAME_START) / 13.0
        lift_F = CUP_REVEAL_LIFT * (1.0 - smooth01(t))
        cup_F["parts"][0]["pb_state"] = "lowering_to_hide_ball"
    elif frame > ROT_END + 3:
        # final reveal: ball_cup (now at the BACK) lifts off the ball
        t = (frame - (ROT_END + 4)) / float(FRAME_END - (ROT_END + 4))
        lift_F = CUP_REVEAL_LIFT * smooth01(t)
        cup_F["parts"][0]["pb_state"] = "lifting_to_reveal_ball"

    _place_cup(cup_F, extra_angle, lift_F, frame)
    _place_cup(cup_B, extra_angle, 0.0, frame)
    _place_cup(cup_C, extra_angle, 0.0, frame)

    # ball: hidden after f14, always pinned to the ball_cup's LIVE world position.
    # _place_cup has already moved the ball_cup for THIS frame; we recompute its
    # live orbit (x, y) from the same extra_angle so the ball rides exactly with
    # its container every frame and never stays at the original front position.
    if frame <= 14:
        bx, by = _orbit_xy(cup_F["start_angle"])   # still at the front
    else:
        bx, by = _current_cup_xy(ball_cup, extra_angle)
    ball.location = (bx, by, DISC_TOP_Z + BALL_RADIUS)
    ball.keyframe_insert(data_path="location", frame=frame)

    if frame <= 8:
        ball["pb_state"] = "visible_under_raised_front_cup"
    elif frame <= ROT_END + 3:
        ball["pb_state"] = "hidden_rotating_with_its_cup"
    else:
        ball["pb_state"] = "revealed_under_back_cup_moved_with_container"
    ball["pb_moves_with_container"] = True
    ball["pb_no_teleport_back_to_origin"] = True


# =============================================================================
# dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "rotating_carousel_cups":
        return build_rotating_carousel_cups()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "rotating_carousel_cups":
            animate_rotating_carousel_cups(objs, frame)
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
