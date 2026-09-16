# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_CLAMSHELL_BOX_0143",
  "scene_kind": "clamshell_box",
  "prompt": "An open clamshell container sits on a table with a coloured object resting inside, in plain view. Its two shells swing shut — the top half lowering over the top and the front half rising up — fully enclosing and hiding the object, then swing open again to reveal the same object, unchanged and in the same place. The container itself does not move; only the shells open and close."
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


def clamp01(t):
    return max(0.0, min(1.0, float(t)))


def smooth01(t):
    t = clamp01(t)
    return 3.0 * t * t - 2.0 * t * t * t


def lerp(a, b, t):
    return a + (b - a) * t


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
        try:
            mat.blend_method = "BLEND"
            mat.show_transparent_back = True
            mat.use_screen_refraction = True
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


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), roughness=0.84)
    MATS["gray"] = make_mat("mat_gray", (0.46, 0.46, 0.46), roughness=0.64)
    MATS["dark"] = make_mat("mat_dark", (0.18, 0.19, 0.21), roughness=0.76)
    MATS["light"] = make_mat("mat_light", (0.68, 0.69, 0.71), roughness=0.68)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.38, 0.06), roughness=0.28)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.92)
    MATS["shell_top"] = make_mat("mat_shell_top", (0.32, 0.55, 0.78), roughness=0.62)
    MATS["shell_bottom"] = make_mat("mat_shell_bottom", (0.40, 0.42, 0.46), roughness=0.68)


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


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (10.0, 5.0, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 2.48, 1.62), (10.2, 0.08, 3.24), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.4, -4.2, 5.5))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 980
    key.data.size = 6.0

    bpy.ops.object.light_add(type="POINT", location=(3.4, -3.0, 3.0))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 150

    return scene


def setup_camera(scene, location, target, lens=32, ortho=False, ortho_scale=4.0):
    bpy.ops.object.camera_add(location=location)
    cam = bpy.context.object
    cam.name = "camera_main"
    cam.data.lens = lens
    cam.data.dof.use_dof = False
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho_scale
    look_at(cam, target)
    scene.camera = cam
    return cam


# =============================================================================
# 0143 clamshell box
#
# A closed clamshell container sits on a table. It is built from a STATIC base
# (a shallow tray with fixed left / right / back walls that the object rests in)
# plus TWO hinged shells that open like a clamshell / oyster:
#
#   * The UPPER shell (a full-footprint roof cap) is hinged at the REAR-TOP
#     edge. It swings UP and BACK about that rear hinge, lifting the roof off
#     the container and rotating it back over the rear -- exactly the hinged-lid
#     technique reused here.
#   * The LOWER / FRONT shell (the front-facing wall panel) is hinged at its
#     FRONT-BOTTOM edge and swings DOWN and FORWARD, dropping the front of the
#     container down flat onto the table -- the lower jaw of the clamshell.
#
# A rear-hinged rigid slab can only ever stand up as a REAR wall, never a front
# wall, so the lower jaw is hinged at the front-bottom edge instead; this is the
# only construction that lets the front drop DOWN and FORWARD (as the prompt
# requires) with a pure rotation and no clipping. Together the two shells fully
# enclose a coloured ball when closed and clearly reveal it when open. The base
# never moves.
#
# Hinge construction (reused from the hinged-lid technique): each shell is built
# as a slab, then its mesh vertices are shifted so the OBJECT ORIGIN lands on
# its hinge edge. A pure world-X rotation then pivots exactly at that edge with
# no translation and no clipping.
# =============================================================================

