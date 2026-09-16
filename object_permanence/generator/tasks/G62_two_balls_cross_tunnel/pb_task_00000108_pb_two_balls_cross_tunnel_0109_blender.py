# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_TWO_BALLS_CROSS_TUNNEL_0109",
  "scene_kind": "two_balls_cross_tunnel",
  "kind": "two_balls_cross_tunnel",
  "prompt": "A red ball on the left and a blue ball on the right roll toward each other and both enter the same opaque horizontal tunnel from opposite ends. Hidden inside, they pass each other on parallel lanes, then each emerges from the far end and continues — the red ball exits on the right, the blue ball exits on the left. Neither ball changes colour, and both remain present the whole time."
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


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


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
    except Exception:
        pass

    return mat


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor", (0.82, 0.80, 0.75), roughness=0.85)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.92)

    MATS["gray"] = make_mat("mat_gray", (0.62, 0.63, 0.66), roughness=0.75)
    MATS["housing"] = make_mat("mat_housing", (0.32, 0.33, 0.37), roughness=0.85)
    MATS["dark"] = make_mat("mat_dark", (0.18, 0.20, 0.24), roughness=0.55)
    MATS["support"] = make_mat("mat_support", (0.16, 0.18, 0.22), roughness=0.60)

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
        obj,
        name,
        role,
        "dynamic_object" if is_dynamic else "static_solid",
        "cube",
        color_name,
        is_dynamic,
        solid=solid,
    )
    return obj


def add_sphere(name, radius, location, material, color_name, role="target", is_dynamic=True):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=48, ring_count=24)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)

    tag(
        obj,
        name,
        role,
        "dynamic_object" if is_dynamic else "static_solid",
        "sphere",
        color_name,
        is_dynamic,
        solid=True,
        pb_radius=radius,
    )
    return obj


def add_cylinder(name, location, radius, depth, material, role, color_name, rotation=(0.0, 0.0, 0.0), is_dynamic=False):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, vertices=24, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    if material is not None:
        obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", "cylinder", color_name, is_dynamic, solid=True)
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


def add_oriented_box(name, location, dimensions, material, role, color_name, rotation=(0.0, 0.0, 0.0), is_dynamic=False, solid=True):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.rotation_euler = rotation

    if material is not None:
        obj.data.materials.append(material)

    tag(
        obj,
        name,
        role,
        "dynamic_object" if is_dynamic else "static_solid",
        "cube",
        color_name,
        is_dynamic,
        solid=solid,
    )
    return obj


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
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Base Contrast"
    except Exception:
        try:
            scene.view_settings.view_transform = "Standard"
            scene.view_settings.look = "None"
        except Exception:
            pass


def setup_base(camera_loc, target, ortho_scale, lens=None):
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (12.0, 8.0, 0.10), MATS["floor"], "ground", "warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 3.55, 2.05), (12.0, 0.08, 4.1), MATS["backdrop"], "background", "off_white")

    bpy.ops.object.light_add(type="AREA", location=(-2.8, -4.5, 6.4))
    key = bpy.context.object
    key.name = "key_area_light"
    key.data.energy = 600
    key.data.size = 7.0

    bpy.ops.object.light_add(type="POINT", location=(3.0, 1.8, 3.6))
    fill = bpy.context.object
    fill.name = "fill_point_light"
    fill.data.energy = 140

    bpy.ops.object.camera_add(location=camera_loc)
    cam = bpy.context.object
    cam.name = "camera_main"
    if lens is not None:
        # Slightly elevated 3/4 perspective view so the two parallel lanes
        # (offset only in Y) separate visibly in the image instead of
        # overlapping as they do from a flat ortho front view.
        cam.data.type = "PERSP"
        cam.data.lens = lens
    else:
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
# 00000108  two_balls_cross_tunnel  (Cluster: Baillargeonian Occlusion)
# =============================================================================
#
# A straight, flat, horizontal track runs left<->right in front of the camera.
# The track carries TWO parallel lanes at slightly different depths (different y)
# so the two balls never collide as they pass. An opaque gray HOUSING (tunnel)
# box covers the MIDDLE crossing region of the track (|x| < tunnel_x_half). It
# is open at BOTH ends (left and right) so each entrance/exit is visible.
#
#   red  ball : starts far LEFT  on the near lane, rolls RIGHT ->
#   blue ball : starts far RIGHT on the far  lane, rolls LEFT  <-
#
# Both enter the shared tunnel from opposite ends, pass each other hidden inside
# (on their separate lanes, no collision), and each exits the FAR end:
#   red  -> exits on the RIGHT
#   blue -> exits on the LEFT
# Each ball is hidden by the TUNNEL GEOMETRY (roof + front/back walls) while
# inside the footprint; neither ball is ever removed from the render, so the
# occlusion is honest image-space cover. Neither changes colour, and both are
# present the entire time.
# =============================================================================


