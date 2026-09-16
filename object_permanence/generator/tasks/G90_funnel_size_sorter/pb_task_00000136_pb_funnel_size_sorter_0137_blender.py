# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_FUNNEL_SIZE_SORTER_0137",
  "scene_kind": "funnel_size_sorter",
  "prompt": "A funnel (a V-shaped chute) has a small round gap at its bottom apex. A small ball dropped into the funnel rolls down to the apex and passes through the gap, falling to the floor below; a large ball, wider than the gap, rolls down but wedges in the funnel and cannot pass. Neither ball is left suspended."
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


def add_cube(name, location, dimensions, material=None, role="static_solid", color_name="gray", is_dynamic=False, solid=True, rotation=(0.0, 0.0, 0.0)):
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
    MATS["dark"] = make_mat("mat_dark_gray", (0.04, 0.04, 0.05), roughness=0.92)
    MATS["box"] = make_mat("mat_box_gray", (0.38, 0.39, 0.40), roughness=0.78)
    MATS["edge"] = make_mat("mat_light_edge", (0.62, 0.63, 0.64), roughness=0.68)
    MATS["funnel"] = make_mat("mat_funnel_steel", (0.55, 0.57, 0.62), roughness=0.45, metallic=0.25)
    MATS["orange"] = make_mat("mat_orange", (1.0, 0.38, 0.06), roughness=0.30)
    MATS["red"] = make_mat("mat_red", (0.85, 0.12, 0.10), roughness=0.32)
    MATS["backdrop"] = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)
    # Clear glass for the funnel front/back cap panels so the balls inside the funnel
    # are visible through them. Low alpha + BLEND makes it render see-through; the
    # sloped funnel walls (MATS["funnel"]) stay fully opaque.
    MATS["glass"] = make_mat(
        "mat_glass_clear", (0.80, 0.88, 0.94),
        roughness=0.05, alpha=0.20, blend="BLEND",
    )
    # Give the caps STABLE (alpha-scaled) transparent shadows instead of a hard
    # black block, and (below, per-object) disable their shadow casting entirely.
    try:
        MATS["glass"].use_transparent_shadow = True
    except Exception:
        pass


def build_base_scene():
    scene = bpy.context.scene
    set_render(scene)
    build_materials()

    add_cube("large_floor_base", (0.0, 0.0, -0.05), (11.0, 5.2, 0.10), MATS["floor"], role="ground", color_name="warm_beige")
    add_cube("rear_backdrop_panel", (0.0, 2.62, 1.90), (11.4, 0.08, 3.80), MATS["backdrop"], role="background", color_name="off_white")

    bpy.ops.object.light_add(type="AREA", location=(-3.8, -4.4, 5.8))
    key = bpy.context.object
    key.name = "large_softbox_light"
    key.data.energy = 1000
    key.data.size = 6.0

    bpy.ops.object.light_add(type="POINT", location=(3.7, -2.8, 3.4))
    fill = bpy.context.object
    fill.name = "right_fill_light"
    fill.data.energy = 155

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
# V-funnel: two inward-sloping walls meeting near the bottom
# with a REAL gap (width = gap) between their lower edges.
# ============================================================

