# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_ONE_WAY_FLAP_GATE_0157",
  "kind": "one_way_flap_gate",
  "prompt": "Two identical one-way flap gates stand side by side across two parallel flat lanes. Each flap is hinged so it can swing open only toward the downstream (+X) direction, backed by a fixed stop so it cannot swing the other way. In the near lane a pink ball rolls in from the OPENABLE side: it pushes its flap open, passes through, and then rolls on decelerating smoothly to rest as the flap swings shut behind it. In the far lane a teal ball rolls in from the BLOCKED side toward an identical flap; the stop prevents the flap from opening that way, so the teal ball is halted at the gate, decelerating to rest pressing against the closed flap, unable to get through. The two lanes are separate, so the balls never touch each other -- the contrast shows the gate passes one direction and blocks the other."
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


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def lerp(a, b, t):
    return a + (b - a) * t


def smooth01(t):
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


def make_mat(name, color, roughness=0.55, metallic=0.0, alpha=1.0):
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

    return mat


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), roughness=0.85)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.92)

    MATS["gray"] = make_mat("mat_gray", (0.62, 0.63, 0.66), roughness=0.75)
    MATS["dark"] = make_mat("mat_dark", (0.18, 0.20, 0.24), roughness=0.55)
    MATS["screen"] = make_mat("mat_screen", (0.46, 0.48, 0.53), roughness=0.88)
    MATS["support"] = make_mat("mat_support", (0.16, 0.18, 0.22), roughness=0.60)

    MATS["red"] = make_mat("mat_red", (0.92, 0.18, 0.18), roughness=0.28)
    MATS["blue"] = make_mat("mat_blue", (0.16, 0.36, 0.95), roughness=0.28)
    MATS["yellow"] = make_mat("mat_yellow", (0.98, 0.78, 0.15), roughness=0.28)
    MATS["orange"] = make_mat("mat_orange", (0.97, 0.45, 0.10), roughness=0.28)
    MATS["pink"] = make_mat("mat_pink", (0.95, 0.35, 0.62), roughness=0.28)
    MATS["teal"] = make_mat("mat_teal", (0.10, 0.72, 0.62), roughness=0.28)


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
        "dynamic_object" if is_dynamic else "static_solid",
        "cube",
        color_name,
        is_dynamic,
        solid=solid,
    )
    return obj


def add_oriented_box(name, location, dimensions, yaw_deg, material, role, color_name, is_dynamic=False, solid=True):
    # A box rotated about the world Z axis by yaw_deg degrees.
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=(0.0, 0.0, math.radians(yaw_deg)))
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    if material is not None:
        obj.data.materials.append(material)

    tag(
        obj,
        name,
        role,
        "dynamic_object" if is_dynamic else "static_solid",
        "oriented_box",
        color_name,
        is_dynamic,
        solid=solid,
        pb_yaw_deg=float(yaw_deg),
    )
    return obj


def add_ball(name, radius, location, material, color_name):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=48, ring_count=24)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)

    tag(
        obj,
        name,
        "target",
        "dynamic_object",
        "sphere",
        color_name,
        True,
        solid=True,
        pb_radius=radius,
    )
    return obj


def add_cylinder_between(name, p1, p2, radius, material, role, color_name):
    p1 = Vector(p1)
    p2 = Vector(p2)
    diff = p2 - p1
    length = diff.length
    mid = (p1 + p2) / 2.0

    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=length, vertices=24, location=mid)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = diff.to_track_quat("Z", "Y").to_euler()

    if material is not None:
        obj.data.materials.append(material)

    tag(obj, name, role, "static_solid", "cylinder", color_name, False, solid=True)
    return obj


def add_vertical_cylinder(name, location, radius, height, material, role, color_name):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=height, vertices=32, location=location)
    obj = bpy.context.object
    obj.name = name

    if material is not None:
        obj.data.materials.append(material)

    tag(obj, name, role, "static_solid", "cylinder", color_name, False, solid=True)
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
        scene.eevee.gtao_distance = 3.0
        scene.eevee.gtao_factor = 1.2
    except Exception:
        pass

    if scene.world is None:
        scene.world = bpy.data.worlds.new("clean_world")
    scene.world.color = (1.0, 1.0, 1.0)

    try:
        scene.view_settings.view_transform = "Filmic"
        scene.view_settings.look = "Medium High Contrast"
    except Exception:
        pass


