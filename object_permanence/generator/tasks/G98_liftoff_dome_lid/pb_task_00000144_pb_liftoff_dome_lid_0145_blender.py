# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_LIFTOFF_DOME_LID_0145",
  "scene_kind": "liftoff_dome_lid",
  "prompt": "A dome-shaped lid (a cloche) sits over an object on a round base. The dome lifts straight up, clearing the object, to reveal it resting on the base. The base does not move; only the dome rises."
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


def add_cylinder(name, radius, depth, location, material, role, color_name, is_dynamic=False, solid=True):
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
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
    MATS["dome"] = make_mat("mat_dome", (0.40, 0.41, 0.43), roughness=0.55, metallic=0.15)


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
# 0145 liftoff dome lid
#
# A round base plate sits on the table. A dome-shaped lid (a cloche) sits over
# the base, covering a single colored ball resting on the base. The dome LIFTS
# STRAIGHT UP (+Z, no rotation) until its rim clears the top of the ball,
# revealing the ball resting on the base. The base and ball never move; only
# the dome translates upward.
#
# Dome construction: a UV-sphere whose LOWER hemisphere is deleted, leaving a
# hemispherical shell. Its origin is placed at the base top (the dome rim
# plane), so translating it straight up in +Z cleanly raises the whole cloche
# without any rotation. The dome inner radius is comfortably larger than the
# ball so there is no clipping between the shell and the ball at any time.
# =============================================================================

def build_liftoff_dome_lid():
    scene = build_base_scene()

    # Front view, slightly raised, so the dome and the revealed ball on the
    # round base are both clearly framed.
    setup_camera(
        scene,
        location=(0.0, -3.85, 1.75),
        target=(0.0, 0.0, 0.55),
        lens=42,
    )

    floor_z = 0.0

    # --- Round base plate ---------------------------------------------------
    base_radius = 1.05
    base_thick = 0.14
    base_cz = floor_z + base_thick / 2.0
    base_top_z = floor_z + base_thick  # top surface the ball & dome rim rest on

    add_cylinder(
        "round_base_plate",
        base_radius,
        base_thick,
        (0.0, 0.0, base_cz),
        MATS["light"],
        "base",
        "light_gray",
    )

    # --- Colored ball resting on the base (the persistent object) -----------
    # Sized to be plainly visible and to fit well inside the dome with margin.
    ball_r = 0.34
    ball_cz = base_top_z + ball_r
    ball = add_sphere(
        "colored_ball_on_base",
        ball_r,
        (0.0, 0.0, ball_cz),
        MATS["orange"],
        "orange",
    )
    ball["pb_visible_when_dome_lifted"] = True
    ball["pb_resting_on_base"] = True

    # --- Dome / cloche lid --------------------------------------------------
    # Inner radius must clear the ball. Ball top is at base_top_z + 2*ball_r.
    # We build a hemispherical SHELL: a sphere of radius dome_radius with the
    # lower half removed; a single hemisphere reads as a cloche. The dome radius
    # comfortably exceeds the ball radius and its apex sits above the ball top
    # with margin, so there is no clipping.
    dome_radius = 0.80          # hemisphere radius; > ball_r with clear margin
    ball_top_z = base_top_z + 2.0 * ball_r
    # Dome apex when resting = base_top_z + dome_radius. Ensure apex clears ball.
    # base_top_z + 0.80 = base_top_z + 0.80; ball_top_z = base_top_z + 0.68.
    # apex is 0.12 above the ball top -> clear, no clipping.

    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=64, ring_count=48, radius=dome_radius,
        location=(0.0, 0.0, base_top_z),
    )
    dome = bpy.context.object
    dome.name = "liftoff_dome_lid"

    # Delete the lower hemisphere (verts below the rim plane z = base_top_z),
    # leaving an upper hemispherical shell whose rim sits on the base top.
    import bmesh
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.object.mode_set(mode="OBJECT")
    for v in dome.data.vertices:
        # local z: sphere centered at origin of object; world z = local z + base_top_z
        if v.co.z < -1.0e-5:
            v.select = True
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.delete(type="VERT")
    bpy.ops.object.mode_set(mode="OBJECT")

    # Give the shell a little thickness so it reads as a solid cloche (not paper).
    solidify = dome.modifiers.new(name="dome_shell", type="SOLIDIFY")
    solidify.thickness = 0.04
    solidify.offset = -1.0  # thicken outward so inner radius stays clear of ball
    bpy.ops.object.select_all(action="DESELECT")
    dome.select_set(True)
    bpy.context.view_layer.objects.active = dome
    bpy.ops.object.modifier_apply(modifier="dome_shell")

    dome.data.materials.append(MATS["dome"])
    tag(dome, "liftoff_dome_lid", "dome_lid", "dynamic_object", "hemisphere", "dark_gray", True, solid=True)
    dome["pb_lifts_straight_up"] = True
    dome["pb_no_rotation"] = True

    # Lift distance: rise until the dome rim (at base_top_z when resting) is
    # above the ball top with clear margin -> whole ball revealed.
    lift_height = (ball_top_z - base_top_z) + 0.65  # rim ends well above ball top

    return {
        "scene": scene,
        "kind": "liftoff_dome_lid",
        "dome": dome,
        "ball": ball,
        "base_top_z": base_top_z,
        "ball_r": ball_r,
        "ball_cz": ball_cz,
        "dome_rest_z": 0.0,          # dome object starts at its built location (Z offset 0)
        "lift_height": lift_height,
    }