def _track_params():
    z_track_top = 0.62      # top surface height of the track slab
    track_thick = 0.16
    ball_radius = 0.22
    lane_dy = 0.30          # half-separation between the two parallel lanes in y
    x_span = 3.35           # balls start/end near +/- this x
    tunnel_x_half = 0.95    # tunnel covers |x| < tunnel_x_half
    return {
        "z_track_top": z_track_top,
        "track_thick": track_thick,
        "ball_radius": ball_radius,
        "lane_dy": lane_dy,
        "x_span": x_span,
        "tunnel_x_half": tunnel_x_half,
    }


def build_two_balls_cross_tunnel():
    # Steep near-overhead 3/4 view: camera raised HIGH in Z and pulled CLOSE in
    # Y so it looks STEEPLY DOWN onto the track. At only lane_dy=0.30 half-
    # separation the two Y-offset lanes overlap in a shallow view; a steep
    # (~65 deg elevation) top-down angle projects that Y gap into a clear
    # VERTICAL separation in the image, so each ball reads on its own track.
    # A slight X offset keeps a 3/4 feel; the wide lens keeps both tunnel
    # entrances/exits (x = +/- 3.35 plus rails) in frame from up close.
    scene = setup_base(
        camera_loc=(1.2, -3.6, 8.6),
        target=(0.0, 0.0, 0.55),
        ortho_scale=8.4,
        lens=26.0,
    )

    P = _track_params()
    z_top = P["z_track_top"]
    track_thick = P["track_thick"]
    ball_radius = P["ball_radius"]
    lane_dy = P["lane_dy"]
    x_span = P["x_span"]
    tx = P["tunnel_x_half"]

    z_center = z_top + ball_radius     # ball center height (rolling on top surface)
    z_slab_c = z_top - track_thick / 2.0

    # ---- Flat horizontal track slab spanning the whole width -----------------
    track_len = 2.0 * x_span + 1.6
    track_width = 2.0 * lane_dy + 0.9
    add_cube(
        "cross_track_slab",
        (0.0, 0.0, z_slab_c),
        (track_len, track_width, track_thick),
        MATS["gray"], "track", "gray",
    )

    # Low guide rails along each lane edge, so the two lanes read clearly.
    rail_radius = 0.045
    rail_lift = z_top + rail_radius
    rail_x0 = -x_span - 0.8
    rail_x1 = x_span + 0.8
    for lane_name, ly in [("near", -lane_dy), ("far", lane_dy)]:
        for side, dy in [("in", ly - 0.13), ("out", ly + 0.13)]:
            add_cylinder_between(
                "rail_%s_%s" % (lane_name, side),
                (rail_x0, dy, rail_lift),
                (rail_x1, dy, rail_lift),
                rail_radius, MATS["dark"], "track_rail", "dark_gray",
            )

    # Support pillars under the track (nothing suspended).
    for sx in (-x_span - 0.4, 0.0, x_span + 0.4):
        add_cube(
            "track_leg_%d" % int(round(sx * 10)),
            (sx, 0.0, z_slab_c / 2.0),
            (0.22, track_width - 0.2, max(0.1, z_slab_c)),
            MATS["support"], "track_support", "dark_gray",
        )

    # ---- Opaque tunnel housing over the MIDDLE crossing region ---------------
    # Open at both ends (left & right). Roof + front wall + back wall enclose the
    # crossing so both balls are hidden while |x| < tx. Front/back walls sit
    # OUTBOARD of the lanes+rails so the balls never clip the walls.
    inner_clear = z_center + ball_radius + 0.14   # clear headroom above ball tops
    t_top = z_top + inner_clear
    t_bot = z_top - 0.01                          # base flush with track top
    t_cz = (t_top + t_bot) / 2.0
    t_h = (t_top - t_bot)
    t_w = 2.0 * tx                                # width = tunnel footprint in x
    t_depth = 2.0 * lane_dy + 0.70                # deeper than lanes+rails
    wall_t = 0.10
    front_y = -t_depth / 2.0 + wall_t / 2.0
    back_y = t_depth / 2.0 - wall_t / 2.0

    add_cube("tunnel_front_wall", (0.0, front_y, t_cz), (t_w, wall_t, t_h), MATS["housing"], "tunnel_front_wall", "gray")
    add_cube("tunnel_back_wall", (0.0, back_y, t_cz), (t_w, wall_t, t_h), MATS["housing"], "tunnel_wall", "gray")
    # Roof NESTED inside the walls (edge-decoupled): recessed in x and y so its
    # outer faces do NOT coincide with the front/back wall faces, and dropped
    # slightly below the wall tops. Coincident/coplanar faces here caused a
    # flickering black bar (z-fighting) at the top of the housing.
    add_cube("tunnel_roof", (0.0, 0.0, t_top - wall_t / 2.0 - 0.012), (t_w - 0.04, t_depth - 2.0 * wall_t - 0.04, wall_t), MATS["housing"], "tunnel_wall", "gray")

    # ---- The two balls -------------------------------------------------------
    red = add_sphere("cross_ball_red", ball_radius, (-x_span, -lane_dy, z_center), MATS["red"], "red")
    red["pb_path"] = "left_to_right_through_shared_tunnel_near_lane"
    red["pb_can_disappear"] = False

    blue = add_sphere("cross_ball_blue", ball_radius, (x_span, lane_dy, z_center), MATS["blue"], "blue")
    blue["pb_path"] = "right_to_left_through_shared_tunnel_far_lane"
    blue["pb_can_disappear"] = False

    return scene, {
        "red": red,
        "blue": blue,
        "ball_radius": ball_radius,
        "z_center": z_center,
        "lane_dy": lane_dy,
        "x_span": x_span,
        "tunnel_x_half": tx,
    }


