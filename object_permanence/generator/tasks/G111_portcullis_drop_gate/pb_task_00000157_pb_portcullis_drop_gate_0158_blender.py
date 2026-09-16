# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_PORTCULLIS_DROP_GATE_0158",
  "scene_kind": "portcullis_drop_gate",
  "prompt": "A grille gate is raised above a track. One ball rolls under it while it is up and passes through. The grille then drops down to block the track, and a second ball arriving after it has dropped is stopped, resting against the bars."
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
OPTIONAL_FRAME_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_gate_closed_frame_02.png")
OPTIONAL_FRAME_02B_PATH = os.path.join(OUT_DIR, f"{ITEM_ID}_optional_second_ball_blocked_frame_02B.png")


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


def make_mat(name, color, roughness=0.55):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (color[0], color[1], color[2], 1.0)

    try:
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            if "Base Color" in bsdf.inputs:
                bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = roughness
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


def add_cube(name, location, dimensions, material, role, color_name, is_dynamic=False, solid=True):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
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


def add_sphere(name, radius, location, material, color_name):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    tag(obj, name, "target", "dynamic_object", "sphere", color_name, True, solid=True, pb_radius=radius)
    return obj


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor_warm", (0.82, 0.80, 0.75), roughness=0.82)
    MATS["track"] = make_mat("mat_track_gray", (0.46, 0.46, 0.46), roughness=0.62)
    MATS["frame"] = make_mat("mat_gate_frame_light", (0.66, 0.67, 0.69), roughness=0.70)
    MATS["slot"] = make_mat("mat_dark_slot", (0.10, 0.10, 0.12), roughness=0.78)
    MATS["bar"] = make_mat("mat_dark_grille_bar", (0.20, 0.20, 0.22), roughness=0.74)
    MATS["orange"] = make_mat("mat_orange_ball", (1.0, 0.38, 0.06), roughness=0.30)
    MATS["blue"] = make_mat("mat_blue_ball", (0.16, 0.36, 0.95), roughness=0.30)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)


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

    add_cube("large_floor_base", (0, 0, -0.05), (10.0, 5.0, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0, 2.48, 1.62), (10.2, 0.08, 3.24), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.6, -4.3, 5.5))
    key = bpy.context.object
    key.name = "large_softbox_light"
    key.data.energy = 960
    key.data.size = 6.2

    bpy.ops.object.light_add(type="POINT", location=(3.6, -3.0, 3.0))
    fill = bpy.context.object
    fill.name = "fill_light"
    fill.data.energy = 145

    return scene


def setup_camera(scene):
    # Left-front side view. Balls move left -> right along +X; this camera sees the
    # left (blocking) face of the portcullis grille.
    bpy.ops.object.camera_add(location=(-2.55, -7.15, 2.05))
    cam = bpy.context.object
    cam.name = "camera_left_front_view_portcullis_gate"
    cam.data.lens = 32
    cam.data.dof.use_dof = False
    look_at(cam, (0.78, 0.0, 0.62))
    scene.camera = cam


# grille geometry constants (shared by build + animate)
GATE_X = 0.92
GATE_HALF_X = 0.07          # half thickness of the grille assembly in X
GATE_UP_Z = 1.62            # grille-center z while raised (bottom clears the track)
GATE_DOWN_Z = 0.60          # grille-center z while closed (bottom sits on the track)
GRILLE_H = 1.00             # grille panel height
GRILLE_W = 0.86             # grille panel width (Y span between posts)
BALL_R = 0.14