def setup_base(camera_loc, target, ortho_scale):
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (11.0, 7.0, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.05, 1.65), (11.0, 0.08, 3.3), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-2.8, -4.5, 5.8))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 950
    key.data.size = 5.5

    bpy.ops.object.light_add(type="POINT", location=(3.0, 1.8, 3.3))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 120

    bpy.ops.object.camera_add(location=camera_loc)
    cam = bpy.context.object
    cam.name = "camera_main"
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = ortho_scale
    look_at(cam, target)
    scene.camera = cam

    return scene


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


def write_task_json(task):
    with open(TASK_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(task, f, indent=2, ensure_ascii=False)


def save_scene():
    bpy.ops.wm.save_as_mainfile(filepath=SCENE_FILE)


# =============================================================================
# 00000156  one_way_flap_gate
# =============================================================================

def build_one_way_flap_gate():
    scene = setup_base(
        camera_loc=(6.6, -7.6, 7.0),
        target=(0.0, 0.0, 0.30),
        ortho_scale=9.4,
    )

    ball_radius = 0.24
    floor_z = ball_radius  # ball-center height for a ball resting on the floor

    gate_x = 0.0                 # both flaps straddle their lane at x = 0
    track_x0 = -3.9
    track_x1 = 3.9

    # ----- Two parallel flat lanes, side by side (separate Y) -----
    # Each lane is a clean flat lane: the ball rolls on the floor along the lane
    # centre-line at centre height z = ball_radius. The "track" is just two low,
    # smooth rounded guide curbs running the full length well OUTSIDE the ball's swept
    # width, so the ball never touches them. No rail under the ball -> no clipping.
    # Because the two lanes have DIFFERENT Y, the two balls never collide or clip.
    curb_y = 0.42                # curb axis offset from the lane centre (> ball_radius)
    curb_r = 0.05
    curb_z = curb_r              # rests on the floor (bottom flush at z = 0)

    flap_len = 2.0 * curb_y      # panel spans the full lane width (Y), from curb to curb
    flap_thick = 0.06
    flap_h = 0.46
    flap_cz = floor_z + 0.01     # bottom just above the floor, top at z = floor_z + 0.24

    def build_lane(lane_y, label):
        # ----- Clean flat lane (no clip) -----
        for side, dy in [("near", -curb_y), ("far", curb_y)]:
            add_cylinder_between(
                f"lane_{label}_guide_curb_{side}",
                (track_x0, lane_y + dy, curb_z),
                (track_x1, lane_y + dy, curb_z),
                curb_r, MATS["dark"], "lane_guide_curb", "dark_gray",
            )
        # A subtle flat lane inlay flush with the floor top (does not rise above the
        # floor, so it cannot clip the ball).
        add_cube(
            f"lane_{label}_flat_strip",
            (0.0, lane_y, -0.005),
            (track_x1 - track_x0, 2.0 * curb_y, 0.02), MATS["screen"], "lane_surface", "gray",
        )

        # ----- One-way hinged FLAP GATE (identical on both lanes) -----
        # A vertical panel hinged on a vertical post at the FAR (+Y) edge of the lane.
        # When CLOSED it lies flat across the lane, blocking it. The hinge only lets it
        # swing toward +X (downstream, the "openable side"): a fixed STOP block on the
        # -X side of the free-edge post (OUTSIDE the ball lane in Y) catches the flap's
        # free edge and prevents any rotation toward -X. So a ball arriving from -X
        # (openable side) pushes the flap open (it swings to +X, away from the stop) and
        # passes; a ball arriving from +X pushes the flap toward -X, where the stop
        # halts it -> the flap stays shut. Panel origin is on the hinge (empty parent)
        # -> pure Z-rotation pivots at the hinge with no translation.
        hinge_y = lane_y + curb_y            # hinge at the FAR (+Y) edge of the lane

        piv = bpy.data.objects.new(f"flap_{label}_pivot", None)
        piv.location = (gate_x, hinge_y, flap_cz)
        bpy.context.scene.collection.objects.link(piv)
        piv["pb_object_id"] = f"flap_{label}_pivot"
        piv["pb_role"] = "flap_hinge"
        piv["pb_is_dynamic"] = True

        add_vertical_cylinder(
            f"flap_{label}_hinge_post",
            (gate_x, hinge_y, (flap_h + 0.14) / 2.0),
            0.04, flap_h + 0.14, MATS["dark"], "flap_post", "dark_gray",
        )

        # The flap panel, extending from the hinge toward the NEAR (-Y) side of the lane.
        panel = add_cube(
            f"one_way_flap_{label}_panel",
            (gate_x, hinge_y - flap_len / 2.0, flap_cz),
            (flap_thick, flap_len, flap_h), MATS["gray"], "flap_gate", "gray",
            is_dynamic=True,
        )
        panel.parent = piv
        panel.matrix_parent_inverse = piv.matrix_world.inverted()
        panel["pb_opens_only_toward_open_side"] = True

        # ----- Fixed STOP that makes the flap one-way -----
        # A short jamb on the -X side of the flap's FREE edge, well OUTSIDE the ball lane
        # in Y so it never obstructs a rolling ball. It catches the flap's free-edge
        # corner if the flap tries to swing toward -X, so a ball from +X cannot push it
        # open. A matching vertical post at the free edge reads as the doorway jamb.
        free_edge_y = hinge_y - flap_len     # y of the flap's free edge (the near curb)
        add_vertical_cylinder(
            f"flap_{label}_free_edge_post",
            (gate_x, free_edge_y, (flap_h + 0.14) / 2.0),
            0.04, flap_h + 0.14, MATS["dark"], "flap_post", "dark_gray",
        )
        add_cube(
            f"flap_{label}_one_side_stop",
            (gate_x - flap_thick / 2.0 - 0.04, free_edge_y, flap_cz),
            (0.06, 0.16, flap_h), MATS["dark"], "flap_stop", "dark_gray",
        )["pb_blocks_flap_swing_toward_stop_side"] = True

        return piv

    # Two lanes, well separated in Y so the balls never collide or clip.
    pass_lane_y = 1.4            # PINK lane (openable side)
    block_lane_y = -1.4         # TEAL lane (blocked side)
    pass_piv = build_lane(pass_lane_y, "pass")
    block_piv = build_lane(block_lane_y, "block")

    # ----- Pink ball: OPENABLE side (-X) of the PASS lane -----
    # Rolls in, pushes its flap open, passes through, then DECELERATES smoothly to rest.
    pink = add_ball(
        "pass_pink_ball", ball_radius, (track_x0 + 0.5, pass_lane_y, floor_z),
        MATS["pink"], "pink",
    )
    pink["pb_side"] = "openable_side_minus_x"
    pink["pb_path"] = "pushes_flap_open_passes_through_then_decelerates_to_rest"

    # ----- Teal ball: BLOCKED side (+X) of the BLOCK lane -----
    # Rolls in toward an identical, stop-backed flap that cannot open that way; it is
    # halted at the gate, decelerating to rest pressing against the closed flap.
    teal = add_ball(
        "blocked_teal_ball", ball_radius, (track_x1 - 0.5, block_lane_y, floor_z),
        MATS["teal"], "teal",
    )
    teal["pb_side"] = "blocked_side_plus_x"
    teal["pb_path"] = "meets_stop_backed_flap_and_is_halted_resting_against_it"

    return scene, {
        "pink": pink,
        "teal": teal,
        "pass_piv": pass_piv,
        "block_piv": block_piv,
        "flap_thick": flap_thick,
        "flap_len": flap_len,
        "ball_radius": ball_radius,
        "curb_y": curb_y,
        "pass_lane_y": pass_lane_y,
        "block_lane_y": block_lane_y,
        "gate_x": gate_x,
        "track_x0": track_x0,
        "track_x1": track_x1,
        "floor_z": floor_z,
    }


def easeout(t):
    # Fast start, easing into the target -> flap swings open promptly as the ball hits it.
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return 1.0 - (1.0 - t) * (1.0 - t)


def animate_one_way_flap_gate(scene, meta):
    pink = meta["pink"]
    teal = meta["teal"]
    pass_piv = meta["pass_piv"]
    block_piv = meta["block_piv"]
    radius = meta["ball_radius"]
    pass_lane_y = meta["pass_lane_y"]
    block_lane_y = meta["block_lane_y"]
    gate_x = meta["gate_x"]
    track_x0 = meta["track_x0"]
    track_x1 = meta["track_x1"]

    max_open = math.radians(92.0)   # flap opens toward +X (positive Z-rotation of pivot)

    # The two balls live on separate lanes (different Y), so their motions are wholly
    # independent -- they never collide or clip. Each is designed to DECELERATE, never
    # accelerate: pink coasts through the gate at constant speed then ramps its velocity
    # linearly to zero; teal ramps its velocity linearly to zero into the closed flap.

    # ================= PINK: openable side (-X). In at constant speed, pushes the flap
    # open, passes through, then a LINEAR velocity ramp to rest downstream. =============
    pink_start = track_x0 + 0.5          # -3.4
    H0 = 4                               # brief settle before it starts rolling
    v_pink = 0.07                        # constant inflow speed (units / frame)
    f_clear = 65                         # ball centre reaches x_clear here (fully past gate)
    x_clear = pink_start + v_pink * (f_clear - H0)   # ~0.87
    T_decel = 40                         # frames of linear deceleration to rest
    f_stop = f_clear + T_decel           # 105

    def pink_x(frame):
        if frame <= H0:
            return pink_start
        if frame <= f_clear:
            return pink_start + v_pink * (frame - H0)        # constant speed in + through
        if frame <= f_stop:
            tau = frame - f_clear
            # v(tau) = v_pink * (1 - tau/T_decel): linear ramp to zero -> pure decel.
            return x_clear + v_pink * tau - (v_pink / (2.0 * T_decel)) * tau * tau
        tau = T_decel
        return x_clear + v_pink * tau - (v_pink / (2.0 * T_decel)) * tau * tau  # at rest

    # Flap opens as the ball drives through, then swings shut behind it once it clears.
    open_start = 48                      # ball's front just reaches the closed flap here
    N_open = 10                          # swings open (verified clear of the passing ball)
    close_start = 68                     # ball has cleared downstream
    close_end = close_start + 16

    def pass_flap_angle(frame):
        if frame < open_start:
            return 0.0
        if frame < open_start + N_open:
            return max_open * easeout((frame - open_start) / float(N_open))
        if frame < close_start:
            return max_open
        if frame < close_end:
            return max_open * (1.0 - smooth01((frame - close_start) / float(close_end - close_start)))
        return 0.0

    # ================= TEAL: blocked side (+X). In at constant speed, then a LINEAR
    # velocity ramp to rest pressing against the stop-backed (never-opening) flap. ======
    teal_start = track_x1 - 0.5          # +3.4
    T0 = 10                              # brief settle before it starts rolling
    v_teal = 0.06                        # constant inflow speed (units / frame)
    f_decel_t = 52                       # begins decelerating here
    T_decel_t = 20
    f_stop_t = f_decel_t + T_decel_t     # 72
    x_decel_start_t = teal_start - v_teal * (f_decel_t - T0)
    # Rest pressed against the closed flap's +X face (front surface just touches it).
    teal_rest = x_decel_start_t - v_teal * T_decel_t / 2.0

    def teal_x(frame):
        if frame <= T0:
            return teal_start
        if frame <= f_decel_t:
            return teal_start - v_teal * (frame - T0)        # constant speed inbound
        if frame <= f_stop_t:
            tau = frame - f_decel_t
            return x_decel_start_t - v_teal * tau + (v_teal / (2.0 * T_decel_t)) * tau * tau
        return teal_rest                                     # halted, pressing the flap

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        pass_piv.rotation_euler = (0.0, 0.0, pass_flap_angle(frame))
        pass_piv.keyframe_insert(data_path="rotation_euler", frame=frame)
        # The blocked-lane flap is stop-backed and never opens toward the teal ball.
        block_piv.rotation_euler = (0.0, 0.0, 0.0)
        block_piv.keyframe_insert(data_path="rotation_euler", frame=frame)

        xp = pink_x(frame)
        pink.location = (xp, pass_lane_y, radius)
        pink.rotation_euler = (0.0, (xp - pink_start) / radius, 0.0)
        pink.keyframe_insert(data_path="location", frame=frame)
        pink.keyframe_insert(data_path="rotation_euler", frame=frame)
        pink["pb_state"] = "pushing_flap_open_passing_through_then_decelerating_to_rest"

        xt = teal_x(frame)
        teal.location = (xt, block_lane_y, radius)
        teal.rotation_euler = (0.0, (xt - teal_start) / radius, 0.0)
        teal.keyframe_insert(data_path="location", frame=frame)
        teal.keyframe_insert(data_path="rotation_euler", frame=frame)
        teal["pb_state"] = "halted_by_one_way_flap_on_blocked_side_resting_against_it"

    scene.frame_set(FRAME_START)


# =============================================================================
# Dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["kind"]

    if kind == "one_way_flap_gate":
        return build_one_way_flap_gate()

    raise RuntimeError("Unknown kind: " + str(kind))


def animate_scene_by_kind(scene, meta):
    kind = CASE["kind"]

    if kind == "one_way_flap_gate":
        return animate_one_way_flap_gate(scene, meta)

    raise RuntimeError("Unknown kind: " + str(kind))


def main():
    ensure_dirs()
    clear_scene()

    scene, meta = build_scene_by_kind()
    animate_scene_by_kind(scene, meta)

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

    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, 60, OPTIONAL_FRAME_PATH)
    render_png(scene, 120, OPTIONAL_FRAME_02B_PATH)
    render_animation(scene)
    write_task_json(task)
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("kind:", CASE["kind"])
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
