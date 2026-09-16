# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_BUMPER_CAROM_0139",
  "kind": "bumper_carom",
  "prompt": "A ball rolls across a flat surface toward a fixed triangular wedge (a solid prism) sitting on the floor. It strikes the wedge's slanted face and caroms off along a new direction set by that face's normal, then decelerates and settles. It is never suspended and does not pass through the wedge."
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
# 00000138  bumper_carom
# =============================================================================

def _build_triangular_prism(name, tri_xy, z0, z1, material, role, color_name):
    """Solid triangular prism from 3 XY points extruded vertically z0->z1."""
    import bmesh
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    bot = [bm.verts.new((x, y, z0)) for (x, y) in tri_xy]
    top = [bm.verts.new((x, y, z1)) for (x, y) in tri_xy]
    bm.faces.new(bot)
    bm.faces.new(top[::-1])
    for i in range(3):
        j = (i + 1) % 3
        bm.faces.new([bot[i], bot[j], top[j], top[i]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    obj.data.materials.append(material)
    tag(obj, name, role, "static_solid", "prism", color_name, False, solid=True)
    return obj


def build_bumper_carom():
    scene = setup_base(
        camera_loc=(6.4, -8.6, 6.8),
        target=(0.10, -0.35, 0.35),
        ortho_scale=8.2,
    )

    ball_radius = 0.20

    # ----- Flat surface: the ball rolls on the floor the whole time -----
    floor_z = ball_radius  # ball-center height for a ball resting on the floor

    # ----- Fixed TRIANGULAR WEDGE the ball caroms off (sits on the floor, no base) --
    # A solid right-triangular prism standing directly on the floor. The ball strikes
    # its slanted front face (the hypotenuse), which has a single CONSTANT 45-deg
    # normal, and deflects in one crisp bounce. The right-angle corner points AWAY
    # from the ball (+x,+y); the hypotenuse BC faces the incoming (-x,-y) ball.
    wedge_h = 0.90
    tri_A = (2.20, 1.00)    # right-angle corner, behind (+x,+y)
    tri_B = (0.50, 1.00)    # leg end toward -x
    tri_C = (2.20, -0.70)   # leg end toward -y
    _build_triangular_prism(
        "fixed_deflecting_wedge", [tri_A, tri_B, tri_C], 0.0, wedge_h,
        MATS["gray"], "fixed_deflecting_wedge", "gray",
    )["pb_deflection"] = "reflect_about_slanted_wedge_face_normal"

    # Constant outward normal of the slanted face BC (points toward the ball).
    normal = Vector((-0.70710678, -0.70710678, 0.0))
    wall_center = Vector((1.35, 0.15, 0.0))   # a point on the slanted (hypotenuse) face

    # ----- Incoming leg: ball rolls straight in along +X at a fixed y -----
    y_in = 0.15
    # Contact ball-center = point on the incoming line (y=y_in) whose distance to the
    # wall plane equals ball_radius (ball surface just touches the face).
    #   (p - wall_center) . normal = ball_radius, with p = (x, y_in).
    denom = normal.x if abs(normal.x) > 1e-6 else 1e-6
    contact_x = wall_center.x + (ball_radius - (y_in - wall_center.y) * normal.y) / denom
    contact = Vector((contact_x, y_in, floor_z))

    # Start well to the −X of the contact point, same y (rolls straight in +X).
    start = Vector((-3.05, y_in, floor_z))

    # ----- Outgoing direction: reflect incoming (+X) about the wall normal -----
    incoming = Vector((1.0, 0.0, 0.0))
    reflected = incoming - normal * (2.0 * incoming.dot(normal))
    reflected.z = 0.0
    reflected.normalize()

    out_len = 3.05
    out_end = contact + reflected * out_len
    out_end.z = floor_z

    ball = add_ball("carom_orange_ball", ball_radius, start, MATS["orange"], "orange")
    ball["pb_path"] = "rolls_in_strikes_angled_flat_wall_caroms_off_decelerates"
    ball["pb_deflected_not_stopped_not_passed_through"] = True

    return scene, {
        "ball": ball,
        "start": start,
        "contact": contact,
        "out_end": out_end,
        "wall_center": wall_center,
        "ball_radius": ball_radius,
        "normal": normal,
        "reflected": reflected,
        "contact_frame": 58,
    }


def animate_bumper_carom(scene, meta):
    ball = meta["ball"]
    start = meta["start"]
    contact = meta["contact"]
    out_end = meta["out_end"]
    radius = meta["ball_radius"]
    contact_frame = meta["contact_frame"]

    # Incoming leg: straight run rest -> contact (constant speed roll).
    in_vec = contact - start
    in_len = in_vec.length
    in_dir = in_vec.normalized()

    # Outgoing leg geometry.
    out_vec = out_end - contact
    out_len_full = out_vec.length
    out_dir = out_vec.normalized() if out_len_full > 1e-9 else Vector((1.0, 0.0, 0.0))

    # Elastic carom with a small speed loss. The outgoing leg must leave the
    # bumper at a REDUCED speed (never faster than the incoming contact speed)
    # and then only DECELERATE (friction) to rest. We therefore pin the exit
    # speed to (1 - speed_loss) * incoming_contact_speed and use a
    # constant-speed-then-settle velocity profile: the ball's speed is highest
    # right at contact and decreases monotonically to zero -- no mid/late
    # acceleration.
    speed_loss = 0.16

    rest_frames = 8

    # Frame budgets for each leg (constant-speed roll-in, then carom-out).
    in_frames = float(contact_frame - rest_frames)
    out_frames = float(FRAME_END - contact_frame)

    # Incoming leg is a steady, constant-speed roll -> speed at contact is the
    # full incoming speed (per-frame distance covered).
    v_in = in_len / max(in_frames, 1.0) if in_len > 1e-9 else 0.0

    # Exit speed after the small elastic loss (<= incoming contact speed).
    v_out = (1.0 - speed_loss) * v_in

    # Outgoing profile: the ball leaves the bumper at v_out and then DECELERATES
    # steadily under friction (linear velocity ramp to zero). Speed is highest right
    # at contact and strictly decreasing all the way to rest -- a clear post-bounce
    # slow-down, no cruise. Distance if it fully stops within the leg = 0.5*v_out*T.
    out_travel = min(0.5 * v_out * out_frames, out_len_full)

    prev_pos = Vector(start)
    spin = 0.0
    # Rolling axis is horizontal and perpendicular to the direction of travel;
    # rotating about world Z-cross gives a plausible roll for a floor ball.

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= rest_frames:
            pos = Vector(start)
            travel_dir = in_dir
            state = "rest_before_roll_in"
        elif frame <= contact_frame:
            # Rolling in at (near) constant speed toward the bumper.
            t = (frame - rest_frames) / float(contact_frame - rest_frames)
            t = max(0.0, min(1.0, t))
            # Steady, constant-speed roll-in: speed at contact stays at the
            # full incoming speed -- no smoothstep stall at the bumper.
            s_in = in_len * t
            pos = start + in_dir * s_in
            travel_dir = in_dir
            state = "rolling_in_toward_bumper"
        else:
            # Carom off along the reflected direction, DECELERATING to rest the whole
            # way under constant friction: v(t) = v_out*(1 - t) so the covered distance
            # is out_travel*(2t - t^2). Speed peaks at contact and ramps to zero -- the
            # ball visibly slows down after the bounce (no cruise, no speed-up).
            t = (frame - contact_frame) / float(FRAME_END - contact_frame)
            t = max(0.0, min(1.0, t))
            s_out = out_travel * (2.0 * t - t * t)
            pos = contact + out_dir * s_out
            travel_dir = out_dir
            state = "caromed_rolling_off_new_direction_then_settling"

        pos = Vector((pos.x, pos.y, radius))

        # Accumulate rolling spin from the distance actually traveled.
        step = (pos - prev_pos).length
        spin += step / radius
        prev_pos = Vector(pos)

        # Roll axis: horizontal, perpendicular to travel direction (Z x dir).
        axis = Vector((0.0, 0.0, 1.0)).cross(Vector((travel_dir.x, travel_dir.y, 0.0)))
        if axis.length > 1e-9:
            axis.normalize()
            ball.rotation_mode = "AXIS_ANGLE"
            ball.rotation_axis_angle = (spin, axis.x, axis.y, axis.z)

        ball.location = pos
        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_axis_angle", frame=frame)

        ball["pb_state"] = state
        ball["pb_contact_frame"] = int(contact_frame)
        ball["pb_speed_loss_fraction"] = float(speed_loss)

    # Force LINEAR F-curve interpolation on every inserted key. With the
    # default Bezier handles, the location curve rounds the sharp corner at the
    # contact frame: the rendered ball bows off the straight incoming line and
    # curves/jogs just before it bounces (the extra little turn), and the eased
    # handles could also momentarily speed it up right after contact. LINEAR
    # makes the rendered path pass exactly through the per-frame collinear
    # sample points as two straight segments meeting only at the contact frame,
    # and keeps the deceleration-only speed profile exact (no post-bounce
    # acceleration).
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

    if kind == "bumper_carom":
        return build_bumper_carom()

    raise RuntimeError("Unknown kind: " + str(kind))


def animate_scene_by_kind(scene, meta):
    kind = CASE["kind"]

    if kind == "bumper_carom":
        return animate_bumper_carom(scene, meta)

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
