# -*- coding: utf-8 -*-
import bpy
import os
import json
import math
import shutil
from mathutils import Vector

CASE = json.loads(r"""{
  "item_id": "PB_PENDULUM_BEHIND_POST_0123",
  "scene_kind": "pendulum_behind_post",
  "kind": "pendulum_behind_post",
  "prompt": "A pendulum bob swings back and forth on a rod. An opaque post stands in front of the lowest point of its arc; each time the bob swings past the bottom it disappears behind the post for a moment and re-emerges on the other side -- the same bob, same size -- continuing its swing."
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
        # Order-INDEPENDENT transparency (HASHED / DITHERED). BLEND sorting made
        # the opaque ramp behind the glass flicker/vanish for a frame; hashed
        # transparency has no sort order and TAA (64 samples) resolves it smooth.
        # alpha<0.999 also makes the render pipeline preserve it (not recolor it).
        try:
            mat.blend_method = "HASHED"
            mat.show_transparent_back = False
            mat.use_screen_refraction = False
        except Exception:
            pass
        try:
            mat.surface_render_method = "DITHERED"
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
    MATS["glass"] = make_mat("mat_glass", (0.60, 0.80, 1.0), roughness=0.08, alpha=0.24, transparent=True)


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
# 00000122  pendulum_behind_post  (Cluster: Baillargeonian Occlusion)
# =============================================================================
#
# A rigid pendulum hangs from a FIXED pivot mounted high on a stand. A thin rod
# runs from the pivot down to a spherical bob at its end. The pendulum swings in
# the camera-facing X-Z plane (y = 0):
#
#     theta(t) = A * cos(omega * t)          (theta measured from straight down)
#     bob = pivot + L * ( sin(theta), 0, -cos(theta) )
#
# so theta = 0 is the LOWEST point of the arc (bob straight below the pivot) and
# the bob sweeps from +A (right) through 0 (bottom) to -A (left) and back.
#
# An opaque vertical POST (1.10 wide vs the 0.48 bob) stands slightly in FRONT of the bob's arc (on the
# camera side, at y < 0), centered on x = 0 -- i.e. directly in front of the
# lowest point of the swing. Each time the bob passes near x = 0 it moves behind
# the post's real opaque geometry and is naturally occluded, then re-emerges on
# the other side -- the SAME continuously rendered bob, same radius, continuing
# its swing. The rod stays visible wherever it is not physically covered.
# =============================================================================


def _pendulum_geom():
    # Pivot high up, arm hangs down; the bottom of the arc sits well above the
    # floor. The swing amplitude A is wide enough that the bob spends most of its
    # time OUTSIDE the post silhouette (clearly visible) and only slips behind it
    # briefly near the bottom of each pass.
    pivot = Vector((0.0, 0.0, 3.35))
    arm_length = 2.05
    bob_radius = 0.24
    amplitude = math.radians(52.0)   # swing half-angle
    # Post is an opaque vertical bar in front of the arc, centered on x = 0. Its
    # half-width in X sets the occlusion window: the bob is hidden while
    # |x_bob| <= post_half_x (plus a little for the bob radius margin handled in
    # the animate step).
    post_half_x = 0.55   # half-width of the occluding post; each of the 6 crossings hides the bob fully for 2 frames
    post_front_y = -0.62            # camera side (y<0), in front of the arc plane
    return {
        "pivot": pivot,
        "arm_length": arm_length,
        "bob_radius": bob_radius,
        "amplitude": amplitude,
        "post_half_x": post_half_x,
        "post_front_y": post_front_y,
    }


def _bob_pos(pivot, arm_length, theta):
    # theta from straight-down; +theta swings toward +x. Bottom of arc at theta=0.
    return pivot + Vector((arm_length * math.sin(theta), 0.0, -arm_length * math.cos(theta)))


def build_pendulum_behind_post():
    scene = setup_base(
        camera_loc=(0.0, -9.6, 2.2),
        target=(0.0, 0.0, 1.9),
        ortho_scale=6.9,
    )

    G = _pendulum_geom()
    pivot = G["pivot"]
    arm_length = G["arm_length"]
    bob_radius = G["bob_radius"]
    amplitude = G["amplitude"]
    post_half_x = G["post_half_x"]
    post_front_y = G["post_front_y"]

    # --- Support stand: two legs + a top beam carrying the pivot -------------
    # The stand sits BEHIND the arc plane (y > 0) so it never occludes the swing
    # and never clips the bob. The legs straddle the full swing width.
    leg_x = arm_length * math.sin(amplitude) + 0.85
    beam_z = pivot.z + 0.18
    stand_y = 0.55
    add_cube("stand_leg_left", (-leg_x, stand_y, beam_z / 2.0), (0.16, 0.16, beam_z),
             MATS["support"], "support", "dark_gray")
    add_cube("stand_leg_right", (leg_x, stand_y, beam_z / 2.0), (0.16, 0.16, beam_z),
             MATS["support"], "support", "dark_gray")
    add_cube("stand_top_beam", (0.0, stand_y, beam_z), (2.0 * leg_x + 0.16, 0.16, 0.16),
             MATS["support"], "support", "dark_gray")

    # --- Pivot hub: small dark cylinder at the fixed rotation point ----------
    add_cylinder("pendulum_pivot", (pivot.x, stand_y, pivot.z), 0.10, 0.30,
                 MATS["dark"], "pivot", "dark_gray", rotation=(math.radians(90.0), 0.0, 0.0))

    # --- Rod: thin cylinder from pivot to the bob at rest (theta = 0) --------
    # Created at the rest (straight-down) orientation; animated each frame.
    bob_rest = _bob_pos(pivot, arm_length, 0.0)
    rod = add_cylinder_between("pendulum_rod", pivot, bob_rest, 0.045, MATS["gray"], "rod", "gray")
    rod["pb_can_disappear"] = False

    # --- Bob: the swinging sphere (the TARGET) -------------------------------
    bob = add_sphere("pendulum_bob", bob_radius, bob_rest, MATS["orange"], "orange")
    bob["pb_path"] = "pendulum_swing_repeated_brief_occlusion_behind_post"
    bob["pb_can_disappear"] = False

    # --- Opaque POST in front of the lowest point of the arc -----------------
    # A vertical bar centered on x = 0, standing on the floor and rising
    # above the bottom of the arc so it fully covers the bob as it passes. Placed
    # at y = post_front_y (camera side) so it sits BETWEEN the camera and the arc.
    bottom_z = pivot.z - arm_length            # lowest point of the arc
    post_top = bottom_z + bob_radius + 0.55    # rises above the bob at the bottom
    post_w = 2.0 * post_half_x
    post_depth = 0.20
    add_cube("occluder_post", (0.0, post_front_y, post_top / 2.0),
             (post_w, post_depth, post_top), MATS["housing"], "occluder_post", "gray")
    # Small base foot for the post so it reads as standing, not floating.
    add_cube("occluder_post_foot", (0.0, post_front_y, 0.06),
             (post_w + 0.18, post_depth + 0.14, 0.12), MATS["support"], "support", "dark_gray")

    return scene, {
        "pivot": pivot,
        "arm_length": arm_length,
        "bob_radius": bob_radius,
        "amplitude": amplitude,
        "post_half_x": post_half_x,
        "bob": bob,
        "rod": rod,
    }


def _orient_rod(rod, pivot, bob_pos):
    # Re-aim the rod cylinder (local Z along its length) from pivot to bob, and
    # recentre it at the midpoint. Its length is fixed (arm_length) so we only
    # rotate + translate.
    diff = bob_pos - pivot
    rod.location = (pivot + bob_pos) / 2.0
    rod.rotation_euler = diff.to_track_quat("Z", "Y").to_euler()


def animate_pendulum_behind_post(scene, meta):
    bob = meta["bob"]
    rod = meta["rod"]
    pivot = meta["pivot"]
    arm_length = meta["arm_length"]
    bob_radius = meta["bob_radius"]
    amplitude = meta["amplitude"]
    post_half_x = meta["post_half_x"]

    # Steady swing: theta(t) = A * cos(omega * t). Pick omega so we get multiple
    # passes across the bottom within the 120-frame clip (multiple disappear/
    # re-emerge events, per the prompt "each time ... swings past the bottom").
    # 3 full cycles -> 6 bottom crossings. The ~40-frame period must NOT divide
    # the 60-frame split window, or the target clip would replay the input
    # phase-for-phase and the pair would stop being a prediction task at all.
    # At 3 cycles the split lands on the far swing extreme, so input and target
    # are mirror halves.
    duration = (FRAME_END - FRAME_START) / FPS
    n_swings = 3.0                              # full back-and-forth cycles
    omega = 2.0 * math.pi * n_swings / duration

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)

        t = (frame - FRAME_START) / FPS
        theta = amplitude * math.cos(omega * t)
        bob_pos = _bob_pos(pivot, arm_length, theta)
        # State annotation only. The bob remains rendered; the opaque post
        # provides the actual image-space occlusion.
        # Full occlusion, not mere overlap: the bob's whole silhouette must be
        # inside the post's width.
        inside = abs(bob_pos.x) + bob_radius <= post_half_x

        bob.location = bob_pos
        # Roll the bob a little for readability (spin about its own axis as it swings).
        bob.rotation_euler = (0.0, theta * 2.0, 0.0)
        bob.keyframe_insert(data_path="location", frame=frame)
        bob.keyframe_insert(data_path="rotation_euler", frame=frame)

        # Rod stays visible; re-aim it from the fixed pivot to the current bob.
        _orient_rod(rod, pivot, bob_pos)
        rod.keyframe_insert(data_path="location", frame=frame)
        rod.keyframe_insert(data_path="rotation_euler", frame=frame)

        if inside:
            bob["pb_state"] = "hidden_behind_post_at_bottom_of_arc"
        elif bob_pos.x > 0:
            bob["pb_state"] = "visible_swinging_on_right"
        else:
            bob["pb_state"] = "visible_swinging_on_left"
        bob["pb_theta"] = float(theta)
        bob["pb_occluded"] = bool(inside)

    scene.frame_set(FRAME_START)

# =============================================================================
# Dispatch
# =============================================================================

def build_scene_by_kind():
    kind = CASE.get("scene_kind", CASE.get("kind"))

    if kind == "pendulum_behind_post":
        return build_pendulum_behind_post()

    raise RuntimeError("Unknown scene_kind: " + str(kind))


def animate_scene_by_kind(scene, meta):
    kind = CASE.get("scene_kind", CASE.get("kind"))

    if kind == "pendulum_behind_post":
        return animate_pendulum_behind_post(scene, meta)

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
