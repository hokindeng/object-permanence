# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_SPIRAL_RAMP_BEHIND_COLUMN_0108",
  "scene_kind": "spiral_ramp_behind_column",
  "kind": "spiral_ramp_behind_column",
  "prompt": "A ball rolls down a helical ramp that spirals around an opaque vertical column. As it descends it passes behind the column on each half-turn, disappearing from view, then re-emerges on the near side - the same ball - continuing down to the floor. It never changes identity or size while hidden."
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
        # Order-INDEPENDENT transparency (HASHED / DITHERED) so opaque geometry
        # behind the glass never flickers/vanishes from blend sort order; TAA
        # resolves it smooth. alpha<0.999 also makes the pipeline preserve it.
        try:
            mat.blend_method = "HASHED"
            mat.show_transparent_back = False
            mat.use_screen_refraction = False
        except Exception:
            pass
        try:
            mat.surface_render_method = "DITHERED"
        except Exception:
            pass

    return mat


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), roughness=0.85)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.92)

    MATS["gray"] = make_mat("mat_gray", (0.62, 0.63, 0.66), roughness=0.75)
    MATS["housing"] = make_mat("mat_housing", (0.32, 0.33, 0.37), roughness=0.85)
    MATS["dark"] = make_mat("mat_dark", (0.18, 0.20, 0.24), roughness=0.55)
    MATS["support"] = make_mat("mat_support", (0.16, 0.18, 0.22), roughness=0.60)

    MATS["red"] = make_mat("mat_red", (0.92, 0.18, 0.18), roughness=0.28)
    MATS["blue"] = make_mat("mat_blue", (0.16, 0.36, 0.95), roughness=0.28)
    MATS["yellow"] = make_mat("mat_yellow", (0.98, 0.78, 0.15), roughness=0.28)
    MATS["orange"] = make_mat("mat_orange", (0.97, 0.45, 0.10), roughness=0.28)
    MATS["glass"] = make_mat("mat_glass", (0.60, 0.80, 1.0), roughness=0.08, alpha=0.24, transparent=True)


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


def add_sphere(name, radius, location, material, color_name, role="target", is_dynamic=True):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=48, ring_count=24)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)

    tag(
        obj,
        name,
        role,
        "dynamic_object" if is_dynamic else "static_solid",
        "sphere",
        color_name,
        is_dynamic,
        solid=True,
        pb_radius=radius,
    )
    return obj


def add_cylinder(name, location, radius, depth, material, role, color_name, rotation=(0.0, 0.0, 0.0), is_dynamic=False):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, vertices=24, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    if material is not None:
        obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "cylinder", color_name, is_dynamic, solid=True)
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


def add_oriented_box(name, location, dimensions, material, role, color_name, rotation=(0.0, 0.0, 0.0), is_dynamic=False, solid=True):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.rotation_euler = rotation

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
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Base Contrast"
    except Exception:
        try:
            scene.view_settings.view_transform = "Standard"
            scene.view_settings.look = "None"
        except Exception:
            pass


def setup_base(camera_loc, target, ortho_scale):
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (12.0, 8.0, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.55, 2.05), (12.0, 0.08, 4.1), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-2.8, -4.5, 6.4))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 600
    key.data.size = 7.0

    bpy.ops.object.light_add(type="POINT", location=(3.0, 1.8, 3.6))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 140

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
# 00000107  spiral_ramp_behind_column  (Cluster: Baillargeonian Occlusion)
# =============================================================================
#
# An opaque vertical CYLINDER column stands at the world origin. A helical ramp
# wraps around it, approximated by a series of short banked ramp segments placed
# at increasing angle theta around the column and decreasing z. One ball rolls
# down this helix, its centre following:
#
#     x(theta) = R * cos(theta)
#     y(theta) = R * sin(theta)
#     z(theta) = z_top - (theta / theta_total) * (z_top - z_floor)
#
# The camera looks at the column from the -Y side (front). Therefore the NEAR
# side of the column is y < 0 (toward camera) and the FAR side is y > 0 (behind
# the column). On every half-turn the ball crosses to the far side (y > 0) where
# the opaque column occludes it. The COLUMN GEOMETRY does the occluding -- the
# ball is never removed from the render -- so occlusion is honest image-space
# cover. Its true position keeps being animated the whole time, so the same ball
# reappears at the correct place/time -- identity and size never change.
# =============================================================================