def build_clamshell_box():
    scene = build_base_scene()

    # Front view, slightly raised, so the clamshell opening (top up-and-back,
    # front down-and-forward) and the revealed ball inside are all clearly read.
    setup_camera(
        scene,
        location=(0.0, -3.75, 2.30),
        target=(0.0, 0.0, 0.55),
        lens=40,
    )

    base_z = 0.10

    # --- Ball first: all container clearances are DERIVED from the ball so that
    # nothing can interpenetrate it. The ball rests on the inner floor with its
    # center exactly ball_r above the floor top surface, occupying
    #   x,y in [-ball_r, ball_r],  z in [floor_top_z, floor_top_z + 2*ball_r].
    ball_r = 0.30

    # Explicit safety margins (all >= ball_r-independent gaps around the ball).
    side_gap = 0.30        # min horizontal gap from ball surface to any wall
    roof_gap = 0.22        # min vertical gap from ball top to the closed roof

    # Container footprint. Inner cavity half-width derived so the ball clears the
    # side / back walls with side_gap to spare on every side.
    wall_t = 0.10
    inner_half = ball_r + side_gap             # 0.60 inner half-width / half-depth
    outer_half = inner_half + wall_t / 2.0     # wall centerline
    footprint = 2.0 * outer_half + wall_t      # full outer span incl. walls

    hinge_y = outer_half + wall_t / 2.0        # outer back edge (roof rear hinge)

    # --- Static base + fixed left / right / back walls ----------------------
    # Solid floor slab the ball rests on, plus fixed left / right / back walls
    # that stay put the whole time. The FRONT is left open -- the lower/front
    # shell provides that wall when closed. This base never moves.
    base_slab_top = base_z + 0.10              # 0.20, surface the ball rests on
    add_cube("clamshell_base_floor", (0.0, 0.0, base_z + 0.05),
             (footprint, footprint, 0.10),
             MATS["shell_bottom"], "container_base", "gray")

    # Walls rise from the floor top to the roof underside (== inner clearance),
    # so they enclose the ball vertically with roof_gap to spare above it.
    wall_h = 2.0 * ball_r + roof_gap           # floor top -> roof underside
    wall_cz = base_slab_top + wall_h / 2.0
    add_cube("clamshell_base_left_wall", (-outer_half, 0.0, wall_cz),
             (wall_t, footprint, wall_h), MATS["shell_bottom"], "container_base", "gray")
    add_cube("clamshell_base_right_wall", (outer_half, 0.0, wall_cz),
             (wall_t, footprint, wall_h), MATS["shell_bottom"], "container_base", "gray")
    add_cube("clamshell_base_back_wall", (0.0, outer_half, wall_cz),
             (footprint, wall_t, wall_h), MATS["shell_bottom"], "container_base", "gray")

    floor_top_z = base_slab_top  # top surface the ball rests on

    # Ball top sits at floor_top_z + 2*ball_r. The roof underside must clear it
    # by at least roof_gap, so the inner clearance (floor top -> roof underside)
    # is derived as ball height + roof_gap. The side walls run up to that roof.
    inner_clearance = 2.0 * ball_r + roof_gap  # floor top -> roof underside
    roof_z = floor_top_z + inner_clearance     # top of the fixed side walls / roof underside

    # --- Upper shell (roof cap, rear-top hinge) -----------------------------
    # Full-footprint roof slab. Origin moved to its REAR edge so it swings UP and
    # BACK about the rear-top hinge line, lifting the roof off the container.
    top_thick = 0.09
    top_span_x = footprint
    top_depth = 2.0 * hinge_y                   # from front outer edge back to hinge
    top_cz = roof_z + top_thick / 2.0           # rests just above the walls
    top_hinge_y = hinge_y                        # rear-top hinge line

    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.0, top_hinge_y, top_cz))
    top_shell = bpy.context.object
    top_shell.name = "clamshell_upper_shell"
    top_shell.dimensions = (top_span_x, top_depth, top_thick)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    # Shift verts so geometry extends in -Y (forward) from the rear-edge origin.
    mesh_t = top_shell.data
    for v in mesh_t.vertices:
        v.co.y -= top_depth / 2.0
    mesh_t.update()
    top_shell.data.materials.append(MATS["shell_top"])
    tag(top_shell, "clamshell_upper_shell", "clamshell_upper", "dynamic_object", "cube", "blue", True, solid=True)
    top_shell["pb_hinge_at_rear_top_edge"] = True

    # --- Lower / front shell (front wall panel, front-bottom hinge) ---------
    # A vertical wall panel that, when closed, forms the front face of the
    # container (front outer edge y = -hinge_y, from base up to the roof). Its
    # origin is moved to its BOTTOM edge (front-bottom) so it swings DOWN and
    # FORWARD about that edge, laying flat on the table in front and clearing the
    # ball entirely -- the lower jaw dropping open.
    front_thick = 0.09
    front_span_x = footprint
    front_h = roof_z - base_slab_top            # covers the full front gap (floor top -> roof)
    front_hy = -hinge_y                          # front-bottom hinge line (y)
    front_hz = base_slab_top                     # front-bottom hinge line (z)

    # Create the panel with its OBJECT ORIGIN exactly on the front-bottom hinge
    # edge (y = front_hy, z = front_hz), then shift the mesh verts UP (+Z) so the
    # panel body extends from that hinge edge up to the roof. This mirrors the
    # upper-shell construction: origin ON the hinge line -> a pure world-X
    # rotation pivots at the edge with no translation.
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.0, front_hy, front_hz))
    front_shell = bpy.context.object
    front_shell.name = "clamshell_lower_front_shell"
    front_shell.dimensions = (front_span_x, front_thick, front_h)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    # Shift verts so geometry extends UP (+Z) from the front-bottom edge origin.
    mesh_f = front_shell.data
    for v in mesh_f.vertices:
        v.co.z += front_h / 2.0
    mesh_f.update()
    front_shell.data.materials.append(MATS["shell_top"])
    tag(front_shell, "clamshell_lower_front_shell", "clamshell_lower", "dynamic_object", "cube", "blue", True, solid=True)
    front_shell["pb_hinge_at_front_bottom_edge"] = True

    # --- Object inside (revealed when the clamshell opens) -------------------
    # ball_r defined above; the ball rests on the inner floor with its center
    # exactly ball_r above floor_top_z, so it sits on the floor, not sunk in.
    ball = add_sphere(
        "colored_ball_inside_clamshell",
        ball_r,
        (0.0, 0.0, floor_top_z + ball_r),
        MATS["orange"],
        "orange",
    )
    ball["pb_visible_when_clamshell_open"] = True
    ball["pb_resting_inside_container"] = True

    return {
        "scene": scene,
        "kind": "clamshell_box",
        "top_shell": top_shell,
        "front_shell": front_shell,
        "ball": ball,
        "base_z": base_z,
        "ball_r": ball_r,
        "floor_top_z": floor_top_z,
        "roof_z": roof_z,
    }


