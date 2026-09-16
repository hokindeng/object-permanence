# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_RAMP_BALL_DEFLECTED_ANGLED_WALL_0104",
  "kind": "ramp_ball_deflected_angled_wall",
  "prompt": "A ball rolls down a ramp on the left toward a fixed gray wall angled at 45 degrees. On contact the ball deflects elastically through 90 degrees and rolls off to the right along the new direction, conserving speed minus a small loss. The ball is deflected, not stopped and not passed through."
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
# 00000103  ramp_ball_deflected_angled_wall
# =============================================================================

def build_ramp_ball_deflected_angled_wall():
    scene = setup_base(
        camera_loc=(7.4, -8.2, 6.2),
        target=(0.10, -0.55, 0.55),
        ortho_scale=8.0,
    )

    ball_radius = 0.17
    rail_radius = 0.045
    rail_gap = 0.24
    rail_dy = rail_gap / 2.0
    rail_z_drop = math.sqrt((ball_radius + rail_radius) ** 2 - rail_dy ** 2)

    # ----- Incoming leg: ramp on the left then a flat run along +X -----
    floor_z = ball_radius  # ball-center height for a ball resting on the floor

    ramp_start = Vector((-3.30, 0.0, 1.30))
    ramp_end = Vector((-1.45, 0.0, floor_z))
    # Contact point: where the +X-moving ball meets the angled wall face.
    contact = Vector((1.05, 0.0, floor_z))

    for side, dy in [("near", -rail_dy), ("far", rail_dy)]:
        add_cylinder_between(
            f"ramp_{side}_rail",
            (ramp_start.x, dy, ramp_start.z - rail_z_drop),
            (ramp_end.x, dy, ramp_end.z - rail_z_drop),
            rail_radius,
            MATS["dark"],
            "ramp_rail",
            "dark_gray",
        )
        # Stop each incoming rail on the angled wall face. Together with the
        # outgoing rail below, these endpoints form a continuous open-left bend.
        rail_contact_x = contact.x - dy
        add_cylinder_between(
            f"flat_in_{side}_rail",
            (ramp_end.x, dy, ramp_end.z - rail_z_drop),
            (rail_contact_x, dy, contact.z - rail_z_drop),
            rail_radius,
            MATS["dark"],
            "flat_rail",
            "dark_gray",
        )

    n_in = 8
    for i in range(n_in):
        x = lerp(ramp_end.x + 0.10, contact.x - 0.10, i / float(n_in - 1))
        add_cube(
            f"flat_in_tie_{i:02d}",
            (x, 0.0, floor_z - rail_z_drop - 0.08),
            (0.10, 0.42, 0.055),
            MATS["support"],
            "track_tie",
            "dark_gray",
        )

    # ----- Outgoing leg: along -Y (toward camera-front) -----
    # The +X-moving ball reflects off a face whose outward normal is
    # (-1, -1)/sqrt(2): the reflected direction is exactly -Y.
    out_len = 2.55
    out_dir = Vector((0.0, -1.0, 0.0))
    out_end = contact + out_dir * out_len

    for side, dx in [("near", -rail_dy), ("far", rail_dy)]:
        rail_contact_y = -dx
        add_cylinder_between(
            f"flat_out_{side}_rail",
            (contact.x + dx, rail_contact_y, contact.z - rail_z_drop),
            (out_end.x + dx, out_end.y, out_end.z - rail_z_drop),
            rail_radius,
            MATS["dark"],
            "flat_rail",
            "dark_gray",
        )

    n_out = 8
    for i in range(n_out):
        y = lerp(contact.y - 0.10, out_end.y + 0.10, i / float(n_out - 1))
        add_cube(
            f"flat_out_tie_{i:02d}",
            (contact.x, y, floor_z - rail_z_drop - 0.08),
            (0.42, 0.10, 0.055),
            MATS["support"],
            "track_tie",
            "dark_gray",
        )

    # ----- Fixed gray wall, yawed 45 degrees -----
    # Deflecting face normal is (-1, -1)/sqrt(2). A wall whose long axis runs
    # along (1, -1)/sqrt(2) (i.e. yawed -45 deg) presents exactly that face to
    # an incoming +X-moving ball. Place it just past the contact point so the
    # ball touches the face and bends, never clipping into the solid.
    wall_thickness = 0.30
    wall_length = 2.60
    wall_height = 1.05
    inset = (ball_radius + wall_thickness / 2.0) / math.sqrt(2.0)
    wall_center = Vector((
        contact.x + inset,
        contact.y + inset,
        floor_z,
    ))
    wall = add_oriented_box(
        "deflecting_angled_wall",
        (wall_center.x, wall_center.y, wall_center.z),
        (wall_length, wall_thickness, wall_height),
        -45.0,
        MATS["gray"],
        "fixed_deflecting_wall",
        "gray",
    )
    wall["pb_face_normal"] = "(-1,-1)/sqrt(2)"
    wall["pb_deflection_deg"] = 90.0

    # Short support feet for the wall so it reads as fixed, not floating.
    foot_dir = Vector((1.0, -1.0, 0.0)).normalized()
    for sgn in (-1.0, 1.0):
        fc = wall_center + foot_dir * (sgn * (wall_length / 2.0 - 0.18))
        add_cube(
            f"wall_foot_{'pos' if sgn > 0 else 'neg'}",
            (fc.x, fc.y, 0.10),
            (0.22, 0.22, 0.20),
            MATS["support"],
            "wall_support_foot",
            "dark_gray",
        )

    ball = add_ball("ramp_orange_ball", ball_radius, ramp_start, MATS["orange"], "orange")
    ball["pb_path"] = "ramp_accelerated_then_elastic_90deg_deflection_off_angled_wall"
    ball["pb_deflected_not_stopped_not_passed_through"] = True

    return scene, {
        "ball": ball,
        "ramp_start": ramp_start,
        "ramp_end": ramp_end,
        "contact": contact,
        "out_end": out_end,
        "ball_radius": ball_radius,
        "contact_frame": 60,
    }