def build_portcullis_grille():
    """A liftable portcullis: a set of vertical + horizontal bars parented to one
    empty so the whole grille slides vertically as a rigid unit. Bottom of the grille
    at gate-center-z GATE_UP_Z clears the track (ball rolls under); at GATE_DOWN_Z the
    bars reach the track and block it."""
    grille = bpy.data.objects.new("portcullis_grille", None)
    grille.location = (GATE_X, 0.0, GATE_UP_Z)
    bpy.context.scene.collection.objects.link(grille)
    grille["pb_object_id"] = "portcullis_grille"
    grille["pb_role"] = "portcullis_grille"
    grille["pb_is_dynamic"] = True
    grille["pb_slides_vertically_between_posts"] = True
    grille["pb_drops_only_after_first_ball_clears"] = True

    n_vbars = 5
    for i in range(n_vbars):
        y = lerp(-GRILLE_W / 2.0, GRILLE_W / 2.0, i / float(n_vbars - 1))
        bar = add_cube(
            f"grille_vbar_{i:02d}",
            (GATE_X, y, GATE_UP_Z),
            (0.10, 0.05, GRILLE_H),
            MATS["bar"], "grille_vertical_bar", "dark_gray",
            is_dynamic=True, solid=True,
        )
        bar.parent = grille
        bar.matrix_parent_inverse = grille.matrix_world.inverted()

    for j, zoff in enumerate([-GRILLE_H / 2.0 + 0.06, 0.0, GRILLE_H / 2.0 - 0.06]):
        hbar = add_cube(
            f"grille_hbar_{j:02d}",
            (GATE_X, 0.0, GATE_UP_Z + zoff),
            (0.11, GRILLE_W + 0.05, 0.06),
            MATS["bar"], "grille_horizontal_bar", "dark_gray",
            is_dynamic=True, solid=True,
        )
        hbar.parent = grille
        hbar.matrix_parent_inverse = grille.matrix_world.inverted()

    return grille


def build_scene():
    scene = build_base_scene()
    setup_camera(scene)

    add_cube(
        "straight_gate_track",
        (0.0, 0.0, 0.06),
        (9.6, 0.34, 0.08),
        MATS["track"], "gate_track", "gray",
    )

    # Portcullis frame: two side posts + a top crossbeam the grille lifts into.
    add_cube("portcullis_near_side_post", (GATE_X, -0.50, 1.10), (0.18, 0.13, 2.20),
             MATS["frame"], "portcullis_side_post", "light_gray", is_dynamic=False, solid=True)
    add_cube("portcullis_far_side_post", (GATE_X, 0.50, 1.10), (0.18, 0.13, 2.20),
             MATS["frame"], "portcullis_side_post", "light_gray", is_dynamic=False, solid=True)
    add_cube("portcullis_top_crossbeam", (GATE_X, 0.0, 2.24), (0.22, 1.15, 0.16),
             MATS["frame"], "portcullis_top_crossbeam", "light_gray", is_dynamic=False, solid=True)

    # Dark vertical guide slots read as the channels the grille slides in.
    add_cube("portcullis_near_guide_slot", (GATE_X - 0.012, -0.39, 1.02),
             (0.055, 0.055, 1.84), MATS["slot"], "portcullis_guide_slot", "dark_gray",
             is_dynamic=False, solid=True)
    add_cube("portcullis_far_guide_slot", (GATE_X - 0.012, 0.39, 1.02),
             (0.055, 0.055, 1.84), MATS["slot"], "portcullis_guide_slot", "dark_gray",
             is_dynamic=False, solid=True)

    grille = build_portcullis_grille()

    first = add_sphere("first_orange_ball", BALL_R, (-1.80, 0.0, 0.22), MATS["orange"], "orange")
    second = add_sphere("second_blue_ball", BALL_R, (-4.20, 0.0, 0.22), MATS["blue"], "blue")
    first["pb_order"] = 1
    second["pb_order"] = 2

    return {
        "scene": scene,
        "gate": grille,
        "first": first,
        "second": second,
    }


# --- second-ball elastic rebound at the closed grille (FLAT ground) ---
SECOND_REBOUND_BACK = 0.12
SECOND_CONTACT_FRAME = 90
SECOND_REBOUND_FRAME = 102


def ease_out01(t):
    t = clamp01(t)
    return 1.0 - (1.0 - t) * (1.0 - t)


def second_ball_x_at_frame(frame, contact_x, raw_x_at):
    """approach -> contact grille -> recoil backward and come to rest (no settle forward)."""
    if frame <= SECOND_CONTACT_FRAME:
        return min(raw_x_at(frame), contact_x)
    rebound_x = contact_x - SECOND_REBOUND_BACK
    if frame <= SECOND_REBOUND_FRAME:
        t = (frame - SECOND_CONTACT_FRAME) / max(1, (SECOND_REBOUND_FRAME - SECOND_CONTACT_FRAME))
        return lerp(contact_x, rebound_x, ease_out01(t))
    return rebound_x


