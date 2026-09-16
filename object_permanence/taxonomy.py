"""Task taxonomy: which family each of the 150 tasks probes.

This module is the only place the assignment is stored; task.json and the
scene scripts carry no family field.

Six families across two dimensions: object permanence (Baillargeonian
occlusion, static occlusion, container permanence) and object solidity
(Baillargeonian obstruction, object drop, object collision). Container
permanence covers both static and moving containers; G50 and G52 are
obstruction. Run ``python -m object_permanence.taxonomy`` to check the map
against generator/tasks/.
"""

import glob
import json
import os
import sys
from collections import Counter

# An object moves along a track, passes behind or into an occluder, and re-emerges.
BAILLARGEONIAN_OCCLUSION = "baillargeonian_occlusion"
# Objects stay still; a moving occluder covers and then re-exposes them.
OBJECT_STATIC_OCCLUSION = "object_static_occlusion"
# Objects are enclosed in a container that opens and closes in place or moves;
# they are still inside, and where the container took them, when it reopens.
CONTAINER_PERMANENCE = "container_permanence"
# A moving object meets a barrier, gate or aperture and stops, deflects or passes;
# it never goes through a solid.
BAILLARGEONIAN_OBSTRUCTION = "baillargeonian_obstruction"
# Support is removed and an object falls; it lands where gravity takes it.
OBJECT_DROP = "object_drop"
# Two or more objects collide; momentum transfers, nothing interpenetrates.
OBJECT_COLLISION = "object_collision"

CLUSTERS = (
    BAILLARGEONIAN_OCCLUSION,
    OBJECT_STATIC_OCCLUSION,
    CONTAINER_PERMANENCE,
    BAILLARGEONIAN_OBSTRUCTION,
    OBJECT_DROP,
    OBJECT_COLLISION,
)

