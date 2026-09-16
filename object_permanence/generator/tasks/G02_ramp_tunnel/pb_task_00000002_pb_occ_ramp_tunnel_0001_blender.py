# pb_ramp_tunnel_blender.py
# WROP canonical generator
# Item: PB_OCC_RAMP_TUNNEL_0001

import bpy
import math
import os
import json
import shutil
from mathutils import Vector

# ============================================================
# 0. Project / item / output config
# ============================================================
ITEM_ID = "PB_OCC_RAMP_TUNNEL_0001"

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
BALL_X_START = -RAMP_LENGTH / 2.0 + BALL_RADIUS + 0.25
RAMP_EXIT_X = RAMP_LENGTH / 2.0 - 0.06
RAMP_ACCELERATION_PER_FRAME2 = 0.0018
RAMP_EXIT_FRAME = FRAME_START + round(math.sqrt(
    2.0 * (RAMP_EXIT_X - BALL_X_START) / RAMP_ACCELERATION_PER_FRAME2
))
FALL_ACCELERATION_PER_FRAME = 0.018
TABLE_CENTER_X = 0.6
TABLE_LENGTH = 9.2
TABLE_TOP_Z = 0.44
TABLE_RIGHT_X = TABLE_CENTER_X + TABLE_LENGTH / 2.0
TABLE_ROLL_DECELERATION = 0.002

TUNNEL_CENTER_X = 0.20
TUNNEL_LENGTH = 1.75
TUNNEL_RADIUS = 0.70
TUNNEL_WALL_THICKNESS = 0.08
TUNNEL_Z_OFFSET = 0.015

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

def build_ball_trajectory(x_start, exit_frame):
    """Roll down the scaled ramp, land on the tabletop, then roll off its edge."""
    traj = {}
    ramp_travel = RAMP_EXIT_X - x_start
    exit_speed = 2.0 * ramp_travel / float(exit_frame - FRAME_START)
    contact_z = TABLE_TOP_Z + BALL_RADIUS
    distance = 0.0
    previous = None

    for frame in range(FRAME_START, exit_frame + 1):
        t = (frame - FRAME_START) / float(exit_frame - FRAME_START)
        x = x_start + ramp_travel * (t * t)
        position = local_to_world(x, 0.0, RAMP_THICKNESS / 2 + BALL_RADIUS + 0.025)
        if previous is not None:
            distance += (position - previous).length
        traj[frame] = (position.copy(), distance)
        previous = position

    position = previous.copy()
    velocity = U * exit_speed
    supported = False
    for frame in range(exit_frame + 1, FRAME_END + 1):
        next_position = position + velocity
        if not supported:
            velocity.z -= FALL_ACCELERATION_PER_FRAME
            if next_position.x <= TABLE_RIGHT_X and next_position.z <= contact_z:
                next_position.z = contact_z
                velocity.z = 0.0
                supported = True
        else:
            velocity.x = max(0.0, velocity.x - TABLE_ROLL_DECELERATION)
            next_position.z = contact_z
            if next_position.x >= TABLE_RIGHT_X:
                supported = False
                velocity.z = 0.0
        distance += (next_position - position).length
        traj[frame] = (next_position.copy(), distance)
        position = next_position
    return traj


BALL_TRAJECTORY = build_ball_trajectory(BALL_X_START, RAMP_EXIT_FRAME)


def ball_position_at_frame(frame):
    position, distance = BALL_TRAJECTORY[frame]
    return position.copy(), distance

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
mat_tunnel = make_mat("matte_blue_tunnel", (0.05, 0.23, 0.62, 1.0), roughness=0.62)
mat_ball = make_mat("glossy_red_ball", (0.95, 0.03, 0.02, 1.0), roughness=0.35)
mat_floor = make_mat("matte_offwhite_floor", (0.83, 0.81, 0.76, 1.0), roughness=0.75)

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
    (TABLE_CENTER_X, 0.0, TABLE_TOP_Z - 0.09),
    (TABLE_LENGTH, 3.2, 0.18),
    rotation=(0, 0, 0),
    material=mat_floor
)

# ============================================================
# 5. Tunnel mesh aligned to ramp coordinates
# ============================================================
verts = []
faces = []
segments_x = 12
segments_arc = 32

x0 = TUNNEL_CENTER_X - TUNNEL_LENGTH / 2
x1 = TUNNEL_CENTER_X + TUNNEL_LENGTH / 2
z_base = RAMP_THICKNESS / 2 + TUNNEL_Z_OFFSET