def animate_scene(objs):
    scene = objs["scene"]
    gate = objs["gate"]
    first = objs["first"]
    second = objs["second"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        # Grille stays RAISED while the first ball passes under it, then drops
        # (vertical z) only after the first ball is long clear.
        if frame <= 55:
            gate_z = GATE_UP_Z
            gate_state = "raised_grille_ball_rolls_under"
        elif frame <= 78:
            gate_z = lerp(GATE_UP_Z, GATE_DOWN_Z, smooth01((frame - 55) / 23.0))
            gate_state = "dropping_after_first_ball_cleared"
        else:
            gate_z = GATE_DOWN_Z
            gate_state = "closed_grille_blocking_track"

        gate.location = (GATE_X, 0.0, gate_z)
        gate.keyframe_insert(data_path="location", frame=frame)
        gate["pb_state"] = gate_state

        # First ball rolls under the raised grille and clears before it drops. When
        # it reaches the end (edge) of the table/track it free-falls off the edge:
        # horizontal velocity is preserved (projectile) while z accelerates under
        # gravity (drop distance grows as t^2), so it does not float at table height.
        FIRST_VX = 0.074                 # per-frame horizontal speed on the table
        TABLE_EDGE_X = 4.80              # +X end of the track (track dim_x 9.6 -> half 4.8)
        Z_ROLL = 0.22                    # ball-centre height while on the table
        G_PER_FRAME2 = 9.8 * (1.0 / FPS) ** 2   # gravity in units / frame^2

        first_x = -1.80 + FIRST_VX * (frame - 1)
        if first_x <= TABLE_EDGE_X:
            first_z = Z_ROLL
            falling = False
        else:
            # frames elapsed since the centre crossed the edge (continuous)
            n_fall = (first_x - TABLE_EDGE_X) / FIRST_VX
            first_z = Z_ROLL - 0.5 * G_PER_FRAME2 * n_fall * n_fall
            falling = True
        first.location = (first_x, 0.0, first_z)
        first.rotation_euler = (0.0, -0.12 * frame, 0.0)
        first.keyframe_insert(data_path="location", frame=frame)
        first.keyframe_insert(data_path="rotation_euler", frame=frame)

        first_rear_x = first_x - BALL_R
        gate_right_face = GATE_X + GATE_HALF_X
        if falling:
            first["pb_state"] = "free_falling_off_table_edge"
        elif first_rear_x > gate_right_face:
            first["pb_state"] = "fully_cleared_gate_before_grille_drops"
        else:
            first["pb_state"] = "rolling_under_raised_grille"
        first["pb_gate_does_not_hit_first_ball"] = True

        # Second ball arrives after the grille has dropped and stops at the bars,
        # with a slight elastic rebound on contact (recoil then settle).
        stop_x = GATE_X - GATE_HALF_X - BALL_R - 0.012
        second_raw_x = -4.20 + 0.055 * (frame - 1)
        second_x = second_ball_x_at_frame(
            frame, stop_x, lambda fr: -4.20 + 0.055 * (fr - 1)
        )

        second.location = (second_x, 0.0, 0.22)
        second.rotation_euler = (0.0, -0.10 * frame, 0.0)
        second.keyframe_insert(data_path="location", frame=frame)
        second.keyframe_insert(data_path="rotation_euler", frame=frame)

        if second_raw_x >= stop_x and frame >= 78:
            second["pb_state"] = "stopped_resting_against_closed_grille_bars"
        else:
            second["pb_state"] = "approaching_after_first_ball"
        second["pb_must_not_pass_closed_gate"] = True
        second["pb_no_gate_penetration"] = True

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


def write_task_json():
    task = {
        "item_id": ITEM_ID,
        "visual_regime": "3D_procedural_control",
        "fps": FPS,
        "inputs": {
            "text_prompt": CASE["prompt"],
        },
        "reference_completion_frames_dir": "frames",
        "reference_completion_video": None,
        "scene_file": f"{ITEM_ID}_scene.blend",
    }
    with open(TASK_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(task, f, indent=2, ensure_ascii=False)


def save_scene():
    bpy.ops.wm.save_as_mainfile(filepath=SCENE_FILE)


def main():
    ensure_dirs()
    clear_scene()

    kind = CASE["scene_kind"]
    if kind != "portcullis_drop_gate":
        raise RuntimeError("Unknown scene_kind: " + str(kind))

    objs = build_scene()
    scene = objs["scene"]
    animate_scene(objs)

    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, 72, OPTIONAL_FRAME_PATH)
    render_png(scene, 120, OPTIONAL_FRAME_02B_PATH)

    render_animation(scene)
    write_task_json()
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
