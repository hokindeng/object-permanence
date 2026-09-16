# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_HINGED_LID_BOX_OPENS_0106",
  "scene_kind": "hinged_lid_box_opens",
  "prompt": "An open gray box sits on a table with a single orange ball clearly visible resting inside it. The top lid, hinged at the back edge, rotates downward and closes over the ball, fully hiding it from view, and stays closed for a moment. The lid then rotates back upward and reopens, revealing the same orange ball still resting in the same place inside the box. The box body and the ball never move; the ball is the same object throughout, demonstrating that it persisted while hidden."
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
    MATS["lid"] = make_mat("mat_opaque_lid", (0.40, 0.41, 0.43), roughness=0.70)


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
# 0106 hinged lid box opens
#
# An open gray box sits on the table with a colored ball resting inside. The top
# lid is hinged at the BACK top edge of the box: it rotates DOWN about that edge
# to close over the ball, holds, then rotates back UP to reveal the same ball.
# The box body never moves.
#
# Hinge construction: the lid is a thin slab whose mesh origin is moved to its
# BACK edge so that rotating it about the world X axis pivots exactly at the
# back-top edge of the box (no translation, no clipping through the back wall).
# =============================================================================

def build_hinged_lid_box_opens():
    scene = build_base_scene()

    # Positioned in front and well above so the camera looks down INTO the open
    # cavity: the object resting inside is clearly visible while the lid is open,
    # and the closed lid clearly hides it.
    setup_camera(
        scene,
        location=(0.0, -3.55, 3.55),
        target=(0.0, 0.10, 0.45),
        lens=40,
    )

    base_z = 0.10

    # Inner cavity spans roughly x in [-0.60, 0.60], y in [-0.60, 0.60].
    # Walls are 0.10 thick, 0.72 tall.
    wall_h = 0.72
    wall_t = 0.10
    inner_half = 0.60          # inner half-width / half-depth
    outer_half = inner_half + wall_t / 2.0  # 0.65 -> wall centerline
    wall_cz = base_z + 0.05 + wall_h / 2.0

    floor_top_z = base_z + 0.10  # top surface of the box inner floor

    # Box inner floor (a solid slab the object rests on)
    add_cube("box_inner_floor", (0.0, 0.0, base_z + 0.05),
             (2.0 * outer_half + wall_t, 2.0 * outer_half + wall_t, 0.10),
             MATS["gray"], "box_floor", "gray")

    add_cube("box_left_wall", (-outer_half, 0.0, wall_cz),
             (wall_t, 2.0 * outer_half + wall_t, wall_h), MATS["gray"], "box_wall", "gray")
    add_cube("box_right_wall", (outer_half, 0.0, wall_cz),
             (wall_t, 2.0 * outer_half + wall_t, wall_h), MATS["gray"], "box_wall", "gray")
    add_cube("box_front_wall", (0.0, -outer_half, wall_cz),
             (2.0 * outer_half + wall_t, wall_t, wall_h), MATS["gray"], "box_wall", "gray")
    add_cube("box_back_wall", (0.0, outer_half, wall_cz),
             (2.0 * outer_half + wall_t, wall_t, wall_h), MATS["gray"], "box_wall", "gray")

    # --- Hinged lid ---------------------------------------------------------
    # The lid slab covers the full box top. Its back edge sits at the back wall
    # outer edge (y = outer_half + wall_t/2 = 0.70). The hinge pivot is the
    # back-top edge: y = hinge_y, z = hinge_z.
    lid_top_z = base_z + 0.05 + wall_h            # top of the walls
    lid_thick = 0.08
    lid_span_x = 2.0 * outer_half + wall_t        # full top width incl. walls
    lid_depth = 2.0 * outer_half + wall_t         # full top depth incl. walls

    hinge_y = outer_half + wall_t / 2.0           # 0.70, outer back edge
    hinge_z = lid_top_z + lid_thick / 2.0         # center height of resting lid

    # Build lid as a cube, then shift its mesh so the OBJECT ORIGIN is at the
    # back edge of the slab. We create the slab centered, then move its vertices
    # forward (in -Y) by half the depth so the origin lands at the back edge.
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.0, hinge_y, hinge_z))
    lid = bpy.context.object
    lid.name = "hinged_top_lid"
    lid.dimensions = (lid_span_x, lid_depth, lid_thick)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    # Shift mesh verts so geometry extends in -Y from the origin (origin at back edge).
    mesh = lid.data
    for v in mesh.vertices:
        v.co.y -= lid_depth / 2.0
    mesh.update()
    lid.data.materials.append(MATS["lid"])
    tag(lid, "hinged_top_lid", "hinged_lid", "dynamic_object", "cube", "dark_gray", True, solid=True)
    lid["pb_hinge_at_back_edge"] = True

    # --- Object inside (clearly visible while the lid is open) ---------------
    # A single clearly-colored ball, sized so it plainly fills the cavity and is
    # obvious to the viewer both before it is hidden and after it is revealed.
    # It rests on the inner floor and never moves. This is the ONE persistent
    # object the permanence demonstration is about (no other movable items, so
    # the "same object throughout" reading is unambiguous).
    ball_r = 0.28
    ball = add_sphere(
        "colored_ball_inside_box",
        ball_r,
        (0.0, 0.0, floor_top_z + ball_r),
        MATS["orange"],
        "orange",
    )
    ball["pb_visible_when_lid_open"] = True
    ball["pb_resting_inside_box"] = True

    return {
        "scene": scene,
        "kind": "hinged_lid_box_opens",
        "lid": lid,
        "ball": ball,
        "base_z": base_z,
        "ball_r": ball_r,
        "floor_top_z": floor_top_z,
        "hinge_z": hinge_z,
    }


