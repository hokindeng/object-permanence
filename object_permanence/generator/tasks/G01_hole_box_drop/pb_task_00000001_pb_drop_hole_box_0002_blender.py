# pb_drop_hole_box_blender.py
# WROP canonical generator
# Item: PB_DROP_HOLE_BOX_0002
#
# Scene:
#   A semi-transparent acrylic box has a circular hole in the center of its top lid.
#   A colored ball is above the hole.
#   The ball naturally falls downward through the hole, rebounds twice with
#   diminishing height from the box floor, and settles inside the box.

import bpy
import math
import os
import json
import shutil
from mathutils import Vector

# ============================================================
# 0. Project / item / output config
# ============================================================
ITEM_ID = "PB_DROP_HOLE_BOX_0002"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
OUTPUT_ROOT = os.path.join(PROJECT_ROOT, "permanence_blender_outputs")
OUT_DIR = os.path.join(OUTPUT_ROOT, ITEM_ID)

os.makedirs(OUT_DIR, exist_ok=True)

# ============================================================
# 1. Scene constants
# ============================================================
FPS = 24
FRAME_START = 1
FRAME_END = 120

BOX_SIZE = 2.7
BOX_HEIGHT = 1.35
WALL_THICKNESS = 0.075
LID_THICKNESS = 0.08

HOLE_RADIUS = 0.42

BALL_RADIUS = 0.23
BALL_START_Z = 3.05
BALL_FINAL_Z = WALL_THICKNESS + BALL_RADIUS + 0.025

FALL_START_FRAME = 1
LAND_FRAME = 92
FIRST_BOUNCE_FRAMES = 18
SECOND_BOUNCE_FRAMES = 10
FIRST_BOUNCE_HEIGHT = 0.24
SECOND_BOUNCE_HEIGHT = 0.07

INPUT_FRAME_1 = 1
OPTIONAL_FRAME_2 = 38
OPTIONAL_INSIDE_FRAME_2B = 68

# ============================================================
# 2. Utilities
# ============================================================
def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

def make_mat(
    name,
    color,
    roughness=0.55,
    metallic=0.0,
    alpha=1.0,
    transmission_like=False
):
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

            # Blender versions differ in shader socket names.
            # These are optional and safely ignored if unavailable.
            if transmission_like:
                if "Transmission Weight" in bsdf.inputs:
                    bsdf.inputs["Transmission Weight"].default_value = 0.25
                if "Transmission" in bsdf.inputs:
                    bsdf.inputs["Transmission"].default_value = 0.25
                if "IOR" in bsdf.inputs:
                    bsdf.inputs["IOR"].default_value = 1.45
    except Exception:
        pass

    # Transparency settings for Eevee / viewport / render compatibility.
    try:
        mat.blend_method = "BLEND"
        mat.use_screen_refraction = True
        mat.show_transparent_back = True
        mat.alpha_threshold = 0.01
    except Exception:
        pass

    return mat

