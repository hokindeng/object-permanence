# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "scene_kind": "bifold_concertina_doors",
  "variant": "two_objects",
  "prompt": "Two objects sit on a table. A pair of bi-fold doors, hinged in the middle, unfold from the left and right until they meet and fully cover the objects, hold, then fold back open — revealing the same two objects, unchanged.",
  "item_id": "PB_BIFOLD_CONCERTINA_DOORS_0151"
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
    MATS["backboard"] = make_mat("mat_backboard", (0.88, 0.90, 0.93), 0.90)
    MATS["table"] = make_mat("mat_table", (0.74, 0.62, 0.44), 0.70)
    MATS["disc"] = make_mat("mat_disc", (0.24, 0.26, 0.30), 0.80)
    MATS["panel_a"] = make_mat("mat_panel_a", (0.30, 0.34, 0.42), 0.70)
    MATS["panel_b"] = make_mat("mat_panel_b", (0.38, 0.42, 0.50), 0.70)
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


def add_hinge_panel(name, hinge_loc, panel_w, panel_h, panel_t, material, color_name):
    # A door panel that pivots about a VERTICAL hinge EDGE. We create an empty at
    # the hinge location and a panel mesh whose near edge sits at the empty, then
    # parent the panel to the empty so rotating the empty about Z swings the
    # panel about its hinge edge. The panel extends in +local-x from the hinge.
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=hinge_loc)
    hinge = bpy.context.object
    hinge.name = name + "_hinge"

    # Panel mesh centered so its hinge edge is at local x=0 (extends to +x).
    bpy.ops.mesh.primitive_cube_add(size=1, location=(hinge_loc[0] + panel_w / 2.0, hinge_loc[1], hinge_loc[2]))
    panel = bpy.context.object
    panel.name = name
    panel.dimensions = (panel_w, panel_t, panel_h)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    panel.data.materials.append(material)
    tag(panel, name, "bifold_panel", "static_solid", "cube", color_name, True, solid=True)

    panel.parent = hinge
    panel.matrix_parent_inverse = hinge.matrix_world.inverted()
    return hinge, panel


def setup_camera(scene, camera_loc=(0.0, -9.0, 1.9), target=(0.0, 0.0, 1.35)):
    bpy.ops.object.camera_add(location=camera_loc)
    cam = bpy.context.object
    cam.name = "camera_main"
    cam.data.type = "PERSP"
    cam.data.lens = 42
    look_at(cam, target)
    scene.camera = cam
    return cam


def build_base_scene(camera_loc=(0.0, -9.0, 1.9), target=(0.0, 0.0, 1.35)):
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (16.0, 8.5, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.55, 1.95), (16.0, 0.08, 3.90), MATS["backdrop"], "background", "off_white")

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


TABLE_TOP_Z = 0.80
TABLE_THICK = 0.18
OBJ_Y = 0.55
BACKBOARD_Y = 1.20
DOOR_Y = -0.55            # door plane sits IN FRONT of the objects (camera side)


def build_bifold_concertina_doors():
    scene = build_base_scene()

    # 1. Table.
    top_center_z = TABLE_TOP_Z - TABLE_THICK / 2.0
    add_cube("table_top", (0.0, 0.35, top_center_z),
             (6.4, 4.0, TABLE_THICK), MATS["table"], "table", "wood")
    for lx, ly, nm in [(-2.9, -1.4, "leg_fl"), (2.9, -1.4, "leg_fr"),
                        (-2.9, 2.1, "leg_bl"), (2.9, 2.1, "leg_br")]:
        add_cube(nm, (lx, ly, (TABLE_TOP_Z - TABLE_THICK) / 2.0),
                 (0.18, 0.18, TABLE_TOP_Z - TABLE_THICK), MATS["table"], "table", "wood")

    # 2. Backboard.
    board_center_z = TABLE_TOP_Z + 1.55
    add_cube("flat_backboard", (0.0, BACKBOARD_Y, board_center_z),
             (5.2, 0.12, 3.10), MATS["backboard"], "backboard", "light_gray")

    # 3. Two distinct STATIC objects on the table.
    cube_dim = (0.66, 0.66, 0.66)
    cube_z = TABLE_TOP_Z + cube_dim[2] / 2.0
    add_cube("red_cube_target", (-0.80, OBJ_Y, cube_z), cube_dim, MATS["red"],
             "target_object", "red", is_dynamic=False)

    sph_r = 0.36
    sph_z = TABLE_TOP_Z + sph_r
    add_sphere("blue_sphere_target", sph_r, (0.85, OBJ_Y, sph_z), MATS["blue"],
               "target_object", "blue", is_dynamic=False)

    # 4. Two BI-FOLD door assemblies, in a plane in FRONT of the objects. Each
    #    assembly = an OUTER panel hinged on a fixed jamb (outer vertical edge)
    #    plus an INNER panel hinged to the outer panel's inner edge. Folded OPEN,
    #    the two panels of each assembly are accordion-folded back against the
    #    jamb (concertina). Fully CLOSED, all panels lie flat in the door plane,
    #    the two assemblies meeting at the center to cover the objects.
    door_h = 1.30
    door_t = 0.08
    door_cz = TABLE_TOP_Z + door_h / 2.0    # bottom edge rests on the tabletop
    panel_w = 0.92                          # each panel width; 2 panels/side -> 1.84 span/side
    jamb_x = 1.90                           # outer jamb x (fixed hinge), +/- for R/L

    assemblies = []
    for side, sgn in [("left", -1.0), ("right", +1.0)]:
        jx = sgn * jamb_x
        # Outer panel: hinged at the jamb, extends toward center in -sgn*x.
        # We build panels extending +x from the hinge, and use the hinge Z
        # rotation to orient them; store base geometry and let animation set angles.
        outer_hinge, outer_panel = add_hinge_panel(
            "bifold_%s_outer" % side, (jx, DOOR_Y, door_cz),
            panel_w, door_h, door_t, MATS["panel_a"], "dark_gray")
        # Inner panel: hinged at the FAR (inner) edge of the outer panel. Its
        # hinge empty is parented to the outer panel so it follows the fold. We
        # place the inner hinge at the outer panel's far edge (local +x end).
        inner_hinge, inner_panel = add_hinge_panel(
            "bifold_%s_inner" % side, (jx + panel_w, DOOR_Y, door_cz),
            panel_w, door_h, door_t, MATS["panel_b"], "medium_gray")
        # Parent inner assembly to the outer panel so the mid-hinge rides along.
        inner_hinge.parent = outer_panel
        inner_hinge.matrix_parent_inverse = outer_panel.matrix_world.inverted()

        for p in (outer_panel, inner_panel):
            p["pb_motion"] = "bifold_panels_unfold_to_cover_then_fold_back"
            p["pb_fixed_plane_y"] = DOOR_Y
            p["pb_foreground_depth_separated_from_targets"] = True
        assemblies.append({
            "side": side, "sgn": sgn,
            "outer_hinge": outer_hinge, "outer_panel": outer_panel,
            "inner_hinge": inner_hinge, "inner_panel": inner_panel,
            "panel_w": panel_w,
        })

    return scene, {
        "kind": "bifold_concertina_doors",
        "assemblies": assemblies,
        "door_cz": door_cz,
        "panel_w": panel_w,
    }


