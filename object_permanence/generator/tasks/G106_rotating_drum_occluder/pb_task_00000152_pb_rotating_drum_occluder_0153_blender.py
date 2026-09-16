# -*- coding: utf-8 -*-
import bpy
import bmesh
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "scene_kind": "rotating_drum_occluder",
  "variant": "two_objects",
  "prompt": "Two distinct objects — a red cube and a blue sphere — rest on a small round base and never move. A tall hollow drum with an open window cut into its side stands around them: at first the window faces the camera and both objects are clearly visible inside. The drum then rotates about its vertical axis until its solid wall faces the camera, fully hiding both objects; it holds, then rotates back so the window faces the camera again, revealing the same two objects unchanged in number, color, and position.",
  "item_id": "PB_ROTATING_DRUM_OCCLUDER_0153"
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


def smooth01(t):
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


def lerp(a, b, t):
    return a + (b - a) * t


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


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def make_mat(name, color, roughness=0.55):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (color[0], color[1], color[2], 1.0)
    try:
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = roughness
    except Exception:
        pass
    return mat


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), 0.85)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), 0.92)
    MATS["base"] = make_mat("mat_base", (0.70, 0.58, 0.40), 0.72)
    MATS["drum"] = make_mat("mat_drum", (0.55, 0.55, 0.60), 0.65)   # solid opaque drum wall
    MATS["red"] = make_mat("mat_red", (0.92, 0.18, 0.18), 0.28)
    MATS["blue"] = make_mat("mat_blue", (0.16, 0.36, 0.95), 0.28)
    MATS["yellow"] = make_mat("mat_yellow", (0.98, 0.78, 0.15), 0.28)
    MATS["green"] = make_mat("mat_green", (0.18, 0.68, 0.30), 0.28)


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
    obj["pb_component_first_design"] = True
    for k, v in extras.items():
        obj[k] = v


def add_cube(name, location, dimensions, material, role, color_name, is_dynamic=False, solid=True):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "cube", color_name, is_dynamic, solid=solid)
    return obj


def add_sphere(name, radius, location, material, role, color_name, is_dynamic=False):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=48, ring_count=24)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "sphere", color_name, is_dynamic, solid=True, pb_radius=radius)
    return obj


def add_cylinder(name, radius, height, location, material, role, color_name, is_dynamic=False, verts=72):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=height, location=location, vertices=verts)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "cylinder", color_name, is_dynamic, solid=True, pb_radius=radius)
    return obj


def build_drum_shell(name, inner_r, thick, z_bottom, z_top, center_deg, span_deg,
                     material, role, color_name, segments=96):
    # A hollow vertical DRUM built as a PARTIAL cylindrical shell: an arc of the
    # ring (spanning `span_deg`, centered on `center_deg`) extruded in Z and given
    # a small radial thickness, so it is a solid opaque wall with a WINDOW gap
    # (the 360 - span_deg complement of the arc). The mesh is centered on the
    # world Z axis at the origin, so keyframing the object's Z-rotation spins the
    # window/solid alternation around the objects standing inside.
    outer_r = inner_r + thick
    a_start = math.radians(center_deg - span_deg / 2.0)
    a_end = math.radians(center_deg + span_deg / 2.0)
    n = int(segments)

    bm = bmesh.new()
    rings = []  # per cross-section: (inner_bottom, outer_bottom, outer_top, inner_top)
    for i in range(n + 1):
        a = a_start + (a_end - a_start) * (i / float(n))
        ca, sa = math.cos(a), math.sin(a)
        ib = bm.verts.new((inner_r * ca, inner_r * sa, z_bottom))
        ob = bm.verts.new((outer_r * ca, outer_r * sa, z_bottom))
        ot = bm.verts.new((outer_r * ca, outer_r * sa, z_top))
        it = bm.verts.new((inner_r * ca, inner_r * sa, z_top))
        rings.append((ib, ob, ot, it))

    for i in range(n):
        ib0, ob0, ot0, it0 = rings[i]
        ib1, ob1, ot1, it1 = rings[i + 1]
        bm.faces.new((ob0, ob1, ot1, ot0))   # outer wall
        bm.faces.new((ib1, ib0, it0, it1))   # inner wall
        bm.faces.new((it0, it1, ot1, ot0))   # top rim
        bm.faces.new((ib0, ib1, ob1, ob0))   # bottom rim

    # Solid end caps at the two window edges.
    ib0, ob0, ot0, it0 = rings[0]
    bm.faces.new((ib0, ob0, ot0, it0))
    ibn, obn, otn, itn = rings[n]
    bm.faces.new((itn, otn, obn, ibn))

    bm.normal_update()
    mesh = bpy.data.meshes.new(name + "_mesh")
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = (0.0, 0.0, 0.0)
    obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object", "drum_shell", color_name, True, solid=True,
        pb_inner_radius=inner_r, pb_outer_radius=outer_r,
        pb_window_deg=(360.0 - span_deg), pb_wall_span_deg=span_deg)
    return obj


def setup_camera(scene, camera_loc=(0.0, -8.5, 2.8), target=(0.0, 0.0, 0.75)):
    bpy.ops.object.camera_add(location=camera_loc)
    cam = bpy.context.object
    cam.name = "camera_main"
    cam.data.type = "PERSP"
    cam.data.lens = 42
    look_at(cam, target)
    scene.camera = cam
    return cam


def build_base_scene(camera_loc=(0.0, -8.5, 2.8), target=(0.0, 0.0, 0.75)):
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    # Floor / room.
    add_cube("large_floor_base", (0.0, 0.0, -0.05), (16.0, 8.5, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.55, 1.95), (16.0, 0.08, 3.90), MATS["backdrop"], "background", "off_white")

    # Lights.
    bpy.ops.object.light_add(type="AREA", location=(-3.0, -4.5, 6.2))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 1000
    key.data.size = 5.5

    bpy.ops.object.light_add(type="POINT", location=(3.4, -1.4, 3.6))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 140

    setup_camera(scene, camera_loc=camera_loc, target=target)
    return scene


