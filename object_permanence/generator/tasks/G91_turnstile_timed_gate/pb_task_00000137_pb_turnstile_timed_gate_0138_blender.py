# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_TURNSTILE_TIMED_GATE_0138",
  "kind": "turnstile_timed_gate",
  "prompt": "Two balls roll along two parallel tracks toward two hinged flap gates, one per track. As each ball reaches its gate, the flap swings open on its vertical hinge (like a saloon door) to let the ball pass, then swings shut behind it while the ball rolls on. Both balls behave the same way. Neither ball is suspended and neither passes through a closed flap."
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
# 00000137  turnstile_timed_gate
# =============================================================================

def build_turnstile_timed_gate():
    scene = setup_base(
        camera_loc=(6.6, -7.6, 7.4),
        target=(0.0, 0.0, 0.35),
        ortho_scale=9.0,
    )

    ball_radius = 0.17
    rail_radius = 0.045
    rail_gap = 0.24
    rail_dy = rail_gap / 2.0
    rail_z_drop = math.sqrt((ball_radius + rail_radius) ** 2 - rail_dy ** 2)
    floor_z = ball_radius  # ball-center height for a ball resting on the floor

    gate_x = 0.0  # both flap gates straddle their lane at x = 0

    laneA_y = -0.55
    laneA_start_x = -3.60
    laneA_end_x = 3.60
    laneB_y = 0.55
    laneB_start_x = -3.60
    laneB_end_x = 3.60

    def build_lane_rails(tag_prefix, lane_y, x0, x1):
        for side, dy in [("near", -rail_dy), ("far", rail_dy)]:
            add_cylinder_between(
                f"{tag_prefix}_{side}_rail",
                (x0, lane_y + dy, floor_z - rail_z_drop),
                (x1, lane_y + dy, floor_z - rail_z_drop),
                rail_radius,
                MATS["dark"],
                "flat_rail",
                "dark_gray",
            )
        n_tie = 12
        for i in range(n_tie):
            x = lerp(x0 + 0.15, x1 - 0.15, i / float(n_tie - 1))
            add_cube(
                f"{tag_prefix}_tie_{i:02d}",
                (x, lane_y, floor_z - rail_z_drop - 0.08),
                (0.10, 0.42, 0.055),
                MATS["support"],
                "track_tie",
                "dark_gray",
            )

    build_lane_rails("laneA", laneA_y, laneA_start_x, laneA_end_x)
    build_lane_rails("laneB", laneB_y, laneB_start_x, laneB_end_x)

    # ----- Two hinged FLAP GATES, one straddling each lane at gate_x. -----
    # Each flap is a vertical panel that, when CLOSED, lies across its lane (blocking
    # the ball's path). It is hinged on a vertical post at the lane's OUTER edge and
    # swings OPEN about that vertical hinge (like a saloon / dog door) to let its ball
    # through, then swings shut. One gate per ball, so the two lanes behave identically
    # (mirror image). Panel origin is on the hinge (via an empty parent) so a pure
    # Z-rotation pivots at the hinge with no translation.
    flap_len = 0.52     # panel span across the lane (Y)
    flap_thick = 0.05
    flap_h = 0.52
    flap_cz = floor_z + flap_h / 2.0 - 0.02

    def build_flap(name, lane_y, hinge_y):
        piv = bpy.data.objects.new(name + "_pivot", None)
        piv.location = (gate_x, hinge_y, flap_cz)
        bpy.context.scene.collection.objects.link(piv)
        piv["pb_object_id"] = name + "_pivot"
        piv["pb_role"] = "flap_hinge"
        piv["pb_is_dynamic"] = True
        # Vertical hinge post at the outer edge.
        add_vertical_cylinder(
            name + "_post",
            (gate_x, hinge_y, (flap_h + 0.06) / 2.0),
            0.035,
            flap_h + 0.06,
            MATS["dark"],
            "flap_post",
            "dark_gray",
        )
        # Panel extends from the hinge toward the lane centre.
        dir_in = 1.0 if lane_y > hinge_y else -1.0
        panel = add_cube(
            name + "_panel",
            (gate_x, hinge_y + dir_in * flap_len / 2.0, flap_cz),
            (flap_thick, flap_len, flap_h),
            MATS["gray"],
            "flap_gate",
            "gray",
            is_dynamic=True,
        )
        panel.parent = piv
        panel.matrix_parent_inverse = piv.matrix_world.inverted()
        return piv, panel

    # Hinge each flap at its lane's OUTER y-edge (a hair beyond the panel span).
    pivA, panelA = build_flap("gateA", laneA_y, laneA_y - (flap_len / 2.0 + 0.02))
    pivB, panelB = build_flap("gateB", laneB_y, laneB_y + (flap_len / 2.0 + 0.02))

    # Balls (one per lane).
    ballA = add_ball(
        "pass_orange_ball", ball_radius, (laneA_start_x, laneA_y, floor_z),
        MATS["orange"], "orange",
    )
    ballA["pb_path"] = "rolls_in_flap_opens_passes_through_flap_closes_continues"

    ballB = add_ball(
        "blocked_blue_ball", ball_radius, (laneB_start_x, laneB_y, floor_z),
        MATS["blue"], "blue",
    )
    ballB["pb_path"] = "rolls_in_flap_opens_passes_through_flap_closes_continues"

    return scene, {
        "ballA": ballA,
        "ballB": ballB,
        "pivA": pivA,
        "pivB": pivB,
        "ball_radius": ball_radius,
        "laneA_y": laneA_y,
        "laneA_start_x": laneA_start_x,
        "laneA_end_x": laneA_end_x,
        "laneB_y": laneB_y,
        "laneB_start_x": laneB_start_x,
        "laneB_end_x": laneB_end_x,
    }


