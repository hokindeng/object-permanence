# pb_solid_wall_ramp_blender.py
# WROP canonical generator
# Item: PB_IMP_SOLID_WALL_RAMP_0006
#
# Scene:
#   A ball rolls downhill on a ramp.
#   A solid opaque wall stands across the track.
#   The ball rolls into the wall, makes contact, bounces slightly,
#   and remains in front of the wall.
#   The ball must NOT pass through the wall.

import bpy
import math
import os
import json
import shutil
from mathutils import Vector

# ============================================================
# 0. Project / item / output config
# ============================================================
ITEM_ID = "PB_IMP_SOLID_WALL_RAMP_0006"

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

RAMP_LENGTH = 8.0
RAMP_WIDTH = 1.8
RAMP_THICKNESS = 0.18
RAMP_ANGLE_DEG = 12.0
RAMP_ANGLE = math.radians(RAMP_ANGLE_DEG)
RAMP_CENTER = Vector((0.0, 0.0, 1.45))

BALL_RADIUS = 0.23
BALL_X_START = -3.35

# Solid wall position in ramp-local coordinates
WALL_X = 0.55
WALL_THICKNESS_X = 0.16
WALL_WIDTH_Y = 1.24
WALL_HEIGHT_Z = 1.28

# Ball motion:
# contact -> small rebound -> settle in front of wall
BALL_CONTACT_X = WALL_X - WALL_THICKNESS_X / 2.0 - BALL_RADIUS - 0.008
BALL_REBOUND_X = BALL_CONTACT_X - 0.26
BALL_FINAL_X = BALL_CONTACT_X - 0.05

CONTACT_FRAME = 74
REBOUND_FRAME = 92

INPUT_FRAME_1 = 1
OPTIONAL_FRAME_2 = 48
OPTIONAL_CONTACT_FRAME_02B = 84

# ============================================================
# 2. Ramp-local coordinate system
# ============================================================
def ramp_basis():
    u = Vector((math.cos(RAMP_ANGLE), 0.0, -math.sin(RAMP_ANGLE)))   # local +X downhill
    v = Vector((0.0, 1.0, 0.0))                                      # local +Y width
    n = Vector((math.sin(RAMP_ANGLE), 0.0, math.cos(RAMP_ANGLE)))    # local +Z normal
    return u, v, n

U, V, N = ramp_basis()

def local_to_world(x, y, z):
    return RAMP_CENTER + U * x + V * y + N * z

