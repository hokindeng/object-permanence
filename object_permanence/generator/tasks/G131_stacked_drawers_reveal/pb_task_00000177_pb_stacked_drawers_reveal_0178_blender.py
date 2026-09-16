# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_STACKED_DRAWERS_REVEAL_0178",
  "scene_kind": "stacked_drawers_reveal",
  "prompt": "A small chest with two stacked drawers sits on a table. A single colored ball rests inside the lower drawer. The lower drawer slides straight OUT toward the viewer, carrying the ball with it, until the ball is plainly visible resting inside the open drawer; it holds open briefly, then the drawer slides back IN, hiding the ball inside the closed chest, then slides OUT again to reveal the SAME ball. The upper drawer stays shut throughout, the chest never moves, and the ball rides on the drawer floor without ever clipping the chest."
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
    MATS["chest"] = make_mat("mat_chest", (0.40, 0.41, 0.43), roughness=0.70)
    MATS["drawer"] = make_mat("mat_drawer", (0.66, 0.55, 0.38), roughness=0.66)


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
# 0178 stacked drawers reveal
#
# A STATIC chest (apparatus) with two stacked drawer cavities sits on the
# ground. The chest has a bottom, a top, two side walls (+/-x), a back wall
# (+y) and a horizontal divider between the two drawers; the front (-y) is
# open so the drawers can slide OUT toward the camera. A single colored ball
# rests on the floor of the LOWER drawer. This is a START-CLOSED permanence
# cycle: at frame 1 both drawers are shut and the ball is hidden inside the
# chest. The lower drawer then slides OUT (-y), carrying the ball with it,
# until the ball is plainly visible in front of the chest; it holds open,
# slides back IN (+y) to hide the ball, holds closed, then slides OUT again to
# reveal the SAME ball. The UPPER drawer never moves, the chest never moves,
# and the ball rides on the lower drawer floor without clipping the chest.
# =============================================================================

WALL_T = 0.06
INNER_HALF_X = 0.50            # interior half-width in x
INNER_Y = 1.00                 # interior depth (y)
CAVITY_H = 0.50                # each drawer cavity height


