# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_TIPPING_SHELF_DROP_0140",
  "scene_kind": "tipping_shelf_drop",
  "prompt": "A ball rests on a flat shelf that is held level by a support prop under one end. The prop slides out; with that end unsupported the shelf tips down, and the ball rolls off the low end, falls to the floor, bounces briefly, and rolls to rest. Nothing remains suspended."
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


def ease_in_quad(t):
    t = clamp01(t)
    return t * t


def lerp(a, b, t):
    return a + (b - a) * t


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def make_mat(name, color, roughness=0.55, metallic=0.0, alpha=1.0, blend=None):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (color[0], color[1], color[2], alpha)
    try:
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            if "Base Color" in bsdf.inputs:
                bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], alpha)
            if "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = alpha
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = roughness
            if "Metallic" in bsdf.inputs:
                bsdf.inputs["Metallic"].default_value = metallic
    except Exception:
        pass

    if blend is None:
        blend = "BLEND" if alpha < 1.0 else "OPAQUE"
    try:
        mat.blend_method = blend
        mat.show_transparent_back = True
        mat.use_screen_refraction = alpha < 1.0
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


def add_cube(name, location, dimensions, material=None, role="static_solid", color_name="gray", is_dynamic=False, solid=True):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
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


def add_cylinder(name, location, radius, depth, material=None, role="static_solid", color_name="gray", is_dynamic=False, solid=True, rotation=(0.0, 0.0, 0.0), vertices=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    if material is not None:
        obj.data.materials.append(material)
    tag(
        obj,
        name,
        role,
        "dynamic_object" if is_dynamic else ("static_solid" if solid else "non_solid_marker"),
        "cylinder",
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


MATS = {}


def build_materials():
    MATS["floor"] = make_mat("mat_floor_warm", (0.82, 0.80, 0.75), roughness=0.82)
    MATS["gray"] = make_mat("mat_neutral_gray", (0.66, 0.66, 0.68), roughness=0.62)
    MATS["slab"] = make_mat("mat_slab_gray", (0.58, 0.60, 0.64), roughness=0.58)
    MATS["column"] = make_mat("mat_column_blue", (0.24, 0.42, 0.72), roughness=0.50)
    MATS["prop"] = make_mat("mat_prop_blue", (0.24, 0.42, 0.72), roughness=0.50)
    MATS["pivot"] = make_mat("mat_pivot_gray", (0.34, 0.35, 0.38), roughness=0.60)
    MATS["box"] = make_mat("mat_box_gray", (0.38, 0.39, 0.40), roughness=0.78)
    MATS["edge"] = make_mat("mat_light_edge", (0.62, 0.63, 0.64), roughness=0.68)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.38, 0.06), roughness=0.30)
    MATS["red"] = make_mat("mat_red", (0.85, 0.12, 0.10), roughness=0.32)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (9.8, 4.8, 0.10), MATS["floor"], role="ground", color_name="warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 2.42, 1.60), (10.0, 0.08, 3.20), MATS["backdrop"], role="background", color_name="off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.8, -4.4, 5.5))
    key = bpy.context.object
    key.name = "large_softbox_light"
    key.data.energy = 950
    key.data.size = 6.0

    bpy.ops.object.light_add(type="POINT", location=(3.7, -2.8, 3.2))
    fill = bpy.context.object
    fill.name = "right_fill_light"
    fill.data.energy = 145

    return scene


def setup_camera(scene, location=(-0.65, -8.5, 1.75), target=(0.4, 0.0, 0.65), lens=31):
    bpy.ops.object.camera_add(location=location)
    camera = bpy.context.object
    camera.name = "camera_main"
    camera.data.lens = lens
    look_at(camera, target)
    camera.data.dof.use_dof = False
    scene.camera = camera


# ============================================================
# 0140 tipping shelf drop
# ============================================================

