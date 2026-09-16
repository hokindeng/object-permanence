# object-permanence

Code for the paper *Training Object Permanence in World Models*. Everything behind
it in one repository: the data factory that renders the 150 object-permanence and
object-solidity tasks in Blender (the WROP corpus), and the training stack that
fine-tuned PWM-WROP, a 16B video world model, on that data.

| | |
|---|---|
| Website / Leaderboard | https://object-permanence.world |
| Training corpus (1.5M samples) + 300-question exam | https://huggingface.co/datasets/Hokin/object-permanence |
| Benchmark answers (14 models × 300 questions) | https://huggingface.co/datasets/Hokin/object-permanence-benchmark |
| Model weights (PWM-WROP) | https://huggingface.co/Hokin/PWM-WROP |
| Paper | https://object-permanence.world/paper |

```
object-permanence/
├── object_permanence/   data factory: 150 Blender task generators + CLI      (Part 1)
├── pwm/                 training stack: Cosmos3-Nano on AWS Trainium2, native PyTorch (Part 2)
├── pyproject.toml       pip package `object-permanence`
└── LICENSE              CC BY-NC 4.0
```

## Part 1 — Data factory (`object_permanence/`)

Blender-rendered scenes where objects persist while occluded, packaged as
video-to-video samples. 150 self-contained task generators in six cognitively
grounded families — object permanence: Baillargeonian occlusion, static occlusion,
container permanence; object solidity: Baillargeonian obstruction, object drop,
object collision (`object_permanence/taxonomy.py`). Trajectories are hand-authored
keyframes; the one exception is `G73_break_scatter_cluster`, which bakes a Blender
rigid-body simulation to keyframes.

### Install

```bash
pip install -e .
```