# --- Helix parameters (module-level so build + animate share them) ---
COL_RADIUS = 0.72          # opaque column radius
HELIX_R = 1.55             # ball-centre orbit radius (well outside the column)
Z_TOP = 3.20               # helix top (ball centre height at theta=0)
Z_FLOOR = 0.42             # helix bottom (near floor)
N_TURNS = 2.5              # number of full turns (a few full turns -> several occlusions)
THETA_TOTAL = N_TURNS * 2.0 * math.pi
BALL_RADIUS = 0.20
RAMP_WIDTH = 0.72          # radial width of each ramp segment slab
RAMP_THICK = 0.12
N_SEG = 60                 # number of short ramp segments approximating the helix
SURF_OFF = RAMP_THICK / 2.0 + BALL_RADIUS   # ball-centre offset above ramp top face


def _helix_center(theta):
    """Point on the helix centre-line (the ramp mid-surface) for angle theta."""
    frac = theta / THETA_TOTAL
    x = HELIX_R * math.cos(theta)
    y = HELIX_R * math.sin(theta)
    z = Z_TOP - frac * (Z_TOP - Z_FLOOR)
    return Vector((x, y, z))


def _ball_pos(theta):
    """Ball centre: on the helix centre-line lifted by SURF_OFF so it sits ON the ramp."""
    c = _helix_center(theta)
    return Vector((c.x, c.y, c.z + SURF_OFF))


def build_spiral_ramp_behind_column():
    scene = setup_base(
        camera_loc=(0.0, -9.6, 2.35),
        target=(0.0, 0.0, 1.75),
        ortho_scale=5.6,
    )

    # --- Opaque vertical column at the world origin ---
    col_bottom = 0.0
    col_top = Z_TOP + 0.55           # taller than the helix top so it occludes the whole descent
    col_h = col_top - col_bottom
    col_cz = (col_bottom + col_top) / 2.0
    add_cylinder(
        "column_opaque",
        (0.0, 0.0, col_cz),
        COL_RADIUS,
        col_h,
        MATS["housing"],
        "occluder_column",
        "gray",
        rotation=(0.0, 0.0, 0.0),
    )
    # A slim base disc so the column reads as planted on the floor (no floating).
    add_cylinder(
        "column_base",
        (0.0, 0.0, 0.04),
        COL_RADIUS + 0.18,
        0.08,
        MATS["support"],
        "column_base",
        "dark_gray",
    )

    # --- Helical ramp: short banked slabs following the helix centre-line ---
    # Each slab spans a small theta interval; it is centred on the helix and
    # rotated so its long axis follows the local tangent (yaw about Z) and it is
    # pitched about the local horizontal so it descends with the helix.
    for i in range(N_SEG):
        t0 = (i / N_SEG) * THETA_TOTAL
        t1 = ((i + 1) / N_SEG) * THETA_TOTAL
        p0 = _helix_center(t0)
        p1 = _helix_center(t1)
        diff = p1 - p0
        length = diff.length * 1.02        # tiny overlap so segments join with no gaps
        mid = (p0 + p1) / 2.0
        yaw = math.atan2(diff.y, diff.x)
        horiz = math.hypot(diff.x, diff.y)
        pitch = -math.atan2(diff.z, horiz)  # negative dz -> nose-down slope
        add_oriented_box(
            "spiral_ramp_seg_%02d" % i,
            (mid.x, mid.y, mid.z),
            (length, RAMP_WIDTH, RAMP_THICK),
            MATS["blue"],
            "ramp_segment",
            "blue",
            rotation=(0.0, pitch, yaw),
        )

    # --- Transparent guard wall along the OUTER rim of the helix ---------------
    # Keeps the ball visibly on the spiral track (otherwise, descending the
    # helix, it would fly off outward). A see-through glass fence follows the
    # outer edge of every ramp segment, so nothing reads as clutter.
    WALL_H = 0.50
    WALL_T = 0.05
    outer_r = HELIX_R + RAMP_WIDTH / 2.0 - 0.03
    for i in range(N_SEG):
        t0 = (i / N_SEG) * THETA_TOTAL
        t1 = ((i + 1) / N_SEG) * THETA_TOTAL
        cm = _helix_center((t0 + t1) / 2.0)
        o0 = Vector((outer_r * math.cos(t0), outer_r * math.sin(t0), _helix_center(t0).z))
        o1 = Vector((outer_r * math.cos(t1), outer_r * math.sin(t1), _helix_center(t1).z))
        wmid = (o0 + o1) / 2.0
        d = o1 - o0
        seg_len = math.hypot(d.x, d.y) * 1.06
        yaw_w = math.atan2(d.y, d.x)
        surface_z = cm.z + RAMP_THICK / 2.0
        w = add_oriented_box(
            "spiral_guard_%02d" % i,
            (wmid.x, wmid.y, surface_z + WALL_H / 2.0),
            (seg_len, WALL_T, WALL_H),
            MATS["glass"],
            "guard_wall_transparent",
            "glass",
            rotation=(0.0, 0.0, yaw_w),
        )
        w["pb_transparent"] = True

    # --- Ball starts resting on the ramp at theta = 0 (near-ish, front-right) ---
    ball_start = _ball_pos(0.0)
    ball = add_sphere("spiral_ball", BALL_RADIUS, ball_start, MATS["orange"], "orange")
    ball["pb_path"] = "helical_descent_around_opaque_column_repeated_occlusion"
    ball["pb_can_disappear"] = False

    return scene, {
        "ball": ball,
        "ball_radius": BALL_RADIUS,
    }


