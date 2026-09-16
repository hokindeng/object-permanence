# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_THREE_BALLS_ONE_WIDE_TUNNEL_0124",
  "scene_kind": "three_balls_one_wide_tunnel",
  "kind": "three_balls_one_wide_tunnel",
  "prompt": "Three balls — red, green, blue, in that order — roll one behind another along a straight track and pass through a single wide opaque tunnel. They stay hidden inside, then emerge from the far end in the SAME order (red, then green, then blue), unchanged in colour and count."
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
    MATS["green"] = make_mat("mat_green", (0.16, 0.72, 0.24), roughness=0.28)
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


def setup_base(camera_loc, target, ortho_scale):
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
# 00000123  three_balls_one_wide_tunnel  (Cluster: Baillargeonian Occlusion)
# =============================================================================
#
# A straight, flat, horizontal track runs left<->right in front of the camera.
# THREE balls sit one behind another along a SINGLE shared lane (same y), evenly
# spaced, in order red -> green -> blue reading from right to left (red leading).
# All three roll RIGHT at the SAME constant speed, so the spacing between them is
# preserved for the whole run (no collisions, order never changes).
#
# A SINGLE WIDE opaque gray HOUSING (tunnel) box covers the MIDDLE region of the
# track (|x| < tunnel_x_half). It is open at BOTH ends (left & right) so each
# entrance/exit is visible. Each ball is hidden by the TUNNEL GEOMETRY itself
# while inside the footprint -- never removed from the render, so the occlusion
# is honest image-space cover.
#
# Because they share one lane at constant equal speed, they enter the near (left)
# mouth one after another (red, then green, then blue), stay hidden inside, and
# emerge from the far (right) mouth in the SAME order:  red, then green, then
# blue. Colour and count are preserved; every ball is occluded, never deleted.
#
# The tunnel is WIDE enough in x that all three can be simultaneously inside.
# Front/back walls sit OUTBOARD of the single lane + rails so no ball clips a
# wall. The roof is NESTED inside the walls (recessed in x & y, dropped slightly
# below the wall tops) so its outer faces do NOT coincide with the wall faces --
# coincident/coplanar faces there caused a flickering black bar (z-fighting).
# =============================================================================


def _track_params():
    z_track_top = 0.62      # top surface height of the track slab
    track_thick = 0.16
    ball_radius = 0.22
    gap = 1.15              # center-to-center spacing between consecutive balls
    x_start_lead = -3.55    # starting x of the LEADING (red) ball
    tunnel_x_half = 1.75    # WIDE tunnel: covers |x| < tunnel_x_half
    total_travel = 9.10     # how far every ball rolls (constant equal distance)
    return {
        "z_track_top": z_track_top,
        "track_thick": track_thick,
        "ball_radius": ball_radius,
        "gap": gap,
        "x_start_lead": x_start_lead,
        "tunnel_x_half": tunnel_x_half,
        "total_travel": total_travel,
    }