def animate_clamshell_box(objs):
    scene = objs["scene"]
    top_shell = objs["top_shell"]
    front_shell = objs["front_shell"]
    ball = objs["ball"]
    floor_top_z = objs["floor_top_z"]
    ball_r = objs["ball_r"]

    # Each shell rotates about its own hinge edge (origins were moved to those
    # edges), so pure world-X rotations open them with no translation and no
    # movement of the static base.
    #
    # UPPER shell (rear-top hinge): CLOSED lies flat over the top (theta = 0);
    # OPEN lifts UP and BACK over the rear (negative theta rotates the -Y roof
    # slab up and back).
    #
    # LOWER / FRONT shell (front-bottom hinge): CLOSED stands vertical as the
    # front wall (theta = 0); OPEN drops DOWN and FORWARD, laying flat on the
    # table (positive theta rotates the +Z wall panel forward/down).
    #
    top_closed = math.radians(0.0)
    top_open = math.radians(-112.0)     # roof lifts up and back over the rear
    front_closed = math.radians(0.0)    # front wall standing up (closed)
    front_open = math.radians(95.0)     # front wall dropped flat/forward on table

    # Start-OPEN permanence cycle: the container is OPEN and the object is
    # plainly VISIBLE at the start, then the shells CLOSE (hiding it), hold shut,
    # then OPEN again to reveal the same object unchanged.
    #   Phase 1  f1  - f15  : fully OPEN, object visible inside.
    #   Phase 2  f15 - f48  : both shells swing CLOSED (object becomes hidden).
    #   Phase 3  f48 - f66  : hold fully CLOSED (object hidden).
    #   Phase 4  f66 - f100 : both shells swing OPEN again.
    #   Phase 5  f100- f120 : hold OPEN, same object revealed.
    close_start, close_end = 15, 48
    hold_end = 66
    reopen_end = 100

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        # open01: 1.0 = fully open, 0.0 = fully closed.
        if frame <= close_start:
            open01 = 1.0
            top_state = "open_object_visible"
            front_state = "open_front_shell_down"
            ball_state = "visible_inside_open_container"
        elif frame <= close_end:
            open01 = 1.0 - smooth01((frame - close_start) / float(close_end - close_start))
            top_state = "upper_shell_swinging_closed"
            front_state = "lower_front_shell_swinging_up_closed"
            ball_state = "being_hidden_as_clamshell_closes"
        elif frame <= hold_end:
            open01 = 0.0
            top_state = "closed_clamshell_shut"
            front_state = "closed_front_wall_up"
            ball_state = "hidden_inside_closed_clamshell"
        elif frame <= reopen_end:
            open01 = smooth01((frame - hold_end) / float(reopen_end - hold_end))
            top_state = "upper_shell_swinging_up_and_back"
            front_state = "lower_front_shell_dropping_down_and_forward"
            ball_state = "being_revealed_as_clamshell_reopens"
        else:
            open01 = 1.0
            top_state = "open_upper_shell_lifted_up_and_back"
            front_state = "open_lower_front_shell_dropped_down"
            ball_state = "revealed_resting_inside_container"

        s = open01
        theta_top = lerp(top_closed, top_open, s)
        theta_front = lerp(front_closed, front_open, s)

        # Upper shell: rotate about its rear-top edge origin (pure X rotation).
        top_shell.rotation_euler = (theta_top, 0.0, 0.0)
        top_shell.keyframe_insert(data_path="rotation_euler", frame=frame)
        top_shell["pb_state"] = top_state

        # Front shell: rotate about its front-bottom edge origin.
        front_shell.rotation_euler = (theta_front, 0.0, 0.0)
        front_shell.keyframe_insert(data_path="rotation_euler", frame=frame)
        front_shell["pb_state"] = front_state

        # Base and object never move.
        ball.location = (0.0, 0.0, floor_top_z + ball_r)
        ball.keyframe_insert(data_path="location", frame=frame)
        ball["pb_state"] = ball_state
        ball["pb_must_remain_inside_container"] = True
        ball["pb_same_object_throughout"] = True

    scene.frame_set(FRAME_START)


# =============================================================================
# dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "clamshell_box":
        return build_clamshell_box()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(objs):
    kind = objs["kind"]
    if kind == "clamshell_box":
        return animate_clamshell_box(objs)
    raise RuntimeError("Unknown kind: " + str(kind))


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
    animate_scene_by_kind(objs)

    # Input = closed clamshell (object hidden). Event = mid-open. Final = fully
    # open, object revealed resting inside the static container.
    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, 60, OPTIONAL_FRAME_PATH)
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