def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "bifold_concertina_doors":
        return build_bifold_concertina_doors()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_bifold_concertina_doors(scene, meta):
    assemblies = meta["assemblies"]

    # close01: 0.0 = fully OPEN (folded back, objects visible), 1.0 = fully
    # CLOSED (panels flat in the door plane, objects hidden).
    #
    # For each side, panels are modeled extending +local-x from their hinge. To
    # end up flat and pointing toward the CENTER when closed, the outer hinge
    # rotates so the panel points inward, and the inner hinge straightens (0 rel
    # angle) so the inner panel continues in line. When OPEN, the outer panel is
    # swung back ~ perpendicular (toward -y, folding out of the covering plane
    # toward the camera side jamb) and the inner panel folds back ~180deg
    # against the outer, forming a compact concertina stack at the jamb.
    #
    # LEFT side (sgn=-1): closed outer angle points panel toward +x (center) ->
    #   outer_hinge z = pi (panel local +x now points -x world? ) -- we compute
    #   per side below with explicit target angles.
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= 20:
            c = 0.0
            st = "open_objects_visible"
        elif frame <= 55:
            c = smooth01((frame - 20) / 35.0)
            st = "doors_unfolding_to_cover"
        elif frame <= 80:
            c = 1.0
            st = "closed_objects_hidden"
        elif frame <= 115:
            c = 1.0 - smooth01((frame - 80) / 35.0)
            st = "doors_folding_back_to_reveal"
        else:
            c = 0.0
            st = "open_same_objects_revealed"

        for a in assemblies:
            sgn = a["sgn"]
            # CLOSED target: panels lie flat in the door plane, pointing toward
            # center. Panel local +x must point toward -sgn (i.e. toward center).
            #   left  (sgn -1): center is +x -> outer points +x -> z=0
            #   right (sgn +1): center is -x -> outer points -x -> z=pi
            outer_closed = 0.0 if sgn < 0 else math.pi
            inner_closed = 0.0    # inner in line with outer (flat wall)
            # OPEN target: fold the assembly back toward the jamb / camera side so
            # it clears the objects. Outer swings ~ 100deg out of plane (toward
            # -y, camera side) and inner folds ~ -160deg relative to outer,
            # stacking against it (concertina). Signs chosen so the fold opens
            # away from the objects (toward the jamb/camera, never intersecting).
            outer_open = outer_closed + sgn * math.radians(105.0)
            inner_open = -sgn * math.radians(160.0)

            oz = lerp(outer_open, outer_closed, c)
            iz = lerp(inner_open, inner_closed, c)

            a["outer_hinge"].rotation_euler = (0.0, 0.0, oz)
            a["inner_hinge"].rotation_euler = (0.0, 0.0, iz)
            a["outer_hinge"].keyframe_insert(data_path="rotation_euler", frame=frame)
            a["inner_hinge"].keyframe_insert(data_path="rotation_euler", frame=frame)
            a["outer_panel"]["pb_state"] = st
            a["inner_panel"]["pb_state"] = st


def animate_scene(scene, meta):
    if meta["kind"] == "bifold_concertina_doors":
        animate_bifold_concertina_doors(scene, meta)
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
