# object-permanence

<div align="center">

<p align="center">
    <a href="https://object-permanence.world" target="_blank">
        <img alt="Project Page" src="https://img.shields.io/badge/Project%20-%20Homepage-4285F4" height="20" />
    </a>
    <a href="https://object-permanence.world/paper" target="_blank">
        <img alt="Paper" src="https://img.shields.io/badge/Paper-Training_Object_Permanence-red?logo=readthedocs&logoColor=white" height="20" />
    </a>
    <a href="https://object-permanence.world/leaderboard" target="_blank">
        <img alt="Leaderboard" src="https://img.shields.io/badge/Leaderboard-14_video_models-4285F4" height="20" />
    </a>
    <a href="https://huggingface.co/datasets/Hokin/object-permanence" target="_blank">
        <img alt="Training corpus" src="https://img.shields.io/badge/%F0%9F%A4%97%20_Dataset-Training_corpus_1.5M-ffc107?color=ffc107&logoColor=white" height="20" />
    </a>
    <a href="https://huggingface.co/datasets/Hokin/object-permanence-benchmark" target="_blank">
        <img alt="Benchmark" src="https://img.shields.io/badge/%F0%9F%A4%97%20_Dataset-Benchmark_300_questions-ffc107?color=ffc107&logoColor=white" height="20" />
    </a>
    <a href="https://huggingface.co/Hokin/PWM-WROP" target="_blank">
        <img alt="Model" src="https://img.shields.io/badge/%F0%9F%A4%97%20_Model-PWM--WROP_16B-ffc107?color=ffc107&logoColor=white" height="20" />
    </a>
    <a href="LICENSE">
        <img alt="License" src="https://img.shields.io/badge/License-CC_BY--NC_4.0-blue.svg" height="20" />
    </a>
    <a href="LICENSE">
        <img alt="Base model license" src="https://img.shields.io/badge/Cosmos-OpenMDW_1.1-blue.svg" height="20" />
    </a>
</p>

</div>

Code for the paper **_Training Object Permanence in World Models_**. Everything
behind it in one repository:

