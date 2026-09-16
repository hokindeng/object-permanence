# -*- coding: utf-8 -*-
import bpy
import math
import os
import json
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_CORNER_TURN_OCCLUSION_0150",
  "scene_kind": "corner_turn_occlusion",
  "kind": "corner_turn_occlusion",
  "prompt": "A ball rolls along a track whose rounded corner connects two perpendicular straight sections. It follows the curved rails behind a solid corner pillar, becomes hidden, then re-emerges on the second straight section as the same ball continuing its journey."
}""")
ITEM_ID = CASE["item_id"]

FPS = 24
FRAME_START = 1
FRAME_END = 120

BALL_RADIUS = 0.24

# L-track layout. Leg A runs along +x at y = LEG_A_Y; the bend is centered at
# (BEND_X, BEND_Y); leg B runs along +y (away from camera) at x = LEG_B_X.
TRACK_Z = 0.70
RAIL_RADIUS = 0.035
RAIL_HALF_GAUGE = 0.13
# Sphere tangent to both rail tubes: the centre-to-centre distance from the
# ball to either tube is BALL_RADIUS + RAIL_RADIUS.
BALL_Z = TRACK_Z + math.sqrt(
    (BALL_RADIUS + RAIL_RADIUS) ** 2 - RAIL_HALF_GAUGE ** 2
)

LEG_A_Y = -1.2          # near the camera
LEG_A_X0 = -3.4         # ball starts here
BEND_X = 1.15           # x of the bend / of leg B
BEND_Y = LEG_A_Y
LEG_B_X = BEND_X
LEG_B_Y1 = 2.4          # ball ends here (deeper into scene, +y)

BEND_R = 0.9            # turn radius of the ball path at the corner

# Opaque corner pillar sits in FRONT of the bend arc (on the camera / -y side),
# between the camera and the ball's rounded path, tall/wide enough to hide the
# ball as it rounds the corner. It is pushed toward the camera so its volume
# never intersects the ball's arc (clearance >= ball_radius at every frame) yet
# still lies on the line of sight from the camera to the corner.
PILLAR_X = 0.70
PILLAR_Y = -2.00

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
        mat.alpha_threshold = 0.01
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


def add_cube(name, location, dimensions, rotation=(0, 0, 0), material=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    if material is not None:
        obj.data.materials.append(material)

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
    except Exception:
        pass

    try:
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


def build_straight_track(name_prefix, orient, along0, along1, fixed, mat_rail, mat_tie):
    # orient "x": rail runs along x at y=fixed. orient "y": rail runs along y at x=fixed.
    parts = []
    z = TRACK_Z
    if orient == "x":
        p0f = (along0, fixed - RAIL_HALF_GAUGE, z)
        p0b = (along0, fixed + RAIL_HALF_GAUGE, z)
        p1f = (along1, fixed - RAIL_HALF_GAUGE, z)
        p1b = (along1, fixed + RAIL_HALF_GAUGE, z)
    else:
        p0f = (fixed - RAIL_HALF_GAUGE, along0, z)
        p0b = (fixed + RAIL_HALF_GAUGE, along0, z)
        p1f = (fixed - RAIL_HALF_GAUGE, along1, z)
        p1b = (fixed + RAIL_HALF_GAUGE, along1, z)

    for tag_n, pa, pb in [("front", p0f, p1f), ("back", p0b, p1b)]:
        pa = Vector(pa); pb = Vector(pb)
        diff = pb - pa
        length = diff.length
        mid = (pa + pb) / 2.0
        bpy.ops.mesh.primitive_cylinder_add(radius=RAIL_RADIUS, depth=length, vertices=24, location=mid)
        rail = bpy.context.object
        rail.name = f"{name_prefix}_{tag_n}_tube"
        rail.rotation_euler = diff.to_track_quat("Z", "Y").to_euler()
        rail.data.materials.append(mat_rail)
        tag(rail, rail.name, "track_tube", "static_solid", "cylinder", "neutral_gray", False, solid=True)
        parts.append(rail)

    # Cross ties.
    n = 9
    for i in range(n):
        frac = (i + 0.5) / n
        a = lerp(along0, along1, frac)
        if orient == "x":
            loc = (a, fixed, z - 0.045)
            dims = (0.055, 0.40, 0.045)
        else:
            loc = (fixed, a, z - 0.045)
            dims = (0.40, 0.055, 0.045)
        tie = add_cube(f"{name_prefix}_tie_{i:02d}", loc, dims, material=mat_tie)
        tag(tie, tie.name, "track_tie", "static_solid", "cube", "dark_gray", False, solid=True)
        parts.append(tie)
    return parts


def build_curved_track(mat_rail, mat_tie):
    """Build the missing quarter-circle rails around the L-track corner."""
    parts = []
    arc_cx = LEG_B_X - BEND_R
    arc_cy = LEG_A_Y + BEND_R
    segments = 32

    for side_name, offset in (("left", RAIL_HALF_GAUGE), ("right", -RAIL_HALF_GAUGE)):
        points = []
        for i in range(segments + 1):
            theta = 0.5 * math.pi * i / segments
            path_x = arc_cx + BEND_R * math.sin(theta)
            path_y = arc_cy - BEND_R * math.cos(theta)
            # Left normal of the path tangent (cos(theta), sin(theta)).
            nx, ny = -math.sin(theta), math.cos(theta)
            points.append(Vector((
                path_x + offset * nx,
                path_y + offset * ny,
                TRACK_Z,
            )))

        for i, (pa, pb) in enumerate(zip(points[:-1], points[1:])):
            diff = pb - pa
            bpy.ops.mesh.primitive_cylinder_add(
                radius=RAIL_RADIUS,
                depth=diff.length,
                vertices=24,
                location=(pa + pb) / 2.0,
            )
            rail = bpy.context.object
            rail.name = f"bend_track_{side_name}_tube_{i:02d}"
            rail.rotation_euler = diff.to_track_quat("Z", "Y").to_euler()
            rail.data.materials.append(mat_rail)
            tag(rail, rail.name, "track_tube", "static_solid", "cylinder", "neutral_gray", False, solid=True)
            parts.append(rail)

    for i in range(9):
        theta = 0.5 * math.pi * (i + 0.5) / 9.0
        path_x = arc_cx + BEND_R * math.sin(theta)
        path_y = arc_cy - BEND_R * math.cos(theta)
        tie = add_cube(
            f"bend_track_tie_{i:02d}",
            (path_x, path_y, TRACK_Z - 0.045),
            (0.055, 0.40, 0.045),
            rotation=(0.0, 0.0, theta),
            material=mat_tie,
        )
        tag(tie, tie.name, "track_tie", "static_solid", "cube", "dark_gray", False, solid=True)
        parts.append(tie)

    return parts


def build_scene():
    scene = bpy.context.scene
    set_render(scene)

    mat_floor = make_mat("mat_floor_warm", (0.82, 0.80, 0.75), roughness=0.82)
    mat_rail = make_mat("mat_track_tubes", (0.46, 0.46, 0.46), roughness=0.58)
    mat_tie = make_mat("mat_track_ties", (0.28, 0.28, 0.28), roughness=0.74)
    mat_pillar = make_mat("mat_opaque_corner_pillar", (0.30, 0.31, 0.33), roughness=0.82)
    mat_ball = make_mat("mat_red_ball", (0.95, 0.15, 0.10), roughness=0.30)
    mat_backdrop = make_mat("mat_backdrop", (0.96, 0.97, 0.98), roughness=0.90)

    floor = add_cube("large_floor_base", (0.0, 0.4, -0.04), (9.2, 7.2, 0.10), material=mat_floor)
    tag(floor, floor.name, "ground", "static_solid", "cube", "warm_beige", False, solid=True)

    backdrop = add_cube("rear_backdrop_panel", (0.0, 4.2, 1.55), (9.2, 0.08, 3.1), material=mat_backdrop)
    tag(backdrop, backdrop.name, "background", "static_solid", "cube", "off_white", False, solid=True)

    # Leg A: straight rail along +x, near the camera. Leg B: straight rail along
    # +y, deeper into the scene. They meet at the bend.
    arc_cx = LEG_B_X - BEND_R
    arc_cy = LEG_A_Y + BEND_R
    leg_a = build_straight_track("leg_a_track", "x", LEG_A_X0 - 0.2, arc_cx, LEG_A_Y, mat_rail, mat_tie)
    leg_b = build_straight_track("leg_b_track", "y", arc_cy, LEG_B_Y1 + 0.2, LEG_B_X, mat_rail, mat_tie)
    bend = build_curved_track(mat_rail, mat_tie)

    # Opaque CORNER PILLAR standing in FRONT of the bend (on the camera side),
    # between the camera and the arc. Wide and tall enough to fully hide the
    # ball as it rounds the corner. It sits well to the -y (camera) side of the
    # arc so its volume never intersects the ball path, which curves behind it.
    pillar_h = 1.9
    pillar = add_cube(
        "opaque_corner_pillar",
        (PILLAR_X, PILLAR_Y, TRACK_Z + pillar_h / 2.0 - 0.02),
        (1.3, 0.9, pillar_h),
        material=mat_pillar,
    )
    tag(pillar, pillar.name, "corner_occluder", "static_solid", "cube", "gray", False, solid=True, pb_occludes=True)

    # Red ball at the start of leg A.
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=BALL_RADIUS,
                                         location=(LEG_A_X0, LEG_A_Y, BALL_Z))
    ball = bpy.context.object
    ball.name = "corner_turn_red_ball"
    ball.data.materials.append(mat_ball)
    tag(ball, ball.name, "target", "dynamic_object", "sphere", "red", True, solid=True,
        pb_radius=BALL_RADIUS, pb_path="L_track_rounds_corner_behind_pillar",
        pb_tangent_to_both_rails=True, pb_vertical_rail_clearance=0.0)

    # Lights.
    bpy.ops.object.light_add(type="AREA", location=(-2.8, -3.9, 5.8))
    key_light = bpy.context.object
    key_light.name = "large_softbox_light"
    key_light.data.energy = 850
    key_light.data.size = 5.8

    bpy.ops.object.light_add(type="POINT", location=(3.7, -2.8, 3.4))
    fill_light = bpy.context.object
    fill_light.name = "right_fill_light"
    fill_light.data.energy = 135

    # Camera: front view, slightly right and raised, so both legs are visible
    # and the pillar sits between camera and the corner arc.
    bpy.ops.object.camera_add(location=(-3.0, -7.4, 3.0))
    camera = bpy.context.object
    camera.name = "camera_corner_turn"
    camera.data.lens = 32
    look_at(camera, (0.1, 0.4, 0.9))
    camera.data.dof.use_dof = False
    scene.camera = camera

    return {
        "scene": scene,
        "ball": ball,
        "leg_a": leg_a + bend,
        "leg_b": leg_b,
        "pillar": pillar,
    }


def ball_pose_at_u(u):
    # u in [0,1] over the whole L path. The path = straight leg A (along +x to
    # the pre-bend point), a quarter-circle arc of radius BEND_R, then straight
    # leg B (along +y). Arc center is offset from the bend so the ball path bows
    # OUTWARD (toward the camera / -y and toward +x) around the inside pillar.
    # Arc goes from heading +x to heading +y (a left turn into the scene).
    #
    # Pre-bend point on leg A (where the arc starts): the arc is tangent to
    # leg A, so its start is at x = arc_cx, y = LEG_A_Y, and tangent to leg B at
    # x = LEG_B_X, y = arc_cy.
    arc_cx = LEG_B_X - BEND_R      # arc center x
    arc_cy = LEG_A_Y + BEND_R      # arc center y
    # Path segment lengths.
    la = arc_cx - LEG_A_X0          # straight leg A length
    lc = 0.5 * math.pi * BEND_R     # arc length
    lb = LEG_B_Y1 - arc_cy          # straight leg B length
    total = la + lc + lb
    d = u * total

    if d <= la:
        x = LEG_A_X0 + d
        y = LEG_A_Y
        heading = 0.0
    elif d <= la + lc:
        s = d - la
        theta = s / BEND_R          # 0 -> pi/2
        # Center at (arc_cx, arc_cy). Start of arc (theta=0) is at
        # (arc_cx, arc_cy - BEND_R) = (arc_cx, LEG_A_Y); end (theta=pi/2) at
        # (arc_cx + BEND_R, arc_cy) = (LEG_B_X, arc_cy). This bows the path in
        # +x/-y away from the inside pillar corner.
        x = arc_cx + BEND_R * math.sin(theta)
        y = arc_cy - BEND_R * math.cos(theta)
        heading = theta
    else:
        s = d - la - lc
        x = LEG_B_X
        y = arc_cy + s
        heading = math.pi / 2.0

    return x, y, heading, d


def animate_scene(scene, ball, leg_a, leg_b, pillar):
    rest = 6
    move_frames = float(FRAME_END - 2 * rest)

    # Determine total path length once (for rolling spin).
    _, _, _, _ = ball_pose_at_u(0.0)

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        if frame <= rest:
            u = 0.0
        elif frame >= FRAME_END - rest:
            u = 1.0
        else:
            u = smooth01((frame - rest) / move_frames)

        x, y, heading, d = ball_pose_at_u(u)
        ball.location = (x, y, BALL_Z)
        # Rolling: spin about the axis perpendicular to travel direction, in the
        # ground plane. Travel dir = (cos h, sin h). Roll axis = (-sin h, cos h).
        # Approximate no-slip by spinning about z-tilted axis; use total distance
        # to drive a spin about the horizontal axis perpendicular to heading.
        spin = -d / BALL_RADIUS
        ball.rotation_euler = (spin * math.sin(heading), -spin * math.cos(heading), 0.0)
        ball.keyframe_insert(data_path="location", frame=frame)
        ball.keyframe_insert(data_path="rotation_euler", frame=frame)

        # Hidden band: while rounding the corner (arc region), the pillar sits
        # between camera and ball. Tag by whether the ball is near the bend.
        near_bend = (abs(x - BEND_X) < 1.1) and (abs(y - BEND_Y) < 1.1)
        if near_bend:
            ball["pb_state"] = "hidden_behind_corner_pillar"
        elif y > BEND_Y + 0.6:
            ball["pb_state"] = "reemerged_on_leg_b"
        else:
            ball["pb_state"] = "approaching_on_leg_a"
        ball["pb_occluded"] = bool(near_bend)
        ball["pb_pos_x"] = float(x)
        ball["pb_pos_y"] = float(y)

        for obj in leg_a + leg_b:
            obj["pb_state"] = "static_L_track"
        pillar["pb_state"] = "static_opaque_corner_pillar"

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
        "scene_file": f"{ITEM_ID}_scene.blend",
    }

    with open(TASK_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(task, f, indent=2, ensure_ascii=False)


def save_scene():
    bpy.ops.wm.save_as_mainfile(filepath=SCENE_FILE)


def build_scene_by_kind():
    kind = CASE.get("scene_kind", CASE.get("kind"))
    if kind == "corner_turn_occlusion":
        return build_scene()
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(objs):
    kind = CASE.get("scene_kind", CASE.get("kind"))
    if kind == "corner_turn_occlusion":
        return animate_scene(objs["scene"], objs["ball"], objs["leg_a"], objs["leg_b"], objs["pillar"])
    raise RuntimeError("Unknown scene_kind: " + str(kind))


def main():
    ensure_dirs()
    clear_scene()

    objs = build_scene_by_kind()
    scene = objs["scene"]

    animate_scene_by_kind(objs)

    render_png(scene, 1, INPUT_FRAME_PATH)
    render_png(scene, 60, OPTIONAL_FRAME_PATH)
    render_png(scene, 120, OPTIONAL_FRAME_02B_PATH)

    render_animation(scene)
    write_task_json()
    save_scene()

    print("=" * 100)
    print("DONE:", ITEM_ID)
    print("scene_kind:", CASE.get("scene_kind"))
    print("Output:", OUT_DIR)
    print("=" * 100)


if __name__ == "__main__":
    main()
