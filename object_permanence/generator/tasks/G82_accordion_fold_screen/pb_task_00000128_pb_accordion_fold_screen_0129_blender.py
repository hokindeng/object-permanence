# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "scene_kind": "accordion_fold_screen",
  "variant": "two_objects",
  "prompt": "Two objects sit on a table. A folded accordion screen at one side unfolds sideways across in front of them until it fully covers them, holds, then folds back up, revealing the same two objects unchanged.",
  "item_id": "PB_ACCORDION_FOLD_SCREEN_0129"
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
    MATS["table"] = make_mat("mat_table", (0.74, 0.62, 0.44), 0.70)
    MATS["screen"] = make_mat("mat_screen", (0.46, 0.48, 0.53), 0.88)
    MATS["screen_alt"] = make_mat("mat_screen_alt", (0.38, 0.40, 0.45), 0.88)
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


def add_sphere(name, radius, location, material, color_name):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=48, ring_count=24)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, "target_object", "static_solid", "sphere", color_name, False, solid=True, pb_radius=radius)
    return obj


def add_cylinder(name, radius, height, location, material, color_name):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=height, location=location, vertices=48)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, "target_object", "static_solid", "cylinder", color_name, False, solid=True,
        pb_radius=radius, pb_height=height)
    return obj


def setup_camera(scene, camera_loc=(0.0, -9.4, 3.4), target=(0.0, 0.0, 1.35)):
    bpy.ops.object.camera_add(location=camera_loc)
    cam = bpy.context.object
    cam.name = "camera_main"
    cam.data.type = "PERSP"
    cam.data.lens = 40
    look_at(cam, target)
    scene.camera = cam
    return cam


def build_base_scene(camera_loc=(0.0, -9.4, 3.4), target=(0.0, 0.0, 1.35)):
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


# ---------------------------------------------------------------------------
# Accordion-fold-screen geometry.
#
# The occluder is a concertina: a chain of N vertical panels joined end-to-end
# at alternating vertical hinges. Each panel is a thin tall cube whose local
# origin sits at its LEFT edge (the hinge that joins it to the previous panel),
# so rotating the panel about its vertical (Z) axis swings its far edge --
# exactly like a folding screen. We parent panel i to an empty placed at the
# outgoing (right) edge of panel i-1; each empty carries the incremental hinge
# angle. Alternating the sign of that angle makes the chain zig-zag (folded) or
# straighten out (unfolded / flat).
#
# Fully folded  -> hinge magnitude ~ near closed (panels stacked at left).
# Fully unfolded-> hinge magnitude ~ 0 (panels form one flat wall across front).
# ---------------------------------------------------------------------------
TABLE_TOP_Z = 0.80          # top surface of the tabletop
TABLE_THICK = 0.18

N_PANELS = 4                # number of accordion panels
PANEL_W = 1.35             # width of each panel (along its local X, hinge-to-hinge)
PANEL_H = 1.80             # panel height (tall enough to fully hide the objects)
PANEL_T = 0.09             # panel thickness (depth toward camera)

SCREEN_Y = -0.85           # depth of the screen: IN FRONT of the objects (toward camera)
OBJECT_Y = 0.30            # objects sit behind the screen line
HINGE_BASE_X = -3.05       # x of the first (anchor) hinge -- screen folded at left

# When folded, adjacent panels are nearly closed (small opening) so the whole
# concertina is bunched at the left. When unfolded, panels are flat (angle 0).
FOLD_ANGLE = math.radians(80.0)   # half-open angle of each hinge when folded


def build_accordion_fold_screen():
    scene = build_base_scene()

    # 1. Table.
    top_center_z = TABLE_TOP_Z - TABLE_THICK / 2.0
    add_cube("table_top", (0.0, 0.15, top_center_z),
             (7.6, 3.4, TABLE_THICK), MATS["table"], "table", "wood")
    for lx, ly, nm in [(-3.4, -1.3, "leg_fl"), (3.4, -1.3, "leg_fr"),
                        (-3.4, 1.5, "leg_bl"), (3.4, 1.5, "leg_br")]:
        add_cube(nm, (lx, ly, (TABLE_TOP_Z - TABLE_THICK) / 2.0),
                 (0.18, 0.18, TABLE_TOP_Z - TABLE_THICK), MATS["table"], "table", "wood")

    # 2. Two distinct STATIC objects resting on the tabletop, side by side.
    #    A red cube and a blue cylinder -- clearly different, never moved.
    cube_dim = (0.66, 0.66, 0.66)
    cube_z = TABLE_TOP_Z + cube_dim[2] / 2.0
    obj_a = add_cube("target_red_cube", (-0.85, OBJECT_Y, cube_z), cube_dim, MATS["red"],
                     "target_object", "red", is_dynamic=False)

    cyl_r = 0.36
    cyl_h = 0.86
    cyl_z = TABLE_TOP_Z + cyl_h / 2.0
    obj_b = add_cylinder("target_blue_cylinder", cyl_r, cyl_h,
                         (0.90, OBJECT_Y, cyl_z), MATS["blue"], "blue")

    # 3. Accordion screen: N independent VERTICAL panels standing on the table,
    #    in front of the objects. Folded => bunched off to the LEFT (concertina,
    #    alternating yaw); unfolded => spread into a gapless WALL across the front
    #    that fully occludes both objects. Positions/yaw keyframed directly
    #    (simple + robust; a parent-chain hinge fold collapses to a flat strip).
    N = 6
    PW = 0.66                        # panel width
    PH = 1.80                        # panel height (taller than the objects)
    PT = 0.07                        # thickness (toward camera)
    pcz = TABLE_TOP_Z + PH / 2.0     # panel center z (bottom sits on the tabletop)
    panels = []
    for i in range(N):
        mat = MATS["screen"] if (i % 2 == 0) else MATS["screen_alt"]
        p = add_cube("accordion_panel_%d" % i, (0.0, SCREEN_Y, pcz), (PW, PT, PH),
                     mat, "occluder_panel", "gray", is_dynamic=True)
        p["pb_panel_index"] = i
        panels.append(p)

    return scene, {
        "kind": "accordion_fold_screen",
        "panels": panels,
        "targets": [obj_a, obj_b],
        "n_panels": N,
        "panel_w": PW,
        "panel_center_z": pcz,
        "obj_a_loc": (-0.85, OBJECT_Y, cube_z),
        "obj_b_loc": (0.90, OBJECT_Y, cyl_z),
    }