def animate_ramp_ball_deflected_angled_wall(scene, meta):
    ball = meta["ball"]
    ramp_start = meta["ramp_start"]
    ramp_end = meta["ramp_end"]
    contact = meta["contact"]
    out_end = meta["out_end"]
    radius = meta["ball_radius"]
    contact_frame = meta["contact_frame"]

    # Incoming leg geometry (ramp + flat run), traversed rest -> contact.
    in_ramp_vec = ramp_end - ramp_start
    in_flat_vec = contact - ramp_end
    in_len = in_ramp_vec.length + in_flat_vec.length
    ramp_len = in_ramp_vec.length

    # Outgoing leg geometry.
    out_vec = out_end - contact
    out_len_full = out_vec.length
    out_dir = out_vec.normalized()

    # Speed conservation minus a small loss: outgoing travel covers 82% of the
    # leg length over the same number of frames as it would at full speed,
    # i.e. an 18% speed loss, with a quadratic ease-out (decelerating).
    speed_loss = 0.18
    out_travel = (1.0 - speed_loss) * out_len_full

    rest_frames = 8

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= rest_frames:
            # At rest at the top of the ramp.
            s_in = 0.0
            pos, leg = _pos_on_incoming(s_in, in_len, ramp_len, ramp_start, in_ramp_vec, ramp_end, in_flat_vec)
            state = "rest_at_top_of_ramp"
            traveled = 0.0
        elif frame <= contact_frame:
            # Accelerating in: ease-in, s proportional to t^2.
            t = (frame - rest_frames) / float(contact_frame - rest_frames)
            t = max(0.0, min(1.0, t))
            s_in = in_len * (t * t)
            pos, leg = _pos_on_incoming(s_in, in_len, ramp_len, ramp_start, in_ramp_vec, ramp_end, in_flat_vec)
            state = "accelerating_down_ramp_toward_wall" if leg == "ramp" else "rolling_on_flat_toward_wall"
            traveled = s_in
        else:
            # Deflected out along -Y: quadratic ease-out (decelerating).
            t = (frame - contact_frame) / float(FRAME_END - contact_frame)
            t = max(0.0, min(1.0, t))
            ease_out = 1.0 - (1.0 - t) * (1.0 - t)
            s_out = out_travel * ease_out
            pos = contact + out_dir * s_out
            state = "deflected_rolling_off_to_right_along_minus_Y"
            traveled = in_len + s_out

        ball.location = pos
        ball.rotation_euler = (0.0, traveled / radius, 0.0)
        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)

        ball["pb_state"] = state
        ball["pb_contact_frame"] = int(contact_frame)
        ball["pb_speed_loss_fraction"] = float(speed_loss)
        ball["pb_outgoing_leg_direction"] = "-Y"

    scene.frame_set(FRAME_START)


def _pos_on_incoming(s_in, in_len, ramp_len, ramp_start, in_ramp_vec, ramp_end, in_flat_vec):
    s_in = max(0.0, min(in_len, s_in))
    if s_in <= ramp_len:
        u = s_in / ramp_len if ramp_len > 1e-9 else 0.0
        return ramp_start + in_ramp_vec * u, "ramp"
    flat_len = in_flat_vec.length
    u = (s_in - ramp_len) / flat_len if flat_len > 1e-9 else 0.0
    return ramp_end + in_flat_vec * u, "flat"


# =============================================================================
# Dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["kind"]

    if kind == "ramp_ball_deflected_angled_wall":
        return build_ramp_ball_deflected_angled_wall()

    raise RuntimeError("Unknown kind: " + str(kind))


def animate_scene_by_kind(scene, meta):
    kind = CASE["kind"]

    if kind == "ramp_ball_deflected_angled_wall":
        return animate_ramp_ball_deflected_angled_wall(scene, meta)

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