def build_tipping_shelf_drop_scene():
    scene = build_base_scene()
    # Side/front view: the shelf spans along x. Pivot is at the LEFT (-x) end on a
    # short pivot post; the FREE (+x) end is held level by a prop underneath. Camera
    # low and to the -y front so the level hold, the prop sliding out, the shelf
    # tipping down about its left pivot, the ball rolling off the low (+x) end, and
    # the accelerating fall to the floor are all clearly visible with no clipping.
    setup_camera(scene, location=(0.4, -8.8, 2.05), target=(0.6, 0.0, 1.05), lens=34)

    FLOOR_TOP_Z = 0.0

    # ---- Shelf geometry (a flat slab that pivots about its left end) ----
    SHELF_LEN_X = 3.60      # length along x
    SHELF_LEN_Y = 1.30      # depth along y
    SHELF_THICK = 0.18      # thickness in z
    SHELF_LEVEL_Z = FLOOR_TOP_Z + 1.55   # z of the shelf's centerline while level

    # Pivot at the LEFT end of the shelf. The shelf's local origin sits at its
    # geometric center, so the pivot point (left end, at the mid-height of the
    # shelf) is offset by -SHELF_LEN_X/2 from the shelf center.
    PIVOT_X = -SHELF_LEN_X / 2.0
    PIVOT_Z = SHELF_LEVEL_Z
    HALF_LEN = SHELF_LEN_X / 2.0

    # Shelf slab. Built centered at its resting (level) center position.
    shelf = add_cube(
        "flat_shelf",
        (0.0, 0.0, SHELF_LEVEL_Z),
        (SHELF_LEN_X, SHELF_LEN_Y, SHELF_THICK),
        MATS["slab"],
        role="shelf_pivoting_about_left_end",
        color_name="gray",
        solid=True,
    )
    shelf["pb_pivots_about_left_end"] = True
    # Move the object origin to the pivot point (left end, mid-height) so that a
    # rotation about y tips the shelf about that end cleanly.
    _set_origin(shelf, Vector((PIVOT_X, 0.0, PIVOT_Z)))

    # ---- Short pivot post under the left (pivot) end, holds the pivot in place ----
    POST_W = 0.42
    POST_H = SHELF_LEVEL_Z - SHELF_THICK / 2.0 - FLOOR_TOP_Z
    if POST_H < 0.1:
        POST_H = 0.1
    post_center_z = FLOOR_TOP_Z + POST_H / 2.0
    pivot_post = add_cube(
        "pivot_post",
        (PIVOT_X, 0.0, post_center_z),
        (POST_W, POST_W, POST_H),
        MATS["pivot"],
        role="pivot_post",
        color_name="gray",
        solid=True,
    )
    pivot_post["pb_is_support"] = True

    # ---- Support prop under the FREE (+x) end, keeps the shelf level ----
    # The prop's top touches the underside of the shelf near the free end.
    PROP_W = 0.44           # footprint side (x and y)
    PROP_X = HALF_LEN - 0.55  # sits a bit inboard of the very free end
    PROP_TOP_Z = SHELF_LEVEL_Z - SHELF_THICK / 2.0
    PROP_H = PROP_TOP_Z - FLOOR_TOP_Z
    if PROP_H < 0.1:
        PROP_H = 0.1
    prop_center_z = FLOOR_TOP_Z + PROP_H / 2.0
    prop = add_cube(
        "support_prop",
        (PROP_X, 0.0, prop_center_z),
        (PROP_W, PROP_W, PROP_H),
        MATS["prop"],
        role="support_prop_under_free_end",
        color_name="blue",
        solid=True,
    )
    prop["pb_is_support"] = True

    # ---- Ball resting on the shelf, near the free (+x) end ----
    BALL_R = 0.34
    # Ball starts partway out toward the free end so it has room to roll down.
    BALL_S0 = 0.35 * HALF_LEN   # signed distance along the shelf from the pivot end center
    SHELF_TOP_LOCAL_Z = SHELF_THICK / 2.0  # top surface above shelf centerline
    # While level: ball x measured from shelf center; center is at x=0.
    ball_x0 = BALL_S0
    ball_z0 = SHELF_LEVEL_Z + SHELF_TOP_LOCAL_Z + BALL_R
    ball = add_sphere(
        "red_ball_on_shelf",
        BALL_R,
        (ball_x0, 0.0, ball_z0),
        MATS["red"],
        "red",
        role="ball_on_shelf",
    )
    ball["pb_rests_on_shelf"] = True

    return {
        "scene": scene,
        "kind": "tipping_shelf_drop",
        "shelf": shelf,
        "pivot_post": pivot_post,
        "prop": prop,
        "ball": ball,
        "floor_top_z": FLOOR_TOP_Z,
        "shelf_len_x": SHELF_LEN_X,
        "shelf_thick": SHELF_THICK,
        "shelf_level_z": SHELF_LEVEL_Z,
        "pivot_x": PIVOT_X,
        "pivot_z": PIVOT_Z,
        "half_len": HALF_LEN,
        "prop_x": PROP_X,
        "prop_w": PROP_W,
        "prop_center_z": prop_center_z,
        "ball_r": BALL_R,
        "ball_s0": BALL_S0,
        "shelf_top_local_z": SHELF_TOP_LOCAL_Z,
    }