def smooth01(t):
    t = max(0.0, min(1.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)

def accel01(t):
    # gravity-driven roll from rest: displacement ~ t**2 (ease-in / accelerating).
    # Velocity rises monotonically and peaks at wall contact, matching s = 1/2 a t**2.
    t = max(0.0, min(1.0, t))
    return t * t

def lerp(a, b, t):
    return a + (b - a) * t

def ball_x_at_frame(frame):
    """
    1. roll downhill toward wall
    2. contact wall
    3. rebound slightly
    4. settle in front of wall
    """
    if frame <= CONTACT_FRAME:
        t = (frame - FRAME_START) / max(1, (CONTACT_FRAME - FRAME_START))
        return lerp(BALL_X_START, BALL_CONTACT_X, accel01(t))

    if frame <= REBOUND_FRAME:
        t = (frame - CONTACT_FRAME) / max(1, (REBOUND_FRAME - CONTACT_FRAME))
        return lerp(BALL_CONTACT_X, BALL_REBOUND_X, smooth01(t))

    t = (frame - REBOUND_FRAME) / max(1, (FRAME_END - REBOUND_FRAME))
    return lerp(BALL_REBOUND_X, BALL_FINAL_X, smooth01(t))

# ============================================================
# 3. Utilities
# ============================================================
def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

def make_mat(name, color, roughness=0.55, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color

    try:
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            if "Base Color" in bsdf.inputs:
                bsdf.inputs["Base Color"].default_value = color
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = roughness
            if "Metallic" in bsdf.inputs:
                bsdf.inputs["Metallic"].default_value = metallic
    except Exception:
        pass

    return mat

def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

def add_cube(name, location, dimensions, rotation=(0, 0, 0), material=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        obj.data.materials.append(material)
    return obj

# ============================================================
# 4. Build clean scene
# ============================================================
clear_scene()

mat_ramp = make_mat("warm_light_wood", (0.76, 0.57, 0.36, 1.0), roughness=0.68)
mat_track = make_mat("pale_track_surface", (0.86, 0.73, 0.55, 1.0), roughness=0.72)
mat_ball = make_mat("glossy_red_ball", (0.95, 0.03, 0.02, 1.0), roughness=0.35)
mat_floor = make_mat("matte_offwhite_floor", (0.83, 0.81, 0.76, 1.0), roughness=0.75)

# Solid wall materials
mat_wall = make_mat("solid_wall_main", (0.58, 0.61, 0.67, 1.0), roughness=0.82)
mat_wall_contact_face = make_mat("solid_wall_contact_face", (0.50, 0.54, 0.60, 1.0), roughness=0.80)
mat_wall_base = make_mat("solid_wall_base", (0.36, 0.38, 0.42, 1.0), roughness=0.88)
mat_contact_mark = make_mat("small_contact_marker", (1.0, 0.86, 0.12, 1.0), roughness=0.45)

# Ramp body
add_cube(
    "ramp_body",
    RAMP_CENTER,
    (RAMP_LENGTH, RAMP_WIDTH, RAMP_THICKNESS),
    rotation=(0.0, RAMP_ANGLE, 0.0),
    material=mat_ramp
)

# Track strip on ramp
track_center = local_to_world(0.0, 0.0, RAMP_THICKNESS / 2 + 0.018)
add_cube(
    "track_strip_on_ramp",
    track_center,
    (RAMP_LENGTH * 0.96, 0.56, 0.035),
    rotation=(0.0, RAMP_ANGLE, 0.0),
    material=mat_track
)

# Table / floor
add_cube(
    "table_floor",
    (0.6, 0.0, 0.35),
    (9.2, 3.2, 0.18),
    rotation=(0, 0, 0),
    material=mat_floor
)

# Solid wall main body
wall_center = local_to_world(
    WALL_X,
    0.0,
    RAMP_THICKNESS / 2.0 + WALL_HEIGHT_Z / 2.0
)

wall = add_cube(
    "solid_wall_across_track",
    wall_center,
    (WALL_THICKNESS_X, WALL_WIDTH_Y, WALL_HEIGHT_Z),
    rotation=(0.0, RAMP_ANGLE, 0.0),
    material=mat_wall
)

# Slightly darker wall base to visually ground it
add_cube(
    "solid_wall_base_block",
    local_to_world(WALL_X, 0.0, RAMP_THICKNESS / 2.0 + 0.06),
    (WALL_THICKNESS_X * 1.08, WALL_WIDTH_Y + 0.06, 0.12),
    rotation=(0.0, RAMP_ANGLE, 0.0),
    material=mat_wall_base
)

# Small contact marker on track, so impact position is easy to inspect
add_cube(
    "small_contact_marker_on_track_before_wall",
    local_to_world(BALL_CONTACT_X, 0.0, RAMP_THICKNESS / 2.0 + 0.032),
    (0.14, 0.34, 0.018),
    rotation=(0.0, RAMP_ANGLE, 0.0),
    material=mat_contact_mark
)

# Add a thin darker panel slightly in front of the wall face the ball contacts,
# so the contact face reads clearly from the camera.
contact_face_panel = add_cube(
    "wall_contact_face_panel",
    local_to_world(
        WALL_X - WALL_THICKNESS_X / 2.0 + 0.003,
        0.0,
        RAMP_THICKNESS / 2.0 + WALL_HEIGHT_Z / 2.0
    ),
    (0.010, WALL_WIDTH_Y * 0.96, WALL_HEIGHT_Z * 0.96),
    rotation=(0.0, RAMP_ANGLE, 0.0),
    material=mat_wall_contact_face
)

# ============================================================
# 5. Ball and keyframe trajectory
# ============================================================
BALL_Z = RAMP_THICKNESS / 2.0 + BALL_RADIUS + 0.025
ball_initial = local_to_world(BALL_X_START, 0.0, BALL_Z)

bpy.ops.mesh.primitive_uv_sphere_add(
    segments=48,
    ring_count=24,
    radius=BALL_RADIUS,
    location=ball_initial
)

ball = bpy.context.object
ball.name = "target_red_ball_blocked_by_solid_wall"
ball.data.materials.append(mat_ball)

for frame in range(FRAME_START, FRAME_END + 1):
    x = ball_x_at_frame(frame)
    ball.location = local_to_world(x, 0.0, BALL_Z)

    distance = x - BALL_X_START
    ball.rotation_euler = (0.0, -distance / BALL_RADIUS, 0.0)

    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)

# ============================================================
# 6. Camera and lighting
# ============================================================
bpy.ops.object.light_add(type="AREA", location=(-1.6, -3.8, 6.0))
key_light = bpy.context.object
key_light.name = "large_softbox_light"
key_light.data.energy = 700
key_light.data.size = 5.8

bpy.ops.object.light_add(type="POINT", location=(-3.0, -2.0, 3.0))
fill_light = bpy.context.object
fill_light.name = "contact_face_fill_light"
fill_light.data.energy = 85

# Camera on the uphill / contact-face side so the ball-wall impact face is visible.
bpy.ops.object.camera_add(location=(-4.2, -9.5, 4.7))
camera = bpy.context.object
camera.name = "camera_contact_face_view"
look_at(camera, (-0.75, 0.0, 1.32))
camera.data.lens = 30
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

for engine in ["BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"]:
    try:
        scene.render.engine = engine
        break
    except Exception:
        continue

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
render_png(OPTIONAL_CONTACT_FRAME_02B, f"{ITEM_ID}_optional_contact_frame_02B.png")

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
    "script_path_expected": "scripts/pb_solid_wall_ramp_blender.py",
    "output_folder_expected": f"permanence_blender_outputs/{ITEM_ID}",
    "inputs": {
        "text_prompt": (
            "Continue this scene as a short video. A small red ball rolls downhill along a wooden ramp. "
            "A solid opaque wall stands across the track. The ball should roll into the wall, make visible "
            "contact with the wall face, bounce slightly, and remain in front of the wall. The ball must not "
            "pass through the wall, must not teleport to the other side, and must preserve its identity, color, "
            "size, count, and continuous trajectory."
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
print("Key revision: replaced transparent barrier with solid wall.")
print("Key revision: rotated camera to show the wall face contacted by the ball.")
print("Files:")
for name in sorted(os.listdir(OUT_DIR)):
    print(" -", name)