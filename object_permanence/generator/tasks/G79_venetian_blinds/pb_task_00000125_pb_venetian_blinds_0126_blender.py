# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_VENETIAN_BLINDS_0126",
  "scene_kind": "venetian_blinds",
  "prompt": "Two objects sit on a table. In front of them hangs a set of horizontal venetian-blind slats, initially edge-on (open) so the objects are visible between them. The slats all rotate to lie flat and fully occlude the objects, hold, then rotate back to edge-on, revealing the same two objects unchanged."
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
    MATS["slat"] = make_mat("mat_slat", (0.55, 0.57, 0.60), roughness=0.52, metallic=0.15)
    MATS["frame"] = make_mat("mat_frame", (0.30, 0.31, 0.33), roughness=0.66)


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
# 0126 venetian blinds
#
# Object-static-occlusion. Two distinct STATIC objects rest on the table. IN
# FRONT of them (nearer the camera) hangs a set of ~7 horizontal venetian-blind
# slats held in a thin side frame. Each slat is a long thin plate spanning X
# (the long / horizontal axis) that rotates about its OWN long axis (world X).
#
#   * OPEN / edge-on : each slat's broad face is HORIZONTAL (lying in the X-Y
#     plane). From the front camera you see only its thin edge, so wide GAPS
#     open up between successive slats and the two objects are visible between
#     them.
#   * CLOSED / flat  : each slat rotates 90 deg about X so its broad face stands
#     VERTICAL (in the X-Z plane), facing the camera. Adjacent slats then OVERLAP
#     in Z and together fully occlude the two objects.
#
# Hinge construction: every slat's mesh origin sits at its own geometric centre,
# and the plate is symmetric about that centre, so a PURE X rotation spins it in
# place -- no translation, and the slat never clips the table or its neighbours.
# The vertical pitch (centre-to-centre spacing) is smaller than the slat's plate
# width, so at 90 deg the standing plates overlap and leave no gap.
#
# The two objects, the table and the blind frame never move. Only the slats
# rotate, all together, in lock-step.
# =============================================================================

def build_venetian_blinds():
    scene = build_base_scene()

    # Front view, slightly above table height, looking along +Y at the blinds
    # which sit between the camera and the two objects.
    setup_camera(
        scene,
        location=(0.0, -4.05, 1.35),
        target=(0.0, 0.55, 0.70),
        lens=42,
    )

    table_top_z = 0.0  # top surface of the floor slab (floor spans z in [-0.10, 0.0])

    # --- Two distinct STATIC objects on the table --------------------------
    # Placed BEHIND the blinds (larger Y), inside the blinds' occluded footprint
    # when the slats stand vertical. They never move.
    obj_a_r = 0.30
    obj_a = add_sphere(
        "static_object_a_ball",
        obj_a_r,
        (-0.42, 0.78, table_top_z + obj_a_r),
        MATS["orange"],
        "orange",
        role="static_object_a",
    )
    obj_a["pb_static_reference_object"] = True

    obj_b_r = 0.26
    obj_b_h = 0.66
    obj_b = add_cylinder(
        "static_object_b_cylinder",
        obj_b_r,
        obj_b_h,
        (0.46, 0.78, table_top_z + obj_b_h / 2.0),
        MATS["blue"],
        "blue",
        role="static_object_b",
    )
    obj_b["pb_static_reference_object"] = True

    # --- Venetian-blind slats ----------------------------------------------
    # A vertical stack of horizontal slats in front of the objects (smaller Y,
    # nearer the camera). Each slat is a long thin plate:
    #   X = slat_width (long axis, spans wider than the objects),
    #   Y = slat_plate_width (broad-face dimension; becomes VERTICAL cover at 90),
    #   Z = slat_thick (thin).
    # At rotation 0 the broad face lies flat (X-Y plane) -> edge-on / open.
    # At rotation 90 about X the broad face stands vertical -> closed / occlude.
    num_slats = 7
    slat_width = 2.40        # X extent -- wider than the objects' spread
    slat_plate_width = 0.44  # Y extent when open == vertical cover when closed
    slat_thick = 0.05        # thin

    blind_y = 0.06           # plane of the slats, IN FRONT of the objects
    pitch = 0.36             # centre-to-centre vertical spacing (< plate_width => overlap)
    # Stack spans z from bottom_z up; low enough to hide the ball base, high
    # enough (top slat) to cover the top of the taller cylinder object.
    bottom_z = 0.16
    slat_centers_z = [bottom_z + i * pitch for i in range(num_slats)]

    slats = []
    for i, cz in enumerate(slat_centers_z):
        # Origin at the slat's own centre -> pure X rotation spins in place.
        s = add_cube(
            f"blind_slat_{i:02d}",
            (0.0, blind_y, cz),
            (slat_width, slat_plate_width, slat_thick),
            MATS["slat"],
            "blind_slat",
            "steel_gray",
            is_dynamic=True,
            solid=True,
        )
        s["pb_slat_index"] = i
        s["pb_rotates_about_own_long_axis"] = True
        slats.append(s)

    # --- Static side frame holding the blinds (never moves) ----------------
    frame_h = (slat_centers_z[-1] - slat_centers_z[0]) + slat_plate_width + 0.20
    frame_cz = 0.5 * (slat_centers_z[0] + slat_centers_z[-1])
    frame_x = slat_width / 2.0 + 0.06
    frame_post_thick = 0.08
    for sx, tagname in ((-frame_x, "left"), (frame_x, "right")):
        post = add_cube(
            f"blind_frame_post_{tagname}",
            (sx, blind_y, frame_cz),
            (frame_post_thick, slat_plate_width + 0.06, frame_h),
            MATS["frame"],
            "blind_frame",
            "dark_gray",
            is_dynamic=False,
            solid=True,
        )
        post["pb_static_reference_object"] = True
    # Top rail across the frame.
    top_rail = add_cube(
        "blind_frame_top_rail",
        (0.0, blind_y, frame_cz + frame_h / 2.0),
        (slat_width + 2.0 * frame_post_thick + 0.04, slat_plate_width + 0.06, 0.10),
        MATS["frame"],
        "blind_frame",
        "dark_gray",
        is_dynamic=False,
        solid=True,
    )
    top_rail["pb_static_reference_object"] = True

    return {
        "scene": scene,
        "kind": "venetian_blinds",
        "slats": slats,
        "slat_centers_z": slat_centers_z,
        "blind_y": blind_y,
        "obj_a": obj_a,
        "obj_b": obj_b,
        "obj_a_r": obj_a_r,
        "obj_b_r": obj_b_r,
        "obj_b_h": obj_b_h,
        "table_top_z": table_top_z,
    }