def _set_origin(obj, world_point):
    # Move an object's origin to a given world point without moving the mesh.
    delta = obj.location - world_point
    obj.data.transform(_translation_matrix(delta))
    obj.location = world_point.copy()


def _translation_matrix(v):
    from mathutils import Matrix
    return Matrix.Translation(v)


def animate_tipping_shelf_drop(objs, frame):
    shelf = objs["shelf"]
    pivot_post = objs["pivot_post"]
    prop = objs["prop"]
    ball = objs["ball"]
    floor_top_z = objs["floor_top_z"]
    shelf_thick = objs["shelf_thick"]
    pivot_x = objs["pivot_x"]
    pivot_z = objs["pivot_z"]
    half_len = objs["half_len"]
    prop_x = objs["prop_x"]
    prop_w = objs["prop_w"]
    prop_center_z = objs["prop_center_z"]
    ball_r = objs["ball_r"]
    ball_s0 = objs["ball_s0"]
    shelf_top_local_z = objs["shelf_top_local_z"]

    # Timeline:
    #   Phase 0 (1-24):   hold. Shelf level on pivot post + prop, ball resting.
    #   Phase 1 (24-40):  the prop slides out sideways (-y, toward camera) until it
    #                     fully clears the shelf's underside (no clipping). The
    #                     slide is sized so the prop's trailing edge passes the
    #                     shelf's far edge exactly at slide_end == the prop-cleared
    #                     frame.
    #   Phase 2 (40-78):  the instant the prop clears, the free end is unsupported,
    #                     so the shelf begins tipping DOWN about its left pivot with
    #                     NO hold/gap. Ease-in (accelerating fall) from that frame.
    #                     Ball rides the shelf but starts rolling toward the low
    #                     (+x) end.
    #   Phase 3 (~68-110):once the ball reaches the free edge it leaves the shelf
    #                     and free-falls (accelerating) straight to the floor and
    #                     settles.
    #
    # Physical constraint enforced below: tip_start == prop_cleared_frame == slide_end.
    # The shelf must fall the instant its support is gone, so there is intentionally
    # no waiting phase between "prop cleared" and "tip start".
    hold_end = 24
    slide_start = 24
    # The prop (footprint prop_w along y) clears the shelf's underside once it has
    # travelled shelf_half_depth + prop_half_width in -y. Size the slide so that the
    # prop is FULLY clear exactly at slide_end; that same frame is when tipping
    # begins. Any extra coast would delay the physically-required fall.
    shelf_half_depth = 1.30 / 2.0          # SHELF_LEN_Y / 2
    prop_clear_dist = shelf_half_depth + prop_w / 2.0 + 0.06  # +small margin, no clip
    slide_end = 40
    prop_cleared_frame = slide_end         # prop underside is clear at this frame
    tip_start = prop_cleared_frame         # tip begins immediately, no gap
    tip_end = 78

    # ---- Prop slides out from under the free end (moves in -y, away under shelf) ----
    # Ease-out to a stop so the prop is fully clear right at slide_end; the shelf
    # takes over falling on the very next instant.
    if frame <= slide_start:
        ps = 0.0
    elif frame <= slide_end:
        ps = smooth01((frame - slide_start) / float(slide_end - slide_start)) * prop_clear_dist
    else:
        ps = prop_clear_dist
    prop.location = (prop_x, -ps, prop_center_z)
    prop.keyframe_insert(data_path="location", frame=frame)
    prop["pb_state"] = "holding_shelf" if frame <= slide_start else ("sliding_out" if frame < slide_end else "cleared")

    # Pivot post stays fixed the whole time.
    pivot_post.keyframe_insert(data_path="location", frame=frame)
    pivot_post["pb_state"] = "static_support"

    # ---- Shelf tips down about the left pivot once the prop has cleared ----
    # Final tilt: the free (+x) end drops until it reaches the floor. With the pivot
    # at height pivot_z, the free end (length half_len*2 out along +x from pivot)
    # descends. Compute the angle at which the free end's bottom touches the floor.
    full_len = 2.0 * half_len
    # free end bottom starts at pivot_z - shelf_thick/2 (level). It touches floor when
    # the end has dropped by (pivot_z - shelf_thick/2 - floor_top_z) vertically.
    drop_needed = pivot_z - shelf_thick / 2.0 - floor_top_z
    # vertical drop of free end = full_len * sin(theta). Clamp ratio to <=1.
    sin_theta = min(1.0, drop_needed / full_len) if full_len > 1e-6 else 0.0
    max_tilt = math.asin(sin_theta)  # positive angle magnitude

    if frame <= tip_start:
        tilt = 0.0
        tip_t = 0.0
    elif frame <= tip_end:
        tip_t = ease_in_quad((frame - tip_start) / float(tip_end - tip_start))
        tilt = tip_t * max_tilt
    else:
        tip_t = 1.0
        tilt = max_tilt

    # Rotating about +y by a POSITIVE angle drops the +x end (right-hand rule:
    # +y rotation sends +x toward -z). Shelf origin is at the pivot point.
    shelf.rotation_euler = (0.0, tilt, 0.0)
    shelf.keyframe_insert(data_path="rotation_euler", frame=frame)
    shelf["pb_state"] = "level" if frame <= tip_start else ("tipping" if frame < tip_end else "tipped_down")
    shelf["pb_never_suspended"] = True

    # ---- Ball: rides the tilted shelf surface, rolls toward the low (+x) edge,
    #      then leaves the edge and free-falls to the floor. ----
    # Position of a point on the shelf top surface, at signed distance s from the
    # pivot along the shelf's local +x axis, given current tilt (rotation about y at
    # the pivot). Local point on top surface: (s, 0, +shelf_top_local_z) relative to
    # pivot origin. Rotating about +y by 'tilt':
    #   x' = s*cos(tilt) + shelf_top_local_z*sin(tilt)
    #   z' = -s*sin(tilt) + shelf_top_local_z*cos(tilt)
    # world = pivot + (x', 0, z'); ball center sits ball_r along the (rotated) shelf
    # normal above that contact point.
    def surface_point_and_normal(s, tilt):
        c = math.cos(tilt)
        sn = math.sin(tilt)
        x_local = s
        z_local = shelf_top_local_z
        x_w = pivot_x + (x_local * c + z_local * sn)
        z_w = pivot_z + (-x_local * sn + z_local * c)
        # shelf top normal in local +z, rotated: (sin(tilt), 0, cos(tilt))
        nx = sn
        nz = c
        return x_w, z_w, nx, nz

    # Ball's signed distance from pivot along the shelf grows as the shelf tilts
    # (it rolls toward the free/low end). It starts at s0 = ball_s0 + half_len
    # (because ball_s0 was measured from shelf CENTER; pivot is half_len to the -x,
    # so distance from pivot = ball_s0 + half_len).
    s0 = ball_s0 + half_len
    s_edge = full_len - ball_r * 0.6   # contact point can travel until ball is at the very edge

    # Roll progress: begin rolling shortly after tip starts, accelerate as tilt grows.
    # Map tip progress to roll fraction with ease-in so the ball is slow at first.
    # Ball reaches the low edge before the shelf fully finishes tilting, so the
    # roll-off and the ensuing free-fall are clearly visible within the timeline.
    roll_launch_t = ease_in_quad(clamp01((tip_t - 0.10) / 0.65)) if tip_end > tip_start else 0.0
    s_ball = lerp(s0, s_edge, roll_launch_t)

    # Determine the frame at which the ball reaches the edge (roll_launch_t ~ 1).
    # After that, the ball has left the shelf: free-fall from the edge launch point.
    on_shelf = roll_launch_t < 0.999

    if on_shelf:
        cx, cz, nx, nz = surface_point_and_normal(s_ball, tilt)
        ball_x = cx + nx * ball_r
        ball_z = cz + nz * ball_r
        ball["pb_state"] = "resting_on_shelf" if frame <= tip_start else "rolling_down_shelf"
        # Remember the launch state for the fall phase.
        objs["_ball_launch"] = {
            "frame": frame,
            "x": ball_x,
            "z": ball_z,
        }
    else:
        launch = objs.get("_ball_launch")
        if launch is None:
            cx, cz, nx, nz = surface_point_and_normal(s_edge, tilt)
            launch = {"frame": frame, "x": cx + nx * ball_r, "z": cz + nz * ball_r}
            objs["_ball_launch"] = launch
        # True ballistic free-fall from the launch point, followed by a damped
        # floor impact.  Keep both position and horizontal velocity continuous
        # through touchdown: the previous implementation clamped the ball to a
        # complete stop one frame after contact, which looked visibly unphysical.
        floor_rest_z = floor_top_z + ball_r
        gravity = 9.81
        flight_t = max(0.0, (frame - launch["frame"]) / float(FPS))
        fall_height = max(0.0, launch["z"] - floor_rest_z)
        landing_t = math.sqrt(2.0 * fall_height / gravity) if fall_height > 0.0 else 0.0
        forward_speed = 0.90

        if flight_t <= landing_t:
            ball_x = launch["x"] + forward_speed * flight_t
            ball_z = max(floor_rest_z, launch["z"] - 0.5 * gravity * flight_t * flight_t)
            ball["pb_state"] = "free_falling"
        else:
            post_impact_t = flight_t - landing_t

            # Sliding/rolling friction reduces the forward speed linearly over a
            # little more than a second instead of deleting it at impact.
            roll_stop_t = 1.10
            rolling_t = min(post_impact_t, roll_stop_t)
            rolling_distance = forward_speed * (
                rolling_t - 0.5 * rolling_t * rolling_t / roll_stop_t
            )
            ball_x = launch["x"] + forward_speed * landing_t + rolling_distance

            # Resolve the vertical collision with a modest coefficient of
            # restitution.  Repeated impacts decay geometrically, producing two
            # visible small bounces before the ball settles on the floor.
            restitution = 0.42
            bounce_speed = restitution * gravity * landing_t
            bounce_t = post_impact_t
            ball_z = floor_rest_z
            while bounce_speed >= 0.18:
                bounce_duration = 2.0 * bounce_speed / gravity
                if bounce_t <= bounce_duration:
                    ball_z += max(
                        0.0,
                        bounce_speed * bounce_t - 0.5 * gravity * bounce_t * bounce_t,
                    )
                    break
                bounce_t -= bounce_duration
                bounce_speed *= restitution

            if ball_z > floor_rest_z + 0.01:
                ball["pb_state"] = "bouncing_on_floor"
            elif post_impact_t < roll_stop_t:
                ball["pb_state"] = "rolling_on_floor"
            else:
                ball["pb_state"] = "landed_on_floor"

    ball.location = (ball_x, 0.0, ball_z)
    # Rolling spin about -y (rolls toward +x): angle proportional to distance rolled.
    roll_angle = -(s_ball - s0) / max(ball_r, 1e-6)
    if on_shelf:
        # Save the angular state at take-off so post-impact spin follows the
        # actual horizontal travel and stops together with the ball.
        objs["_ball_launch"]["roll_angle"] = roll_angle
    else:
        launch = objs.get("_ball_launch", {})
        launch_roll = launch.get("roll_angle", roll_angle)
        roll_angle = launch_roll - (ball_x - launch.get("x", ball_x)) / max(ball_r, 1e-6)
    ball.rotation_euler = (0.0, roll_angle, 0.0)
    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)
    ball["pb_never_suspended"] = True


# ============================================================
# Build / animate dispatch
# ============================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "tipping_shelf_drop":
        return build_tipping_shelf_drop_scene()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "tipping_shelf_drop":
            animate_tipping_shelf_drop(objs, frame)
        else:
            raise RuntimeError("Unknown kind: " + str(kind))

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
    objs = build_scene_by_kind()
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
    print("scene_kind:", CASE["scene_kind"])
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