def create_v_funnel(name, center_x, apex_z, top_z, half_top_width, wall_thick, wall_depth, gap, tilt_deg):
    """Build a V-shaped chute (a funnel cross-section) at center_x.

    Two flat rectangular walls each tilted inward by tilt_deg. Their upper ends are
    spread apart (half_top_width from centre) and their lower ends stop short of the
    centre so that a REAL horizontal gap of width `gap` remains between the two lower
    edges at the apex. A small ball narrower than the gap can pass straight through;
    a wider ball wedges between the two sloping faces.

    center_x : x of the funnel throat centre
    apex_z   : z of the lower (apex) edges of the walls (top of the gap opening)
    top_z    : z of the upper edges (funnel mouth)
    Returns dict with geometry used by the animator.
    """
    tilt = math.radians(tilt_deg)
    wall_h = top_z - apex_z  # vertical span of each wall
    # Slant length of a wall spanning wall_h vertically while tilted by `tilt`.
    slant_len = wall_h / max(0.15, math.cos(tilt))

    # Each wall is a thin slab, long axis along its slant. We build it as a cube of
    # dimensions (wall_thick, wall_depth, slant_len) then tilt it about Y and place
    # it so its INNER FACE runs exactly along the line used by the animator's
    # _wall_surface_x():  inner_x(z) = center_x + side*(gap/2 + tan(tilt)*(z-apex_z)).
    # i.e. lower inner edge at x = center_x +/- gap/2 (z = apex_z, the throat) and the
    # upper inner edge spread outward by tan(tilt)*wall_h (z = top_z, the wide mouth).
    # The wall thickness is added OUTWARD (away from the throat) from that inner face
    # so a ball resting tangent to the face never sinks into the slab.
    walls = []
    for side in (-1, 1):
        # Inner-face endpoints (the surface the balls actually touch):
        bottom_inner_x = center_x + side * (gap / 2.0)                        # at z = apex_z
        top_inner_x = center_x + side * (gap / 2.0 + math.tan(tilt) * wall_h)  # at z = top_z
        mid_inner_x = 0.5 * (bottom_inner_x + top_inner_x)
        mid_z = 0.5 * (apex_z + top_z)
        # Outward face normal (points away from the throat, slightly downward):
        #   up-slant direction is (side*sin(tilt), cos(tilt)); its outward perpendicular
        #   is (side*cos(tilt), -sin(tilt)).
        n_out_x = side * math.cos(tilt)
        n_out_z = -math.sin(tilt)
        # Slab centre = inner-face midpoint offset outward by half the thickness.
        cx = mid_inner_x + n_out_x * (wall_thick / 2.0)
        cz = mid_z + n_out_z * (wall_thick / 2.0)
        # Rotate slab so its long (local Z) axis follows the up-outward slant: local +Z
        # (0,0,1) maps to (sin(rot_y),0,cos(rot_y)); we need (side*sin(tilt),cos(tilt)),
        # hence rot_y = +side*tilt. The opposite sign builds the funnel upside-down
        # -- wide at the bottom, narrow at the top -- and both balls clip straight
        # through the sloping faces.
        rot_y = side * tilt
        wall = add_cube(
            f"{name}_wall_{'L' if side < 0 else 'R'}",
            (cx, center_x * 0.0, cz),
            (wall_thick, wall_depth, slant_len),
            MATS["funnel"],
            role="funnel_wall",
            color_name="steel_gray",
            solid=True,
            rotation=(0.0, rot_y, 0.0),
        )
        wall["pb_is_funnel_wall"] = True
        walls.append(wall)

    # Two end caps (front/back) close the funnel sides so the balls cannot escape
    # sideways and the V reads as a chute. They use a CLEAR GLASS material (transparent)
    # so the balls inside the funnel remain visible through the front and back panels.
    cap_h = wall_h
    cap_z = apex_z + cap_h / 2.0
    for sy in (-1, 1):
        cap = add_cube(
            f"{name}_endcap_{'F' if sy < 0 else 'B'}",
            (center_x, sy * (wall_depth / 2.0 + 0.06), cap_z),
            (2.0 * half_top_width, 0.04, cap_h),
            MATS["glass"],
            role="funnel_endcap",
            color_name="clear_glass",
            solid=True,
        )
        cap["pb_transparent"] = True
        # Left casting shadows, the clear BLEND caps throw a hard black shadow
        # (EEVEE-Next transparent-shadow of a low-alpha panel) that pops as a ball
        # moves behind them. A thin sheet of clear glass realistically casts almost
        # nothing, so the caps cast no shadow at all -> nothing appears or
        # disappears mid-clip.
        try:
            cap.visible_shadow = False
        except Exception:
            pass

    return {
        "center_x": center_x,
        "apex_z": apex_z,
        "top_z": top_z,
        "gap": gap,
        "half_top_width": half_top_width,
        "tilt": tilt,
        "walls": walls,
    }


