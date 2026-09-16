# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_TILTING_TRAY_RELOCATE_0156",
  "scene_kind": "tilting_tray_relocate",
  "prompt": "An object rests in an OPEN tray, plainly visible at the near end. A lid closes over it; the tray then tilts so the hidden object slides under the cover to the far end and the tray levels out; finally the lid lifts at that far end to reveal the same object has moved there, unchanged."
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
    for block in list(bpy.data.curves):
        if block.users == 0:
            bpy.data.curves.remove(block)
    for block in list(bpy.data.worlds):
        if block.users == 0:
            bpy.data.worlds.remove(block)


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

    try:
        scene.view_settings.view_transform = "Filmic"
        scene.view_settings.look = "Medium High Contrast"
    except Exception:
        pass


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def lerp(a, b, t):
    return a + (b - a) * t


def smooth01(t):
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


def make_mat(name, color, roughness=0.55, metallic=0.0, alpha=1.0):
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

        if alpha < 1.0:
            mat.blend_method = "BLEND"
            mat.use_screen_refraction = True
            mat.show_transparent_back = True
    except Exception:
        pass

    return mat


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), roughness=0.85)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.92)

    MATS["gray"] = make_mat("mat_gray", (0.62, 0.63, 0.66), roughness=0.75)
    MATS["dark"] = make_mat("mat_dark", (0.18, 0.20, 0.24), roughness=0.55)
    MATS["screen"] = make_mat("mat_screen", (0.46, 0.48, 0.53), roughness=0.88)
    MATS["support"] = make_mat("mat_support", (0.16, 0.18, 0.22), roughness=0.60)
    MATS["tray"] = make_mat("mat_tray", (0.72, 0.73, 0.76), roughness=0.70)
    MATS["lid"] = make_mat("mat_lid", (0.55, 0.57, 0.62), roughness=0.66)

    MATS["red"] = make_mat("mat_red", (0.92, 0.18, 0.18), roughness=0.28)
    MATS["blue"] = make_mat("mat_blue", (0.16, 0.36, 0.95), roughness=0.28)
    MATS["yellow"] = make_mat("mat_yellow", (0.98, 0.78, 0.15), roughness=0.28)
    MATS["orange"] = make_mat("mat_orange", (0.97, 0.45, 0.10), roughness=0.28)


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
        obj, name, role,
        "dynamic_object" if is_dynamic else "static_solid",
        "cube", color_name, is_dynamic, solid=solid
    )
    return obj


def add_ball(name, radius, location, material, color_name):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=48, ring_count=24)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(
        obj, name, "target", "dynamic_object", "sphere", color_name, True,
        solid=True, pb_radius=radius
    )
    return obj


def add_cylinder_between(name, p1, p2, radius, material, role, color_name):
    p1 = Vector(p1)
    p2 = Vector(p2)
    diff = p2 - p1
    length = diff.length
    mid = (p1 + p2) / 2.0

    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=length, vertices=24, location=mid)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = diff.to_track_quat("Z", "Y").to_euler()

    if material is not None:
        obj.data.materials.append(material)

    tag(obj, name, role, "static_solid", "cylinder", color_name, False, solid=True)
    return obj


def make_root(name, location=(0.0, 0.0, 0.0), role="dynamic_root"):
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=location)
    root = bpy.context.object
    root.name = name
    tag(root, name, role, "dynamic_object", "empty", "gray", True, solid=False)
    return root


def parent_to(obj, parent):
    obj.parent = parent
    obj.matrix_parent_inverse = parent.matrix_world.inverted()
    return obj


def setup_base(camera_loc, target, ortho_scale, floor_size=(12.0, 8.0), backdrop_x=12.0):
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (floor_size[0], floor_size[1], 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.40, 1.85), (backdrop_x, 0.08, 3.70), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.0, -4.5, 5.8))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 950
    key.data.size = 5.5

    bpy.ops.object.light_add(type="POINT", location=(3.0, 1.8, 3.3))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 120

    bpy.ops.object.camera_add(location=camera_loc)
    cam = bpy.context.object
    cam.name = "camera_main"
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = ortho_scale
    look_at(cam, target)
    scene.camera = cam

    return scene


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