def animate_spiral_ramp_behind_column(scene, meta):
    ball = meta["ball"]
    radius = meta["ball_radius"]

    rest_frames = 8
    move_frames = FRAME_END - rest_frames   # frames over which the descent plays out

    # Occlusion test: the ball is hidden when it is on the FAR side of the column
    # (y > 0, behind the column from the camera at -Y) AND close enough to the
    # column axis in X that the column body actually covers it. Using y > 0 with a
    # small margin gives a clean "blink behind the column" on each half-turn.
    # The column half-width seen by the camera is COL_RADIUS in X; the ball
    # counts as occluded only when its whole silhouette fits inside that
    # silhouette, i.e. y > 0 and |x| + ball radius <= COL_RADIUS.
    def is_behind_column(pos):
        # Camera looks along +Y (from y=-9.6 toward origin). The column occludes
        # the ball when the ball is farther from the camera than the column's near
        # face AND its projected X falls within the column silhouette.
        if pos.y <= 0.0:
            return False  # near side -> always visible
        # far side: the flag means FULLY hidden, so require full containment of
        # the ball silhouette inside the column silhouette: |x| + r <= COL_RADIUS.
        # On this on-axis ortho camera that containment form matches the true
        # image-space window exactly.
        return abs(pos.x) + radius <= COL_RADIUS

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= rest_frames:
            u = 0.0
        else:
            # ease-in then roughly constant descent along the helix arc parameter
            p = (frame - rest_frames) / float(move_frames)
            p = min(1.0, max(0.0, p))
            # smoothstep-ish acceleration so it starts gently and keeps rolling
            u = p * p * (3.0 - 2.0 * p) * 0.35 + p * 0.65
            u = min(1.0, u)

        theta = u * THETA_TOTAL
        pos = _ball_pos(theta)
        # Documentary-only flag (frontal camera, so the world-space test tracks
        # the image well); the column geometry does the actual occluding.
        hidden = is_behind_column(pos)

        ball.location = pos
        # roll about a horizontal axis roughly perpendicular to travel; arc-length
        # based spin so rotation reads as rolling, not sliding.
        arc_s = theta * HELIX_R
        ball.rotation_euler = (0.0, arc_s / radius, theta)
        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)

        if hidden:
            ball["pb_state"] = "hidden_behind_opaque_column"
        elif pos.y > 0.0:
            ball["pb_state"] = "visible_on_far_arc_beside_column"
        else:
            ball["pb_state"] = "visible_on_near_side_descending"
        ball["pb_theta"] = float(theta)
        ball["pb_occluded"] = bool(hidden)

    scene.frame_set(FRAME_START)


# =============================================================================
# Dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE.get("scene_kind", CASE.get("kind"))

    if kind == "spiral_ramp_behind_column":
        return build_spiral_ramp_behind_column()

    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(scene, meta):
    kind = CASE.get("scene_kind", CASE.get("kind"))

    if kind == "spiral_ramp_behind_column":
        return animate_spiral_ramp_behind_column(scene, meta)

    raise RuntimeError("Unknown scene_kind: " + str(kind))


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
    print("scene_kind:", CASE.get("scene_kind"))
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