Requires **Blender 4.4.x** (the corpus was rendered with 4.4.3; the renderer
refuses any other version because pixels would differ — set
`OP_ALLOW_BLENDER_MISMATCH=1` to override for local experiments) and **ffmpeg**
on the PATH. Blender is found via `OP_BLENDER`, then the usual install paths
(`/opt/homebrew/bin/blender`, `/Applications/Blender.app/...`, `/usr/local/bin`,
`/usr/bin`, `/snap/bin`), then the PATH; `--blender <path>` overrides all of them.
Homebrew and apt often ship a different major version — point `OP_BLENDER` at a
4.4.x download (https://download.blender.org/release/Blender4.4/).

Set `OP_FORCE_EEVEE=1` on every headless machine, Mac included: without it the
OpenGL probe fails and Blender silently falls back to Cycles, the engine changes
and a sample takes minutes instead of seconds.

### Quick start

```bash
# List all 150 tasks
object-permanence generate --list

# Generate all tasks (150 x 20 = 3000 samples; --parallel 3 Blender processes by default)
OP_FORCE_EEVEE=1 object-permanence generate --out ./out --per 20 --parallel 4

# Generate a shard (for parallel fleets)
object-permanence generate --gens G01-G11 --per 20

# Part of one task — samples 200..299 only
object-permanence generate --task G18 --per 100 --start 200

# Single task, fast preview (360p; audit it with --allow-preview)
object-permanence generate --task G18 --per 20 --preview 1
object-permanence audit --out ./out --allow-preview

# Standard-resolution, frame-continuous preview for collision-boundary QA
object-permanence generate --task G120 --per 3 --preview 1 --preview-frame-step 1

# Keep only the previous appearance-level variation
object-permanence generate --task G18 --per 20 --diversity-profile surface

# Audit generated output
object-permanence audit --out ./out

# Require real task-level variation rather than appearance-only samples
object-permanence audit --out ./out --require-task-specific-diversity

# Require balanced factorial provenance and non-repeating design cells
object-permanence audit --out ./out --require-balanced-factorial
```

Samples land in `<out>/<task>_task/<task>_NNNN/`. Generation prints a live
progress line (`880/3000 (29%) | ok=872 fail=8 | 12m03s elapsed | ETA 42m11s`);
it updates in place in a terminal and falls back to one line per step when piped
to a log. A failed sample leaves an `ERROR.txt` in its directory. Other flags:
`--render-timeout` (seconds per Blender process), `--split-mode half|event`
(see Output format), `--gen G18` (same as `--task`).

The released corpus on Hugging Face was rendered with this package at version
1.9.1 (`object_permanence.__version__`), Blender 4.4.3, EEVEE Next.

### Package layout

```
object_permanence/
├── cli.py                   # unified CLI: object-permanence generate / audit
├── __main__.py              # python -m object_permanence
├── taxonomy.py              # the 150 tasks -> six-family map, stored here only
└── generator/
    ├── core/
    │   ├── generate.py      # driver
    │   ├── render.py        # Blender render backend
    │   ├── state_graph.py   # bounded trajectory-object prioritization
    │   └── diversity.py     # deterministic sampling and source bindings
    ├── tasks/
    │   ├── G01_hole_box_drop/
    │   │   ├── task.json    # task manifest
    │   │   └── pb_task_*.py # Blender scene scripts
    │   ├── ...              # 150 self-contained task directories
    │   └── G150_rollers_part_drop/
    └── tools/
        ├── audit.py         # manifest/output validator
        ├── plan_task_diversity.py       # conservative legacy-task binding planner
        ├── plan_five_sample_review.py   # five-sample factor-coverage planner
        ├── upgrade_visible_diversity.py # idempotent legacy-range migration
        └── render_diversity_extremes.py # low/high witness renderer for every member
```

### Output format

Each sample is a five-file V2V / TV2V set:

| File | Description |
|------|-------------|
| `input_video.mp4` | Simulation up to the split point (model conditioning input) |
| `target_video.mp4` | Simulation after the split point (reference output) |
| `prompt.txt` | Continuation instruction: what the target clip shows |
| `trajectory.npz` | Per-frame ground truth for every body: `xpos [T,N,3]`, `xquat [T,N,4]`, `qpos [T,N*7]`, `qvel [T,N*6]` (free-body), plus `body_names`, `body_roles`, `body_shapes`, `body_colors`, `is_target`, `fps`, `frame_start`, `frame_end` |
| `metadata.json` | `parameters` (seed, source script, diversity cell, applied knobs, source bindings), `provenance` (generator version, Blender version, render engine), `video_split` (frame boundary and clip indices) |

Each task renders 120 frames at 24 fps and splits them 60/60. By default the split
is the temporal midpoint (`--split-mode half`, `"method": "midpoint"` in
`metadata.json`); 43 task manifests carry a `video_split` block with a semantic
policy instead: `before_event` places the event's first frame at the beginning of
the target clip, and collision tasks use `overlap_event`, which repeats the exact
contact frame as both the final input frame and the first target frame. Both clips
always contain exactly 60 frames, using edge-frame padding when fewer than 60
source frames are available on one side. The released corpus uses these defaults.

### Known issues (v1.9.1)

The released corpus was rendered with this version, defects included. They are
listed on the dataset card and repeated here so the two never diverge:

- `wiper_screen_occlusion` (G121): the screen still hides the ball at the end of
  the target half under the -16° viewpoint. `sliding_cover_panel` (G123): the
  occluder is recoloured close to the backdrop, so the ball appears to vanish
  rather than be covered. `three_balls_parallel_tunnels` (G43): the balls start
  out of frame.
- The dark world background shows at frame edges in `high_low_cover`,
  `car_vs_barrier`, `guillotine_gate_stops`, `u_tube_three_lanes`,
  `theater_curtain`, `pendulum_behind_post`, `picket_fence_flicker`,
  `drop_screen_occluder`, `corner_turn_occlusion` and `ball_behind_box_stack`;
  `hole_box_drop`, `ramp_tunnel` and `ramp_ball_blocked_by_wall` render against a
  flat dark backdrop; targets are very small in `cart_swap`,
  `guided_elevator_hidden_ball`, `trapdoor_opens_ball_falls` and
  `two_balls_collide_and_bounce`.
- Physical-plausibility defects flagged in review were not all fixed
  (penetrations, super-elastic rebounds, objects starting out of frame under
  scaled dynamics). In some tasks the `is_target` mask also marks apparatus
  bodies, not only the object of interest.
- `trajectory.npz` borrows MuJoCo's field names (`xpos`, `xquat`, `qpos`,
  `qvel`) but the arrays are sampled from keyframed animation (G73 excepted);
  they are not physics ground truth.