# =============================================================================
# 00000155  tilting_tray_relocate
# =============================================================================
#
# A long tray sits on a central pivot support. A ball rests at the NEAR (-X)
# end of the tray, inside the trough. The tray STARTS OPEN: at frame 1 the lid is
# swung up so the ball is plainly VISIBLE resting in the trough. The sequence is:
#   (1) start open, ball visible at the near end;
#   (2) the lid closes down over the trough, hiding the ball;
#   (3) the tray tilts down toward the FAR (+X) end so the hidden ball slides along
#       the (now-sloped) trough floor from the near end to the far end
#       (gravity-consistent);
#   (4) the tray levels back to horizontal;
#   (5) the lid lifts again (rotates up about a hinge on the FAR end) to REVEAL the
#       same ball has relocated to the far end, unchanged.
# The whole tray assembly (trough floor + side walls + end walls + lid + the ball)
# is parented to a tilt pivot empty at the tray CENTER, so the tray see-saws about
# its middle.
#
# Geometry is in the pivot's LOCAL frame: local +X = along the tray toward the far end.
# The ball's local X is keyframed so it slides downhill while the tray is tilted.

TRAY_LEN = 3.20           # trough interior length in local X
TRAY_W = 0.78             # trough interior width (Y)
WALL_T = 0.07
FLOOR_T = 0.08
WALL_H = 0.60             # tall enough to fully contain the ball (dia 2*BALL_R) below the lid
BALL_R = 0.24
PIVOT_Z = 0.75            # height of the tray see-saw axis above the floor (raised so the tilted tray clears the table)