def animate_hinged_lid_box_opens(objs):
    scene = objs["scene"]
    lid = objs["lid"]
    ball = objs["ball"]
    floor_top_z = objs["floor_top_z"]
    ball_r = objs["ball_r"]

    # Full HIDE -> REVEAL object-permanence cycle. theta=open_angle is the lid
    # fully OPEN (front edge lifted up and back over the back wall); theta=0 is
    # the lid CLOSED (flat over the box, hiding the object). The lid origin was
    # moved to its back-top edge, so a pure X rotation pivots there with no
    # translation and never clips through the back wall.
    #
    #   Phase 1  f1  - f22   : OPEN, object clearly visible inside (hold).
    #   Phase 2  f22 - f48   : lid rotates DOWN/CLOSED over the object (hides it).
    #   Phase 3  f48 - f74   : hold fully CLOSED (object hidden).
    #   Phase 4  f74 - f112  : lid rotates UP/OPEN again, revealing SAME object.
    #   Phase 5  f112 - f120 : hold OPEN, object revealed still inside.
    open_angle = math.radians(-105.0)
    p1_end = 22     # end of initial open hold
    close_end = 48  # lid fully closed
    closed_hold_end = 74  # end of closed hold
    reopen_end = 112  # lid fully reopened

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= p1_end:
            theta = open_angle
            lid_state = "open_object_visible_inside"
            ball_state = "visible_inside_open_box_before_hiding"
        elif frame <= close_end:
            t = (frame - p1_end) / float(close_end - p1_end)
            theta = lerp(open_angle, 0.0, smooth01(t))
            lid_state = "hinged_lid_rotating_closed_over_object"
            ball_state = "being_hidden_as_lid_closes"
        elif frame <= closed_hold_end:
            theta = 0.0
            lid_state = "closed_object_hidden_inside"
            ball_state = "hidden_inside_closed_box"
        elif frame <= reopen_end:
            t = (frame - closed_hold_end) / float(reopen_end - closed_hold_end)
            theta = lerp(0.0, open_angle, smooth01(t))
            lid_state = "hinged_lid_rotating_open_about_back_edge"
            ball_state = "being_revealed_as_lid_reopens"
        else:
            theta = open_angle
            lid_state = "open_same_object_revealed_still_inside"
            ball_state = "revealed_resting_inside_open_box"

        # Rotate about back-edge origin: pure X rotation, no translation.
        lid.rotation_euler = (theta, 0.0, 0.0)
        lid.keyframe_insert(data_path="rotation_euler", frame=frame)
        lid["pb_state"] = lid_state

        # The box body and the object never move.
        ball.location = (0.0, 0.0, floor_top_z + ball_r)
        ball.keyframe_insert(data_path="location", frame=frame)
        ball["pb_state"] = ball_state
        ball["pb_must_remain_inside_box"] = True
        ball["pb_same_object_throughout"] = True

    scene.frame_set(FRAME_START)


# =============================================================================
# dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "hinged_lid_box_opens":
        return build_hinged_lid_box_opens()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(objs):
    kind = objs["kind"]
    if kind == "hinged_lid_box_opens":
        return animate_hinged_lid_box_opens(objs)
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

    # Input = open box, object clearly visible. Event = fully closed (object
    # hidden). Final = reopened, same object revealed still inside.
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
