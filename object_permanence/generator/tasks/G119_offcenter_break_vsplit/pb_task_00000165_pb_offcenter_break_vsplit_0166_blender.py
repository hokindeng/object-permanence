# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_OFFCENTER_BREAK_VSPLIT_0166",
  "scene_kind": "offcenter_break_vsplit",
  "prompt": "A ball rolls into the seam of two touching balls at rest, striking them off-center. The two struck balls scatter apart symmetrically to the left and right while the incoming ball slows; momentum is shared and the ball count is conserved."
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


def add_cylinder(name, location, radius, depth, rotation=(0, 0, 0), material=None, role="static_solid", color_name="gray", is_dynamic=False, solid=True, vertices=32):
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


def add_oriented_box(name, center, length, width, height, direction, material, role, color_name, is_dynamic=False, solid=True):
    direction = Vector(direction).normalized()
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.scale = (length / 2.0, width / 2.0, height / 2.0)
    obj.rotation_euler = direction.to_track_quat("X", "Z").to_euler()
    if material is not None:
        obj.data.materials.append(material)
    tag(
        obj,
        name,
        role,
        "dynamic_object" if is_dynamic else ("static_solid" if solid else "non_solid_marker"),
        "oriented_cube",
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
    MATS["green"] = make_mat("mat_green", (0.12, 0.62, 0.22), roughness=0.34)
    MATS["black"] = make_mat("mat_black", (0.03, 0.03, 0.035), roughness=0.78)
    MATS["glass"] = make_mat("mat_glass", (0.50, 0.82, 1.0), roughness=0.08, alpha=0.32, blend="BLEND")
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    # Floor spans y in [-3.1, 3.1] so it underlies the full playfield,
    # including the incoming ball's approach start at y = -2.7.
    add_cube("large_floor_base", (0.0, 0.0, -0.05), (10.0, 6.2, 0.10), MATS["floor"], role="ground", color_name="warm_beige")
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
# scene 0166 off-center break (V-split)
#
# Two identical balls rest on the floor TOUCHING each other side-by-side along
# the X axis: their centers are one diameter apart (x = -R, +R at the same y),
# so their surfaces just touch at the seam (x = 0). A third incoming ball rolls
# in from the FRONT (from -Y toward +Y) straight along the seam plane (x = 0),
# aimed at the contact seam between the two resting balls -- an OFF-CENTER strike
# that splits the pair.
#
# Contact happens when the incoming ball's surface simultaneously touches both
# resting balls. With the incoming ball centered on x = 0 at y = y_in and the
# resting balls at (+/-R, y_rest), contact is when
#   dist((0, y_in), (R, y_rest)) = 2R
#   => (y_rest - y_in)^2 = (2R)^2 - R^2 = 3 R^2  => y_in = y_rest - R*sqrt(3).
# At that instant the line of centres from the incoming ball to each resting
# ball points outward-and-forward at +/-30 deg from the seam plane, so the two
# struck balls recoil SYMMETRICALLY along those lines (left/right + forward),
# while the incoming ball loses most of its speed and nearly halts at the seam.
#
# Impact model (equal masses, restitution e = 0.6 along each line of centres,
# unit direction (+/-1/2, sqrt(3)/2)):
#   impulse per struck ball  J = v_in * uy * (1 + e) / (1 + 2 uy^2),  uy = sqrt(3)/2
#   struck-ball exit speed   = J          = 0.554 * v_in   (SLOWER than incoming)
#   incoming after strike    = 0.04 * v_in (nearly stops, tiny forward drift)
# Momentum along +Y is conserved EXACTLY: 2 * J * uy + 0.04 v_in = v_in.
# Kinetic energy drops 38% at the strike (inelastic loss). After the strike all
# three balls decelerate under constant rolling friction and ease to rest; the
# struck balls' roll-out is sized to stop SHORT of the rear backboard, so no
# wall rebound occurs.
# No interpenetration: contact is defined at surface-touch, and post-impact the
# separations only increase. Ball count is conserved (always exactly 3).
# =============================================================================

def build_offcenter_break_scene():
    scene = build_base_scene()
    setup_camera(scene, location=(0.0, -7.6, 3.15), target=(0.0, 0.6, 0.30), lens=34)

    R = 0.26
    z = 0.06 + R  # ball center height so the ball rests on the track top (z_top=0.12? track below)

    # A wide flat playfield / low table for the balls to roll on. It sits
    # flush on the floor (bottom at z = 0) and its front edge (y = -2.9)
    # reaches behind the incoming ball's start (centre y = -2.7), so every
    # ball is supported by the playfield from frame 1 -- nothing hovers.
    add_cube("break_playfield", (0.0, 0.0, 0.05), (6.6, 5.8, 0.10), MATS["gray"], role="playfield", color_name="gray")
    z = 0.10 + R  # rest on the playfield top (thickness 0.10 -> top at 0.10)

    y_rest = 0.9  # the two resting balls sit a bit back from center

    # Two touching resting balls, centers one diameter apart along X.
    left = add_sphere("resting_ball_left", R, (-R, y_rest, z), MATS["blue"], "blue")
    right = add_sphere("resting_ball_right", R, (R, y_rest, z), MATS["green"], "green")
    left["pb_role_note"] = "struck_scatters_left"
    right["pb_role_note"] = "struck_scatters_right"

    # Incoming ball approaches along +Y on the seam plane x = 0.
    incoming = add_sphere("incoming_ball", R, (0.0, -2.7, z), MATS["orange"], "orange")
    incoming["pb_role_note"] = "incoming_strikes_seam"

    return {
        "scene": scene,
        "kind": "offcenter_break_vsplit",
        "left": left,
        "right": right,
        "incoming": incoming,
        "R": R,
        "z": z,
        "y_rest": y_rest,
    }


def _roll_rotation(obj, radius, prev_pos, cur_pos):
    """Accumulate a rolling rotation proportional to the ball's displacement.

    Rolls about the horizontal axis (up x travel_dir) by (distance / radius)
    radians, so spin rate is proportional to linear speed and exactly zero
    while the ball is at rest.
    """
    delta = Vector(cur_pos) - Vector(prev_pos)
    delta.z = 0.0
    dist = delta.length
    if dist < 1e-7:
        return
    travel_d = delta.normalized()
    up = Vector((0.0, 0.0, 1.0))
    axis = up.cross(travel_d)
    if axis.length < 1e-7:
        return
    axis.normalize()
    angle = dist / radius
    from mathutils import Quaternion
    q = Quaternion(axis, angle)
    cur = obj.rotation_euler.to_quaternion()
    obj.rotation_euler = (q @ cur).to_euler()


def animate_offcenter_break_scene(objs, frame):
    left = objs["left"]
    right = objs["right"]
    incoming = objs["incoming"]
    R = objs["R"]
    z = objs["z"]
    y_rest = objs["y_rest"]

    # Contact geometry: incoming ball center reaches y_contact on the seam plane.
    y_contact = y_rest - R * math.sqrt(3.0)          # incoming center at contact
    y_start = -2.7

    # Unit outward-forward directions for the struck balls (+/-30 deg from +Y).
    # Line of centres from incoming(0, y_contact) to right(+R, y_rest):
    #   dx = R, dy = R*sqrt(3), length 2R -> unit = (0.5, sqrt(3)/2).
    ux, uy = 0.5, math.sqrt(3.0) / 2.0

    impact_frame = 52

    # Incoming approach speed (constant, linear over frames 1..52): ~0.0618 u/f.
    v_in = (y_contact - y_start) / float(impact_frame - FRAME_START)

    # Symmetric two-ball strike with restitution e along each line of centres
    # (see header). Equal masses; momentum along +Y conserved exactly.
    e_rest = 0.6
    j_struck = v_in * uy * (1.0 + e_rest) / (1.0 + 2.0 * uy * uy)   # 0.554*v_in ~0.0342
    v_inc_after = v_in * (1.0 - 2.0 * uy * uy * (1.0 + e_rest) / (1.0 + 2.0 * uy * uy))  # 0.04*v_in

    # Struck-ball roll-out: constant friction deceleration from j_struck to rest
    # after S_STOP of arc length. S_STOP is chosen SHORT of the backboard
    # (centre-contact arc s_wall ~1.47), so the balls stop on the playfield and
    # never touch the wall: max centre y = y_rest + uy*S_STOP = 1.85 < 2.175.
    S_STOP = 1.10
    a_struck = (j_struck * j_struck) / (2.0 * S_STOP)
    dt_struck = j_struck / a_struck              # ~64.3 frames -> rest by frame ~116

    # Incoming ball's residual forward drift: decelerates to a stop in 30 frames
    # (total extra drift ~0.037), never reaching the struck balls.
    dt_inc = 30.0
    a_inc = v_inc_after / dt_inc

    if frame <= impact_frame:
        # Phase A: incoming ball rolls in at constant speed to the seam contact.
        t = (frame - FRAME_START) / float(impact_frame - FRAME_START)
        iy = lerp(y_start, y_contact, t)
        ix = 0.0
        # Resting balls stay put, just touching.
        lx, ly = -R, y_rest
        rx, ry = R, y_rest
        inc_state = "approaching_seam_constant_speed"
        struck_state = "at_rest_touching"
    else:
        # Phase B: symmetric split. Each struck ball leaves the strike at
        # j_struck (0.554x the incoming speed -- SLOWER than the incoming ball
        # arrived) along its outward line of centres, then decelerates under
        # constant rolling friction and eases to rest short of the backboard.
        df = frame - impact_frame
        if df >= dt_struck:
            s = S_STOP
            struck_state = "at_rest_after_symmetric_scatter"
        else:
            s = j_struck * df - 0.5 * a_struck * df * df
            struck_state = "scattering_symmetrically_decelerating"

        lx = -R - ux * s
        rx = R + ux * s
        ly = y_rest + uy * s
        ry = ly

        # Incoming ball nearly stops at the seam: tiny forward drift that
        # decelerates smoothly to rest (velocity continuous after the impact
        # drop from v_in to v_inc_after).
        if df >= dt_inc:
            drift = v_inc_after * dt_inc * 0.5
        else:
            drift = v_inc_after * df - 0.5 * a_inc * df * df
        iy = y_contact + drift
        ix = 0.0
        inc_state = "slowed_near_seam_after_strike"

    prev = objs.setdefault("_prev_pos", {})

    incoming.location = (ix, iy, z)
    if "incoming" in prev:
        _roll_rotation(incoming, R, prev["incoming"], incoming.location)
    incoming.keyframe_insert(data_path="location", frame=frame)
    incoming.keyframe_insert(data_path="rotation_euler", frame=frame)
    incoming["pb_state"] = inc_state
    incoming["pb_count_conserved"] = True

    left.location = (lx, ly, z)
    if "left" in prev:
        _roll_rotation(left, R, prev["left"], left.location)
    left.keyframe_insert(data_path="location", frame=frame)
    left.keyframe_insert(data_path="rotation_euler", frame=frame)
    left["pb_state"] = struck_state

    right.location = (rx, ry, z)
    if "right" in prev:
        _roll_rotation(right, R, prev["right"], right.location)
    right.keyframe_insert(data_path="location", frame=frame)
    right.keyframe_insert(data_path="rotation_euler", frame=frame)
    right["pb_state"] = struck_state

    prev["incoming"] = Vector(incoming.location)
    prev["left"] = Vector(left.location)
    prev["right"] = Vector(right.location)

    for b in (left, right, incoming):
        b["pb_no_interpenetration"] = True


# =============================================================================
# dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "offcenter_break_vsplit":
        return build_offcenter_break_scene()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "offcenter_break_vsplit":
            animate_offcenter_break_scene(objs, frame)
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
