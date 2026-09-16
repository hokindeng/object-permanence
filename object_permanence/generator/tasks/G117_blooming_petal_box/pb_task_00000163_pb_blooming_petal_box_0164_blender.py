# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_BLOOMING_PETAL_BOX_0164",
  "scene_kind": "blooming_petal_box",
  "prompt": "Four triangular flaps are folded up and inward to form a closed pyramid over an object. The four flaps fold outward and down (blooming open like a flower) to reveal the object resting on the base, unchanged."
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
    MATS["petal"] = make_mat("mat_petal", (0.72, 0.28, 0.42), roughness=0.55)
    MATS["base"] = make_mat("mat_base", (0.40, 0.42, 0.46), roughness=0.68)


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
# 0164 blooming petal box
#
# A square base plate sits on the table. Four identical TRIANGULAR flaps are
# hinged on the four edges of the square base. Each flap is an isosceles
# triangle whose base edge lies along a base edge of the square and whose apex
# reaches up toward the center. When CLOSED the flaps are folded UP and INWARD
# so their apexes meet high over the center, forming a closed four-sided pyramid
# that fully hides the object resting on the base. To OPEN, all four flaps
# rotate OUTWARD and DOWN about their base-edge hinges (blooming open like a
# flower) until they lie flat on the table around the base, revealing the object.
#
# Hinge construction (reused hinged-lid technique): each flap is a thin
# triangular prism built with its OBJECT ORIGIN placed exactly on its hinge
# edge (a base edge of the square). A pure rotation about the horizontal edge
# axis then pivots the flap at that edge with no translation:
#   * closed = flap tilted up/in so its plane is nearly vertical (apex high);
#   * open   = flap lying flat outward on the table (plane horizontal, apex out).
# The four flaps sit on the four edges (+Y back, -Y front, +X right, -X left),
# each rotating about the edge tangent so they never translate off the base and
# clear the object (the pyramid apex is well above the object top when closed).
# =============================================================================

def _make_triangle_flap(name, edge, half_edge, flap_len, thick, mat):
    """Build a thin triangular-prism flap with its origin on its hinge edge.

    edge: "back"/"front"/"right"/"left" -> which base edge the flap hinges on.
    The flap is built lying FLAT in the XY plane with its hinge edge (the full
    2*half_edge base) centred on the local origin and its apex pointing OUTWARD
    (away from the base centre) by flap_len; local +Z is thickness. Because the
    apex already points outward, rotation about the hinge-edge axis by a POSITIVE
    fold angle lifts the apex UP and INWARD toward the centre, forming the closed
    pyramid, with NO translation (origin sits on the hinge edge).

        back  -> hinge along X at +Y edge, apex toward +Y (outward)
        front -> hinge along X at -Y edge, apex toward -Y (outward)
        right -> hinge along Y at +X edge, apex toward +X (outward)
        left  -> hinge along Y at -X edge, apex toward -X (outward)
    """
    if edge == "back":
        a2 = (-half_edge, 0.0); b2 = (half_edge, 0.0); apex2 = (0.0, flap_len)
        hinge_axis = "x"
    elif edge == "front":
        a2 = (-half_edge, 0.0); b2 = (half_edge, 0.0); apex2 = (0.0, -flap_len)
        hinge_axis = "x"
    elif edge == "right":
        a2 = (0.0, -half_edge); b2 = (0.0, half_edge); apex2 = (flap_len, 0.0)
        hinge_axis = "y"
    else:  # left
        a2 = (0.0, -half_edge); b2 = (0.0, half_edge); apex2 = (-flap_len, 0.0)
        hinge_axis = "y"

    hz2 = thick / 2.0
    verts = [
        (a2[0], a2[1], -hz2),
        (b2[0], b2[1], -hz2),
        (apex2[0], apex2[1], -hz2),
        (a2[0], a2[1], hz2),
        (b2[0], b2[1], hz2),
        (apex2[0], apex2[1], hz2),
    ]
    faces = [
        (0, 1, 2),        # bottom triangle
        (5, 4, 3),        # top triangle
        (0, 3, 4, 1),     # hinge-edge quad
        (1, 4, 5, 2),     # right slant quad
        (2, 5, 3, 0),     # left slant quad
    ]
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    tag(obj, name, "petal_flap", "dynamic_object", "triangle_flap", "magenta", True, solid=True)
    obj["pb_hinge_axis"] = hinge_axis
    obj["pb_edge"] = edge
    obj["pb_hinge_at_base_edge"] = True
    return obj


