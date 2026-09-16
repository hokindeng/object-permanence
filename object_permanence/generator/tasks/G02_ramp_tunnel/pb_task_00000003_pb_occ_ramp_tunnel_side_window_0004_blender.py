# pb_ramp_tunnel_side_window_blender.py
# WROP canonical generator
# Item: PB_OCC_RAMP_TUNNEL_SIDE_WINDOW_0004
#
# Scene:
#   Similar to PB_OCC_RAMP_TUNNEL_0001.
#   A ball rolls down a ramp into a blue tunnel.
#   The tunnel has an actual side window / hole on the camera-facing side.
#   When the ball passes inside the tunnel, it becomes visible through the side window,
#   then continues and exits from the other side.

import bpy
import math
import os
import json
import shutil
from mathutils import Vector

# ============================================================
# 0. Project / item / output config
# ============================================================
ITEM_ID = "PB_OCC_RAMP_TUNNEL_SIDE_WINDOW_0004"

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
TUNNEL_LENGTH = 1.90
TUNNEL_RADIUS = 0.72
TUNNEL_WALL_THICKNESS = 0.08
TUNNEL_Z_OFFSET = 0.015

# Side window / hole on camera-facing side.
# The camera is on negative Y, so the opening is placed on the negative-Y side of the tunnel arch.
#
# The window is a small observation hole:
#   - narrow along the tunnel direction
#   - short along the curved tunnel wall
#   - still large enough to briefly see the ball inside

WINDOW_CENTER_X = TUNNEL_CENTER_X
WINDOW_HALF_X = 0.34

WINDOW_PHI_CENTER = 2.30
WINDOW_HALF_PHI = 0.18

WINDOW_X_MIN = WINDOW_CENTER_X - WINDOW_HALF_X
WINDOW_X_MAX = WINDOW_CENTER_X + WINDOW_HALF_X

WINDOW_PHI_MIN = WINDOW_PHI_CENTER - WINDOW_HALF_PHI
WINDOW_PHI_MAX = WINDOW_PHI_CENTER + WINDOW_HALF_PHI

WINDOW_RIM_X_WIDTH = 0.040
WINDOW_RIM_PHI_WIDTH = 0.040
WINDOW_RIM_RADIAL_OFFSET = 0.012

INPUT_FRAME_1 = 1
OPTIONAL_FRAME_2 = 48
OPTIONAL_SIDE_WINDOW_FRAME_02B = 63

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

def tunnel_surface_point(x, phi, radial_offset=0.0):
    r = TUNNEL_RADIUS + radial_offset
    y = r * math.cos(phi)
    z = RAMP_THICKNESS / 2.0 + TUNNEL_Z_OFFSET + r * math.sin(phi)
    return local_to_world(x, y, z)

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

def make_mat(name, color, roughness=0.55, metallic=0.0, alpha=1.0):
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

    if alpha < 1.0:
        try:
            mat.blend_method = "BLEND"
            mat.show_transparent_back = True
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

def in_window_region(x_mid, phi_mid):
    return (
        WINDOW_X_MIN <= x_mid <= WINDOW_X_MAX
        and WINDOW_PHI_MIN <= phi_mid <= WINDOW_PHI_MAX
    )

# ============================================================
# 4. Build clean scene
# ============================================================
clear_scene()

mat_ramp = make_mat("warm_light_wood", (0.76, 0.57, 0.36, 1.0), roughness=0.68)
mat_track = make_mat("pale_track_surface", (0.86, 0.73, 0.55, 1.0), roughness=0.72)
mat_tunnel = make_mat("matte_blue_tunnel", (0.05, 0.23, 0.62, 1.0), roughness=0.62)
mat_window_rim = make_mat("dark_side_window_rim", (0.015, 0.018, 0.025, 1.0), roughness=0.50)
mat_ball = make_mat("glossy_red_ball", (0.95, 0.03, 0.02, 1.0), roughness=0.35)
mat_floor = make_mat("matte_offwhite_floor", (0.83, 0.81, 0.76, 1.0), roughness=0.75)
mat_shadow_inside = make_mat("dark_inside_tunnel_floor_shadow", (0.055, 0.06, 0.07, 1.0), roughness=0.80)

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