for ix in range(segments_x + 1):
    x = x0 + (x1 - x0) * ix / segments_x
    for ia in range(segments_arc + 1):
        phi = math.pi - math.pi * ia / segments_arc
        y = TUNNEL_RADIUS * math.cos(phi)
        z = z_base + TUNNEL_RADIUS * math.sin(phi)
        verts.append(local_to_world(x, y, z))

for ix in range(segments_x):
    for ia in range(segments_arc):
        a = ix * (segments_arc + 1) + ia
        b = a + 1
        c = (ix + 1) * (segments_arc + 1) + ia + 1
        d = (ix + 1) * (segments_arc + 1) + ia
        faces.append((a, b, c, d))

mesh = bpy.data.meshes.new("tunnel_cover_mesh")
mesh.from_pydata([tuple(v) for v in verts], [], faces)
mesh.update()

tunnel = bpy.data.objects.new("blue_tunnel_cover_aligned_to_ramp", mesh)
bpy.context.collection.objects.link(tunnel)
tunnel.data.materials.append(mat_tunnel)

solid = tunnel.modifiers.new("solidify_wall_thickness", "SOLIDIFY")
solid.thickness = TUNNEL_WALL_THICKNESS
solid.offset = 1.0

# ============================================================
# 6. Ball and keyframe trajectory
# ============================================================
ball_initial = local_to_world(BALL_X_START, 0.0, RAMP_THICKNESS / 2 + BALL_RADIUS + 0.025)

bpy.ops.mesh.primitive_uv_sphere_add(
    segments=48,
    ring_count=24,
    radius=BALL_RADIUS,
    location=ball_initial
)

ball = bpy.context.object
ball.name = "target_red_ball"
ball.data.materials.append(mat_ball)

# The ball is never manually hidden.
# It is naturally occluded by the tunnel geometry, so entrance/exit are gradual.
for frame in range(FRAME_START, FRAME_END + 1):
    ball.location, distance = ball_position_at_frame(frame)
    ball.rotation_euler = (0.0, -distance / BALL_RADIUS, 0.0)

    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)

# ============================================================
# 7. Camera and lighting
# ============================================================
bpy.ops.object.light_add(type="AREA", location=(0.0, -3.8, 6.0))
key_light = bpy.context.object
key_light.name = "large_softbox_light"
key_light.data.energy = 650
key_light.data.size = 5.5

bpy.ops.object.camera_add(location=(7.2, -9.6, 3.9))
camera = bpy.context.object
camera.name = "camera_three_quarter_side_view"
look_at(camera, (0.55, 0.0, 0.95))
camera.data.lens = 35
camera.data.dof.use_dof = False
bpy.context.scene.camera = camera

# ============================================================
# 8. Render settings
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

if scene.world is None:
    scene.world = bpy.data.worlds.new("clean_white_world")
scene.world.color = (1.0, 1.0, 1.0)
scene.render.film_transparent = False

# ============================================================
# 9. Render input frames and reference frame sequence
# ============================================================
def render_png(frame, filename):
    scene.frame_set(frame)
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = os.path.join(OUT_DIR, filename)
    bpy.ops.render.render(write_still=True)

INPUT_FRAME_1 = 1
OPTIONAL_FRAME_2 = 52
OPTIONAL_HIDDEN_FRAME_2B = 63

render_png(INPUT_FRAME_1, f"{ITEM_ID}_input_frame_01.png")
render_png(OPTIONAL_FRAME_2, f"{ITEM_ID}_optional_frame_02.png")
render_png(OPTIONAL_HIDDEN_FRAME_2B, f"{ITEM_ID}_optional_hidden_frame_02B.png")

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
# 10. Save task metadata
# ============================================================
task = {
    "item_id": ITEM_ID,
    "visual_regime": "3D_procedural_control",
    "script_path_expected": "scripts/pb_ramp_tunnel_blender.py",
    "output_folder_expected": f"permanence_blender_outputs/{ITEM_ID}",
    "inputs": {
        "text_prompt": (
            "Continue this scene as a short video. A small red ball rolls downhill along the wooden slope. "
            "It enters the tunnel in the middle of the slope, becomes hidden by the tunnel, "
            "and then the same red ball gradually exits from the other side of the tunnel, continuing downhill. "
            "It must keep rolling beyond the lower edge of the ramp, fall off the table, and leave the frame; "
            "it must not stop on the slope. Preserve the ball's identity, color, size, count, and trajectory."
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
print("Key fix: ball is naturally occluded by tunnel geometry; no binary hide_render toggle.")
print("Files:")
for name in sorted(os.listdir(OUT_DIR)):
    print(" -", name)