def build_tilting_tray_relocate():
    from mathutils import Matrix

    # Camera: elevated 3/4 view (~48 deg above horizontal) that looks DOWN into the
    # open trough over the near side wall, aimed at the FAR (+X) end where the ball
    # ends up. The tray side walls (top at world z = PIVOT_Z + WALL_H = 1.35) are
    # slightly taller than the ball (top at 1.23), so a low camera hides the ball
    # entirely; this steeper, closer-in view puts the revealed ball clearly in frame
    # (its centre and lower third both project ABOVE the front wall's top edge) while
    # still keeping the whole tray and the lifted lid inside the frame.
    scene = setup_base(
        camera_loc=(3.4, -7.2, 9.6),
        target=(1.0, 0.2, 0.95),
        ortho_scale=10.2,
    )

    # Tilt pivot at the tray center (its see-saw axis passes through the trough
    # floor's TOP surface at world z = PIVOT_Z).
    pivot = make_root("tilting_tray_pivot", (0.0, 0.0, PIVOT_Z), role="tilting_tray_pivot")

    half_len = TRAY_LEN / 2.0
    # The trough floor is centred at local z = -FLOOR_T/2, so its top surface is
    # at local z = 0 (i.e. on the pivot's see-saw axis).
    floor_top_local = 0.0

    # Trough floor (local z centered at 0 so the pivot is at the floor's mid-plane).
    floor = add_cube("tray_floor", (0.0, 0.0, -FLOOR_T / 2.0),
                     (TRAY_LEN + 2 * WALL_T, TRAY_W + 2 * WALL_T, FLOOR_T),
                     MATS["tray"], "tray_floor", "gray", is_dynamic=True)
    # Side walls (run the full length along X).
    near_wall = add_cube("tray_side_wall_near", (0.0, -(TRAY_W / 2.0 + WALL_T / 2.0), WALL_H / 2.0),
                         (TRAY_LEN + 2 * WALL_T, WALL_T, WALL_H),
                         MATS["tray"], "tray_wall", "gray", is_dynamic=True)
    far_wall = add_cube("tray_side_wall_far", (0.0, (TRAY_W / 2.0 + WALL_T / 2.0), WALL_H / 2.0),
                        (TRAY_LEN + 2 * WALL_T, WALL_T, WALL_H),
                        MATS["tray"], "tray_wall", "gray", is_dynamic=True)
    # End walls (cap both ends so the ball cannot fall out; the far end catches it).
    end_lo = add_cube("tray_end_wall_near", (-(half_len + WALL_T / 2.0), 0.0, WALL_H / 2.0),
                      (WALL_T, TRAY_W + 2 * WALL_T, WALL_H),
                      MATS["tray"], "tray_end_wall", "gray", is_dynamic=True)
    end_hi = add_cube("tray_end_wall_far", (half_len + WALL_T / 2.0, 0.0, WALL_H / 2.0),
                      (WALL_T, TRAY_W + 2 * WALL_T, WALL_H),
                      MATS["tray"], "tray_end_wall", "gray", is_dynamic=True)

    for part in [floor, near_wall, far_wall, end_lo, end_hi]:
        parent_to(part, pivot)

    # ----- Opaque LID over the whole trough, hinged on the FAR (+X) end -----
    # A separate pivot empty at the far top edge lets the lid rotate UP to reveal.
    lid_z_local = WALL_H + 0.03           # lid sits just above the walls
    lid_hinge = make_root("tray_lid_hinge", (0.0, 0.0, 0.0), role="tray_lid_hinge")
    lid_hinge.location = (half_len + WALL_T, 0.0, lid_z_local)   # local frame of tray
    parent_to(lid_hinge, pivot)

    lid = add_cube("tray_opaque_lid",
                   (-(TRAY_LEN + 2 * WALL_T) / 2.0, 0.0, 0.0),   # extends back toward the near end from the hinge
                   (TRAY_LEN + 2 * WALL_T, TRAY_W + 2 * WALL_T, 0.06),
                   MATS["lid"], "tray_lid", "gray", is_dynamic=True)
    parent_to(lid, lid_hinge)
    lid["pb_opaque_cover"] = True

    # ----- The ball, resting on the trough floor at the NEAR (-X) end -----
    ball_local_z = floor_top_local + BALL_R
    ball_near_x = -half_len + BALL_R + 0.10
    ball_far_x = half_len - BALL_R - 0.10
    ball = add_ball("relocating_orange_ball", BALL_R, (ball_near_x, 0.0, ball_local_z),
                    MATS["orange"], "orange")
    parent_to(ball, pivot)
    ball["pb_path"] = "slides_under_cover_from_near_end_to_far_end_as_tray_tilts"

    # ----- External static support the tray see-saws on (visual pedestal) -----
    # Pedestal + axle support: kept BELOW the trough floor bottom (world z =
    # PIVOT_Z - FLOOR_T) so they never intrude into the ball resting on the
    # floor top. The axle rod sits just under the floor; the pedestal rises from
    # the table to just under the axle.
    floor_bottom_z = PIVOT_Z - FLOOR_T
    # Axle: short and set below the floor so the tilted tray (whose floor swings
    # down away from centre) and the ball on it never dip onto it.
    axle_z = floor_bottom_z - 0.07
    ped_top = floor_bottom_z - 0.03
    add_cube("tray_pivot_pedestal", (0.0, 0.0, ped_top / 2.0),
             (0.55, 0.70, ped_top), MATS["support"], "tray_support", "dark_gray")
    add_cylinder_between("tray_pivot_axle", (-0.25, 0.0, axle_z), (0.25, 0.0, axle_z),
                         0.05, MATS["dark"], "tray_axle", "dark_gray")

    # Use NATURAL parenting for the whole tray assembly: each child's world pose
    # must equal parent.matrix_world @ child.matrix_basis so that the tray rides
    # UP at the pivot height and see-saws about the pivot's axis. (parent_to sets
    # matrix_parent_inverse to cancel the pivot transform, which would collapse
    # the tray back down to the floor and make it swing through the table.)
    for child in [floor, near_wall, far_wall, end_lo, end_hi, lid_hinge, lid, ball]:
        child.matrix_parent_inverse = Matrix.Identity(4)

    return scene, {
        "pivot": pivot,
        "lid_hinge": lid_hinge,
        "ball": ball,
        "ball_local_z": ball_local_z,
        "ball_near_x": ball_near_x,
        "ball_far_x": ball_far_x,
    }