def add_cube(name, location, dimensions, rotation=(0, 0, 0), material=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material is not None:
        obj.data.materials.append(material)
    return obj

def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

def ball_z_at_frame(frame):
    """
    Deterministic gravity-like vertical motion:
    - Starts above the hole.
    - Accelerates downward.
    - Lands inside the transparent box.
    - Makes two clearly visible, diminishing rebounds after contact.
    """
    if frame <= LAND_FRAME:
        t = (frame - FALL_START_FRAME) / max(1, (LAND_FRAME - FALL_START_FRAME))
        t = max(0.0, min(1.0, t))

        # Quadratic acceleration: visually like gravity.
        z = BALL_START_Z + (BALL_FINAL_Z - BALL_START_Z) * (t ** 2)
        return z

    # Two explicit ballistic-looking arcs keep both impacts and both apices
    # visible even in preview renders that sample every sixth source frame.
    first_end = LAND_FRAME + FIRST_BOUNCE_FRAMES
    if frame <= first_end:
        phase = (frame - LAND_FRAME) / FIRST_BOUNCE_FRAMES
        return BALL_FINAL_Z + FIRST_BOUNCE_HEIGHT * math.sin(math.pi * phase)

    second_end = first_end + SECOND_BOUNCE_FRAMES
    if frame <= second_end:
        phase = (frame - first_end) / SECOND_BOUNCE_FRAMES
        return BALL_FINAL_Z + SECOND_BOUNCE_HEIGHT * math.sin(math.pi * phase)

    return BALL_FINAL_Z

# ============================================================
# 3. Build circular-hole square lid mesh
# ============================================================
def create_square_lid_with_circular_hole(
    name,
    size,
    hole_radius,
    thickness,
    z_center,
    segments,
    material
):
    """
    Build a square plate with a real circular hole.

    The mesh contains:
    - top ring surface
    - bottom ring surface
    - inner circular wall
    - outer square-side wall

    This avoids unreliable boolean operations and keeps the hole explicit.
    """
    half = size / 2.0
    top_z = z_center + thickness / 2.0
    bot_z = z_center - thickness / 2.0

    verts = []
    faces = []

    outer_top = []
    inner_top = []
    outer_bot = []
    inner_bot = []

    for i in range(segments):
        theta = 2.0 * math.pi * i / segments
        c = math.cos(theta)
        s = math.sin(theta)

        # Ray from center intersects square boundary.
        scale_to_square = half / max(abs(c), abs(s))
        ox = scale_to_square * c
        oy = scale_to_square * s

        ix = hole_radius * c
        iy = hole_radius * s

        outer_top.append(len(verts))
        verts.append((ox, oy, top_z))

        inner_top.append(len(verts))
        verts.append((ix, iy, top_z))

        outer_bot.append(len(verts))
        verts.append((ox, oy, bot_z))

        inner_bot.append(len(verts))
        verts.append((ix, iy, bot_z))

    for i in range(segments):
        j = (i + 1) % segments

        # Top ring surface.
        faces.append((outer_top[i], outer_top[j], inner_top[j], inner_top[i]))

        # Bottom ring surface.
        faces.append((outer_bot[j], outer_bot[i], inner_bot[i], inner_bot[j]))

        # Inner circular wall of the hole.
        faces.append((inner_top[i], inner_top[j], inner_bot[j], inner_bot[i]))

        # Outer square boundary wall.
        faces.append((outer_top[j], outer_top[i], outer_bot[i], outer_bot[j]))

    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)

    if material is not None:
        obj.data.materials.append(material)

    return obj

# ============================================================
# 4. Build clean scene
# ============================================================
clear_scene()

# Materials
mat_acrylic = make_mat(
    "semi_transparent_blue_acrylic",
    (0.35, 0.72, 1.0),
    roughness=0.18,
    alpha=0.28,
    transmission_like=True
)

mat_acrylic_edge = make_mat(
    "darker_transparent_acrylic_edges",
    (0.12, 0.38, 0.70),
    roughness=0.25,
    alpha=0.42,
    transmission_like=True
)

mat_ball = make_mat(
    "glossy_orange_ball",
    (1.0, 0.36, 0.04),
    roughness=0.28,
    alpha=1.0
)

mat_hole_rim = make_mat(
    "dark_hole_rim",
    (0.02, 0.025, 0.03),
    roughness=0.48,
    alpha=1.0
)

mat_floor = make_mat(
    "matte_warm_floor",
    (0.82, 0.80, 0.75),
    roughness=0.78,
    alpha=1.0
)

mat_inside_pad = make_mat(
    "soft_inside_landing_pad",
    (0.92, 0.90, 0.84),
    roughness=0.86,
    alpha=1.0
)

# Ground plane / table
add_cube(
    "large_table_floor",
    location=(0.0, 0.0, -0.055),
    dimensions=(5.8, 5.2, 0.11),
    material=mat_floor
)

# Transparent box bottom panel
add_cube(
    "transparent_box_bottom_panel",
    location=(0.0, 0.0, WALL_THICKNESS / 2.0),
    dimensions=(BOX_SIZE, BOX_SIZE, WALL_THICKNESS),
    material=mat_acrylic
)

# Four transparent side walls
wall_z_center = WALL_THICKNESS + BOX_HEIGHT / 2.0