def animate_liftoff_dome_lid(objs):
    scene = objs["scene"]
    dome = objs["dome"]
    ball = objs["ball"]
    ball_cz = objs["ball_cz"]
    lift_height = objs["lift_height"]

    # The dome object was created at world location z = base_top_z; a +Z delta
    # of 0 = CLOSED (rim on base, ball covered), delta = lift_height = OPEN
    # (rim well above ball top, ball fully revealed). We keyframe a pure +Z
    # translation with zero rotation, so the cloche only ever moves straight
    # up / straight down and never tilts.
    #
    # Timeline is a START-OPEN hide -> reveal cycle:
    #   Phase 1  f1   - f18  : dome fully LIFTED/clear, ball visible (hold open).
    #   Phase 2  f18  - f48  : dome LOWERS straight DOWN to cover the ball (hide).
    #   Phase 3  f48  - f72  : hold CLOSED, ball hidden under the dome.
    #   Phase 4  f72  - f102 : dome LIFTS straight UP again, revealing the ball.
    #   Phase 5  f102 - f120 : hold OPEN, same ball revealed on base.
    dome_home = Vector(dome.location)  # closed position (rim on base, dz = 0)

    p1_end = 18    # end of initial open hold
    lower_end = 48  # dome fully lowered (closed)
    p3_end = 72    # end of closed hold
    lift_end = 102  # dome fully lifted (open) again

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= p1_end:
            # Phase 1: start OPEN, dome lifted clear, ball visible.
            dz = lift_height
            dome_state = "fully_lifted_ball_visible_hold_open"
            ball_state = "revealed_resting_on_base"
        elif frame <= lower_end:
            # Phase 2: lower straight DOWN to cover the ball.
            t = (frame - p1_end) / float(lower_end - p1_end)
            dz = lerp(lift_height, 0.0, smooth01(t))
            dome_state = "lowering_straight_down_hiding_ball"
            ball_state = "being_hidden_as_dome_lowers"
        elif frame <= p3_end:
            # Phase 3: hold CLOSED, ball hidden.
            dz = 0.0
            dome_state = "resting_over_ball_object_hidden"
            ball_state = "hidden_under_dome_on_base"
        elif frame <= lift_end:
            # Phase 4: lift straight UP again, revealing the same ball.
            t = (frame - p3_end) / float(lift_end - p3_end)
            dz = lerp(0.0, lift_height, smooth01(t))
            dome_state = "lifting_straight_up_revealing_ball"
            ball_state = "being_revealed_as_dome_rises"
        else:
            # Phase 5: hold OPEN, same ball revealed on base.
            dz = lift_height
            dome_state = "fully_lifted_ball_revealed_on_base"
            ball_state = "revealed_resting_on_base"

        # Pure straight up/down translation; rotation stays zero (no tilt).
        dome.location = (dome_home.x, dome_home.y, dome_home.z + dz)
        dome.rotation_euler = (0.0, 0.0, 0.0)
        dome.keyframe_insert(data_path="location", frame=frame)
        dome.keyframe_insert(data_path="rotation_euler", frame=frame)
        dome["pb_state"] = dome_state

        # The base and the ball never move.
        ball.location = (0.0, 0.0, ball_cz)
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
    if kind == "liftoff_dome_lid":
        return build_liftoff_dome_lid()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(objs):
    kind = objs["kind"]
    if kind == "liftoff_dome_lid":
        return animate_liftoff_dome_lid(objs)
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

    # Input = start OPEN, dome lifted clear, ball visible. Event = dome down /
    # closed (ball hidden under dome). Final = lifted again, ball revealed.
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
