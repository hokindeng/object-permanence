# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_BANKED_QUARTER_PIPE_REDIRECT_0159",
  "kind": "banked_quarter_pipe_redirect",
  "prompt": "A ball rolls toward a curved banked wall (a quarter-pipe). Instead of stopping, it is smoothly redirected through ninety degrees and rolls away along a new perpendicular lane, conserving most of its speed. It is deflected, not stopped or passed through."
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
    # Rotation is baked into the mesh via transform_apply so the local
    # dimensions stay clean and the object exposes its yaw as a tag.
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


def add_upright_cylinder(name, center_xy, radius, height, material, role, color_name):
    # A vertical cylindrical post standing on the floor, base at z=0.
    bpy.ops.mesh.primitive_cylinder_add(
        radius=radius,
        depth=height,
        vertices=48,
        location=(center_xy[0], center_xy[1], height / 2.0),
    )
    obj = bpy.context.object
    obj.name = name

    if material is not None:
        obj.data.materials.append(material)

    tag(
        obj,
        name,
        role,
        "static_solid",
        "cylinder",
        color_name,
        False,
        solid=True,
        pb_radius=float(radius),
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
# 00000158  banked_quarter_pipe_redirect
# =============================================================================

def _build_quarter_pipe_wall(name, arc_center_xy, inner_radius, wall_thick, wall_h,
                             ang0_deg, ang1_deg, segments, material, role, color_name):
    """Solid curved banked wall (a quarter-pipe seen from above): an annular sector
    swept from ang0->ang1 about arc_center, extruded vertically 0->wall_h. The ball
    rides against the INNER concave face at radius=inner_radius. The wall occupies the
    annulus inner_radius .. inner_radius+wall_thick so it is a real solid barrier."""
    import bmesh
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()

    cx, cy = arc_center_xy
    r_in = inner_radius
    r_out = inner_radius + wall_thick
    a0 = math.radians(ang0_deg)
    a1 = math.radians(ang1_deg)

    bot_in = []
    bot_out = []
    top_in = []
    top_out = []
    for i in range(segments + 1):
        a = a0 + (a1 - a0) * (i / float(segments))
        ca, sa = math.cos(a), math.sin(a)
        xin, yin = cx + r_in * ca, cy + r_in * sa
        xout, yout = cx + r_out * ca, cy + r_out * sa
        bot_in.append(bm.verts.new((xin, yin, 0.0)))
        bot_out.append(bm.verts.new((xout, yout, 0.0)))
        top_in.append(bm.verts.new((xin, yin, wall_h)))
        top_out.append(bm.verts.new((xout, yout, wall_h)))

    for i in range(segments):
        j = i + 1
        # inner concave face (the contact face)
        bm.faces.new([bot_in[i], top_in[i], top_in[j], bot_in[j]])
        # outer face
        bm.faces.new([bot_out[i], bot_out[j], top_out[j], top_out[i]])
        # top face
        bm.faces.new([top_in[i], top_out[i], top_out[j], top_in[j]])
        # bottom face
        bm.faces.new([bot_in[i], bot_in[j], bot_out[j], bot_out[i]])
    # end caps
    bm.faces.new([bot_in[0], bot_out[0], top_out[0], top_in[0]])
    bm.faces.new([bot_in[segments], top_in[segments], top_out[segments], bot_out[segments]])

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    obj.data.materials.append(material)
    tag(obj, name, role, "static_solid", "curved_wall", color_name, False, solid=True,
        pb_arc_center_x=float(cx), pb_arc_center_y=float(cy),
        pb_inner_radius=float(inner_radius))
    return obj


def build_banked_quarter_pipe_redirect():
    scene = setup_base(
        camera_loc=(6.4, -8.6, 7.2),
        target=(0.0, 0.85, 0.30),
        ortho_scale=9.0,
    )

    ball_radius = 0.22
    floor_z = ball_radius  # ball-center height for a ball resting on the floor

    # ----- The banked quarter-pipe curved wall -----
    # Seen from above, the ball's PATH is a quarter circle of radius R about a center C.
    # The ball rolls in heading +X (east) along the lane y = y_in, meets the curve, and
    # is smoothly turned 90 deg (a LEFT turn) to leave heading +Y (north) along the lane
    # x = x0 + R. For the arc to be TANGENT to both straight legs (no kink), the arc
    # center must sit to the ball's LEFT, i.e. NORTH of the incoming lane:
    #     C = (x0, y_in + R).
    # Sweeping the ball-center angle from 270 deg -> 360 deg (counter-clockwise) gives:
    #     a=270 -> ball at (x0, y_in), tangent = +X  (matches the roll-in leg)
    #     a=360 -> ball at (x0 + R, y_in + R), tangent = +Y  (matches the roll-out leg)
    # Inertia throws the ball OUTWARD (to its right / south), pressing it against the
    # curved wall whose concave inner face is on the OUTSIDE of the arc. Wall inner
    # radius = R + ball_radius so the ball CENTER stays on the radius-R arc while its
    # surface just kisses the wall's inner face (contact, no interpenetration).
    R = 1.55                              # radius of the ball-center arc
    x0 = 0.0                              # x where the turn begins
    y_in = -0.90                          # y of the incoming lane
    arc_center = Vector((x0, y_in + R, 0.0))   # C sits to the LEFT of the roll-in lane
    wall_inner_r = R + ball_radius        # inner concave face radius
    _build_quarter_pipe_wall(
        "banked_quarter_pipe_wall",
        (arc_center.x, arc_center.y),
        wall_inner_r,
        0.30,          # wall thickness
        0.85,          # wall height
        270.0,         # start angle: ball-center at the roll-in lane (x0, y_in)
        360.0,         # end angle: ball-center at the roll-out lane (x0 + R, y_in + R)
        48,
        MATS["gray"], "banked_quarter_pipe_wall", "gray",
    )["pb_redirect"] = "smooth_90_degree_curved_deflection"

    # Ball-center arc endpoints (on the radius-R circle) for the 270->360 sweep:
    #  angle 270 deg -> arc start at (x0, y_in)         ... ball heading +X reaches here
    #  angle 360 deg -> arc end   at (x0 + R, y_in + R) ... ball leaves heading +Y
    # The ball rides the concave inner face of the wall the whole quarter turn.
    a_start = math.radians(270.0)
    a_end = math.radians(360.0)
    arc_start = Vector((arc_center.x + R * math.cos(a_start),
                        arc_center.y + R * math.sin(a_start), floor_z))  # (x0, y_in)
    arc_end = Vector((arc_center.x + R * math.cos(a_end),
                      arc_center.y + R * math.sin(a_end), floor_z))      # (x0 + R, y_in + R)

    # Incoming straight leg: heading +X toward arc_start (same y as arc_start).
    in_start = Vector((arc_start.x - 2.7, arc_start.y, floor_z))
    # Outgoing straight leg: heading +Y away from arc_end (same x as arc_end).
    out_end = Vector((arc_end.x, arc_end.y + 2.7, floor_z))

    ball = add_ball("redirect_orange_ball", ball_radius, in_start, MATS["orange"], "orange")
    ball["pb_path"] = "rolls_in_straight_curves_90deg_along_quarter_pipe_rolls_out_perpendicular"
    ball["pb_deflected_not_stopped_not_passed_through"] = True

    return scene, {
        "ball": ball,
        "ball_radius": ball_radius,
        "arc_center": arc_center,
        "arc_radius": R,
        "a_start": a_start,
        "a_end": a_end,
        "in_start": in_start,
        "arc_start": arc_start,
        "arc_end": arc_end,
        "out_end": out_end,
        "floor_z": floor_z,
    }


def animate_banked_quarter_pipe_redirect(scene, meta):
    ball = meta["ball"]
    radius = meta["ball_radius"]
    C = meta["arc_center"]
    R = meta["arc_radius"]
    a_start = meta["a_start"]
    a_end = meta["a_end"]
    in_start = meta["in_start"]
    arc_start = meta["arc_start"]
    arc_end = meta["arc_end"]
    out_end = meta["out_end"]
    floor_z = meta["floor_z"]

    # Three phases at (near) CONSTANT speed so the ball is clearly "deflected, not
    # stopped": straight roll-in -> curved arc along the pipe -> straight roll-out.
    # A tiny speed loss (5%) is applied only on the curved contact leg so the exit
    # leg is slightly slower than the entry (energy lost to the banked wall), but the
    # ball keeps MOST of its speed. Arc-length parameterisation keeps the per-frame
    # distance uniform on the curve (no visual slow-down while turning).
    in_len = (arc_start - in_start).length
    arc_len = abs(a_end - a_start) * R
    out_len = (out_end - arc_end).length

    speed_loss = 0.05

    rest_frames = 6
    # Choose per-leg frame counts proportional to length (uniform speed), with a small
    # speed reduction after the curve (out leg gets a few extra frames per unit length).
    v = (in_len + arc_len) / float(70)          # base per-frame speed (entry+curve budget)
    in_frames = max(1, int(round(in_len / v)))
    arc_frames = max(1, int(round(arc_len / v)))
    v_out = v * (1.0 - speed_loss)
    out_frames = max(1, int(round(out_len / v_out)))

    f_in_end = rest_frames + in_frames
    f_arc_end = f_in_end + arc_frames
    f_out_end = min(FRAME_END, f_arc_end + out_frames)

    in_dir = (arc_start - in_start).normalized()

    prev_pos = Vector(in_start)
    spin = 0.0

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= rest_frames:
            pos = Vector(in_start)
            travel_dir = in_dir
            state = "rest_before_roll_in"
        elif frame <= f_in_end:
            t = (frame - rest_frames) / float(in_frames)
            pos = in_start + (arc_start - in_start) * t
            travel_dir = in_dir
            state = "rolling_in_straight_toward_quarter_pipe"
        elif frame <= f_arc_end:
            t = (frame - f_in_end) / float(arc_frames)
            a = a_start + (a_end - a_start) * t
            pos = Vector((C.x + R * math.cos(a), C.y + R * math.sin(a), floor_z))
            # tangent direction of travel along the arc (d/dt of position)
            da = (a_end - a_start)
            travel_dir = Vector((-math.sin(a) * da, math.cos(a) * da, 0.0))
            if travel_dir.length > 1e-9:
                travel_dir.normalize()
            state = "redirected_along_banked_quarter_pipe"
        elif frame <= f_out_end:
            t = (frame - f_arc_end) / float(max(1, f_out_end - f_arc_end))
            pos = arc_end + (out_end - arc_end) * t
            travel_dir = (out_end - arc_end).normalized()
            state = "rolling_out_straight_perpendicular_lane"
        else:
            pos = Vector(out_end)
            travel_dir = (out_end - arc_end).normalized()
            state = "settled_on_perpendicular_lane"

        pos = Vector((pos.x, pos.y, radius))

        step = (pos - prev_pos).length
        spin += step / radius
        prev_pos = Vector(pos)

        axis = Vector((0.0, 0.0, 1.0)).cross(Vector((travel_dir.x, travel_dir.y, 0.0)))
        if axis.length > 1e-9:
            axis.normalize()
            ball.rotation_mode = "AXIS_ANGLE"
            ball.rotation_axis_angle = (spin, axis.x, axis.y, axis.z)

        ball.location = pos
        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_axis_angle", frame=frame)

        ball["pb_state"] = state
        ball["pb_speed_loss_fraction"] = float(speed_loss)

    # Linear interpolation keeps the straight legs perfectly straight and the arc
    # samples exactly on the quarter circle (no Bezier overshoot off the wall).
    adata = ball.animation_data
    if adata is not None and adata.action is not None:
        for fcurve in adata.action.fcurves:
            for kp in fcurve.keyframe_points:
                kp.interpolation = "LINEAR"
            fcurve.update()

    scene.frame_set(FRAME_START)


# =============================================================================
# Dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["kind"]

    if kind == "banked_quarter_pipe_redirect":
        return build_banked_quarter_pipe_redirect()

    raise RuntimeError("Unknown kind: " + str(kind))


def animate_scene_by_kind(scene, meta):
    kind = CASE["kind"]

    if kind == "banked_quarter_pipe_redirect":
        return animate_banked_quarter_pipe_redirect(scene, meta)

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