add_cube(
    "transparent_box_front_wall",
    location=(0.0, -BOX_SIZE / 2.0 + WALL_THICKNESS / 2.0, wall_z_center),
    dimensions=(BOX_SIZE, WALL_THICKNESS, BOX_HEIGHT),
    material=mat_acrylic
)

add_cube(
    "transparent_box_back_wall",
    location=(0.0, BOX_SIZE / 2.0 - WALL_THICKNESS / 2.0, wall_z_center),
    dimensions=(BOX_SIZE, WALL_THICKNESS, BOX_HEIGHT),
    material=mat_acrylic
)

add_cube(
    "transparent_box_left_wall",
    location=(-BOX_SIZE / 2.0 + WALL_THICKNESS / 2.0, 0.0, wall_z_center),
    dimensions=(WALL_THICKNESS, BOX_SIZE, BOX_HEIGHT),
    material=mat_acrylic
)

add_cube(
    "transparent_box_right_wall",
    location=(BOX_SIZE / 2.0 - WALL_THICKNESS / 2.0, 0.0, wall_z_center),
    dimensions=(WALL_THICKNESS, BOX_SIZE, BOX_HEIGHT),
    material=mat_acrylic
)

# Soft pad inside the box, so final state is visually clear.
add_cube(
    "inside_landing_pad",
    location=(0.0, 0.0, WALL_THICKNESS + 0.012),
    dimensions=(1.25, 1.25, 0.024),
    material=mat_inside_pad
)

# Top lid with circular hole.
lid_z_center = WALL_THICKNESS + BOX_HEIGHT + LID_THICKNESS / 2.0
lid = create_square_lid_with_circular_hole(
    name="transparent_top_lid_with_real_circular_hole",
    size=BOX_SIZE,
    hole_radius=HOLE_RADIUS,
    thickness=LID_THICKNESS,
    z_center=lid_z_center,
    segments=128,
    material=mat_acrylic
)

# Dark rim around the hole to make the circular opening obvious.
bpy.ops.mesh.primitive_torus_add(
    major_radius=HOLE_RADIUS,
    minor_radius=0.018,
    major_segments=96,
    minor_segments=8,
    location=(0.0, 0.0, lid_z_center + LID_THICKNESS / 2.0 + 0.012)
)
hole_rim = bpy.context.object
hole_rim.name = "thin_dark_rim_around_hole"
hole_rim.data.materials.append(mat_hole_rim)

# Add subtle darker vertical corner edges for box readability.
edge_height = BOX_HEIGHT
edge_z = WALL_THICKNESS + edge_height / 2.0
edge_positions = [
    (-BOX_SIZE / 2.0, -BOX_SIZE / 2.0),
    (-BOX_SIZE / 2.0, BOX_SIZE / 2.0),
    (BOX_SIZE / 2.0, -BOX_SIZE / 2.0),
    (BOX_SIZE / 2.0, BOX_SIZE / 2.0),
]

for idx, (x, y) in enumerate(edge_positions, start=1):
    add_cube(
        f"transparent_box_corner_edge_{idx:02d}",
        location=(x, y, edge_z),
        dimensions=(0.045, 0.045, edge_height),
        material=mat_acrylic_edge
    )

# ============================================================
# 5. Ball and keyframed gravity-like fall
# ============================================================
bpy.ops.mesh.primitive_uv_sphere_add(
    segments=64,
    ring_count=32,
    radius=BALL_RADIUS,
    location=(0.0, 0.0, BALL_START_Z)
)

ball = bpy.context.object
ball.name = "target_orange_ball"
ball.data.materials.append(mat_ball)

# The ball is never hidden and never teleported.
# It follows a continuous vertical path through the actual hole.
for frame in range(FRAME_START, FRAME_END + 1):
    z = ball_z_at_frame(frame)
    ball.location = (0.0, 0.0, z)

    # Slight rotation during the fall so the object feels physical.
    spin = frame * 0.045
    ball.rotation_euler = (spin, 0.0, spin * 0.35)

    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)