# Slight darker floor strip inside the tunnel, visible through the side window.
inside_shadow_center = local_to_world(
    TUNNEL_CENTER_X,
    -0.02,
    RAMP_THICKNESS / 2 + 0.042
)
add_cube(
    "visible_dark_inside_tunnel_floor_strip",
    inside_shadow_center,
    (TUNNEL_LENGTH * 0.84, 0.46, 0.025),
    rotation=(0.0, RAMP_ANGLE, 0.0),
    material=mat_shadow_inside
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
# 5. Tunnel mesh with a real side window / hole
# ============================================================
verts = []
faces = []

segments_x = 40
segments_arc = 72

x0 = TUNNEL_CENTER_X - TUNNEL_LENGTH / 2
x1 = TUNNEL_CENTER_X + TUNNEL_LENGTH / 2

# Build vertices on a half-cylinder tunnel surface.
# Then skip faces in the window parameter region, creating an actual side opening.
phis = []
xs = []

for ix in range(segments_x + 1):
    x = x0 + (x1 - x0) * ix / segments_x
    xs.append(x)

for ia in range(segments_arc + 1):
    phi = math.pi - math.pi * ia / segments_arc
    phis.append(phi)

for ix, x in enumerate(xs):
    for ia, phi in enumerate(phis):
        verts.append(tunnel_surface_point(x, phi, radial_offset=0.0))

for ix in range(segments_x):
    for ia in range(segments_arc):
        x_mid = 0.5 * (xs[ix] + xs[ix + 1])
        phi_mid = 0.5 * (phis[ia] + phis[ia + 1])

        # Skip the faces where the side observation hole should be.
        if in_window_region(x_mid, phi_mid):
            continue

        a = ix * (segments_arc + 1) + ia
        b = a + 1
        c = (ix + 1) * (segments_arc + 1) + ia + 1
        d = (ix + 1) * (segments_arc + 1) + ia
        faces.append((a, b, c, d))

mesh = bpy.data.meshes.new("tunnel_with_side_window_mesh")
mesh.from_pydata([tuple(v) for v in verts], [], faces)
mesh.update()

tunnel = bpy.data.objects.new("blue_tunnel_with_camera_facing_side_window", mesh)
bpy.context.collection.objects.link(tunnel)
tunnel.data.materials.append(mat_tunnel)

solid = tunnel.modifiers.new("solidify_wall_thickness", "SOLIDIFY")
solid.thickness = TUNNEL_WALL_THICKNESS
solid.offset = 1.0

# ============================================================
# 6. Add dark rim patches around the side window
# ============================================================
def make_tunnel_surface_patch(name, x_min, x_max, phi_min, phi_max, nx, nphi, radial_offset, material):
    local_verts = []
    local_faces = []

    for ix in range(nx + 1):
        x = x_min + (x_max - x_min) * ix / nx
        for ip in range(nphi + 1):
            phi = phi_min + (phi_max - phi_min) * ip / nphi
            local_verts.append(tunnel_surface_point(x, phi, radial_offset=radial_offset))

    for ix in range(nx):
        for ip in range(nphi):
            a = ix * (nphi + 1) + ip
            b = a + 1
            c = (ix + 1) * (nphi + 1) + ip + 1
            d = (ix + 1) * (nphi + 1) + ip
            local_faces.append((a, b, c, d))

    patch_mesh = bpy.data.meshes.new(name + "_mesh")
    patch_mesh.from_pydata([tuple(v) for v in local_verts], [], local_faces)
    patch_mesh.update()

    obj = bpy.data.objects.new(name, patch_mesh)
    bpy.context.collection.objects.link(obj)

    if material is not None:
        obj.data.materials.append(material)

    return obj

# Left and right vertical rim strips.
make_tunnel_surface_patch(
    "side_window_left_dark_rim_strip",
    WINDOW_X_MIN - WINDOW_RIM_X_WIDTH,
    WINDOW_X_MIN,
    WINDOW_PHI_MIN,
    WINDOW_PHI_MAX,
    nx=2,
    nphi=18,
    radial_offset=WINDOW_RIM_RADIAL_OFFSET,
    material=mat_window_rim
)

make_tunnel_surface_patch(
    "side_window_right_dark_rim_strip",
    WINDOW_X_MAX,
    WINDOW_X_MAX + WINDOW_RIM_X_WIDTH,
    WINDOW_PHI_MIN,
    WINDOW_PHI_MAX,
    nx=2,
    nphi=18,
    radial_offset=WINDOW_RIM_RADIAL_OFFSET,
    material=mat_window_rim
)

# Upper and lower curved rim strips.
make_tunnel_surface_patch(
    "side_window_upper_dark_rim_strip",
    WINDOW_X_MIN - WINDOW_RIM_X_WIDTH,
    WINDOW_X_MAX + WINDOW_RIM_X_WIDTH,
    WINDOW_PHI_MIN - WINDOW_RIM_PHI_WIDTH,
    WINDOW_PHI_MIN,
    nx=18,
    nphi=2,
    radial_offset=WINDOW_RIM_RADIAL_OFFSET,
    material=mat_window_rim
)

make_tunnel_surface_patch(
    "side_window_lower_dark_rim_strip",
    WINDOW_X_MIN - WINDOW_RIM_X_WIDTH,
    WINDOW_X_MAX + WINDOW_RIM_X_WIDTH,
    WINDOW_PHI_MAX,
    WINDOW_PHI_MAX + WINDOW_RIM_PHI_WIDTH,
    nx=18,
    nphi=2,
    radial_offset=WINDOW_RIM_RADIAL_OFFSET,
    material=mat_window_rim
)

# ============================================================
# 7. Ball and keyframe trajectory
# ============================================================
ball_initial = local_to_world(
    BALL_X_START,
    0.0,
    RAMP_THICKNESS / 2 + BALL_RADIUS + 0.025
)

bpy.ops.mesh.primitive_uv_sphere_add(
    segments=48,
    ring_count=24,
    radius=BALL_RADIUS,
    location=ball_initial
)

ball = bpy.context.object
ball.name = "target_red_ball"
ball.data.materials.append(mat_ball)

# The ball is never hidden.
# It is naturally occluded by the tunnel geometry, visible through the side window,
# then exits the tunnel on the downhill side.
for frame in range(FRAME_START, FRAME_END + 1):
    ball.location, distance = ball_position_at_frame(frame)
    ball.rotation_euler = (0.0, -distance / BALL_RADIUS, 0.0)

    ball.keyframe_insert(data_path="location", frame=frame)
    ball.keyframe_insert(data_path="rotation_euler", frame=frame)

# ============================================================
# 8. Camera and lighting
# ============================================================
bpy.ops.object.light_add(type="AREA", location=(0.0, -3.8, 6.0))
key_light = bpy.context.object
key_light.name = "large_softbox_light"
key_light.data.energy = 680
key_light.data.size = 5.5

bpy.ops.object.light_add(type="POINT", location=(-2.6, -2.6, 2.8))
window_fill_light = bpy.context.object
window_fill_light.name = "small_side_window_fill_light"
window_fill_light.data.energy = 65

# Camera stays on the negative-Y side so the side window faces the viewer.
bpy.ops.object.camera_add(location=(7.4, -9.7, 3.85))
camera = bpy.context.object
camera.name = "camera_three_quarter_side_window_view"
look_at(camera, (0.5, -0.04, 0.95))
camera.data.lens = 35
camera.data.dof.use_dof = False
bpy.context.scene.camera = camera

# ============================================================
# 9. Render settings
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
# 10. Render input frames and reference frame sequence
# ============================================================
def render_png(frame, filename):
    scene.frame_set(frame)
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = os.path.join(OUT_DIR, filename)
    bpy.ops.render.render(write_still=True)

render_png(INPUT_FRAME_1, f"{ITEM_ID}_input_frame_01.png")
render_png(OPTIONAL_FRAME_2, f"{ITEM_ID}_optional_frame_02.png")
render_png(OPTIONAL_SIDE_WINDOW_FRAME_02B, f"{ITEM_ID}_optional_side_window_frame_02B.png")

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
# 11. Save task metadata
# ============================================================
task = {
    "item_id": ITEM_ID,
    "visual_regime": "3D_procedural_control",
    "script_path_expected": "scripts/pb_ramp_tunnel_side_window_blender.py",
    "output_folder_expected": f"permanence_blender_outputs/{ITEM_ID}",
    "inputs": {
        "text_prompt": (
            "Continue this scene as a short video. A small red ball rolls downhill along the wooden slope "
            "and enters the tunnel. The tunnel has a side window or hole on the viewer-facing side, "
            "so the same red ball should be briefly visible inside the tunnel through the side opening. "
            "The ball then continues moving and exits from the other side of the tunnel. Preserve the ball's "
            "identity, color, size, count, and continuous left-to-right downhill trajectory. It must continue "
            "past the lower edge of the ramp, fall off the table, and leave the frame rather than stop on the slope."
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
print("Key rule: tunnel has an actual mesh side window on the camera-facing side.")
print("Key rule: ball is naturally occluded by tunnel geometry but visible through the side window.")
print("Key rule: no hide_render toggle, no teleportation, no object replacement.")
print("Files:")
for name in sorted(os.listdir(OUT_DIR)):
    print(" -", name)
