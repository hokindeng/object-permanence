# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_MATCHBOX_DRAWER_0165",
  "scene_kind": "matchbox_drawer",
  "prompt": "A matchbox sits on a table: a static outer sleeve, open on its two opposite ends, with an inner tray that fits inside it. At the start the tray is slid OUT of the sleeve and a single colored object rests plainly visible in the open tray. The inner tray then slides straight back INTO the sleeve horizontally, carrying the object with it, until the object is fully hidden inside the closed sleeve; it holds closed briefly, then the tray slides back OUT and the SAME object is revealed again in clear view. The object rides on the tray the whole time and is the same object throughout; the outer sleeve never moves and the object rests on the tray floor without ever clipping the sleeve."
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
    MATS["sleeve"] = make_mat("mat_sleeve", (0.40, 0.41, 0.43), roughness=0.70)
    MATS["tray"] = make_mat("mat_tray", (0.66, 0.55, 0.38), roughness=0.66)


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
# 0165 matchbox drawer
#
# A matchbox rests on the ground: a STATIC outer SLEEVE (a box open on its two
# opposite +x/-x ends -- it has top, bottom, front and back walls only) and an
# inner TRAY that fits inside the sleeve. A single colored ball rests on the
# tray floor. This is a START-OPEN permanence cycle: at frame 1 the tray is slid
# OUT in +x and the ball is plainly VISIBLE resting in the open tray. The tray
# then SLIDES back IN (-x) into the sleeve, carrying the ball with it, until the
# ball is fully HIDDEN inside the closed sleeve (the opaque front wall hides it
# from the camera and the top plate hides it from above). It holds closed
# briefly, then the tray slides back OUT (+x) and the SAME ball is REVEALED
# again. The ball is pinned to the tray's live position, resting on the tray
# floor. The outer sleeve never moves; the ball is the SAME object throughout
# and never clips the sleeve.
# =============================================================================

WALL_T = 0.08
CAVITY_H = 0.58
SLEEVE_LEN = 1.70          # outer x length of the sleeve
CAVITY_Y = 0.90            # inner depth (y)


def build_matchbox_drawer():
    scene = build_base_scene()

    # Frontal view, slightly raised and offset so the tray reads as sliding out
    # to the right; the camera never looks into the sleeve's open ends.
    setup_camera(
        scene,
        location=(0.6, -3.85, 2.05),
        target=(0.35, 0.0, 0.32),
        lens=40,
    )

    tray_parts = []  # list of (obj, base_location) that translate together in +x

    # ---- Static outer SLEEVE (open on the two x ends) -----------------------
    bottom_cz = WALL_T / 2.0                      # sits on the ground (top z=0)
    bottom_top = WALL_T                           # 0.08
    top_bottom = bottom_top + CAVITY_H            # 0.66
    top_cz = top_bottom + WALL_T / 2.0            # 0.70
    plate_y = CAVITY_Y + 2.0 * WALL_T             # 1.06
    wall_cy = CAVITY_Y / 2.0 + WALL_T / 2.0       # 0.49 (front/back wall centre y)
    side_wall_cz = (bottom_top + top_bottom) / 2.0
    side_wall_h = top_bottom - bottom_top         # 0.58
    sleeve_right_x = SLEEVE_LEN / 2.0             # 0.85 (the open end the tray exits)

    add_cube("sleeve_bottom_plate", (0.0, 0.0, bottom_cz),
             (SLEEVE_LEN, plate_y, WALL_T), MATS["sleeve"], "sleeve", "dark_gray")
    add_cube("sleeve_top_plate", (0.0, 0.0, top_cz),
             (SLEEVE_LEN, plate_y, WALL_T), MATS["sleeve"], "sleeve", "dark_gray")
    add_cube("sleeve_front_wall", (0.0, -wall_cy, side_wall_cz),
             (SLEEVE_LEN, WALL_T, side_wall_h), MATS["sleeve"], "sleeve", "dark_gray")
    add_cube("sleeve_back_wall", (0.0, wall_cy, side_wall_cz),
             (SLEEVE_LEN, WALL_T, side_wall_h), MATS["sleeve"], "sleeve", "dark_gray")

    # ---- Inner TRAY (slides out) -------------------------------------------
    tray_len = 1.50
    tray_floor_top = bottom_top + 0.07            # small clearance above sleeve floor
    tray_floor_cz = tray_floor_top - 0.03         # floor slab 0.06 thick
    tray_floor = add_cube("tray_floor", (0.0, 0.0, tray_floor_cz),
                          (tray_len, CAVITY_Y - 0.06, 0.06), MATS["tray"], "tray", "wood",
                          is_dynamic=True)
    tray_parts.append((tray_floor, tray_floor.location.copy()))

    side_h = 0.16
    side_cz = tray_floor_top + side_h / 2.0
    tray_side_y = (CAVITY_Y - 0.06) / 2.0 - 0.025
    for sy, nm in ((-tray_side_y, "front"), (tray_side_y, "back")):
        w = add_cube("tray_side_%s" % nm, (0.0, sy, side_cz),
                     (tray_len, 0.05, side_h), MATS["tray"], "tray", "wood", is_dynamic=True)
        tray_parts.append((w, w.location.copy()))

    # Drawer face on the +x (leading) end -- the pull face.
    face_h = 0.26
    face_cz = tray_floor_cz + 0.02 + face_h / 2.0
    face_x = tray_len / 2.0 - 0.03
    face = add_cube("tray_drawer_face", (face_x, 0.0, face_cz),
                    (0.06, CAVITY_Y - 0.04, face_h), MATS["tray"], "tray", "wood", is_dynamic=True)
    tray_parts.append((face, face.location.copy()))

    # ---- The single colored object resting IN the tray ----------------------
    ball_r = 0.16
    ball_cz = tray_floor_top + ball_r
    ball_base_x = -0.15                           # ball x when the tray is CLOSED (s=0)
    # Distance the tray slides so the ball fully clears the sleeve's open end
    # while the tray remains partly inside the sleeve (never floating/detached).
    slide_dist = 1.25
    # Start OPEN: place the ball at its slid-out position (base_x + slide_dist)
    # so frame 1 shows the ball plainly visible outside the sleeve.
    ball = add_sphere("colored_ball_in_tray", ball_r, (ball_base_x + slide_dist, 0.0, ball_cz),
                      MATS["orange"], "orange")
    ball["pb_starts_visible_in_open_tray"] = True
    ball["pb_rides_with_tray"] = True

    return {
        "scene": scene,
        "kind": "matchbox_drawer",
        "tray_parts": tray_parts,
        "ball": ball,
        "ball_base_x": ball_base_x,
        "ball_cz": ball_cz,
        "slide_dist": slide_dist,
        "sleeve_right_x": sleeve_right_x,
        "ball_r": ball_r,
    }


