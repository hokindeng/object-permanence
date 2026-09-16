# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector
import bmesh

CASE = json.loads(r"""{
  "item_id": "PB_TWIST_OPEN_CAPSULE_0179",
  "scene_kind": "twist_open_capsule",
  "prompt": "A two-half capsule shaped like an egg sits on a small stand and contains a single colored ball. The top half lifts straight up and off with a slight twist, revealing the ball resting inside the bottom half; it holds open briefly, then the top half lowers back down and twists closed over the ball, then lifts off again to reveal the SAME ball. The bottom half and the stand never move, the ball stays put inside, and the top half fully clears the ball when open so the ball is plainly visible."
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


def add_cylinder(name, location, radius, depth, material, role, color_name, is_dynamic=False, vertices=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    if material is not None:
        obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "cylinder", color_name, is_dynamic, solid=True)
    return obj


def make_hemisphere_shell(name, radius, thickness, z_scale, top, mat, role, color_name, is_dynamic):
    """Build a hollow hemispherical shell (a dome or a bowl).

    A closed UV sphere is created, one hemisphere of its vertices is deleted
    (keeping z >= 0 for `top`, z <= 0 for the bottom bowl), and a Solidify
    modifier gives the remaining open half-shell a wall thickness so the object
    inside is hidden when closed and visible when the top is removed. The mesh
    is scaled in z afterwards for an egg-like profile. The object ORIGIN sits at
    the equator centre (0,0,0), so pure translation/rotation pivots cleanly.
    """
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=radius, location=(0.0, 0.0, 0.0))
    obj = bpy.context.object
    obj.name = name
    me = obj.data

    bm = bmesh.new()
    bm.from_mesh(me)
    if top:
        kill = [v for v in bm.verts if v.co.z < -1e-5]
    else:
        kill = [v for v in bm.verts if v.co.z > 1e-5]
    bmesh.ops.delete(bm, geom=kill, context="VERTS")
    bm.to_mesh(me)
    bm.free()

    # Wall thickness so the shell reads as a hollow half-capsule.
    mod = obj.modifiers.new("solidify", "SOLIDIFY")
    mod.thickness = thickness
    mod.offset = 1.0        # thicken outward so the interior radius is preserved
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.modifier_apply(modifier="solidify")

    # Egg profile: gentle vertical stretch.
    obj.scale = (1.0, 1.0, z_scale)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    obj.data.materials.append(mat)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid",
        "capsule_shell", color_name, is_dynamic, solid=True)
    return obj


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), roughness=0.84)
    MATS["gray"] = make_mat("mat_gray", (0.46, 0.46, 0.46), roughness=0.64)
    MATS["dark"] = make_mat("mat_dark", (0.18, 0.19, 0.21), roughness=0.76)
    MATS["light"] = make_mat("mat_light", (0.68, 0.69, 0.71), roughness=0.68)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.38, 0.06), roughness=0.28)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.92)
    MATS["capsule"] = make_mat("mat_capsule", (0.58, 0.59, 0.62), roughness=0.48)
    MATS["stand"] = make_mat("mat_stand", (0.40, 0.42, 0.46), roughness=0.68)


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
# 0179 twist open capsule
#
# A small STAND (apparatus) sits on the table. A two-half egg-shaped CAPSULE
# (apparatus, gray) rests on it: a fixed BOTTOM BOWL (a hollow lower hemisphere)
# and a removable TOP DOME (a hollow upper hemisphere) that together enclose a
# single colored ball resting inside the bottom bowl. This is a START-CLOSED
# permanence cycle: at frame 1 the capsule is shut and the ball is hidden. The
# TOP half lifts straight UP with a slight twist about the vertical axis until
# it fully clears the ball; it holds open (ball plainly visible in the bottom
# bowl), then lowers back down (twisting closed) over the ball, holds shut, then
# lifts off again to reveal the SAME ball. The stand, the bottom bowl and the
# ball never move; the ball stays put inside the bottom bowl throughout.
# =============================================================================

def build_twist_open_capsule():
    scene = build_base_scene()

    setup_camera(
        scene,
        location=(0.0, -3.85, 2.05),
        target=(0.0, 0.0, 0.85),
        lens=42,
    )

    R = 0.55                       # capsule (equator) radius
    THICK = 0.04                   # shell wall thickness
    Z_SCALE = 1.15                 # egg vertical stretch
    ball_r = 0.30

    # --- Stand (apparatus, never moves) -------------------------------------
    stand_h = 0.35
    stand_top = stand_h            # 0.35
    add_cylinder("capsule_support_pedestal", (0.0, 0.0, stand_h / 2.0),
                 0.34, stand_h, MATS["stand"], "capsule_support", "gray")
    add_cylinder("capsule_support_cap", (0.0, 0.0, stand_h + 0.02),
                 0.40, 0.04, MATS["stand"], "capsule_support", "gray")

    # --- Capsule equator plane sits so the bottom bowl rests on the stand ----
    # The bottom bowl exterior reaches down by R*Z_SCALE from the equator.
    eq_z = stand_top + R * Z_SCALE + 0.04     # equator height above the stand cap

    # --- Bottom bowl (fixed hollow lower hemisphere) ------------------------
    bottom = make_hemisphere_shell(
        "capsule_cover_bottom", R, THICK, Z_SCALE, top=False,
        mat=MATS["capsule"], role="capsule_cover", color_name="gray", is_dynamic=False,
    )
    bottom.location = (0.0, 0.0, eq_z)

    # Interior floor of the bowl (its lowest inner point) where the ball rests.
    bowl_inner_bottom = eq_z - (R - THICK) * Z_SCALE
    ball_cz = bowl_inner_bottom + ball_r

    # --- Ball (target, vivid) resting inside the bottom bowl ----------------
    ball = add_sphere(
        "hidden_ball_in_capsule", ball_r, (0.0, 0.0, ball_cz),
        MATS["orange"], "orange", role="hidden_ball",
    )
    ball["pb_stays_inside_bottom_bowl"] = True

    # --- Top dome (removable hollow upper hemisphere) -----------------------
    top = make_hemisphere_shell(
        "capsule_lid_top", R, THICK, Z_SCALE, top=True,
        mat=MATS["capsule"], role="capsule_lid", color_name="gray", is_dynamic=True,
    )
    top_base_z = eq_z              # closed: top equator meets bottom equator
    top.location = (0.0, 0.0, top_base_z)

    ball_top_z = ball_cz + ball_r
    # Lift the top so its lowest rim (at eq_z when closed) rises well clear of
    # the ball's top; a comfortable margin so the ball is plainly visible.
    lift_dist = (ball_top_z - eq_z) + 0.65
    if lift_dist < 0.60:
        lift_dist = 0.60

    return {
        "scene": scene,
        "kind": "twist_open_capsule",
        "top": top,
        "bottom": bottom,
        "ball": ball,
        "top_base_z": top_base_z,
        "ball_cz": ball_cz,
        "ball_top_z": ball_top_z,
        "eq_z": eq_z,
        "lift_dist": lift_dist,
        "ball_r": ball_r,
    }


def animate_twist_open_capsule(objs):
    scene = objs["scene"]
    top = objs["top"]
    ball = objs["ball"]
    top_base_z = objs["top_base_z"]
    ball_cz = objs["ball_cz"]
    lift_dist = objs["lift_dist"]

    # Container-static permanence, START-CLOSED cycle. The stand, bottom bowl
    # and ball never move. The TOP half lifts straight up (with a slight twist)
    # and lowers back, keyframed every frame. Open fraction u: 0 = closed,
    # 1 = fully lifted clear of the ball.
    #   Phase 1  f1   - f12  : closed; ball hidden inside the capsule.
    #   Phase 2  f12  - f44  : top lifts + twists off; ball revealed.
    #   Phase 3  f44  - f66  : hold OPEN; ball plainly visible in the bottom bowl.
    #   Phase 4  f66  - f92  : top lowers + twists closed over the ball.
    #   Phase 5  f92  - f100 : hold CLOSED.
    #   Phase 6  f100 - f120 : top lifts off again; same ball revealed.
    open_a_start, open_a_end = 12, 44
    hold_open_end = 66
    close_start, close_end = 66, 92
    closed_hold_end = 100
    reopen_end = 120

    TWIST = math.radians(90.0)     # slight twist coupled to the lift

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= open_a_start:
            u = 0.0
            state = "closed_ball_hidden"
        elif frame <= open_a_end:
            u = smooth01((frame - open_a_start) / float(open_a_end - open_a_start))
            state = "top_lifting_off_ball_revealing"
        elif frame <= hold_open_end:
            u = 1.0
            state = "open_ball_visible_in_bottom_bowl"
        elif frame <= close_end:
            u = 1.0 - smooth01((frame - close_start) / float(close_end - close_start))
            state = "top_lowering_closed_over_ball"
        elif frame <= closed_hold_end:
            u = 0.0
            state = "closed_ball_hidden"
        else:
            u = smooth01((frame - closed_hold_end) / float(reopen_end - closed_hold_end))
            state = "top_lifting_off_same_ball_revealed"

        top.location = (0.0, 0.0, top_base_z + lift_dist * u)
        top.rotation_euler = (0.0, 0.0, TWIST * u)
        top.keyframe_insert(data_path="location", frame=frame)
        top.keyframe_insert(data_path="rotation_euler", frame=frame)
        top["pb_state"] = state

        # Ball never moves; stays put inside the bottom bowl.
        ball.location = (0.0, 0.0, ball_cz)
        ball.keyframe_insert(data_path="location", frame=frame)
        ball["pb_state"] = "revealed_in_bottom_bowl" if u > 0.5 else "hidden_inside_capsule"
        ball["pb_same_object_throughout"] = True

    scene.frame_set(FRAME_START)


# =============================================================================
# dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "twist_open_capsule":
        return build_twist_open_capsule()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(objs):
    kind = objs["kind"]
    if kind == "twist_open_capsule":
        return animate_twist_open_capsule(objs)
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

    # Input = closed (ball hidden). Event = top lifted off (ball visible).
    # Final = reopened, same ball revealed.
    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, 55, OPTIONAL_FRAME_PATH)
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