# ============================================================
# 6. Camera and lighting
# ============================================================
bpy.ops.object.light_add(type="AREA", location=(-2.4, -3.6, 5.8))
key_light = bpy.context.object
key_light.name = "large_softbox_key_light"
key_light.data.energy = 720
key_light.data.size = 4.8

bpy.ops.object.light_add(type="POINT", location=(2.7, 2.6, 3.2))
fill_light = bpy.context.object
fill_light.name = "small_fill_light"
fill_light.data.energy = 80

bpy.ops.object.camera_add(location=(3.55, -4.65, 2.75))
camera = bpy.context.object
camera.name = "camera_three_quarter_view_box_and_hole"
look_at(camera, (0.0, 0.0, 1.15))
camera.data.lens = 45
camera.data.dof.use_dof = False
bpy.context.scene.camera = camera

# ============================================================
# 7. Render settings
# ============================================================
scene = bpy.context.scene
scene.frame_start = FRAME_START
scene.frame_end = FRAME_END
scene.frame_set(FRAME_START)
scene.render.fps = FPS
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100

# Prefer Eevee for transparent material speed and compatibility.
for engine in ["BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"]:
    try:
        scene.render.engine = engine
        break
    except Exception:
        continue

# Eevee transparency / shadow options vary by Blender version.
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
    scene.world = bpy.data.worlds.new("clean_white_world")
scene.world.color = (1.0, 1.0, 1.0)
scene.render.film_transparent = False

# Set color management for clean benchmark-style renders.
try:
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
except Exception:
    pass

# ============================================================
# 8. Render input frames and reference frame sequence
# ============================================================
def render_png(frame, filename):
    scene.frame_set(frame)
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = os.path.join(OUT_DIR, filename)
    bpy.ops.render.render(write_still=True)

render_png(INPUT_FRAME_1, f"{ITEM_ID}_input_frame_01.png")
render_png(OPTIONAL_FRAME_2, f"{ITEM_ID}_optional_frame_02.png")
render_png(OPTIONAL_INSIDE_FRAME_2B, f"{ITEM_ID}_optional_inside_frame_02B.png")

frames_dir = os.path.join(OUT_DIR, f"{ITEM_ID}_reference_frames")
if os.path.exists(frames_dir):
    shutil.rmtree(frames_dir)
os.makedirs(frames_dir, exist_ok=True)

scene.render.image_settings.file_format = "PNG"
scene.render.filepath = os.path.join(frames_dir, f"{ITEM_ID}_frame_")
bpy.ops.render.render(animation=True)

# Save .blend
blend_path = os.path.join(OUT_DIR, f"{ITEM_ID}_scene.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend_path)

# ============================================================
# 9. Save task metadata
# ============================================================
task = {
    "item_id": ITEM_ID,
    "visual_regime": "3D_procedural_control",
    "script_path_expected": "scripts/pb_drop_hole_box_blender.py",
    "output_folder_expected": f"permanence_blender_outputs/{ITEM_ID}",
    "inputs": {
        "text_prompt": (
            "Continue this scene as a short video. A single orange ball is above the circular hole "
            "in the top of a semi-transparent box. The ball naturally falls straight downward through "
            "the hole, lands on the bottom, rebounds twice with diminishing height, and settles inside "
            "the transparent box. Preserve the ball's identity, color, size, "
            "count, and continuous vertical trajectory. The ball should not disappear, teleport, split, "
            "or change shape."
        ),
    },
    "reference_completion_frames_dir": f"{ITEM_ID}_reference_frames",
    "reference_completion_video": None,
    "scene_file": f"{ITEM_ID}_scene.blend"
}

json_path = os.path.join(OUT_DIR, f"{ITEM_ID}_task.json")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(task, f, indent=2, ensure_ascii=False)

print("\nDONE.")
print("Project root:", PROJECT_ROOT)
print("Script dir:", SCRIPT_DIR)
print("Output root:", OUTPUT_ROOT)
print("Item output directory:", OUT_DIR)
print("Key rule: ball follows continuous vertical gravity-like path through the actual circular hole.")
print("Key rule: ball is never hidden, never teleported, and remains visible inside the transparent box.")
print("Files:")
for name in sorted(os.listdir(OUT_DIR)):
    print(" -", name)