def build_three_balls_one_wide_tunnel():
    scene = setup_base(
        camera_loc=(0.0, -9.6, 2.2),
        target=(0.0, 0.0, 1.05),
        ortho_scale=9.2,
    )

    P = _track_params()
    z_top = P["z_track_top"]
    track_thick = P["track_thick"]
    ball_radius = P["ball_radius"]
    gap = P["gap"]
    x_start_lead = P["x_start_lead"]
    tx = P["tunnel_x_half"]
    total_travel = P["total_travel"]

    z_center = z_top + ball_radius     # ball center height (rolling on top surface)
    z_slab_c = z_top - track_thick / 2.0
    # Put the lane near the visible front edge of the slab.  With a centred lane
    # the slab's front edge and near guide rail occlude the bottom of each
    # mathematically tangent ball, making it look embedded in the floor.
    lane_y = -0.38

    # ---- Flat horizontal track slab spanning the whole width -----------------
    track_len = abs(x_start_lead) + total_travel + 2.2
    track_width = 1.3
    add_cube(
        "wide_track_slab",
        (0.0, 0.0, z_slab_c),
        (track_len, track_width, track_thick),
        MATS["gray"], "track", "gray",
    )

    # Low guide rails bracketing the single lane, so the path reads clearly.
    # Rails must span from the TRAILING (blue) ball's start to the LEADING
    # (red) ball's finish, so no ball is ever off the rails.
    x_trail_start = x_start_lead - 2.0 * gap
    rail_radius = 0.045
    rail_lift = z_top + rail_radius
    rail_x0 = x_trail_start - 0.8
    rail_x1 = x_start_lead + total_travel + 0.8
    # Keep only the far guide rail.  A foreground rail adds no physical constraint
    # in this authored trajectory and visually slices through the rolling balls.
    for side, dy in [("far", lane_y + 0.32)]:
        add_cylinder_between(
            "rail_%s" % side,
            (rail_x0, dy, rail_lift),
            (rail_x1, dy, rail_lift),
            rail_radius, MATS["dark"], "track_rail", "dark_gray",
        )

    # Support pillars under the track (nothing suspended).
    for sx in (x_trail_start + 0.2, 0.0, x_start_lead + total_travel - 0.2):
        add_cube(
            "track_leg_%d" % int(round(sx * 10)),
            (sx, 0.0, z_slab_c / 2.0),
            (0.22, track_width - 0.2, max(0.1, z_slab_c)),
            MATS["support"], "track_support", "dark_gray",
        )

    # ---- SINGLE WIDE opaque tunnel housing over the MIDDLE region ------------
    # Open at both ends (left & right). Roof + front wall + back wall enclose the
    # crossing so every ball is hidden while |x| < tx. Front/back walls sit
    # OUTBOARD of the lane+rails so the balls never clip the walls. WIDE in x so
    # all three balls can be inside at once.
    inner_clear = z_center + ball_radius + 0.14   # clear headroom above ball tops
    t_top = z_top + inner_clear
    t_bot = z_top - 0.01                          # base flush with track top
    t_cz = (t_top + t_bot) / 2.0
    t_h = (t_top - t_bot)
    t_w = 2.0 * tx                                # width = tunnel footprint in x
    t_depth = 1.30                                # deeper than lane + rails
    wall_t = 0.10
    front_y = lane_y - t_depth / 2.0 + wall_t / 2.0
    back_y = lane_y + t_depth / 2.0 - wall_t / 2.0

    add_cube("tunnel_front_wall", (0.0, front_y, t_cz), (t_w, wall_t, t_h), MATS["housing"], "tunnel_front_wall", "gray")
    add_cube("tunnel_back_wall", (0.0, back_y, t_cz), (t_w, wall_t, t_h), MATS["housing"], "tunnel_wall", "gray")
    # Roof NESTED inside the walls (edge-decoupled): recessed in x and y so its
    # outer faces do NOT coincide with the front/back wall faces, and dropped
    # slightly below the wall tops. Coincident/coplanar faces here caused a
    # flickering black bar (z-fighting) at the top of the housing.
    add_cube("tunnel_roof", (0.0, lane_y, t_top - wall_t / 2.0 - 0.012), (t_w - 0.04, t_depth - 2.0 * wall_t - 0.04, wall_t), MATS["housing"], "tunnel_wall", "gray")

    # ---- The three balls (single lane, red leading, then green, then blue) ---
    # Reading right->left at rest: red (front/leading), green, blue (trailing).
    x_red = x_start_lead
    x_green = x_start_lead - gap
    x_blue = x_start_lead - 2.0 * gap

    red = add_sphere("chain_ball_red", ball_radius, (x_red, lane_y, z_center), MATS["red"], "red")
    red["pb_path"] = "left_to_right_through_shared_wide_tunnel_lead"
    red["pb_order_index"] = 0

    green = add_sphere("chain_ball_green", ball_radius, (x_green, lane_y, z_center), MATS["green"], "green")
    green["pb_path"] = "left_to_right_through_shared_wide_tunnel_middle"
    green["pb_order_index"] = 1

    blue = add_sphere("chain_ball_blue", ball_radius, (x_blue, lane_y, z_center), MATS["blue"], "blue")
    blue["pb_path"] = "left_to_right_through_shared_wide_tunnel_trail"
    blue["pb_order_index"] = 2

    return scene, {
        "balls": [
            ("red", red, x_red),
            ("green", green, x_green),
            ("blue", blue, x_blue),
        ],
        "ball_radius": ball_radius,
        "z_center": z_center,
        "lane_y": lane_y,
        "tunnel_x_half": tx,
        "total_travel": total_travel,
    }


def animate_three_balls_one_wide_tunnel(scene, meta):
    balls = meta["balls"]
    radius = meta["ball_radius"]
    z_center = meta["z_center"]
    lane_y = meta["lane_y"]
    tx = meta["tunnel_x_half"]
    total_travel = meta["total_travel"]

    rest_frames = 8
    # Single constant speed shared by all three balls, so the spacing between
    # consecutive balls is preserved for the entire run (order never changes).
    move_frames = float(FRAME_END - rest_frames)
    speed = total_travel / (move_frames / FPS)   # units per second

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= rest_frames:
            s = 0.0
        else:
            t = (frame - rest_frames) / FPS
            s = min(total_travel, speed * t)

        for color_name, ball, x0 in balls:
            x = x0 + s   # all move +x by the same displacement
            ball.location = (x, lane_y, z_center)
            # Rolling spin about Y; sign matches +x travel direction.
            ball.rotation_euler = (0.0, s / radius, 0.0)

            # Documentary-only containment flag (frontal camera); the tunnel
            # geometry does the actual occluding.
            inside = abs(x) + radius <= tx

            ball.keyframe_insert(data_path="location", frame=frame)
            ball.keyframe_insert(data_path="rotation_euler", frame=frame)

            # Semantic state tags.
            if inside:
                ball["pb_state"] = "hidden_inside_shared_wide_tunnel"
            elif x > tx:
                ball["pb_state"] = "reemerged_exiting_right"
            else:
                ball["pb_state"] = "visible_approaching_from_left"
            ball["pb_occluded"] = bool(inside)
            ball["pb_pos_x"] = float(x)

    scene.frame_set(FRAME_START)


# =============================================================================
# Dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE.get("scene_kind", CASE.get("kind"))

    if kind == "three_balls_one_wide_tunnel":
        return build_three_balls_one_wide_tunnel()

    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(scene, meta):
    kind = CASE.get("scene_kind", CASE.get("kind"))

    if kind == "three_balls_one_wide_tunnel":
        return animate_three_balls_one_wide_tunnel(scene, meta)

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