def animate_turnstile_timed_gate(scene, meta):
    # -------------------------------------------------------------------------
    # Two hinged flap gates. Each ball rolls in along its lane at a steady speed;
    # its flap swings OPEN (about a vertical hinge) just before the ball reaches the
    # gate, the ball passes through, then the flap swings shut behind it and the ball
    # rolls on. Both lanes use IDENTICAL timing, so the two balls behave the same way
    # (mirror image). Flap swing is purely a Z-rotation of the hinge pivot -> the open
    # flap folds back to the lane's outer edge, clear of the ball's path.
    # -------------------------------------------------------------------------
    ballA = meta["ballA"]
    ballB = meta["ballB"]
    pivA = meta["pivA"]
    pivB = meta["pivB"]
    radius = meta["ball_radius"]
    laneA_y = meta["laneA_y"]
    laneA_start_x = meta["laneA_start_x"]
    laneA_end_x = meta["laneA_end_x"]
    laneB_y = meta["laneB_y"]
    laneB_start_x = meta["laneB_start_x"]
    laneB_end_x = meta["laneB_end_x"]

    rest = 6
    roll_end = FRAME_END - 6            # steady roll rest..roll_end (ball at x=0 ~mid)
    max_open = math.radians(95.0)

    # The ball must TOUCH the closed flap first; only then does the flap open. So the
    # ball rolls up to the closed flap and waits against it, the flap swings open
    # (contact-triggered), the ball rolls through, the flap shuts behind it, and the
    # ball decelerates to rest. Timing (same for both lanes):
    x_contact = -0.20        # ball-CENTER x where its front just meets the closed flap
    contact_frame = 54       # ball reaches the closed flap here
    open_end = 62            # flap fully open here (opened while the ball waits)
    through_end = 74         # ball has rolled clear of the gate here
    decel_end = FRAME_END    # then decelerates to rest
    close_start, close_end = 74, 88   # flap shuts after the ball is well clear

    def flap_angle(frame, sign):
        """Hinge Z-rotation: 0 = closed; opens ONLY once the ball has reached it."""
        if frame <= contact_frame:
            o = 0.0
        elif frame < open_end:
            o = smooth01((frame - contact_frame) / float(open_end - contact_frame))
        elif frame <= close_start:
            o = 1.0
        elif frame < close_end:
            o = 1.0 - smooth01((frame - close_start) / float(close_end - close_start))
        else:
            o = 0.0
        return sign * max_open * o

    v_in = (x_contact - laneA_start_x) / float(contact_frame - rest)   # steady roll-in speed
    x_through = 0.66                                                   # x once clear of the gate

    def ball_x(frame, start_x):
        # rest -> steady roll-in to the closed flap -> WAIT while the flap opens ->
        # roll through the open gate -> decelerate to rest after clearing it.
        if frame <= rest:
            return start_x
        if frame <= contact_frame:
            return start_x + v_in * (frame - rest)
        xc = start_x + v_in * (contact_frame - rest)      # == x_contact for laneA start
        if frame <= open_end:
            return xc                                     # waiting against the closed flap
        if frame <= through_end:
            t = (frame - open_end) / float(through_end - open_end)
            return xc + (x_through - xc) * t              # roll through the open gate
        v_thru = (x_through - xc) / float(through_end - open_end)
        out_frames = float(decel_end - through_end)
        u = min(1.0, (frame - through_end) / out_frames)
        return x_through + v_thru * out_frames * (u - 0.5 * u * u)   # decelerate to rest

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        # Flaps swing open in the ball's direction of travel (downstream, +x), like a
        # door pushed open ahead of the ball; mirror directions on the two lanes.
        pivA.rotation_euler = (0.0, 0.0, flap_angle(frame, -1.0))
        pivB.rotation_euler = (0.0, 0.0, flap_angle(frame, +1.0))
        pivA.keyframe_insert(data_path="rotation_euler", frame=frame)
        pivB.keyframe_insert(data_path="rotation_euler", frame=frame)

        for ball, (sx, ly) in (
            (ballA, (laneA_start_x, laneA_y)),
            (ballB, (laneB_start_x, laneB_y)),
        ):
            bx = ball_x(frame, sx)
            ball.location = (bx, ly, radius)
            ball.rotation_euler = (0.0, (bx - sx) / radius, 0.0)
            ball.keyframe_insert(data_path="location", frame=frame)
            ball.keyframe_insert(data_path="rotation_euler", frame=frame)
            ball["pb_state"] = "rolling_through_hinged_flap_gate"

    scene.frame_set(FRAME_START)


# =============================================================================
# Dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["kind"]

    if kind == "turnstile_timed_gate":
        return build_turnstile_timed_gate()

    raise RuntimeError("Unknown kind: " + str(kind))


def animate_scene_by_kind(scene, meta):
    kind = CASE["kind"]

    if kind == "turnstile_timed_gate":
        return animate_turnstile_timed_gate(scene, meta)

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