def animate_two_balls_cross_tunnel(scene, meta):
    red = meta["red"]
    blue = meta["blue"]
    radius = meta["ball_radius"]
    z_center = meta["z_center"]
    lane_dy = meta["lane_dy"]
    x_span = meta["x_span"]
    tx = meta["tunnel_x_half"]

    rest_frames = 8
    # Constant, equal speed so the two balls are mirror images. Travel the full
    # 2*x_span span over the moving portion of the animation.
    move_frames = float(FRAME_END - rest_frames)
    speed = (2.0 * x_span) / (move_frames / FPS)   # units per second

    def x_of(x0, direction, s):
        return x0 + direction * s

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= rest_frames:
            s = 0.0
        else:
            t = (frame - rest_frames) / FPS
            s = min(2.0 * x_span, speed * t)

        # Red: starts at -x_span, moves +x (left -> right).
        xr = x_of(-x_span, +1.0, s)
        # Blue: starts at +x_span, moves -x (right -> left).
        xb = x_of(+x_span, -1.0, s)

        red.location = (xr, -lane_dy, z_center)
        blue.location = (xb, lane_dy, z_center)

        # Rolling spin about Y; sign matches travel direction.
        red.rotation_euler = (0.0, s / radius, 0.0)
        blue.rotation_euler = (0.0, -s / radius, 0.0)

        # Documentary-only containment flags (camera offset x=+1.2 shifts the
        # true image-space window slightly); the tunnel geometry occludes.
        red_inside = abs(xr) + radius <= tx
        blue_inside = abs(xb) + radius <= tx

        for b in (red, blue):
            b.keyframe_insert(data_path="location", frame=frame)
            b.keyframe_insert(data_path="rotation_euler", frame=frame)

        # Semantic state tags.
        if red_inside:
            red["pb_state"] = "hidden_inside_shared_tunnel"
        elif xr > tx:
            red["pb_state"] = "reemerged_exiting_right"
        else:
            red["pb_state"] = "visible_approaching_from_left"
        red["pb_occluded"] = bool(red_inside)
        red["pb_pos_x"] = float(xr)

        if blue_inside:
            blue["pb_state"] = "hidden_inside_shared_tunnel"
        elif xb < -tx:
            blue["pb_state"] = "reemerged_exiting_left"
        else:
            blue["pb_state"] = "visible_approaching_from_right"
        blue["pb_occluded"] = bool(blue_inside)
        blue["pb_pos_x"] = float(xb)

    scene.frame_set(FRAME_START)


# =============================================================================
# Dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE.get("scene_kind", CASE.get("kind"))

    if kind == "two_balls_cross_tunnel":
        return build_two_balls_cross_tunnel()

    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(scene, meta):
    kind = CASE.get("scene_kind", CASE.get("kind"))

    if kind == "two_balls_cross_tunnel":
        return animate_two_balls_cross_tunnel(scene, meta)

    raise RuntimeError("Unknown scene_kind: " + str(kind))


def main():
    ensure_dirs()
    clear_scene()

    scene, meta = build_scene_by_kind()
    animate_scene_by_kind(scene, meta)

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
    print("scene_kind:", CASE.get("scene_kind"))
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