def animate_venetian_blinds(objs):
    scene = objs["scene"]
    slats = objs["slats"]
    slat_centers_z = objs["slat_centers_z"]
    blind_y = objs["blind_y"]
    obj_a = objs["obj_a"]
    obj_b = objs["obj_b"]
    obj_a_r = objs["obj_a_r"]
    obj_b_h = objs["obj_b_h"]
    table_top_z = objs["table_top_z"]

    obj_a_loc = (-0.42, 0.78, table_top_z + obj_a_r)
    obj_b_loc = (0.46, 0.78, table_top_z + obj_b_h / 2.0)

    # HIDE -> REVEAL object-permanence cycle. theta=0 is the OPEN / edge-on pose
    # (slat broad faces horizontal, objects visible through the gaps).
    # theta=closed_angle (90 deg) is the CLOSED pose (slat broad faces vertical,
    # overlapping, fully occluding both objects). Each slat origin is at its own
    # centre, so a pure X rotation spins it in place with no translation and no
    # clipping.
    #
    #   Phase 1  f1   - f22  : OPEN, objects clearly visible between slats (hold).
    #   Phase 2  f22  - f48  : all slats rotate together to CLOSED (occlude).
    #   Phase 3  f48  - f74  : hold CLOSED (both objects fully hidden).
    #   Phase 4  f74  - f112 : all slats rotate back to OPEN, revealing objects.
    #   Phase 5  f112 - f120 : hold OPEN, both objects revealed unchanged.
    closed_angle = math.radians(90.0)
    p1_end = 22       # end of initial open hold
    close_end = 48    # slats fully closed
    close_hold_end = 74  # end of closed hold
    open_end = 112    # slats fully back open

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= p1_end:
            theta = 0.0
            slat_state = "open_edge_on_objects_visible_between_slats"
            occ_state = "both_objects_visible_before_occlusion"
        elif frame <= close_end:
            t = (frame - p1_end) / float(close_end - p1_end)
            theta = lerp(0.0, closed_angle, smooth01(t))
            slat_state = "rotating_closed"
            occ_state = "objects_being_occluded_as_slats_close"
        elif frame <= close_hold_end:
            theta = closed_angle
            slat_state = "closed_flat_objects_fully_hidden"
            occ_state = "both_objects_hidden_behind_closed_blinds"
        elif frame <= open_end:
            t = (frame - close_hold_end) / float(open_end - close_hold_end)
            theta = lerp(closed_angle, 0.0, smooth01(t))
            slat_state = "rotating_back_open"
            occ_state = "objects_being_revealed_as_slats_open"
        else:
            theta = 0.0
            slat_state = "open_edge_on_same_objects_revealed_unchanged"
            occ_state = "both_objects_revealed_unchanged_in_number_and_position"

        # All slats rotate together about their own long (X) axis, in place.
        for i, s in enumerate(slats):
            s.location = (0.0, blind_y, slat_centers_z[i])
            s.rotation_euler = (theta, 0.0, 0.0)
            s.keyframe_insert(data_path="location", frame=frame)
            s.keyframe_insert(data_path="rotation_euler", frame=frame)
            s["pb_state"] = slat_state

        # The two objects and the table never move.
        obj_a.location = obj_a_loc
        obj_a.keyframe_insert(data_path="location", frame=frame)
        obj_a["pb_state"] = occ_state
        obj_a["pb_same_object_throughout"] = True

        obj_b.location = obj_b_loc
        obj_b.keyframe_insert(data_path="location", frame=frame)
        obj_b["pb_state"] = occ_state
        obj_b["pb_same_object_throughout"] = True

    scene.frame_set(FRAME_START)


# =============================================================================
# dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "venetian_blinds":
        return build_venetian_blinds()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(objs):
    kind = objs["kind"]
    if kind == "venetian_blinds":
        return animate_venetian_blinds(objs)
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

    # Input = open blinds, both objects clearly visible. Event = closed blinds
    # (objects hidden). Final = blinds back open, same objects revealed.
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