def animate_tilting_tray_relocate(scene, meta):
    pivot = meta["pivot"]
    lid_hinge = meta["lid_hinge"]
    ball = meta["ball"]
    ball_local_z = meta["ball_local_z"]
    ball_near_x = meta["ball_near_x"]
    ball_far_x = meta["ball_far_x"]

    tilt_max = math.radians(16.0)     # tray tilts so the far (+X) end goes DOWN (kept modest so the tilted end stays above the table)
    lid_open = math.radians(78.0)     # lid swings up about its far hinge

    # Timeline (START OPEN -> cover -> tilt/relocate -> reveal):
    #   1..8    : rest, tray level, lid OPEN, ball plainly visible at the near end
    #   8..24   : lid CLOSES down over the trough, hiding the ball
    #   30..50  : tray tilts down toward the far end (far end drops)
    #   48..72  : hidden ball slides downhill from near end to far end (while tilted)
    #   72..92  : tray levels back to horizontal
    #   100..116: lid lifts at the far end to REVEAL the ball has moved there
    #   116..120: hold revealed
    def tilt_angle(frame):
        if frame <= 30:
            return 0.0
        if frame <= 50:
            return tilt_max * smooth01((frame - 30) / 20.0)
        if frame <= 72:
            return tilt_max
        if frame <= 92:
            return tilt_max * (1.0 - smooth01((frame - 72) / 20.0))
        return 0.0

    def ball_local_x(frame):
        # The ball stays at the near end (visible, then covered) until the tray has
        # tilted, then slides down to the far end while tilted, and remains there.
        if frame <= 48:
            return ball_near_x
        if frame <= 72:
            return ball_near_x + (ball_far_x - ball_near_x) * smooth01((frame - 48) / 24.0)
        return ball_far_x

    def lid_angle(frame):
        # OPEN at the start (ball visible), close over the ball, stay shut through the
        # tilt/relocate, then open again at the far end to reveal.
        if frame <= 8:
            return lid_open
        if frame <= 24:
            return lid_open * (1.0 - smooth01((frame - 8) / 16.0))
        if frame <= 100:
            return 0.0
        if frame <= 116:
            return lid_open * smooth01((frame - 100) / 16.0)
        return lid_open

    # Tilt the tray about its Y axis (tray long axis is world X, width is world Y).
    # For a point on +X, rotation about +Y by angle t gives world z' = -x*sin(t), so a
    # POSITIVE angle drops the FAR (+X) end downward. The far end must be the LOW end so
    # the ball slides downhill toward it (gravity-consistent).
    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        a = tilt_angle(frame)
        # Positive rotation about Y tips the +X (far) end DOWN -> ball slides downhill.
        pivot.rotation_euler = (0.0, a, 0.0)
        pivot.keyframe_insert(data_path="rotation_euler", frame=frame)
        pivot["pb_state"] = "tilting" if 30 < frame <= 92 else ("level" if frame > 92 else "resting_level")

        # Lid rotates UP about its far hinge (open toward +Z / -X so it clears the far end).
        la = lid_angle(frame)
        lid_hinge.rotation_euler = (0.0, la, 0.0)
        lid_hinge.keyframe_insert(data_path="rotation_euler", frame=frame)
        lid_hinge["pb_state"] = ("open_start_ball_visible" if frame <= 8 else
                                 ("closing_over_ball" if frame <= 24 else
                                  ("closed_covering_ball" if frame <= 100 else "opening_to_reveal")))

        # Ball slides along the trough floor (local X); local Z stays on the floor.
        ball.location = (ball_local_x(frame), 0.0, ball_local_z)
        ball.keyframe_insert(data_path="location", frame=frame)
        # Rolling spin about local Y proportional to distance travelled.
        ball.rotation_euler = (0.0, -(ball_local_x(frame) - ball_near_x) / BALL_R, 0.0)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)
        ball["pb_state"] = ("visible_at_near_end_before_cover" if frame <= 24 else
                            ("sliding_under_cover_to_far_end" if frame <= 72 else
                             "revealed_relocated_at_far_end"))

    scene.frame_set(FRAME_START)


# =============================================================================
# Dispatch
# =============================================================================

def build_scene():
    kind = CASE["scene_kind"]
    if kind == "tilting_tray_relocate":
        return build_tilting_tray_relocate()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(scene, meta):
    kind = CASE["scene_kind"]
    if kind == "tilting_tray_relocate":
        return animate_tilting_tray_relocate(scene, meta)
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def main():
    ensure_dirs()
    clear_scene()

    scene, meta = build_scene()
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
    render_png(scene, 60, OPTIONAL_FRAME_PATH)
    render_png(scene, 120, OPTIONAL_FRAME_02B_PATH)
    render_animation(scene)
    write_task_json(task)
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("kind:", CASE["scene_kind"])
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
