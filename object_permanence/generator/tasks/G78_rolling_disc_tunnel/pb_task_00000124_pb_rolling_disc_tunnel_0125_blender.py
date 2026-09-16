# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_ROLLING_DISC_TUNNEL_0125",
  "scene_kind": "rolling_disc_tunnel",
  "kind": "rolling_disc_tunnel",
  "prompt": "An upright disc (a coin standing on its edge) rolls along a straight flat track and passes through an opaque tunnel. It is hidden inside the tunnel, then re-emerges from the far end — the same disc, still rolling — unchanged in size and shape."
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

    # Coin/disc: warm metallic gold so the round face reads clearly as a coin.
    MATS["coin"] = make_mat("mat_coin", (0.90, 0.68, 0.16), roughness=0.35, metallic=0.85)
    MATS["coin_rim"] = make_mat("mat_coin_rim", (0.72, 0.52, 0.10), roughness=0.45, metallic=0.85)


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


def add_cylinder(name, location, radius, depth, material, role, color_name, rotation=(0.0, 0.0, 0.0), is_dynamic=False, shape="cylinder", **extras):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, vertices=64, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    if material is not None:
        obj.data.materials.append(material)
    tag(obj, name, role, "dynamic_object" if is_dynamic else "static_solid", shape, color_name, is_dynamic, solid=True, **extras)
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
# 00000124  rolling_disc_tunnel  (Cluster: Baillargeonian Occlusion)
# =============================================================================
#
# A straight, flat, horizontal track runs left->right in front of the camera.
# The moving object is an upright DISC / COIN: a thin flat cylinder standing on
# its edge, with its round face pointing at the camera (cylinder axis along y).
# It rolls on its rim along +x. To read as "rolling" it both translates in +x
# and spins about its y-axis (its horizontal roll axis) at the no-slip rate
# theta = x / radius.
#
# An opaque gray HOUSING (tunnel) box covers the MIDDLE region of the track
# (|x| < tunnel_x_half). It is open at BOTH ends (left & right) so the disc's
# entrance and exit are visible. Front / back / roof walls sit OUTBOARD of the
# disc so the disc never clips the housing.
#
#   disc : starts far LEFT, rolls RIGHT ->, enters the tunnel, is hidden by the
#          TUNNEL GEOMETRY while inside (never removed from the render, so the
#          occlusion is honest image-space cover), then re-emerges from the
#          RIGHT (far) end and keeps rolling -- the SAME disc, unchanged.
# =============================================================================


def _track_params():
    z_track_top = 0.62      # top surface height of the track slab
    track_thick = 0.16
    disc_radius = 0.34      # radius of the coin (rolls on its rim)
    disc_thick = 0.09       # thin -> reads clearly as a flat disc / coin
    x_span = 3.35           # disc starts near -x_span, ends near +x_span
    tunnel_x_half = 0.95    # tunnel covers |x| < tunnel_x_half
    return {
        "z_track_top": z_track_top,
        "track_thick": track_thick,
        "disc_radius": disc_radius,
        "disc_thick": disc_thick,
        "x_span": x_span,
        "tunnel_x_half": tunnel_x_half,
    }