def build_stacked_drawers_reveal():
    scene = build_base_scene()

    # Front view, slightly raised so the ball reads clearly as it emerges from
    # the lower drawer toward the camera.
    setup_camera(
        scene,
        location=(0.0, -3.9, 1.75),
        target=(0.0, -0.35, 0.42),
        lens=42,
    )

    inner_half_x = INNER_HALF_X
    outer_half_x = inner_half_x + WALL_T                 # 0.56
    back_y = INNER_Y / 2.0                               # +0.50 interior back plane
    front_y = -INNER_Y / 2.0                             # -0.50 interior front plane
    chest_front_outer = front_y - WALL_T                 # -0.56

    # ---- z layout (ground at 0) --------------------------------------------
    bottom_cz = WALL_T / 2.0                             # bottom plate
    bottom_top = WALL_T                                  # 0.06
    lower_bottom = bottom_top                            # 0.06
    lower_top = lower_bottom + CAVITY_H                  # 0.56
    div_cz = lower_top + WALL_T / 2.0                    # divider centre 0.59
    div_top = lower_top + WALL_T                         # 0.62
    upper_bottom = div_top                               # 0.62
    upper_top = upper_bottom + CAVITY_H                  # 1.12
    top_cz = upper_top + WALL_T / 2.0                    # top plate centre 1.15
    chest_top = upper_top + WALL_T                       # 1.18

    chest_h = chest_top                                  # from 0
    side_wall_cz = chest_h / 2.0
    plate_x = 2.0 * outer_half_x                         # 1.12 (spans side walls)
    plate_y_depth = INNER_Y + WALL_T                     # back wall + open front
    plate_center_y = WALL_T / 2.0                        # plates extend back over back wall

    # ---- Static chest shell ------------------------------------------------
    add_cube("chest_bottom_plate", (0.0, plate_center_y, bottom_cz),
             (plate_x, plate_y_depth, WALL_T), MATS["chest"], "chest_wall", "dark_gray")
    add_cube("chest_top_plate", (0.0, plate_center_y, top_cz),
             (plate_x, plate_y_depth, WALL_T), MATS["chest"], "chest_wall", "dark_gray")
    add_cube("chest_divider_panel", (0.0, plate_center_y, div_cz),
             (2.0 * inner_half_x, plate_y_depth, WALL_T), MATS["chest"], "chest_panel", "gray")
    add_cube("chest_back_wall", (0.0, back_y + WALL_T / 2.0, side_wall_cz),
             (plate_x, WALL_T, chest_h), MATS["chest"], "chest_wall", "dark_gray")
    add_cube("chest_side_wall_px", (outer_half_x - WALL_T / 2.0, plate_center_y, side_wall_cz),
             (WALL_T, plate_y_depth, chest_h), MATS["chest"], "chest_wall", "dark_gray")
    add_cube("chest_side_wall_nx", (-(outer_half_x - WALL_T / 2.0), plate_center_y, side_wall_cz),
             (WALL_T, plate_y_depth, chest_h), MATS["chest"], "chest_wall", "dark_gray")

    # ---- Drawer geometry helper --------------------------------------------
    drawer_len_x = 2.0 * inner_half_x - 0.06             # 0.94
    drawer_depth_y = INNER_Y - 0.06                      # 0.94
    face_h = CAVITY_H - 0.06                             # 0.44 front pull face
    side_h = 0.18                                        # low interior walls

    def build_drawer(prefix, cavity_bottom, role):
        parts = []
        floor_thick = 0.05
        floor_cz = cavity_bottom + floor_thick / 2.0 + 0.02
        floor_top = floor_cz + floor_thick / 2.0
        floor = add_cube(f"{prefix}_floor", (0.0, 0.0, floor_cz),
                         (drawer_len_x, drawer_depth_y, floor_thick),
                         MATS["drawer"], role, "wood", is_dynamic=True)
        parts.append((floor, floor.location.copy()))

        side_cz = floor_top + side_h / 2.0
        side_off_x = drawer_len_x / 2.0 - 0.025
        for sx, nm in ((-side_off_x, "nx"), (side_off_x, "px")):
            w = add_cube(f"{prefix}_side_{nm}", (sx, 0.0, side_cz),
                         (0.05, drawer_depth_y, side_h), MATS["drawer"], role, "wood", is_dynamic=True)
            parts.append((w, w.location.copy()))
        # low back wall of the drawer (+y interior end)
        back = add_cube(f"{prefix}_back", (0.0, drawer_depth_y / 2.0 - 0.025, side_cz),
                        (drawer_len_x, 0.05, side_h), MATS["drawer"], role, "wood", is_dynamic=True)
        parts.append((back, back.location.copy()))

        # Front pull face on the -y (leading) end; fills the cavity opening.
        face_cz = cavity_bottom + face_h / 2.0 + 0.02
        face_y = front_y + 0.02                          # flush with chest front when closed
        face = add_cube(f"{prefix}_face", (0.0, face_y, face_cz),
                        (drawer_len_x + 0.04, 0.05, face_h), MATS["drawer"], role, "wood", is_dynamic=True)
        parts.append((face, face.location.copy()))
        return parts, floor_top

    # LOWER drawer (holds the ball) and UPPER drawer (stays shut).
    lower_parts, lower_floor_top = build_drawer("lower_drawer", lower_bottom, "lower_drawer")
    upper_parts, _ = build_drawer("upper_drawer", upper_bottom, "upper_drawer")

    # ---- The colored ball, resting on the LOWER drawer floor ----------------
    ball_r = 0.16
    ball_cz = lower_floor_top + ball_r
    ball_base_y = 0.10                                   # y when the drawer is CLOSED (s=0)
    # Slide distance: enough that the ball clears the chest front and is fully
    # visible, while the drawer stays partly inside (never detaches).
    slide_dist = 0.90
    ball = add_sphere("ball_in_lower_drawer", ball_r, (0.0, ball_base_y, ball_cz),
                      MATS["orange"], "orange", role="hidden_ball")
    ball["pb_rides_with_drawer"] = True
    ball["pb_starts_hidden_in_closed_chest"] = True

    return {
        "scene": scene,
        "kind": "stacked_drawers_reveal",
        "lower_parts": lower_parts,
        "upper_parts": upper_parts,
        "ball": ball,
        "ball_base_y": ball_base_y,
        "ball_cz": ball_cz,
        "ball_r": ball_r,
        "slide_dist": slide_dist,
        "chest_front_outer": chest_front_outer,
    }