def build_funnel_support(name, center_x, apex_z, wall_depth, half_top_width):
    """Four legs holding the funnel above the floor so the small ball has clear space
    to fall through the apex gap down to the floor below."""
    leg_h = apex_z - 0.06
    leg_z = leg_h / 2.0
    inset_x = half_top_width - 0.10
    inset_y = wall_depth / 2.0 - 0.04
    for sx in (-inset_x, inset_x):
        for sy in (-inset_y, inset_y):
            add_cube(
                f"{name}_leg_{('e' if sx > 0 else 'w')}{('b' if sy > 0 else 'f')}",
                (center_x + sx, sy, leg_z),
                (0.10, 0.10, leg_h),
                MATS["edge"],
                role="funnel_leg",
                color_name="light_gray",
                solid=True,
            )


# ============================================================
# 0137 funnel size sorter
# ============================================================

def build_funnel_size_sorter_scene():
    scene = build_base_scene()
    # 3/4 view, moderately elevated, angled so the apex gap and the small ball passing
    # through it are clearly visible. Aimed between the two funnels at throat height.
    setup_camera(scene, location=(0.0, -8.2, 3.6), target=(0.0, 0.0, 1.7), lens=38)

    APEX_Z = 1.55            # top of the apex gap (lower edges of walls)
    TOP_Z = 3.05             # funnel mouth height
    HALF_TOP = 1.05          # half-width of the funnel mouth
    WALL_THICK = 0.10
    WALL_DEPTH = 1.10
    TILT_DEG = 30.0          # inward tilt of walls from vertical

    SMALL_GAP = 0.62         # small funnel apex gap  (small ball passes)
    LARGE_GAP = 0.62         # large funnel apex gap  (large ball too wide -> wedges)
    # NOTE: the animator reuses small_gap for the LARGE funnel's wall-tangency and
    # wedge math; that is only correct while LARGE_GAP == SMALL_GAP.

    SMALL_FUNNEL_X = -2.0
    LARGE_FUNNEL_X = 2.0

    # Two side-by-side funnels sharing identical geometry: only the ball size differs.
    small_funnel = create_v_funnel(
        "small_funnel", SMALL_FUNNEL_X, APEX_Z, TOP_Z, HALF_TOP, WALL_THICK, WALL_DEPTH, SMALL_GAP, TILT_DEG
    )
    build_funnel_support("small_funnel", SMALL_FUNNEL_X, APEX_Z, WALL_DEPTH, HALF_TOP)

    large_funnel = create_v_funnel(
        "large_funnel", LARGE_FUNNEL_X, APEX_Z, TOP_Z, HALF_TOP, WALL_THICK, WALL_DEPTH, LARGE_GAP, TILT_DEG
    )
    build_funnel_support("large_funnel", LARGE_FUNNEL_X, APEX_Z, WALL_DEPTH, HALF_TOP)

    SMALL_R = 0.24  # diameter 0.48 < gap 0.62 -> passes through apex gap
    LARGE_R = 0.46  # diameter 0.92 > gap 0.62 -> wedges between the sloping walls

    # Small ball: dropped into the LEFT funnel mouth.
    small = add_sphere(
        "small_orange_ball_narrower_than_gap",
        SMALL_R,
        (SMALL_FUNNEL_X, 0.0, TOP_Z + SMALL_R + 0.3),
        MATS["orange"],
        "orange",
        role="small_ball_passes_gap",
    )
    small["pb_narrower_than_gap"] = True
    small["pb_expected_behavior"] = "rolls_to_apex_then_falls_through_gap"

    # Large ball: dropped into the RIGHT funnel mouth.
    large = add_sphere(
        "large_red_ball_wider_than_gap",
        LARGE_R,
        (LARGE_FUNNEL_X, 0.0, TOP_Z + LARGE_R + 0.3),
        MATS["red"],
        "red",
        role="large_ball_wedges_in_funnel",
    )
    large["pb_wider_than_gap"] = True
    large["pb_expected_behavior"] = "rolls_down_then_wedges_cannot_pass"

    return {
        "scene": scene,
        "kind": "funnel_size_sorter",
        "small": small,
        "large": large,
        "small_funnel": small_funnel,
        "large_funnel": large_funnel,
        "apex_z": APEX_Z,
        "top_z": TOP_Z,
        "small_r": SMALL_R,
        "large_r": LARGE_R,
        "small_funnel_x": SMALL_FUNNEL_X,
        "large_funnel_x": LARGE_FUNNEL_X,
        "small_gap": SMALL_GAP,
        "tilt": math.radians(TILT_DEG),
    }