# Geometry constants for the round base, the two static objects, and the drum.
BASE_TOP_Z = 0.20           # top surface of the small round base
BASE_HEIGHT = 0.20
BASE_RADIUS = 1.85          # base is wider than the drum so the drum rests on it
DRUM_INNER_R = 1.50         # inner radius: comfortably encloses both objects
DRUM_THICK = 0.14           # radial wall thickness (outer radius 1.64)
DRUM_HEIGHT = 1.30          # wall height; top at BASE_TOP_Z + 1.30 = 1.50
DRUM_WALL_SPAN_DEG = 250.0  # solid arc spans 250 deg -> 110 deg window gap
DRUM_WINDOW_CENTER_START = -90.0  # window faces the camera (-Y) at frame 1


def build_rotating_drum_occluder():
    scene = build_base_scene()

    # 1. Small round base at the origin. Objects rest on its top; the drum
    #    stands on it too. Base radius > drum outer radius.
    add_cylinder("round_base", BASE_RADIUS, BASE_HEIGHT,
                 (0.0, 0.0, BASE_TOP_Z - BASE_HEIGHT / 2.0),
                 MATS["base"], "base", "wood")

    # 2. Two distinct STATIC objects resting on the base, side by side. They
    #    NEVER move. Placed at +/-X near the middle so both sit well inside the
    #    drum with clearance, and both are visible through the front window.
    cube_dim = (0.62, 0.62, 0.62)
    cube_z = BASE_TOP_Z + cube_dim[2] / 2.0
    add_cube("red_cube_target", (-0.55, 0.0, cube_z), cube_dim, MATS["red"],
             "target_object", "red", is_dynamic=False)

    sph_r = 0.34
    sph_z = BASE_TOP_Z + sph_r
    add_sphere("blue_sphere_target", sph_r, (0.55, 0.0, sph_z), MATS["blue"],
               "target_object", "blue", is_dynamic=False)

    # 3. The hollow rotating DRUM (partial cylindrical shell) around them. At
    #    frame 1 the WINDOW is centered on -Y (the camera direction), so the
    #    solid wall is centered on +Y (away from the camera). The wall is tall
    #    (z 0.20 -> 1.50, far above the ~0.88 object tops) and its 250 deg arc
    #    fully covers the front hemisphere when it faces the camera.
    solid_center_deg = DRUM_WINDOW_CENTER_START + 180.0   # solid opposite the window (+Y)
    drum = build_drum_shell(
        "rotating_drum_occluder", DRUM_INNER_R, DRUM_THICK,
        BASE_TOP_Z, BASE_TOP_Z + DRUM_HEIGHT,
        solid_center_deg, DRUM_WALL_SPAN_DEG,
        MATS["drum"], "occluder", "steel_gray",
    )
    drum["pb_motion"] = "drum_rotates_to_hide_then_rotates_back_to_reveal"
    drum["pb_rotates_about_vertical_axis"] = True
    drum["pb_encloses_targets_with_clearance"] = True

    return scene, {
        "kind": "rotating_drum_occluder",
        "drum": drum,
        # rotation applied so the solid wall swings to face the camera and back.
        "hide_angle_rad": math.radians(180.0),
    }


def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "rotating_drum_occluder":
        return build_rotating_drum_occluder()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_rotating_drum_occluder(scene, meta):
    drum = meta["drum"]
    hide_angle = meta["hide_angle_rad"]

    # open01: 1.0 = WINDOW facing the camera (both objects visible), 0.0 = SOLID
    # wall facing the camera (both objects hidden). The objects are static and
    # only the drum's Z-rotation changes.
    #   1-20   : window faces camera (objects visible)
    #   20-55  : drum rotates so the solid wall swings around to hide them
    #   55-80  : hold hidden (solid wall faces the camera)
    #   80-115 : drum rotates back so the window returns to the camera
    #   115-120: window faces camera again (same objects revealed)
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 20:
            open01 = 1.0
            st = "window_faces_camera_objects_visible"
        elif frame <= 55:
            open01 = 1.0 - smooth01((frame - 20) / 35.0)
            st = "drum_rotating_solid_toward_camera"
        elif frame <= 80:
            open01 = 0.0
            st = "solid_wall_faces_camera_objects_hidden"
        elif frame <= 115:
            open01 = smooth01((frame - 80) / 35.0)
            st = "drum_rotating_window_back_to_camera"
        else:
            open01 = 1.0
            st = "window_faces_camera_same_objects_revealed"

        ang = lerp(hide_angle, 0.0, open01)
        drum.rotation_euler = (0.0, 0.0, ang)
        drum.keyframe_insert(data_path="rotation_euler", frame=frame)
        drum["pb_state"] = st


def animate_scene(scene, meta):
    if meta["kind"] == "rotating_drum_occluder":
        animate_rotating_drum_occluder(scene, meta)
    else:
        raise RuntimeError("Unknown animation kind: " + str(meta["kind"]))
    scene.frame_set(FRAME_START)


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


def main():
    ensure_dirs()
    clear_scene()

    scene, meta = build_scene_by_kind()
    animate_scene(scene, meta)

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
    render_png(scene, 67, OPTIONAL_FRAME_PATH)
    render_png(scene, 120, OPTIONAL_FRAME_02B_PATH)
    render_animation(scene)
    write_task_json(task)
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("scene_kind:", CASE["scene_kind"], "variant:", CASE["variant"])
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