def animate_stacked_drawers_reveal(objs):
    scene = objs["scene"]
    lower_parts = objs["lower_parts"]
    ball = objs["ball"]
    ball_base_y = objs["ball_base_y"]
    ball_cz = objs["ball_cz"]
    ball_r = objs["ball_r"]
    slide_dist = objs["slide_dist"]
    chest_front_outer = objs["chest_front_outer"]

    # Container-static permanence, START-CLOSED cycle. The chest and the upper
    # drawer never move. The lower drawer (and the ball resting on it) translate
    # together along -y (out toward the camera). The slide offset s runs
    # CLOSED (0) -> OUT (slide_dist) -> hold -> IN (0) -> hold -> OUT again.
    #   Phase 1  f1   - f12  : closed; ball hidden inside the chest.
    #   Phase 2  f12  - f44  : lower drawer slides OUT, ball revealed.
    #   Phase 3  f44  - f66  : hold OPEN; ball plainly visible.
    #   Phase 4  f66  - f92  : lower drawer slides IN, ball hidden again.
    #   Phase 5  f92  - f100 : hold CLOSED.
    #   Phase 6  f100 - f120 : slides OUT again; same ball revealed.
    open_a_start, open_a_end = 12, 44
    hold_open_end = 66
    close_start, close_end = 66, 92
    closed_hold_end = 100
    reopen_end = 120

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= open_a_start:
            s = 0.0
            state = "closed_ball_hidden_inside_chest"
        elif frame <= open_a_end:
            t = (frame - open_a_start) / float(open_a_end - open_a_start)
            s = lerp(0.0, slide_dist, smooth01(t))
            state = "lower_drawer_sliding_out_ball_revealing"
        elif frame <= hold_open_end:
            s = slide_dist
            state = "open_ball_visible_in_lower_drawer"
        elif frame <= close_end:
            t = (frame - close_start) / float(close_end - close_start)
            s = lerp(slide_dist, 0.0, smooth01(t))
            state = "lower_drawer_sliding_in_ball_hiding"
        elif frame <= closed_hold_end:
            s = 0.0
            state = "closed_ball_hidden_inside_chest"
        else:
            t = (frame - closed_hold_end) / float(reopen_end - closed_hold_end)
            s = lerp(0.0, slide_dist, smooth01(t))
            state = "lower_drawer_sliding_out_same_ball_revealed"

        # Drawer slides in -y (toward the camera) as s increases.
        for obj, base in lower_parts:
            obj.location = (base.x, base.y - s, base.z)
            obj.keyframe_insert(data_path="location", frame=frame)
            obj["pb_state"] = state

        # Upper drawer parts hold their closed pose (keyframed every frame).
        for obj, base in objs["upper_parts"]:
            obj.location = (base.x, base.y, base.z)
            obj.keyframe_insert(data_path="location", frame=frame)
            obj["pb_state"] = "upper_drawer_stays_shut"

        ball_y = ball_base_y - s
        ball.location = (0.0, ball_y, ball_cz)
        ball.keyframe_insert(data_path="location", frame=frame)
        revealed = (ball_y + ball_r) < chest_front_outer
        ball["pb_state"] = "revealed_in_open_drawer" if revealed else "hidden_inside_chest"
        ball["pb_same_object_throughout"] = True

    scene.frame_set(FRAME_START)


# =============================================================================
# dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "stacked_drawers_reveal":
        return build_stacked_drawers_reveal()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(objs):
    kind = objs["kind"]
    if kind == "stacked_drawers_reveal":
        return animate_stacked_drawers_reveal(objs)
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

    # Input = closed (ball hidden). Event = lower drawer open (ball visible).
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
