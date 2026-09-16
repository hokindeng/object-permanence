# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_WIPER_SCREEN_OCCLUSION_0168",
  "scene_kind": "wiper_screen_occlusion",
  "prompt": "A single object stands on a table. A tall vertical screen, hinged at its base on one side, sweeps horizontally across in front of the object like a windshield wiper -- fully covering the object at the middle of its sweep, then continuing on and uncovering it. The screen ends clear of the object, which is unchanged and in the same place."
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


def add_sphere(name, radius, location, material, color_name, role="target", is_dynamic=False):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "sphere", color_name, is_dynamic, solid=True, pb_radius=radius)
    return obj


def add_cylinder(name, radius, depth, location, material, color_name, role="target", is_dynamic=False):
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "cylinder", color_name, is_dynamic, solid=True, pb_radius=radius)
    return obj


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), roughness=0.84)
    MATS["gray"] = make_mat("mat_gray", (0.46, 0.46, 0.46), roughness=0.64)
    MATS["dark"] = make_mat("mat_dark", (0.18, 0.19, 0.21), roughness=0.76)
    MATS["light"] = make_mat("mat_light", (0.68, 0.69, 0.71), roughness=0.68)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.38, 0.06), roughness=0.28)
    MATS["blue"] = make_mat("mat_blue", (0.12, 0.34, 0.86), roughness=0.34)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.92)
    MATS["screen"] = make_mat("mat_screen", (0.40, 0.41, 0.43), roughness=0.70)


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
# 0168 wiper_screen_occlusion  (Cluster: Baillargeonian Occlusion)
#
# A single STATIC object (a vivid ball) stands on the table. A tall, thin,
# VERTICAL rectangular SCREEN is hinged along a vertical edge at its base on one
# side of the object. The screen pivots about that vertical hinge (rotation about
# the world Z axis) and sweeps HORIZONTALLY across IN FRONT of the object -- like
# a single windshield-wiper blade. As it sweeps through the middle of its arc it
# lies flat-on to the camera directly between the camera and the object, fully
# covering it; it then continues on to the far side and uncovers the object.
#
# Hinge construction: the screen slab's mesh origin is moved to its NEAR vertical
# edge (local x = 0, local z = 0) so that rotating it about world Z pivots exactly
# at that edge -- no translation, bottom stays on the floor. The slab extends in
# local +X (radially) and is tall in +Z. When its radial direction lies along the
# world X axis (sweep angle phi = 0) the slab lies across the front of the object,
# broad face toward the camera, and occludes it. At the sweep extremes the slab is
# rotated ~50 deg to either side, its far end swings clear, and the object is
# fully visible. Only the screen moves; the object and table never move.
#
# Clearance geometry (screen never touches the ball): the hinge is placed well
# IN FRONT of the ball, toward the camera (pivot y = -1.7 vs ball y = 0.45), so
# the swept slab plane is offset from the ball's plane along the camera axis.
# Ball centre sits 2.869 from the pivot at bearing 48.5 deg; the slab reach is
# only 2.2, so even at the sweep angle that points straight at the ball the slab
# far edge stays 0.669 from the ball centre -> 0.319 clearance to the ball
# surface (minimum over the whole 120-frame sweep). At phi = 0 the slab spans
# x in [-1.9, 0.3] on the plane y = -1.7; the ball's projected silhouette from
# the camera on that plane is only x in [-0.19, 0.19], z in [0.63, 1.02], so the
# 2.2 x 1.5 slab still fully hides the ball at mid-sweep.
# =============================================================================

# --- geometry -----------------------------------------------------------------
TABLE_TOP_Z = 0.0            # top surface of the floor slab

OBJ_RADIUS = 0.35
OBJ_X = 0.0
OBJ_Y = 0.45
OBJ_Z = TABLE_TOP_Z + OBJ_RADIUS

SCREEN_PIVOT_X = -1.9        # hinge sits off to one side, in front of the object
SCREEN_PIVOT_Y = -1.7        # WELL in front of the object, toward the camera, so the
                             # swept slab clears the ball at every sweep angle
SCREEN_LENGTH = 2.2          # radial reach (local +X); covers the ball's projected
                             # silhouette at phi=0 yet never reaches the ball itself
                             # (ball centre is 2.869 from the pivot: 0.319 clearance)
SCREEN_HEIGHT = 1.5          # tall enough to fully cover the ball's projection
SCREEN_THICK = 0.06

PHI_SIDE = math.radians(50.0)   # sweep half-angle (~100 deg total sweep)