def build_rolling_disc_tunnel():
    # Raised, angled 3/4 view: the camera is lifted above the track and pulled
    # to one side in +x, so we look DOWN and ACROSS the disc. A dead-on front
    # view would fill the frame with the disc's round face and hide its thin
    # edge, so it would read like a ball. From this oblique angle both the
    # disc's flat circular face (which points toward -y) AND its thin edge/rim
    # profile are visible at once, so it clearly reads as a coin/disc rolling
    # on its rim. ortho_scale is generous enough to keep the full track in frame
    # from the wider oblique view.
    scene = setup_base(
        camera_loc=(4.6, -8.8, 3.2),
        target=(0.0, 0.0, 1.05),
        ortho_scale=9.6,
    )

    P = _track_params()
    z_top = P["z_track_top"]
    track_thick = P["track_thick"]
    disc_radius = P["disc_radius"]
    disc_thick = P["disc_thick"]
    x_span = P["x_span"]
    tx = P["tunnel_x_half"]

    z_center = z_top + disc_radius     # disc center height (rolls on its rim on top surface)
    z_slab_c = z_top - track_thick / 2.0
    # Bring the disc close to the visible front edge so that edge cannot hide the
    # bottom of its rim and make exact contact look like floor penetration.
    lane_y = -0.58

    # ---- Flat horizontal track slab spanning the whole width -----------------
    track_len = 2.0 * x_span + 1.6
    track_width = 1.4
    add_cube(
        "disc_track_slab",
        (0.0, 0.0, z_slab_c),
        (track_len, track_width, track_thick),
        MATS["gray"], "track", "gray",
    )

    # Low guide rails flanking the single lane, so the rolling path reads clearly.
    rail_radius = 0.045
    rail_lift = z_top + rail_radius
    rail_x0 = -x_span - 0.8
    rail_x1 = x_span + 0.8
    # A near rail would cut across the disc silhouette.  The far rail is enough
    # to communicate the lane while leaving the rim/floor contact fully visible.
    for side, dy in [("far", lane_y + disc_thick / 2.0 + 0.14)]:
        add_cylinder_between(
            "rail_%s" % side,
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

    # ---- Opaque tunnel housing over the MIDDLE region ------------------------
    # Open at both ends (left & right). Roof + front wall + back wall enclose the
    # crossing so the disc is hidden while |x| < tx. Front/back walls sit
    # OUTBOARD of the disc (deeper in y than the disc thickness + rails) so the
    # disc never clips the walls.
    inner_clear = z_center + disc_radius + 0.16   # clear headroom above disc top
    t_top = z_top + inner_clear
    t_bot = z_top - 0.01                          # base flush with track top
    t_cz = (t_top + t_bot) / 2.0
    t_h = (t_top - t_bot)
    t_w = 2.0 * tx                                # width = tunnel footprint in x
    t_depth = 2.0 * (disc_thick / 2.0 + 0.14) + 0.55   # deeper than disc + rails
    wall_t = 0.10
    front_y = lane_y - t_depth / 2.0 + wall_t / 2.0
    back_y = lane_y + t_depth / 2.0 - wall_t / 2.0

    add_cube("tunnel_front_wall", (0.0, front_y, t_cz), (t_w, wall_t, t_h), MATS["housing"], "tunnel_front_wall", "gray")
    add_cube("tunnel_back_wall", (0.0, back_y, t_cz), (t_w, wall_t, t_h), MATS["housing"], "tunnel_wall", "gray")
    # Roof NESTED inside the walls (edge-decoupled): recessed in x and y so its
    # outer faces do NOT coincide with the front/back wall faces, and dropped
    # slightly below the wall tops, to avoid z-fighting at the top of the housing.
    add_cube("tunnel_roof", (0.0, lane_y, t_top - wall_t / 2.0 - 0.012), (t_w - 0.04, t_depth - 2.0 * wall_t - 0.04, wall_t), MATS["housing"], "tunnel_wall", "gray")

    # ---- The rolling disc / coin ---------------------------------------------
    # Thin cylinder standing upright on its rim: axis along y so its round flat
    # faces point at the camera (-y) and the far backdrop (+y). Default cylinder
    # axis is +z, so rotate +90deg about x to lay the axis along y.
    disc = add_cylinder(
        "rolling_disc",
        (-x_span, lane_y, z_center),
        disc_radius, disc_thick,
        MATS["coin"], "target", "gold",
        rotation=(math.pi / 2.0, 0.0, 0.0),
        is_dynamic=True, shape="disc",
        pb_radius=disc_radius, pb_thickness=disc_thick,
    )
    disc["pb_path"] = "left_to_right_through_opaque_tunnel_rolling_on_edge"
    disc["pb_can_disappear"] = False

    return scene, {
        "disc": disc,
        "disc_radius": disc_radius,
        "z_center": z_center,
        "lane_y": lane_y,
        "x_span": x_span,
        "tunnel_x_half": tx,
    }


def animate_rolling_disc_tunnel(scene, meta):
    disc = meta["disc"]
    radius = meta["disc_radius"]
    z_center = meta["z_center"]
    lane_y = meta["lane_y"]
    x_span = meta["x_span"]
    tx = meta["tunnel_x_half"]

    # The disc lies on its edge with axis along +y (base rotation +90deg about x).
    # It rolls in +x, so it must spin about its y-axis at the no-slip rate
    # theta_y = distance / radius. Blender applies rotation_euler in XYZ order;
    # with rx fixed at +90deg, adding a Y-euler cleanly spins it about its (now
    # horizontal) roll axis, reading as rolling on the rim.
    base_rx = math.pi / 2.0

    rest_frames = 8
    move_frames = float(FRAME_END - rest_frames)
    speed = (2.0 * x_span) / (move_frames / FPS)   # units per second

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= rest_frames:
            s = 0.0
        else:
            t = (frame - rest_frames) / FPS
            s = min(2.0 * x_span, speed * t)

        # Disc: starts at -x_span, moves +x (left -> right).
        xd = -x_span + s

        disc.location = (xd, lane_y, z_center)
        # No-slip rolling spin about the horizontal y roll axis. Sign chosen so
        # the top of the rim moves forward (+x) as the disc advances.
        disc.rotation_euler = (base_rx, -s / radius, 0.0)

        # Documentary-only containment flag. The camera sits at x=+4.6, well
        # off-axis, so the true image-space window drifts a few frames earlier
        # than this world-x test; the tunnel geometry does the actual occluding.
        inside = abs(xd) + radius <= tx

        disc.keyframe_insert(data_path="location", frame=frame)
        disc.keyframe_insert(data_path="rotation_euler", frame=frame)

        # Semantic state tags.
        if inside:
            disc["pb_state"] = "hidden_inside_tunnel"
        elif xd > tx:
            disc["pb_state"] = "reemerged_rolling_right"
        else:
            disc["pb_state"] = "visible_approaching_from_left"
        disc["pb_occluded"] = bool(inside)
        disc["pb_pos_x"] = float(xd)

    scene.frame_set(FRAME_START)


# =============================================================================
# Dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE.get("scene_kind", CASE.get("kind"))

    if kind == "rolling_disc_tunnel":
        return build_rolling_disc_tunnel()

    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(scene, meta):
    kind = CASE.get("scene_kind", CASE.get("kind"))

    if kind == "rolling_disc_tunnel":
        return animate_rolling_disc_tunnel(scene, meta)

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