TASKS = {
    "G01": OBJECT_DROP,  # hole_box_drop
    "G02": BAILLARGEONIAN_OCCLUSION,  # ramp_tunnel
    "G03": BAILLARGEONIAN_OBSTRUCTION,  # ramp_ball_blocked_by_wall
    "G04": BAILLARGEONIAN_OCCLUSION,  # high_low_cover
    "G05": BAILLARGEONIAN_OBSTRUCTION,  # car_vs_barrier
    "G06": OBJECT_DROP,  # car_on_bridge
    "G07": BAILLARGEONIAN_OBSTRUCTION,  # guillotine_gate_stops
    "G08": CONTAINER_PERMANENCE,  # drawer_moves_hidden_object
    "G09": BAILLARGEONIAN_OBSTRUCTION,  # low_beam_car_height
    "G10": BAILLARGEONIAN_OBSTRUCTION,  # size_gate
    "G11": CONTAINER_PERMANENCE,  # box_holds_N_objects
    "G12": CONTAINER_PERMANENCE,  # partition_box
    "G13": CONTAINER_PERMANENCE,  # three_drawers
    "G14": BAILLARGEONIAN_OCCLUSION,  # u_tube_three_lanes
    "G15": OBJECT_STATIC_OCCLUSION,  # ramp_panel_occludes_objects
    "G16": OBJECT_STATIC_OCCLUSION,  # window_slit_mask_reveals
    "G17": BAILLARGEONIAN_OCCLUSION,  # moving_tray
    "G18": OBJECT_STATIC_OCCLUSION,  # turntable_behind_screen
    "G19": OBJECT_STATIC_OCCLUSION,  # row_screen_hides_objects
    "G20": OBJECT_STATIC_OCCLUSION,  # connected_vertical_panel
    "G21": OBJECT_STATIC_OCCLUSION,  # connected_sliding_doors
    "G22": OBJECT_STATIC_OCCLUSION,  # top_rail_screen
    "G23": OBJECT_STATIC_OCCLUSION,  # cabinet
    "G24": OBJECT_STATIC_OCCLUSION,  # pivoting_occluder
    "G25": OBJECT_STATIC_OCCLUSION,  # no_top_side_post_panel
    "G26": OBJECT_STATIC_OCCLUSION,  # bottom_rail_screen
    "G27": OBJECT_DROP,  # support_removed_then_fall
    "G28": BAILLARGEONIAN_OCCLUSION,  # open_ended_tunnel
    "G29": BAILLARGEONIAN_OCCLUSION,  # container_entry_left_u
    "G30": CONTAINER_PERMANENCE,  # hidden_object_moves_with_cart
    "G31": BAILLARGEONIAN_OCCLUSION,  # two_lane_tunnel
    "G32": CONTAINER_PERMANENCE,  # cart_swap
    "G33": BAILLARGEONIAN_OCCLUSION,  # partial_window_parallel_cars
    "G34": BAILLARGEONIAN_OBSTRUCTION,  # occ_small_ball_behind_screen
    "G35": BAILLARGEONIAN_OCCLUSION,  # single_low_window
    "G36": BAILLARGEONIAN_OCCLUSION,  # rollercoaster_u_track_glassbox
    "G37": BAILLARGEONIAN_OCCLUSION,  # u_track_occluded_ball
    "G38": BAILLARGEONIAN_OCCLUSION,  # pendulum_occluded_by_screen
    "G39": BAILLARGEONIAN_OCCLUSION,  # lidded_box_ball_enters
    "G40": CONTAINER_PERMANENCE,  # guided_elevator_hidden_ball
    "G41": OBJECT_DROP,  # trapdoor_opens_ball_falls
    "G42": BAILLARGEONIAN_OCCLUSION,  # ring_track_behind_center_block
    "G43": BAILLARGEONIAN_OCCLUSION,  # three_balls_parallel_tunnels
    "G44": OBJECT_COLLISION,  # two_balls_collide_and_bounce
    "G45": CONTAINER_PERMANENCE,  # opaque_lid_front_panel_drops
    "G46": CONTAINER_PERMANENCE,  # marked_boxes_swap
    "G47": OBJECT_STATIC_OCCLUSION,  # theater_curtain
    "G48": OBJECT_STATIC_OCCLUSION,  # sliding_window_row
    "G49": OBJECT_STATIC_OCCLUSION,  # two_supported_screens_close
    "G50": BAILLARGEONIAN_OBSTRUCTION,  # ramp_ball_slotted_screen
    "G51": OBJECT_STATIC_OCCLUSION,  # vertical_panel_two_objects
    "G52": BAILLARGEONIAN_OBSTRUCTION,  # ramp_open_right_gated_box
    "G53": OBJECT_STATIC_OCCLUSION,  # no_gap_top_rail_curtain
    "G54": BAILLARGEONIAN_OCCLUSION,  # serpentine_ramp_tunnel
    "G55": OBJECT_STATIC_OCCLUSION,  # rising_floor_screen
    "G56": CONTAINER_PERMANENCE,  # three_cup_shell_game
    "G57": BAILLARGEONIAN_OBSTRUCTION,  # ramp_ball_deflected_angled_wall
    "G58": OBJECT_DROP,  # two_ball_trapdoor_size_filter
    "G59": CONTAINER_PERMANENCE,  # hinged_lid_box_opens
    "G60": OBJECT_COLLISION,  # newtons_cradle
    "G61": BAILLARGEONIAN_OCCLUSION,  # spiral_ramp_behind_column
    "G62": BAILLARGEONIAN_OCCLUSION,  # two_balls_cross_tunnel
    "G63": OBJECT_STATIC_OCCLUSION,  # comb_occluder_sweep
    "G64": OBJECT_STATIC_OCCLUSION,  # flipboard_occluder
    "G65": CONTAINER_PERMANENCE,  # box_two_balls_relocate
    "G66": CONTAINER_PERMANENCE,  # rotating_carousel_cups
    "G67": BAILLARGEONIAN_OBSTRUCTION,  # double_deflector_zigzag
    "G68": BAILLARGEONIAN_OBSTRUCTION,  # width_slot_wall_two_balls
    "G69": OBJECT_DROP,  # two_tier_trapdoor_cascade
    "G70": OBJECT_DROP,  # popaway_support_columns
    "G71": CONTAINER_PERMANENCE,  # double_doors_swing_open
    "G72": CONTAINER_PERMANENCE,  # sliding_lid_box
    "G73": OBJECT_COLLISION,  # break_scatter_cluster
    "G74": OBJECT_COLLISION,  # glancing_oblique_collision
    "G75": BAILLARGEONIAN_OCCLUSION,  # ball_behind_rotating_billboard
    "G76": BAILLARGEONIAN_OCCLUSION,  # pendulum_behind_post
    "G77": BAILLARGEONIAN_OCCLUSION,  # three_balls_one_wide_tunnel
    "G78": BAILLARGEONIAN_OCCLUSION,  # rolling_disc_tunnel
    "G79": OBJECT_STATIC_OCCLUSION,  # venetian_blinds
    "G80": OBJECT_STATIC_OCCLUSION,  # sliding_double_doors
    "G81": OBJECT_STATIC_OCCLUSION,  # rolling_shutter
    "G82": OBJECT_STATIC_OCCLUSION,  # accordion_fold_screen
    "G83": CONTAINER_PERMANENCE,  # four_cup_three_swaps
    "G84": CONTAINER_PERMANENCE,  # two_balls_three_cups
    "G85": CONTAINER_PERMANENCE,  # nested_cup_transfer
    "G86": CONTAINER_PERMANENCE,  # conveyor_covered_boxes
    "G87": CONTAINER_PERMANENCE,  # four_cup_carousel
    "G88": CONTAINER_PERMANENCE,  # shell_game_fakeout_reveal
    "G89": BAILLARGEONIAN_OBSTRUCTION,  # limbo_height_bar
    "G90": BAILLARGEONIAN_OBSTRUCTION,  # funnel_size_sorter
    "G91": BAILLARGEONIAN_OBSTRUCTION,  # turnstile_timed_gate
    "G92": BAILLARGEONIAN_OBSTRUCTION,  # bumper_carom
    "G93": OBJECT_DROP,  # tipping_shelf_drop
    "G94": OBJECT_DROP,  # trapdoor_drop
    "G95": OBJECT_DROP,  # conveyor_edge_fall
    "G96": CONTAINER_PERMANENCE,  # clamshell_box
    "G97": CONTAINER_PERMANENCE,  # rolltop_tambour
    "G98": CONTAINER_PERMANENCE,  # liftoff_dome_lid
    "G99": OBJECT_COLLISION,  # headon_velocity_exchange
    "G100": OBJECT_COLLISION,  # heavy_light_collision
    "G101": BAILLARGEONIAN_OCCLUSION,  # picket_fence_flicker
    "G102": BAILLARGEONIAN_OCCLUSION,  # drop_screen_occluder
    "G103": BAILLARGEONIAN_OCCLUSION,  # corner_turn_occlusion
    "G104": OBJECT_STATIC_OCCLUSION,  # bifold_concertina_doors
    "G105": OBJECT_STATIC_OCCLUSION,  # descending_dome_cover
    "G106": OBJECT_STATIC_OCCLUSION,  # rotating_drum_occluder
    "G107": CONTAINER_PERMANENCE,  # sliding_cup_relocate
    "G108": CONTAINER_PERMANENCE,  # two_carts_cross_swap
    "G109": CONTAINER_PERMANENCE,  # tilting_tray_relocate
    "G110": BAILLARGEONIAN_OBSTRUCTION,  # one_way_flap_gate
    "G111": BAILLARGEONIAN_OBSTRUCTION,  # portcullis_drop_gate
    "G112": BAILLARGEONIAN_OBSTRUCTION,  # banked_quarter_pipe_redirect
    "G113": OBJECT_DROP,  # whipped_away_card
    "G114": OBJECT_DROP,  # retractable_support_pins
    "G115": OBJECT_DROP,  # steep_slope_slide
    "G116": CONTAINER_PERMANENCE,  # vault_swing_door
    "G117": CONTAINER_PERMANENCE,  # blooming_petal_box
    "G118": CONTAINER_PERMANENCE,  # matchbox_drawer
    "G119": OBJECT_COLLISION,  # offcenter_break_vsplit
    "G120": OBJECT_COLLISION,  # pendulum_strike_projectile
    "G121": OBJECT_STATIC_OCCLUSION,  # wiper_screen_occlusion
    "G122": BAILLARGEONIAN_OCCLUSION,  # ball_behind_box_stack
    "G123": OBJECT_STATIC_OCCLUSION,  # sliding_cover_panel
    "G124": OBJECT_STATIC_OCCLUSION,  # rising_sleeve_cover
    "G125": CONTAINER_PERMANENCE,  # two_carts_reveal_empty
    "G126": CONTAINER_PERMANENCE,  # turntable_two_boxes
    "G127": BAILLARGEONIAN_OBSTRUCTION,  # rising_bollard_stop
    "G128": BAILLARGEONIAN_OBSTRUCTION,  # swing_arm_barrier_stop
    "G129": OBJECT_DROP,  # sliding_hatch_drop
    "G130": OBJECT_DROP,  # bomb_bay_doors_drop
    "G131": CONTAINER_PERMANENCE,  # stacked_drawers_reveal
    "G132": CONTAINER_PERMANENCE,  # twist_open_capsule
    "G133": OBJECT_COLLISION,  # ball_topples_block
    "G134": OBJECT_COLLISION,  # knock_ball_off_tee
    "G135": OBJECT_COLLISION,  # lever_launch_transfer
    "G136": OBJECT_COLLISION,  # ball_strikes_pendulum
    "G137": OBJECT_COLLISION,  # pool_rack_break
    "G138": OBJECT_COLLISION,  # bank_shot_carom
    "G139": OBJECT_COLLISION,  # ball_shoves_block_slide
    "G140": OBJECT_COLLISION,  # light_ball_rebounds_off_heavy
    "G141": OBJECT_COLLISION,  # glancing_billiard_split
    "G142": OBJECT_COLLISION,  # knock_ball_off_ledge
    "G143": OBJECT_COLLISION,  # topple_two_blocks_apart
    "G144": CONTAINER_PERMANENCE,  # double_flap_top_box
    "G145": OBJECT_DROP,  # tilt_platform_rolloff
    "G146": OBJECT_DROP,  # hanging_ball_release_drop
    "G147": OBJECT_DROP,  # drop_leaf_shelf
    "G148": OBJECT_DROP,  # latch_release_flap_drop
    "G149": OBJECT_DROP,  # snap_pillar_topple
    "G150": OBJECT_DROP,  # rollers_part_drop
}