## Part 2 — Training stack (`pwm/`)

A native-PyTorch implementation of NVIDIA Cosmos3-Nano for AWS Trainium2: it
loads the public diffusers-layout weights and trains and samples on Neuron
without XLA graph tracing. Tensor parallel × FSDP2 over 64 NeuronCores on a
trn2.48xlarge. Two configs, every key commented: `pwm/configs/wrop.yaml` is the
PWM-WROP recipe of the paper (320×192, 57 conditioning + 60 predicted frames,
one epoch over the 1.5M corpus at batch 16); `pwm/configs/example.yaml` is the
288×512 text-to-video geometry the throughput numbers were measured at.

Requirements: a trn2 instance (trn2.48xlarge for the production layout, trn2.3xlarge
for single-node inference), the Neuron driver, Docker, and a Neuron Deep Learning
Container whose PyTorch runs natively on Trainium (`torch_neuronx` ≥ 2.11.3 with
`device="neuron"` and `torch.compile(backend="neuron")`). pwm was developed on a
pre-release build of that runtime from the AWS Neuron team; ask them for the image
or use the public release once it ships, and pass it as `PWM_IMAGE=<image@digest>`.
The Cosmos3-Nano checkpoint (diffusers layout: `transformer/`, `vae/`,
`text_tokenizer/`) goes under `$HOME/weights/Cosmos3-Nano`.

The full guide — machine setup, the pre-flight checks, data encoding, training,
sampling, checkpoint export, the performance ledger and thirteen architecture
diagrams derived from the code — is [`pwm/README.md`](pwm/README.md).
In short, from the repository root on a trn2 box:

```bash
export PWM_IMAGE=<neuron native-pytorch container image@digest>
bash pwm/launch.sh pip pwm            # container "pwm" + deps
bash pwm/launch.sh preflight          # read-only checks: driver, devices, image, cache, weights, box idle

# Part 1 renders -> encode manifest -> fixed-shape clips (once, on CPU)
python -m pwm.data.from_object_permanence /out/renders > /out/rows.jsonl
bash pwm/launch.sh pwm -- python -m pwm.cli encode --manifest /out/rows.jsonl \
    --out /out/data/clips_320x192_t30 --ckpt /weights/Cosmos3-Nano --latent-t 30 --height 192 --width 320 --text-len 128

# train the paper recipe / benchmark step time
bash pwm/launch.sh pwm -- python -m pwm.cli train /repo/pwm/configs/wrop.yaml
bash pwm/launch.sh pwm -- python -m pwm.cli bench /repo/pwm/configs/example.yaml --warmup 3 --steps 20

# sample with the released PWM-WROP weights (download https://huggingface.co/Hokin/PWM-WROP to /weights/PWM-WROP)
bash pwm/launch.sh pwm -- python -m pwm.cli infer /repo/pwm/configs/wrop.yaml --weights /weights/PWM-WROP \
    --v2v /out/data/clips_320x192_t30/<id>.pt --prompt "..." --out /out/sample.mp4

# export a training checkpoint to diffusers layout
bash pwm/launch.sh pwm -- python -m pwm.cli consolidate /repo/pwm/configs/wrop.yaml --step 93750 --out /out/ckpt-final --dtype bf16
```

`pwm` is not part of the pip package; run it from the repository root
(`python -m pwm.cli`). Its dependencies are installed by `launch.sh pip`.

Every misconfiguration is rejected before step one (typed YAML validation, parallel
degree vs. process count, clip geometry vs. config, checkpoint/config consistency,
checkpoint-directory capacity); the only mid-run stop is the divergence gate.

## License

CC BY-NC 4.0 — Copyright (c) 2026 Hokin Deng <hokinxqdeng@gmail.com>.
Non-commercial research use with attribution; contact the author for commercial licensing.
PWM-WROP is built on NVIDIA Cosmos (base model https://huggingface.co/nvidia/Cosmos3-Nano);
its own terms apply to the base-model portions.

## Citation

```bibtex
@article{deng2026wrop,
  title   = {Training Object Permanence in World Models},
  author  = {Deng, Hokin and others},
  year    = {2026},
  url     = {https://object-permanence.world}
}
```