def animate_matchbox_drawer(objs):
    scene = objs["scene"]
    tray_parts = objs["tray_parts"]
    ball = objs["ball"]
    ball_base_x = objs["ball_base_x"]
    ball_cz = objs["ball_cz"]
    slide_dist = objs["slide_dist"]
    sleeve_right_x = objs["sleeve_right_x"]
    ball_r = objs["ball_r"]

    # Container-static permanence, START-OPEN cycle. The outer sleeve never
    # moves. The tray (and the ball resting on it) translate together along x.
    # The slide offset s runs OUT (slide_dist) -> IN (0) -> hold -> OUT again.
    #   Phase 1  f1   - f18  : hold OPEN; tray slid out, ball plainly visible.
    #   Phase 2  f18  - f52  : tray slides IN (-x), ball rides in and hides.
    #   Phase 3  f52  - f78  : hold CLOSED; ball fully hidden inside sleeve.
    #   Phase 4  f78  - f112 : tray slides back OUT (+x), same ball revealed.
    #   Phase 5  f112 - f120 : hold OPEN; ball revealed again.
    open_hold_end = 18
    close_end = 52
    closed_hold_end = 78
    reopen_end = 112

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= open_hold_end:
            s = slide_dist
            state = "open_ball_visible_in_tray"
        elif frame <= close_end:
            t = (frame - open_hold_end) / float(close_end - open_hold_end)
            s = lerp(slide_dist, 0.0, smooth01(t))
            state = "tray_sliding_in_ball_hiding"
        elif frame <= closed_hold_end:
            s = 0.0
            state = "closed_ball_hidden_inside_sleeve"
        elif frame <= reopen_end:
            t = (frame - closed_hold_end) / float(reopen_end - closed_hold_end)
            s = lerp(0.0, slide_dist, smooth01(t))
            state = "tray_sliding_out_ball_revealing"
        else:
            s = slide_dist
            state = "open_same_ball_revealed_again"

        for obj, base in tray_parts:
            obj.location = (base.x + s, base.y, base.z)
            obj.keyframe_insert(data_path="location", frame=frame)
            obj["pb_state"] = state

        ball_x = ball_base_x + s
        ball.location = (ball_x, 0.0, ball_cz)
        ball.keyframe_insert(data_path="location", frame=frame)
        # Ball is revealed once its near edge clears the sleeve's open end.
        revealed = (ball_x - ball_r) > sleeve_right_x
        ball["pb_state"] = "revealed_outside_sleeve" if revealed else "hidden_inside_sleeve"
        ball["pb_same_object_throughout"] = True

    scene.frame_set(FRAME_START)


# =============================================================================
# dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "matchbox_drawer":
        return build_matchbox_drawer()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(objs):
    kind = objs["kind"]
    if kind == "matchbox_drawer":
        return animate_matchbox_drawer(objs)
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

    # Input = tray OPEN, ball plainly visible (start-open). Event = drawer
    # CLOSED, ball hidden inside the sleeve. Final = tray reopened, same ball
    # revealed again.
    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, 65, OPTIONAL_FRAME_PATH)
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