| | Part | What it is |
|---|---|---|
| 1 | [`object_permanence/`](#1-data-factory) | Data factory — 150 Blender task generators that render the WROP corpus (object permanence + object solidity) as video-to-video samples, plus the `object-permanence` CLI |
| 2 | [`pwm/`](#2-training-stack) | Training stack — native-PyTorch Cosmos3-Nano on AWS Trainium2, the recipe that fine-tuned PWM-WROP (16B) on 1.5M samples |

```
object-permanence/
├── object_permanence/   Part 1 · data factory: 150 Blender task generators + CLI
├── pwm/                 Part 2 · training stack: Cosmos3-Nano on Trainium2, native PyTorch
├── pyproject.toml       pip package `object-permanence`
└── LICENSE              CC BY-NC 4.0 (Part A) + NVIDIA Cosmos OpenMDW-1.1 (Part B)
```

---

## 1. Data factory

Blender-rendered scenes where objects persist while occluded, packaged as
video-to-video samples. 150 self-contained task generators in six cognitively
grounded families:

| Concept | Families |
|---|---|
| Object permanence | Baillargeonian occlusion · static occlusion · container permanence |
| Object solidity | Baillargeonian obstruction · object drop · object collision |

The task → family map lives in one place, `object_permanence/taxonomy.py`.
Trajectories are hand-authored keyframes; the one exception is
`G73_break_scatter_cluster`, which bakes a Blender rigid-body simulation to keyframes.

### 1.1 Install

```bash
git clone https://github.com/hokindeng/object-permanence.git
cd object-permanence

pip install -e .
```

Two things must be on the machine:

| Requirement | Why |
|---|---|
| **Blender 4.4.x** | The corpus was rendered with 4.4.3. The renderer refuses any other version because pixels would differ (`OP_ALLOW_BLENDER_MISMATCH=1` overrides, for local experiments only) |
| **ffmpeg** on the PATH | Encodes the rendered frames into the two clips |

Blender is found via `OP_BLENDER`, then the usual install paths
(`/opt/homebrew/bin/blender`, `/Applications/Blender.app/...`, `/usr/local/bin`,
`/usr/bin`, `/snap/bin`), then the PATH; `--blender <path>` overrides all of them.

> **Note:** Homebrew and apt often ship a different major version — point
> `OP_BLENDER` at a 4.4.x download from
> [download.blender.org/release/Blender4.4](https://download.blender.org/release/Blender4.4/).

> **Note:** Set `OP_FORCE_EEVEE=1` on every headless machine, Mac included.
> Without it the OpenGL probe fails and Blender silently falls back to Cycles:
> the engine changes and a sample takes minutes instead of seconds.

### 1.2 Generate

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

# Standard-resolution, frame-continuous preview for collision-boundary QA
object-permanence generate --task G120 --per 3 --preview 1 --preview-frame-step 1

# Keep only the previous appearance-level variation
object-permanence generate --task G18 --per 20 --diversity-profile surface
```

Samples land in `<out>/<name>_task/<name>_NNNN/`, where `<name>` is the task name without its G-id. Generation prints a live
progress line (`880/3000 (29%) | ok=872 fail=8 | 12m03s elapsed | ETA 42m11s`);
it updates in place in a terminal and falls back to one line per step when piped
to a log. A failed sample leaves an `ERROR.txt` in its directory.

| Flag | Description |
|---|---|
| `--task G18` / `--gen G18` | One task |
| `--gens G01-G11` | A range of tasks (shards for parallel fleets) |
| `--per N` / `--start N` | Samples per task / first sample index |
| `--parallel N` | Concurrent Blender processes (default 3) |
| `--preview 1` | 360p fast preview; `--preview-frame-step 1` keeps every frame |
| `--split-mode half\|event` | Where the input/target split falls (see [Output format](#14-output-format)) |
| `--diversity-profile surface` | Appearance-only variation, as in earlier corpus versions |
| `--render-timeout S` | Seconds per Blender process |
| `--blender <path>` | Blender binary, overrides `OP_BLENDER` and the search paths |

The released corpus on Hugging Face was rendered with this package at version
1.9.1 (`object_permanence.__version__`), Blender 4.4.3, EEVEE Next.

### 1.3 Audit

```bash
# Validate generated output against the task manifests
object-permanence audit --out ./out

# Previews too
object-permanence audit --out ./out --allow-preview

# Require real task-level variation rather than appearance-only samples
object-permanence audit --out ./out --require-task-specific-diversity

# Require balanced factorial provenance and non-repeating design cells
object-permanence audit --out ./out --require-balanced-factorial
```

### 1.4 Output format

Each sample is a five-file V2V / TV2V set:

```
<out>/turntable_behind_screen_task/turntable_behind_screen_0000/          # task G18
├── input_video.mp4      # Simulation up to the split point (model conditioning input)
├── target_video.mp4     # Simulation after the split point (reference output)
├── prompt.txt           # Continuation instruction: what the target clip shows
├── trajectory.npz       # Per-frame ground truth for every body
└── metadata.json        # Parameters, provenance, video split
```

| File | Contents |
|------|----------|
| `trajectory.npz` | `xpos [T,N,3]`, `xquat [T,N,4]`, `qpos [T,N*7]`, `qvel [T,N*6]` (free-body), plus `body_names`, `body_roles`, `body_shapes`, `body_colors`, `is_target`, `fps`, `frame_start`, `frame_end` |
| `metadata.json` | `parameters` (seed, source script, diversity cell, applied knobs, source bindings) · `provenance` (generator version, Blender version, render engine) · `video_split` (frame boundary and clip indices) |

Each task renders **120 frames at 24 fps** and splits them **60 / 60**. Both
clips always contain exactly 60 frames, using edge-frame padding when fewer than
60 source frames are available on one side.

| Split policy (`metadata.json` → `video_split.method`) | Where the cut falls | Tasks |
|---|---|---|
| `midpoint` — the default, `--split-mode half` | Temporal midpoint | 107 |
| `before_event` | The event's first frame opens the target clip | 36 |
| `overlap_event` | The exact contact frame is both the last input frame and the first target frame (collision tasks) | 7 |

The 43 semantic policies come from a `video_split` block in the task manifest.
The released corpus uses these defaults.

### 1.5 Package layout

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

### 1.6 Known issues (v1.9.1)

The released corpus was rendered with this version, defects included. They are
listed on the dataset card and repeated here so the two never diverge.

| Where | Defect |
|---|---|
| `wiper_screen_occlusion` (G121) | The screen still hides the ball at the end of the target half under the −16° viewpoint |
| `sliding_cover_panel` (G123) | The occluder is recoloured close to the backdrop, so the ball appears to vanish rather than be covered |
| `three_balls_parallel_tunnels` (G43) | The balls start out of frame |
| `high_low_cover`, `car_vs_barrier`, `guillotine_gate_stops`, `u_tube_three_lanes`, `theater_curtain`, `pendulum_behind_post`, `picket_fence_flicker`, `drop_screen_occluder`, `corner_turn_occlusion`, `ball_behind_box_stack` | The dark world background shows at frame edges |
| `hole_box_drop`, `ramp_tunnel`, `ramp_ball_blocked_by_wall` | Render against a flat dark backdrop |
| `cart_swap`, `guided_elevator_hidden_ball`, `trapdoor_opens_ball_falls`, `two_balls_collide_and_bounce` | Targets are very small |
| Several tasks | Physical-plausibility defects flagged in review were not all fixed: penetrations, super-elastic rebounds, objects starting out of frame under scaled dynamics. In some tasks the `is_target` mask also marks apparatus bodies, not only the object of interest |
| `trajectory.npz` | Borrows MuJoCo's field names (`xpos`, `xquat`, `qpos`, `qvel`) but the arrays are sampled from keyframed animation (G73 excepted); they are not physics ground truth |

---

## 2. Training stack

A native-PyTorch implementation of NVIDIA Cosmos3-Nano for AWS Trainium2: it
loads the public diffusers-layout weights and trains and samples on Neuron
without XLA graph tracing. Tensor parallel × FSDP2 over 64 NeuronCores on a
trn2.48xlarge.

| Config | Geometry | Purpose |
|---|---|---|
| `pwm/configs/wrop.yaml` | 320×192, 57 conditioning + 60 predicted frames, batch 16, one epoch over the 1.5M corpus | The PWM-WROP recipe of the paper |
| `pwm/configs/example.yaml` | 288×512 text-to-video | The geometry the throughput numbers were measured at |

Every key in both files is commented.

### 2.1 Requirements

| Requirement | Notes |
|---|---|
| trn2 instance | trn2.48xlarge for the production layout, trn2.3xlarge for single-node inference |
| Neuron driver + Docker | On the host |
| Neuron Deep Learning Container | PyTorch running natively on Trainium: `torch_neuronx` ≥ 2.11.3 with `device="neuron"` and `torch.compile(backend="neuron")`. Passed as `PWM_IMAGE=<image@digest>` |
| Cosmos3-Nano checkpoint | diffusers layout (`transformer/`, `vae/`, `text_tokenizer/`) under `$HOME/weights/Cosmos3-Nano` |

> **Note:** pwm was developed on a pre-release build of the native-PyTorch Neuron
> runtime from the AWS Neuron team. Ask them for the image, or use the public
> release once it ships.

### 2.2 Run

From the repository root on a trn2 box:

```bash
export PWM_IMAGE=<neuron native-pytorch container image@digest>
bash pwm/launch.sh pip pwm            # container "pwm" + deps
bash pwm/launch.sh preflight          # read-only checks: driver, devices, image, cache, weights, box idle
```

**Encode** — Part 1 renders (under `~/out/renders` = `/out/renders` in the
container) → encode manifest → fixed-shape clips. Once, on CPU:

```bash
bash pwm/launch.sh pwm -- sh -c 'python -m pwm.data.from_object_permanence /out/renders > /out/rows.jsonl'
bash pwm/launch.sh pwm -- python -m pwm.cli encode --manifest /out/rows.jsonl \
    --out /out/data/clips_320x192_t30 --ckpt /weights/Cosmos3-Nano --latent-t 30 --height 192 --width 320 --text-len 128
```

**Train** the paper recipe, or benchmark step time:

```bash
bash pwm/launch.sh pwm -- python -m pwm.cli train /repo/pwm/configs/wrop.yaml
bash pwm/launch.sh pwm -- python -m pwm.cli bench /repo/pwm/configs/example.yaml --warmup 3 --steps 20
```

**Sample** with the released PWM-WROP weights
(download [Hokin/PWM-WROP](https://huggingface.co/Hokin/PWM-WROP) to `/weights/PWM-WROP`):

```bash
bash pwm/launch.sh pwm -- python -m pwm.cli infer /repo/pwm/configs/wrop.yaml --weights /weights/PWM-WROP \
    --v2v /out/data/clips_320x192_t30/<id>.pt --prompt "..." --out /out/sample.mp4
```

**Export** a training checkpoint to diffusers layout:

```bash
bash pwm/launch.sh pwm -- python -m pwm.cli consolidate /repo/pwm/configs/wrop.yaml --step 93750 --out /out/ckpt-final --dtype bf16
```

`pwm` is not part of the pip package; run it from the repository root
(`python -m pwm.cli`). Its dependencies are installed by `launch.sh pip`.

Every misconfiguration is rejected before step one (typed YAML validation, parallel
degree vs. process count, clip geometry vs. config, checkpoint/config consistency,
checkpoint-directory capacity); the only mid-run stop is the divergence gate.

The full guide — machine setup, the pre-flight checks, data encoding, training,
sampling, checkpoint export, the performance ledger and thirteen architecture
diagrams derived from the code — is [`pwm/README.md`](pwm/README.md).

---

## License

CC BY-NC 4.0 — Copyright (c) 2026 Hokin Deng <hokinxqdeng@gmail.com>.
Non-commercial research use with attribution; contact the author for commercial licensing.

PWM-WROP is built on NVIDIA Cosmos. The base model, nvidia/Cosmos3-Nano
(Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES), and the Cosmos framework from
which `pwm/inference/unipc.py` is adapted are distributed by NVIDIA under the
OpenMDW License Agreement 1.1; its text is Part B of [LICENSE](LICENSE)
and its terms apply to those portions.

## Citation

```bibtex
@article{zhang2026training,
  title   = {Training Object Permanence in World Models},
  author  = {Zhang, Haotian and others},
  year    = {2026},
  url     = {https://object-permanence.world}
}
```