def build_blooming_petal_box():
    scene = build_base_scene()

    # Slightly raised front view so the closed pyramid, the blooming flaps, and
    # the revealed object on the base all read clearly.
    setup_camera(
        scene,
        location=(0.0, -3.95, 2.55),
        target=(0.0, 0.0, 0.45),
        lens=40,
    )

    base_z = 0.10

    # --- Ball first: container geometry derived from the ball so nothing clips.
    ball_r = 0.28

    # Square base half-width. Chosen so the ball has clearance to every edge
    # and the flaps, folded flat, extend outward beyond the base footprint.
    base_half = ball_r + 0.34          # 0.62 half-width of the square base top
    base_thick = 0.10
    base_slab_top = base_z + base_thick  # top surface the ball & flaps rest on

    # Square base plate the ball rests on; this NEVER moves.
    add_cube(
        "petal_base_plate",
        (0.0, 0.0, base_z + base_thick / 2.0),
        (2.0 * base_half + 0.10, 2.0 * base_half + 0.10, base_thick),
        MATS["base"], "container_base", "gray",
    )

    floor_top_z = base_slab_top  # ball rests here

    # --- Object inside (revealed when the flaps bloom open) -----------------
    ball = add_sphere(
        "colored_ball_inside_petals",
        ball_r,
        (0.0, 0.0, floor_top_z + ball_r),
        MATS["orange"],
        "orange",
    )
    ball["pb_visible_when_petals_open"] = True
    ball["pb_resting_on_base"] = True

    # --- Four triangular flaps hinged on the four base edges ----------------
    # Each flap's hinge edge lies on a base edge (at distance base_half from the
    # center). The flap length (hinge edge -> apex) is chosen so that, when the
    # four flaps stand up and tilt inward, their apexes meet high above the
    # center forming a closed pyramid whose interior comfortably clears the ball.
    thick = 0.05
    half_edge = base_half              # hinge edge spans the full base edge
    # Flap length: long enough that when tilted up to ~pyramid the apex reaches
    # over the center and above the ball. flap_len ~ 1.15*base_half*sqrt(2)-ish.
    flap_len = 1.35

    # Hinge-edge z is the base top; hinge lines sit on the four edges.
    hz = base_slab_top

    flaps = []

    # Back flap: hinge edge along X at y = +base_half; apex points +Y (outward).
    back = _make_triangle_flap("petal_flap_back", "back", half_edge, flap_len, thick, MATS["petal"])
    back.location = (0.0, base_half, hz)
    flaps.append(("back", back))

    # Front flap: hinge edge along X at y = -base_half; apex points -Y (outward).
    front = _make_triangle_flap("petal_flap_front", "front", half_edge, flap_len, thick, MATS["petal"])
    front.location = (0.0, -base_half, hz)
    flaps.append(("front", front))

    # Right flap: hinge edge along Y at x = +base_half; apex points +X (outward).
    right = _make_triangle_flap("petal_flap_right", "right", half_edge, flap_len, thick, MATS["petal"])
    right.location = (base_half, 0.0, hz)
    flaps.append(("right", right))

    # Left flap: hinge edge along Y at x = -base_half; apex points -X (outward).
    left = _make_triangle_flap("petal_flap_left", "left", half_edge, flap_len, thick, MATS["petal"])
    left.location = (-base_half, 0.0, hz)
    flaps.append(("left", left))

    return {
        "scene": scene,
        "kind": "blooming_petal_box",
        "flaps": flaps,
        "ball": ball,
        "base_z": base_z,
        "ball_r": ball_r,
        "floor_top_z": floor_top_z,
    }