def cluster_of(gid):
    """Family of task ``gid`` (e.g. ``"G61"``). Unknown ids raise KeyError."""
    return TASKS[gid]


def tasks_in(cluster):
    """Task ids assigned to ``cluster``, in G order."""
    return [g for g, c in TASKS.items() if c == cluster]


def _task_ids_on_disk():
    here = os.path.dirname(os.path.abspath(__file__))
    pattern = os.path.join(here, "generator", "tasks", "*", "task.json")
    ids = set()
    for tj in glob.glob(pattern):
        with open(tj, encoding="utf-8") as f:
            ids.add(json.load(f)["id"])
    return ids


def main():
    on_disk = _task_ids_on_disk()
    mapped = set(TASKS)
    missing = sorted(on_disk - mapped, key=lambda g: int(g[1:]))
    extra = sorted(mapped - on_disk, key=lambda g: int(g[1:]))
    bad = sorted(g for g, c in TASKS.items() if c not in CLUSTERS)
    if missing or extra or bad:
        if missing:
            print("tasks on disk missing from taxonomy:", " ".join(missing))
        if extra:
            print("taxonomy ids with no task on disk:", " ".join(extra))
        if bad:
            print("tasks with an unknown cluster:", " ".join(bad))
        return 1
    counts = Counter(TASKS.values())
    for c in CLUSTERS:
        print(f"{counts[c]:4d}  {c}")
    print(f"{len(TASKS):4d}  total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