def build_wiper_screen_occlusion():
    scene = build_base_scene()

    setup_camera(
        scene,
        location=(0.0, -4.05, 1.35),
        target=(0.0, 0.55, 0.55),
        lens=42,
    )

    # --- the single STATIC target object (vivid) ---------------------------
    obj = add_sphere(
        "shown_object_ball",
        OBJ_RADIUS,
        (OBJ_X, OBJ_Y, OBJ_Z),
        MATS["orange"],
        "orange",
        role="shown_object",
        is_dynamic=True,
    )
    obj["pb_static_reference_object"] = True

    # --- hinged vertical wiper screen (apparatus, gray) --------------------
    # Build a slab, then shift its mesh so the ORIGIN is at the NEAR vertical
    # edge (local x=0) and the slab extends toward local +X, resting on the
    # floor (local z in [0, height]). A pure Z rotation about the origin then
    # sweeps it horizontally with the bottom edge staying on the floor.
    bpy.ops.mesh.primitive_cube_add(size=1, location=(SCREEN_PIVOT_X, SCREEN_PIVOT_Y, TABLE_TOP_Z))
    screen = bpy.context.object
    screen.name = "wiper_screen"
    screen.dimensions = (SCREEN_LENGTH, SCREEN_THICK, SCREEN_HEIGHT)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    mesh = screen.data
    for v in mesh.vertices:
        v.co.x += SCREEN_LENGTH / 2.0    # extend from the hinge toward local +X
        v.co.z += SCREEN_HEIGHT / 2.0    # bottom edge sits on the floor
    mesh.update()

    screen.data.materials.append(MATS["screen"])
    tag(screen, "wiper_screen", "wiper_screen", "dynamic_object", "cube", "gray", True, solid=True)
    screen["pb_hinge_at_base_vertical_edge"] = True
    screen["pb_sweeps_horizontally"] = True

    return {
        "scene": scene,
        "kind": "wiper_screen_occlusion",
        "screen": screen,
        "obj": obj,
        "obj_loc": (OBJ_X, OBJ_Y, OBJ_Z),
    }


def animate_wiper_screen_occlusion(objs):
    scene = objs["scene"]
    screen = objs["screen"]
    obj = objs["obj"]
    obj_loc = objs["obj_loc"]

    # phi = 0 : screen flat across the front of the object -> COVERED.
    # phi = +PHI_SIDE (start) and -PHI_SIDE (end) : screen swung to a side -> CLEAR.
    #
    #   f1   - f10  : hold at +PHI_SIDE (object clear on one side)
    #   f10  - f55  : sweep +PHI_SIDE -> 0 (covering the object)
    #   f55  - f65  : hold at 0 (object fully covered mid-sweep)
    #   f65  - f110 : sweep 0 -> -PHI_SIDE (uncovering the object)
    #   f110 - f120 : hold at -PHI_SIDE (object clear on the other side)
    p1_end = 10
    cover_start = 55
    cover_end = 65
    p4_end = 110

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= p1_end:
            phi = PHI_SIDE
            st = "screen_clear_object_visible_before_sweep"
        elif frame <= cover_start:
            t = (frame - p1_end) / float(cover_start - p1_end)
            phi = lerp(PHI_SIDE, 0.0, smooth01(t))
            st = "screen_sweeping_in_covering_object"
        elif frame <= cover_end:
            phi = 0.0
            st = "screen_flat_across_front_object_fully_covered"
        elif frame <= p4_end:
            t = (frame - cover_end) / float(p4_end - cover_end)
            phi = lerp(0.0, -PHI_SIDE, smooth01(t))
            st = "screen_sweeping_on_uncovering_object"
        else:
            phi = -PHI_SIDE
            st = "screen_clear_object_revealed_unchanged"

        screen.rotation_euler = (0.0, 0.0, phi)
        screen.keyframe_insert(data_path="rotation_euler", frame=frame)
        screen["pb_state"] = st
        screen["pb_sweep_angle_deg"] = float(math.degrees(phi))

        obj.location = obj_loc
        obj.keyframe_insert(data_path="location", frame=frame)
        obj["pb_state"] = st
        obj["pb_same_object_throughout"] = True

    scene.frame_set(FRAME_START)


# =============================================================================
# dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "wiper_screen_occlusion":
        return build_wiper_screen_occlusion()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(objs):
    kind = objs["kind"]
    if kind == "wiper_screen_occlusion":
        return animate_wiper_screen_occlusion(objs)
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

    # Input = screen clear (object visible). Event = screen covering (object
    # hidden mid-sweep). Final = screen swung to far side, same object revealed.
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