def _flap_rotation(edge, open01):
    """Return the Euler rotation for a flap given open fraction (1=open flat,
    0=closed pyramid).

    Each flap is built lying FLAT with its apex pointing OUTWARD (local +Z is
    thickness). Rotating about its hinge-edge axis lifts the apex UP and INWARD:
      open01 = 1.0 -> rotation 0 (flap flat, apex pointing outward).
      open01 = 0.0 -> flap folded up by ~closed_angle (apex high over center).

    The sign per edge is chosen so every apex rises up and converges over the
    centre (a positive fold about the hinge-edge tangent, expressed as a signed
    Euler about world X or Y depending on the edge orientation):
        back  -> +X   front -> -X   right -> -Y   left -> +Y
    """
    # closed_angle: how far up from flat the flap tilts when closed. Slightly
    # past vertical-inward so the four apexes converge into a pyramid over center.
    closed_angle = math.radians(118.0)
    ang = (1.0 - open01) * closed_angle
    if edge == "back":
        return (ang, 0.0, 0.0)
    if edge == "front":
        return (-ang, 0.0, 0.0)
    if edge == "right":
        return (0.0, -ang, 0.0)
    return (0.0, ang, 0.0)  # left


def animate_blooming_petal_box(objs):
    scene = objs["scene"]
    flaps = objs["flaps"]
    ball = objs["ball"]
    floor_top_z = objs["floor_top_z"]
    ball_r = objs["ball_r"]

    # Start-OPEN permanence cycle: the flaps are bloomed OPEN and the object is
    # plainly VISIBLE at the start, then the flaps fold UP/IN to close over it
    # (pyramid, object hidden), hold shut, then bloom OPEN again to reveal the
    # same object unchanged on the base.
    #   Phase 1  f1  - f15  : fully OPEN (flaps flat), object visible.
    #   Phase 2  f15 - f48  : flaps fold up/inward to close (pyramid forms).
    #   Phase 3  f48 - f66  : hold fully CLOSED (pyramid, object hidden).
    #   Phase 4  f66 - f100 : flaps bloom OPEN again.
    #   Phase 5  f100- f120 : hold OPEN, same object revealed.
    close_start, close_end = 15, 48
    hold_end = 66
    reopen_end = 100

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= close_start:
            open01 = 1.0
            flap_state = "open_flat_object_visible"
            ball_state = "visible_on_base_open"
        elif frame <= close_end:
            open01 = 1.0 - smooth01((frame - close_start) / float(close_end - close_start))
            flap_state = "flaps_folding_up_closing_pyramid"
            ball_state = "being_hidden_as_petals_close"
        elif frame <= hold_end:
            open01 = 0.0
            flap_state = "closed_pyramid_object_hidden"
            ball_state = "hidden_inside_closed_pyramid"
        elif frame <= reopen_end:
            open01 = smooth01((frame - hold_end) / float(reopen_end - hold_end))
            flap_state = "flaps_blooming_open_outward_down"
            ball_state = "being_revealed_as_petals_bloom"
        else:
            open01 = 1.0
            flap_state = "open_flat_object_revealed"
            ball_state = "revealed_resting_on_base"

        for (name, flap) in flaps:
            flap.rotation_euler = _flap_rotation(name, open01)
            flap.keyframe_insert(data_path="rotation_euler", frame=frame)
            flap["pb_state"] = flap_state

        # Base and object never move.
        ball.location = (0.0, 0.0, floor_top_z + ball_r)
        ball.keyframe_insert(data_path="location", frame=frame)
        ball["pb_state"] = ball_state
        ball["pb_must_remain_on_base"] = True
        ball["pb_same_object_throughout"] = True

    scene.frame_set(FRAME_START)


# =============================================================================
# dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "blooming_petal_box":
        return build_blooming_petal_box()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(objs):
    kind = objs["kind"]
    if kind == "blooming_petal_box":
        return animate_blooming_petal_box(objs)
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

    # Input = start OPEN (object visible on base). Event = mid (closed pyramid).
    # Final = bloomed open again, object revealed on the static base.
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