def _wall_surface_x(center_x, side, z, apex_z, tilt, gap):
    """x-coordinate of the inner face of a funnel wall at height z.
    side = -1 (left wall) or +1 (right wall). Below apex the inner faces continue to
    the throat; a ball centre resting against a wall sits at this x offset inward."""
    return center_x + side * (gap / 2.0 + math.tan(tilt) * max(0.0, z - apex_z))


def _wall_tangent_ball_center(center_x, side, face_z, radius, apex_z, tilt, gap):
    """Ball center exactly one radius inward from a sloped funnel face."""
    face_x = _wall_surface_x(center_x, side, face_z, apex_z, tilt, gap)
    return Vector((
        face_x - side * radius * math.cos(tilt),
        0.0,
        face_z + radius * math.sin(tilt),
    ))


def animate_funnel_size_sorter(objs, frame):
    small = objs["small"]
    large = objs["large"]
    apex_z = objs["apex_z"]
    top_z = objs["top_z"]
    small_r = objs["small_r"]
    large_r = objs["large_r"]
    small_x = objs["small_funnel_x"]
    large_x = objs["large_funnel_x"]
    tilt = objs["tilt"]
    small_gap = objs["small_gap"]

    floor_land_z = small_r + 0.0  # small ball rests on the floor (z=0 top surface)

    # ---- SMALL BALL (LEFT funnel) ----
    # P1: drop vertically to an exact tangent point on the left wall.
    # P2: roll down while staying exactly tangent to that same wall.
    # P3: leave the lower wall edge, move into the clear centre of the gap, then fall.
    small_drop_start = 1
    small_drop_end = 16
    small_roll_end = 44
    small_center_end = 54
    small_fall_end = 92

    small_entry_face_z = top_z - 0.30
    small_entry = _wall_tangent_ball_center(
        small_x, -1, small_entry_face_z, small_r, apex_z, tilt, small_gap
    )
    small_release = _wall_tangent_ball_center(
        small_x, -1, apex_z, small_r, apex_z, tilt, small_gap
    )
    # At this height the full horizontal cross-section of the ball fits inside
    # the throat, so the subsequent vertical fall cannot clip either lower edge.
    small_gap_center = Vector((small_x, 0.0, apex_z - small_r * 0.25))
    small_start_z = top_z + small_r + 0.05

    if frame <= small_drop_end:
        t = ease_in_quad((frame - small_drop_start) / float(small_drop_end - small_drop_start))
        sx = small_entry.x
        sz = lerp(small_start_z, small_entry.z, t)
        s_state = "dropping_into_funnel_mouth"
    elif frame <= small_roll_end:
        t = smooth01((frame - small_drop_end) / float(small_roll_end - small_drop_end))
        face_z = lerp(small_entry_face_z, apex_z, t)
        tangent_pos = _wall_tangent_ball_center(
            small_x, -1, face_z, small_r, apex_z, tilt, small_gap
        )
        sx, sz = tangent_pos.x, tangent_pos.z
        s_state = "rolling_down_to_apex"
    elif frame <= small_center_end:
        t = smooth01((frame - small_roll_end) / float(small_center_end - small_roll_end))
        sx = lerp(small_release.x, small_gap_center.x, t)
        sz = lerp(small_release.z, small_gap_center.z, t)
        s_state = "rolling_off_lower_edge_into_gap"
    else:
        sx = small_x
        ft = ease_in_quad((frame - small_center_end) / float(small_fall_end - small_center_end))
        sz = lerp(small_gap_center.z, floor_land_z, ft)
        sz = max(floor_land_z, sz)
        s_state = "falling_through_gap" if sz > floor_land_z + 0.01 else "settled_on_floor_below"

    small.location = (sx, 0.0, sz)
    small.rotation_euler = (0.0, -0.18 * frame, 0.0)
    small.keyframe_insert(data_path="location", frame=frame)
    small.keyframe_insert(data_path="rotation_euler", frame=frame)
    small["pb_state"] = s_state
    small["pb_never_suspended"] = True

    # ---- LARGE BALL (RIGHT funnel) ----
    # Staggered start. P1 (30-46): drop into the funnel mouth onto a wall.
    # P2 (46-80): roll DOWN the V until it WEDGES. Its wedge height is where the two
    #   sloping inner faces are tangent to the ball (perpendicular centre-to-face
    #       distance == large_r):
    #       z_wedge = apex + (large_r - (gap/2)*cos(tilt)) / sin(tilt)
    #   the ball surface is tangent to BOTH sloping inner faces. Using the PERPENDICULAR
    #   distance from the on-axis centre to a face (not the horizontal span):
    #       perp(z) = (gap/2)*cos(tilt) + (z-apex)*sin(tilt) == large_r  ->
    #       z_wedge = apex + (large_r - (gap/2)*cos(tilt)) / sin(tilt)
    #   Both flanks touch the walls (centre-to-face == radius), so it is fully supported
    #   (never suspended, cannot pass the gap) and does NOT sink into the walls.
    large_drop_start = 30
    large_drop_end = 46
    large_roll_end = 80

    large_start_z = top_z + large_r + 0.05
    large_entry_face_z = top_z - 0.25
    large_entry = _wall_tangent_ball_center(
        large_x, -1, large_entry_face_z, large_r, apex_z, tilt, small_gap
    )

    # Wedge height (ball centre) where the ball surface is tangent to both inner faces:
    # perpendicular centre-to-face distance == large_r.
    z_wedge = apex_z + (large_r - (small_gap / 2.0) * math.cos(tilt)) / max(1e-4, math.sin(tilt))
    z_wedge = max(apex_z + large_r * 0.4, z_wedge)  # keep it clearly above the apex
    wedge_face_z = z_wedge - large_r * math.sin(tilt)

    if frame <= large_drop_start:
        lx = large_entry.x
        lz = large_start_z
        l_state = "waiting_above_funnel"
    elif frame <= large_drop_end:
        t = ease_in_quad((frame - large_drop_start) / float(large_drop_end - large_drop_start))
        lx = large_entry.x
        lz = lerp(large_start_z, large_entry.z, t)
        l_state = "dropping_into_funnel_mouth"
    elif frame <= large_roll_end:
        t = smooth01((frame - large_drop_end) / float(large_roll_end - large_drop_end))
        face_z = lerp(large_entry_face_z, wedge_face_z, t)
        tangent_pos = _wall_tangent_ball_center(
            large_x, -1, face_z, large_r, apex_z, tilt, small_gap
        )
        lx, lz = tangent_pos.x, tangent_pos.z
        l_state = "rolling_down_toward_apex"
    else:
        lx = large_x
        lz = z_wedge
        l_state = "wedged_between_walls_cannot_pass"

    large.location = (lx, 0.0, lz)
    large.rotation_euler = (0.0, -0.14 * frame, 0.0)
    large.keyframe_insert(data_path="location", frame=frame)
    large.keyframe_insert(data_path="rotation_euler", frame=frame)
    large["pb_state"] = l_state
    large["pb_wedged"] = bool(frame > large_roll_end)
    large["pb_never_suspended"] = True


# ============================================================
# Build / animate dispatch
# ============================================================

def build_scene_by_kind():
    kind = CASE["scene_kind"]
    if kind == "funnel_size_sorter":
        return build_funnel_size_sorter_scene()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene(objs):
    scene = objs["scene"]
    kind = objs["kind"]

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        if kind == "funnel_size_sorter":
            animate_funnel_size_sorter(objs, frame)
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