def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "accordion_fold_screen":
        return build_accordion_fold_screen()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def _apply_fold(meta, unfold_t):
    """Set every hinge angle for a given unfold amount.

    unfold_t == 0.0 -> fully folded (concertina bunched at left).
    unfold_t == 1.0 -> fully unfolded (flat wall across the front).

    Panel 0's own hinge (hinge_0) is anchored parallel to X (angle 0) so the
    whole screen stays aligned with the front plane. Each subsequent hinge
    alternates sign so the chain zig-zags when folded and straightens when flat.
    Also swing the anchor slightly so the folded stack tucks to the left.
    """
    fold = meta["fold_angle"]
    hinges = meta["hinges"]  # [anchor, hinge_0, hinge_1, ...]
    n = meta["n_panels"]

    # Folded amount is the complement of unfold.
    folded = 1.0 - unfold_t

    # Anchor: when folded, rotate the whole assembly so the zig-zag opens toward
    # +X (to the right / across the front); when unfolded, anchor is at 0.
    anchor = hinges[0]
    anchor.rotation_euler = (0.0, 0.0, folded * (fold * 0.5))

    # hinge_0 (first panel) is the reference; keep it at 0 relative to anchor.
    hinges[1].rotation_euler = (0.0, 0.0, 0.0)

    # Remaining hinges alternate: +fold, -fold, +fold, ... scaled by folded amt.
    for i in range(1, n):
        sign = 1.0 if (i % 2 == 1) else -1.0
        hinges[i + 1].rotation_euler = (0.0, 0.0, sign * fold * folded)


def animate_accordion_fold_screen(scene, meta):
    panels = meta["panels"]
    N = meta["n_panels"]
    PW = meta["panel_w"]
    pcz = meta["panel_center_z"]
    targets = meta["targets"]
    ta, tb = meta["obj_a_loc"], meta["obj_b_loc"]

    span_half = (N * PW) / 2.0                    # half of the unfolded wall width
    def spread_x(i):
        return -span_half + PW / 2.0 + i * PW     # side-by-side, centred on x=0
    fold_x = -(span_half + 0.55)                  # bunched off to the left when folded

    #   1-16   : folded (bunched at left, objects visible)
    #   16-52  : unfold -> gapless wall covering both objects
    #   52-80  : hold (fully covering)
    #   80-114 : fold back up to the left
    #   114-120: folded again (objects revealed unchanged)
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if frame <= 16:
            u = 0.0
        elif frame <= 52:
            u = smooth01((frame - 16) / 36.0)
        elif frame <= 80:
            u = 1.0
        elif frame <= 114:
            u = smooth01(1.0 - (frame - 80) / 34.0)
        else:
            u = 0.0
        s_ = smooth01(u)
        state = "folded" if u <= 0.001 else ("covering" if u >= 0.999 else "unfolding")
        for i, p in enumerate(panels):
            x = lerp(fold_x + i * 0.06, spread_x(i), s_)                    # bunched -> spread
            yaw = lerp((1.0 if i % 2 == 0 else -1.0) * math.radians(72.0), 0.0, s_)
            p.location = (x, SCREEN_Y, pcz)
            p.rotation_euler = (0.0, 0.0, yaw)
            p.keyframe_insert(data_path="location", frame=frame)
            p.keyframe_insert(data_path="rotation_euler", frame=frame)
            p["pb_state"] = state
        # the two objects stay perfectly static
        for o, loc in ((targets[0], ta), (targets[1], tb)):
            o.location = loc
            o.keyframe_insert(data_path="location", frame=frame)


def animate_scene(scene, meta):
    if meta["kind"] == "accordion_fold_screen":
        animate_accordion_fold_screen(scene, meta)
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
