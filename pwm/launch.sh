#!/usr/bin/env bash
# launch.sh — run pwm on one trn2 box (trn2.48xlarge or trn2.3xlarge), either directly in the Neuron SDK
# 2.33 DLAMI's torch-neuronx venv (default when present) or in a persistent Neuron DLC container.
#
# The pwm CLI reads tp/fsdp from the YAML and re-execs itself under torchrun, so this script never
# passes rank/mesh flags.
#
# Usage:
#   bash pwm/launch.sh preflight                 # host checks incl. device occupancy — read-only
#   bash pwm/launch.sh pip  <name>               # create container if needed + install pwm deps
#   bash pwm/launch.sh <name> -- <cmd...>        # run <cmd> inside <name>, tee to /out/<name>/<UTC>.log
#     e.g. bash pwm/launch.sh pwm -- python -m pwm.cli bench /repo/pwm/configs/example.yaml --warmup 3 --steps 20
#
# Host paths (override by env)         -> container mount
#   REPO_HOST   this checkout (derived)  -> /repo         PYTHONPATH=/repo (NO stubs dir: pwm never imports torchvision)
#   WEIGHTS_HOST $HOME/weights           -> /weights:ro   must contain Cosmos3-Nano/{transformer,vae,text_tokenizer}
#   OUT_HOST    $HOME/out                -> /out          logs, checkpoints, samples
#   NEFF_HOST   $HOME/neff_cache         -> /neff_cache   TORCH_NEURONX_NEFF_CACHE_DIR (persists across containers)
# Runtime, one of:
#   venv mode (default on an SDK 2.33 DLAMI): PWM_VENV=/opt/aws_neuronx_venv_torch_neuronx_2_14_0 (torch 2.14,
#     torch-neuronx 2.14.3). No Docker. The container paths above become host symlinks (sudo once) so every
#     command and config path in the README works unchanged; <name> is just the log directory.
#   container mode: PWM_IMAGE=<image> — a Neuron Deep Learning Container whose PyTorch runs natively on
#     Trainium (torch_neuronx >= 2.11.3 with device="neuron" and torch.compile(backend="neuron")), pulled by
#     digest. Setting PWM_IMAGE selects container mode even when the venv exists.
# Knobs: DRY_RUN=1 (print commands only) · DETACH=1 (docker exec -d; tail the log yourself)
#        RECREATE=1 (docker rm -f the container first) · NEURONX_CC_SLOTS=8 (parallel neuronx-cc bound)
#        ALLOW_BUSY=1 (preflight: report device occupancy but do not fail on it)
#        EXPECT_DEVICES=N (preflight: expected /dev/neuron* count; default by instance type)
#
# Deliberately NOT exported: NEURON_RT_NUM_CORES / NEURON_RT_VISIBLE_CORES — the torch_neuronx c10d
# backend binds one logical core per torchrun rank; setting either makes 64 ranks fight over cores.
set -euo pipefail

PWM_VENV_DEFAULT=/opt/aws_neuronx_venv_torch_neuronx_2_14_0   # Neuron SDK 2.33 DLAMI
if [ -n "${PWM_IMAGE:-}" ]; then
  MODE=container
elif [ -n "${PWM_VENV:-}" ] || [ -x "$PWM_VENV_DEFAULT/bin/python" ]; then
  MODE=venv; PWM_VENV="${PWM_VENV:-$PWM_VENV_DEFAULT}"
else
  echo "set PWM_VENV (Neuron SDK 2.33 DLAMI: $PWM_VENV_DEFAULT) or PWM_IMAGE (see header)" >&2; exit 2
fi
DIGEST="${PWM_IMAGE:-}"
# Host driver the runtime expects. This is PAIRED WITH THE RUNTIME, not fixed:
#   SDK 2.33 DLAMI venv (torch 2.14): 2.31.7.0 -- what that DLAMI ships
#   Beta 3 container (torch 2.11):    2.28.0.0 -- 2.29+ cannot DMA the Q7 pooling ucode through its firmware
#   Beta 5/6 containers (torch 2.12/2.13): 2.30.2.0 (SDK 2.32 DLAMI 20260818)
# Override to match yours.
if [ "$MODE" = venv ]; then DKMS_REQUIRED="${DKMS_REQUIRED:-2.31.7.0}"; else DKMS_REQUIRED="${DKMS_REQUIRED:-2.30.2.0}"; fi
# Python to run. Venv mode: the DLAMI venv. Container mode: the DLC's native-torch venv (bare `python` can mix
# interpreters) -- Beta 3/4 at /opt/torch-neuronx/.venv/bin, Beta 5/6 at /usr/local/bin; unset = autodetect
# from the image (detect_venv), or pin VENV.
if [ "$MODE" = venv ]; then VENV="$PWM_VENV/bin"; else VENV="${VENV:-}"; fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_HOST="${REPO_HOST:-$(cd "$SCRIPT_DIR/.." && pwd)}"
WEIGHTS_HOST="${WEIGHTS_HOST:-$HOME/weights}"
OUT_HOST="${OUT_HOST:-$HOME/out}"
NEFF_HOST="${NEFF_HOST:-$HOME/neff_cache}"
NEURONX_CC_SLOTS="${NEURONX_CC_SLOTS:-8}"
DRY_RUN="${DRY_RUN:-0}"

# Locate the image's python. Beta 3/4: /opt/torch-neuronx/.venv/bin. Beta 5/6: /usr/local/bin.
# Set VENV explicitly to skip the probe. Runs once; every caller goes through ensure_container
# or preflight, both of which call this first.
detect_venv() {
  [ "$MODE" = venv ] && return 0
  [ -n "$VENV" ] && return 0
  command -v docker >/dev/null || return 0        # preflight reports missing docker itself
  docker image inspect "$DIGEST" >/dev/null 2>&1 || return 0   # ditto for an unpulled image
  local c
  for c in /opt/torch-neuronx/.venv/bin /usr/local/bin; do
    if docker run --rm --entrypoint test "$DIGEST" -x "$c/python" 2>/dev/null; then
      VENV="$c"
      log "venv in image: $VENV"
      return 0
    fi
  done
  echo "launch.sh: no python found in $DIGEST (tried /opt/torch-neuronx/.venv/bin and" >&2
  echo "  /usr/local/bin). Set VENV=<dir containing python> explicitly." >&2
  exit 1
}

usage() { sed -n '2,23p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit "${1:-2}"; }
log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
run() { if [ "$DRY_RUN" = 1 ]; then printf '+ %q' "$1"; shift; for a in "$@"; do printf ' %q' "$a"; done; printf '\n'; else "$@"; fi; }

# ----------------------------------------------------------------------------- preflight (host)
preflight() {
  local fail=0 busy=0
  detect_venv
  echo "== pwm preflight $(date -u +%Y-%m-%dT%H:%M:%SZ) host=$(hostname) =="

  # 1. host driver row. /sys/module/neuron/version works on Ubuntu DLAMI and AL2023 alike.
  local drv=""
  [ -r /sys/module/neuron/version ] && drv="$(cat /sys/module/neuron/version)"
  [ -z "$drv" ] && command -v modinfo >/dev/null && drv="$(modinfo neuron 2>/dev/null | awk '$1=="version:"{print $2}' || true)"
  if [ "$drv" = "$DKMS_REQUIRED" ]; then
    echo "driver      : aws-neuronx-dkms $drv  OK"
  else
    echo "driver      : aws-neuronx-dkms '${drv:-not loaded}'  FAIL (need $DKMS_REQUIRED)"
    echo "  the driver must match the IMAGE (Beta 3 -> 2.28.0.0; Beta 5/6 -> 2.30.2.0)."
    echo "  If the image is NEWER than the host driver, prefer a newer DLAMI, or install the"
    echo "  image-bundled debs inside the container: dpkg -i /workspace/runtime_artifacts/*.deb"
    echo "  To move the HOST driver instead (DLAMI holds the package; then reboot or reload):"
    echo "    sudo apt-get update -qq && sudo apt-mark unhold aws-neuronx-dkms && \\"
    echo "    sudo apt-get install -y --allow-downgrades --allow-change-held-packages aws-neuronx-dkms=$DKMS_REQUIRED && \\"
    echo "    sudo apt-mark hold aws-neuronx-dkms && sudo reboot"
    fail=1
  fi

  # 2. Devices: 16 on trn2.48xlarge (64 logical cores under LNC2), 1 on trn2.3xlarge (4 cores).
  local ndev; ndev="$(find /dev -maxdepth 1 -name 'neuron[0-9]*' | wc -l)"
  local want="${EXPECT_DEVICES:-}"
  if [ -z "$want" ]; then
    local itype; itype="$(curl -s -m 2 http://169.254.169.254/latest/meta-data/instance-type 2>/dev/null || true)"
    case "$itype" in trn2.48xlarge) want=16 ;; trn2.3xlarge) want=1 ;; *) want="$ndev" ;; esac
  fi
  if [ "$ndev" -ge 1 ] && [ "$ndev" -eq "$want" ]; then echo "devices     : $ndev /dev/neuron* OK"; else echo "devices     : $ndev /dev/neuron* FAIL (expected $want; set EXPECT_DEVICES to override)"; fail=1; fi
  if command -v neuron-ls >/dev/null; then { neuron-ls 2>&1 | sed 's/^/  /' | head -40; } || true; else echo "  neuron-ls: not on PATH (aws-neuronx-tools missing?)"; fi

  # 3. runtime: the venv (venv mode) or the image pulled by digest (container mode).
  if [ "$MODE" = venv ]; then
    if TORCH_DEVICE_BACKEND_AUTOLOAD=0 "$VENV/python" -c 'import importlib.util as u, sys; sys.exit(0 if u.find_spec("torch_neuronx") else 1)' 2>/dev/null; then
      echo "venv        : $PWM_VENV OK ($(TORCH_DEVICE_BACKEND_AUTOLOAD=0 "$VENV/python" -c 'import importlib.metadata as m; print("torch", m.version("torch"), "torch-neuronx", m.version("torch-neuronx"))' 2>/dev/null))"
    else echo "venv        : $PWM_VENV has no torch_neuronx"; fail=1; fi
    for l in /repo /weights /out /neff_cache; do
      [ -e "$l" ] && echo "path        : $l -> $(readlink -f "$l") OK" || { echo "path        : $l MISSING (run: bash pwm/launch.sh pip <name>)"; }
    done
  elif ! command -v docker >/dev/null; then echo "docker      : MISSING"; fail=1
  elif docker image inspect "$DIGEST" --format 'image       : {{.Id}} OK' 2>/dev/null; then :
  else
    echo "image       : $DIGEST NOT PULLED"
    echo "  fix: log in to the registry that hosts it, then: docker pull $DIGEST"
    fail=1
  fi

  # 4. NEFF cache dir writable (host side of /neff_cache).
  if mkdir -p "$NEFF_HOST" 2>/dev/null && touch "$NEFF_HOST/.preflight" 2>/dev/null; then
    rm -f "$NEFF_HOST/.preflight"; echo "neff_cache  : $NEFF_HOST writable OK ($(ls "$NEFF_HOST" | wc -l) entries)"
  else echo "neff_cache  : $NEFF_HOST NOT WRITABLE"; fail=1; fi

  # 5. flock — the compile-throttle shim needs it INSIDE the image.
  if [ "$MODE" = container ] && command -v docker >/dev/null && docker image inspect "$DIGEST" >/dev/null 2>&1; then
    if docker run --rm --entrypoint bash "$DIGEST" -c 'command -v flock' >/dev/null 2>&1; then echo "flock(image): OK"; else echo "flock(image): MISSING in DLC"; fail=1; fi
  fi

  # 6. weights + repo.
  for d in transformer vae text_tokenizer; do
    [ -d "$WEIGHTS_HOST/Cosmos3-Nano/$d" ] && echo "weights     : $WEIGHTS_HOST/Cosmos3-Nano/$d OK" || { echo "weights     : $WEIGHTS_HOST/Cosmos3-Nano/$d MISSING"; fail=1; }
  done
  [ -f "$REPO_HOST/pwm/cli.py" ] && echo "repo        : $REPO_HOST OK ($(git -C "$REPO_HOST" rev-parse --short HEAD 2>/dev/null || echo no-git))" || { echo "repo        : $REPO_HOST has no pwm/cli.py"; fail=1; }

  # 7. Is anyone else on the box? load, RAM, containers, device holders, active runtimes.
  echo "uptime      : $(uptime)"
  command -v free >/dev/null && free -g | sed 's/^/  /'
  df -hP "$OUT_HOST" 2>/dev/null | tail -1 | sed 's/^/  out disk: /' || true
  if command -v docker >/dev/null; then
    local cts; cts="$(docker ps --format '{{.Names}}\t{{.Status}}\t{{.Image}}' 2>/dev/null || true)"
    if [ -n "$cts" ]; then echo "containers  :"; echo "$cts" | sed 's/^/  /'; else echo "containers  : none running"; fi
  fi
  local holders=""
  if command -v fuser >/dev/null; then holders="$( (sudo -n fuser /dev/neuron* 2>/dev/null || fuser /dev/neuron* 2>/dev/null) | tr -s ' ' | sed 's/^ *//' || true)"; fi
  # fuser cannot see processes inside containers; neuron-ls lists every PID holding a core.
  if command -v neuron-ls >/dev/null; then holders="$holders $(neuron-ls 2>/dev/null | awk -F'|' '$7 ~ /^[[:space:]]*[0-9]+[[:space:]]*$/ {printf "%s ", $7}' | tr -s ' ')"; holders="$(echo "$holders" | xargs 2>/dev/null || true)"; fi
  if [ -n "$holders" ]; then echo "device pids : $holders  <- BUSY"; busy=1; else echo "device pids : none (fuser)"; fi
  if command -v neuron-monitor >/dev/null; then
    # one JSON sample; count runtimes that report memory in use (neuron-top-style occupancy).
    local sample; sample="$(timeout 8 neuron-monitor 2>/dev/null | head -n1 || true)"
    if [ -n "$sample" ]; then
      local occ; occ="$(printf '%s' "$sample" | python3 -c '
import json,sys
d=json.load(sys.stdin); rts=d.get("neuron_runtime_data",[]); cores=set(); n=0
for r in rts:
    n+=1
    mu=r.get("report",{}).get("memory_used",{}).get("neuron_runtime_used_bytes",{})
    cores.update((mu.get("usage_breakdown",{}).get("neuroncore_memory_usage",{}) or {}).keys())
print(f"{n} runtime(s), {len(cores)} core(s) with resident memory")' 2>/dev/null || echo "unparsed sample")"
      echo "neuron-mon  : $occ"
      case "$occ" in 0\ runtime*) : ;; unparsed*) : ;; *) busy=1 ;; esac
    else echo "neuron-mon  : no sample (tool present, nothing reported)"; fi
  else echo "neuron-mon  : neuron-monitor not on PATH — occupancy from fuser only"; fi

  echo "== result =="
  if [ "$fail" -ne 0 ]; then echo "PREFLIGHT FAILED — fix the FAIL lines above before launching"; return 1; fi
  if [ "$busy" -ne 0 ] && [ "${ALLOW_BUSY:-0}" != 1 ]; then
    echo "PREFLIGHT: BOX BUSY — Neuron devices are held by other processes; do not launch (ALLOW_BUSY=1 to override)."
    return 3
  fi
  echo "PREFLIGHT OK — $ndev device(s), driver $DKMS_REQUIRED, $MODE runtime + cache + weights present, box idle"
}

# ----------------------------------------------------------------------------- container
ensure_container() {
  local name="$1"
  detect_venv
  for d in "$WEIGHTS_HOST/Cosmos3-Nano" "$REPO_HOST/pwm"; do
    [ -d "$d" ] || { echo "missing $d" >&2; [ "$DRY_RUN" = 1 ] || exit 1; }
  done
  run mkdir -p "$OUT_HOST" "$NEFF_HOST"
  if [ "${RECREATE:-0}" = 1 ]; then run docker rm -f "$name"; fi
  local state; state="$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null || echo absent)"
  if [ "$state" = true ]; then log "container $name already running — reusing"; return; fi
  if [ "$state" = false ]; then log "container $name exists but stopped — starting"; run docker start "$name"; return; fi
  local devs=(); for d in /dev/neuron[0-9]*; do [ -e "$d" ] && devs+=("--device=$d"); done
  log "creating container $name from $DIGEST"
  run docker run -d --name "$name" ${devs[@]+"${devs[@]}"} --shm-size=64g \
    -e PYTHONUNBUFFERED=1 \
    -e PYTHONPATH=/repo \
    -e NEURON_RT_VIRTUAL_CORE_SIZE=2 \
    -e TORCH_NEURONX_NEFF_CACHE_DIR=/neff_cache \
    -e PWM_PG_TIMEOUT_S=21600 \
    -e NEURON_RT_EXEC_TIMEOUT=7200 \
    -e TORCH_NEURONX_ENABLE_HOST_CC=1 \
    -e TORCH_NEURONX_ENABLE_STREAMS=1 \
    -e TORCH_NEURONX_ENABLE_ASYNC_NRT=1 \
    -e NEURON_CC_FLAGS="--model-type=transformer" \
    -e NEURON_RT_STOCHASTIC_ROUNDING_EN=0 \
    -e NEURONX_CC_SLOTS="$NEURONX_CC_SLOTS" \
    -v "$REPO_HOST":/repo \
    -v "$WEIGHTS_HOST":/weights:ro \
    -v "$OUT_HOST":/out \
    -v "$NEFF_HOST":/neff_cache \
    -w /repo --entrypoint sleep "$DIGEST" infinity
  install_cc_shim "$name"
}

# compile-concurrency throttle: nothing in the CLI bounds concurrent neuronx-cc, and 64 first-touch
# compiles at tens of GB RSS each swap-thrash the box. The shim bounds them to NEURONX_CC_SLOTS (default 8).
install_cc_shim() {
  local name="$1"
  run docker exec "$name" bash -c '
set -e
CC='"$VENV"'/neuronx-cc
[ -x "$CC" ] || { echo "compile throttle: no neuronx-cc at $CC" >&2; exit 1; }
[ -f "$CC.real" ] && { echo "compile throttle present"; exit 0; }
mv "$CC" "$CC.real"
cat > "$CC" <<"SHIM"
#!/bin/bash
N=${NEURONX_CC_SLOTS:-8}
D=/tmp/nccslots; mkdir -p $D
while :; do
  for i in $(seq 1 $N); do
    exec {fd}>"$D/slot.$i"
    if flock -n $fd; then exec '"$VENV"'/neuronx-cc.real "$@"; fi
    exec {fd}>&-
  done
  sleep 5
done
SHIM
chmod +x "$CC"
# Verify rather than assume: a wrong $VENV used to leave every step above failing
# while this function still printed success, and an unthrottled 64-rank first-touch
# compile wave swap-thrashes the box.
[ -x "$CC" ] && [ -x "$CC.real" ] || { echo "compile throttle: install FAILED" >&2; exit 1; }
echo "compile throttle installed"'
}

# ----------------------------------------------------------------------------- pip
# pwm runtime deps from public PyPI. `--isolated` drops the DLC's pip.conf (its extra-index-url is a private
# Neuron repository that 401s on every package); `--index-url` must come AFTER `install`. A constraints file
# written live pins torch/numpy to the versions the container has, so the resolver may install transitive
# deps (Pillow, huggingface-hub, regex, ...) but can never swap the Neuron torch; torchvision is not a
# dependency of anything here and must never be added. The guard afterwards fails loudly if torch changed,
# torch_neuronx vanished, or torchvision appeared.
# TORCH_DEVICE_BACKEND_AUTOLOAD=0 on every CPU-only python here: a bare `import torch` in this container
# auto-loads torch_neuronx, which initialises the runtime and dies without a device.
pip_deps() {
  local name="$1"
  ensure_container "$name"
  run docker exec "$name" bash -c '
set -euo pipefail
V='"$VENV"'
if TORCH_DEVICE_BACKEND_AUTOLOAD=0 $V/python -c "import yaml, safetensors, numpy, imageio, imageio_ffmpeg, diffusers, transformers, accelerate" 2>/dev/null; then
  echo "pwm deps OK (cached)"
else
  C=/tmp/pwm-constraints.txt
  TORCH_DEVICE_BACKEND_AUTOLOAD=0 $V/python - <<"PY" > $C
import importlib.metadata as m
for d in ("torch", "numpy"):
    print(f"{d}=={m.version(d)}")
PY
  echo "live constraints:"; cat $C
  $V/pip --isolated install -q --index-url https://pypi.org/simple -c $C \
    pyyaml safetensors numpy imageio imageio-ffmpeg "diffusers>=0.39.0" \
    "transformers>=4.57.1,<5" accelerate
fi
TORCH_DEVICE_BACKEND_AUTOLOAD=0 $V/python - <<"PY"
import importlib.util as u, torch, numpy, yaml, safetensors, diffusers, transformers
assert u.find_spec("torch_neuronx") is not None, "torch-neuronx was uninstalled"
assert u.find_spec("torchvision") is None, "torchvision got installed — ABI-incompatible, remove it"
print("DLC stack intact: torch", torch.__version__, "| numpy", numpy.__version__,
      "| transformers", transformers.__version__, "| diffusers", diffusers.__version__)
PY
$V/python -c "import torch, torch_neuronx; print(torch.__version__)"'
}

# ----------------------------------------------------------------------------- run
run_cmd() {
  local name="$1"; shift
  [ "$#" -gt 0 ] || usage
  ensure_container "$name"
  local ts; ts="$(date -u +%Y-%m-%dT%H%M%SZ)"
  local logf="/out/$name/$ts.log"
  log "exec in $name -> $logf (host: $OUT_HOST/$name/$ts.log)"
  # PATH puts the DLC venv first so `python` / `torchrun` in <cmd> are the native-torch ones.
  local inner='unset NEURON_RT_NUM_CORES NEURON_RT_VISIBLE_CORES; export PATH='"$VENV"':$PATH
mkdir -p "$(dirname "$1")"; L="$1"; shift; cd /repo
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] launch: $*" | tee -a "$L"
set -o pipefail; "$@" 2>&1 | tee -a "$L"; rc=${PIPESTATUS[0]}
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] exit $rc" | tee -a "$L"; exit $rc'
  if [ "${DETACH:-0}" = 1 ]; then
    run docker exec -d "$name" bash -c "$inner" bash "$logf" "$@"
    echo "detached. tail: tail -f $OUT_HOST/$name/$ts.log   stop: docker exec $name pkill -f torch.distributed.run"
  else
    run docker exec "$name" bash -c "$inner" bash "$logf" "$@"
  fi
}

# ----------------------------------------------------------------------------- venv mode (no container)
# The env vars the container sets with -e, for processes run straight from the venv.
venv_env() {
  export PYTHONUNBUFFERED=1 PYTHONPATH=/repo NEURON_RT_VIRTUAL_CORE_SIZE=2 \
    TORCH_NEURONX_NEFF_CACHE_DIR=/neff_cache PWM_PG_TIMEOUT_S=21600 NEURON_RT_EXEC_TIMEOUT=7200 \
    TORCH_NEURONX_ENABLE_HOST_CC=1 TORCH_NEURONX_ENABLE_STREAMS=1 \
    NEURON_CC_FLAGS="--model-type=transformer" NEURON_RT_STOCHASTIC_ROUNDING_EN=0 \
    NEURONX_CC_SLOTS="$NEURONX_CC_SLOTS"
  unset NEURON_RT_NUM_CORES NEURON_RT_VISIBLE_CORES
  # compile throttle without editing the shared venv: a neuronx-cc wrapper first on PATH.
  local sd=/tmp/pwm-cc-shim; mkdir -p "$sd"
  if [ ! -x "$sd/neuronx-cc" ]; then
    cat > "$sd/neuronx-cc" <<SHIM
#!/bin/bash
N=\${NEURONX_CC_SLOTS:-8}; D=/tmp/nccslots; mkdir -p \$D
while :; do
  for i in \$(seq 1 \$N); do
    exec {fd}>"\$D/slot.\$i"
    if flock -n \$fd; then exec $VENV/neuronx-cc "\$@"; fi
    exec {fd}>&-
  done
  sleep 5
done
SHIM
    chmod +x "$sd/neuronx-cc"
  fi
  export PATH="$sd:$VENV:$PATH"
}

# /repo, /weights, /out, /neff_cache as host symlinks so README paths and YAML paths resolve as in the container.
ensure_paths() {
  run mkdir -p "$OUT_HOST" "$NEFF_HOST"
  local l t
  for pair in "/repo:$REPO_HOST" "/weights:$WEIGHTS_HOST" "/out:$OUT_HOST" "/neff_cache:$NEFF_HOST"; do
    l="${pair%%:*}"; t="${pair#*:}"
    if [ -L "$l" ] && [ "$(readlink "$l")" = "$t" ]; then continue; fi
    if [ -e "$l" ] && [ ! -L "$l" ]; then echo "$l exists and is not a symlink; refusing to replace it" >&2; exit 1; fi
    log "linking $l -> $t (sudo)"; run sudo ln -sfn "$t" "$l"
  done
}

pip_deps_venv() {
  ensure_paths
  local V="$VENV"
  if TORCH_DEVICE_BACKEND_AUTOLOAD=0 "$V/python" -c "import yaml, safetensors, numpy, imageio, imageio_ffmpeg, diffusers, transformers, accelerate" 2>/dev/null; then
    echo "pwm deps OK (cached)"
  else
    local C=/tmp/pwm-constraints.txt
    TORCH_DEVICE_BACKEND_AUTOLOAD=0 "$V/python" - > "$C" <<"PY"
import importlib.metadata as m
for d in ("torch", "numpy", "torch-neuronx", "neuronx-cc", "nki"):
    print(f"{d}=={m.version(d)}")
PY
    echo "live constraints:"; cat "$C"
    run "$V/pip" install -q -c "$C" pyyaml safetensors numpy imageio imageio-ffmpeg "diffusers>=0.39.0" \
      "transformers>=4.57.1,<5" accelerate
  fi
  TORCH_DEVICE_BACKEND_AUTOLOAD=0 "$V/python" - <<"PY"
import importlib.util as u, torch, numpy, yaml, safetensors, diffusers, transformers
assert u.find_spec("torch_neuronx") is not None, "torch-neuronx was uninstalled"
assert u.find_spec("torchvision") is None, "torchvision got installed — ABI-incompatible, remove it"
print("venv stack intact: torch", torch.__version__, "| numpy", numpy.__version__,
      "| transformers", transformers.__version__, "| diffusers", diffusers.__version__)
PY
}

run_cmd_venv() {
  local name="$1"; shift
  [ "$#" -gt 0 ] || usage
  ensure_paths
  local ts; ts="$(date -u +%Y-%m-%dT%H%M%SZ)"
  local logf="$OUT_HOST/$name/$ts.log"; mkdir -p "$(dirname "$logf")"
  log "run in $PWM_VENV -> $logf"
  if [ "$DRY_RUN" = 1 ]; then run "$@"; return; fi
  (
    venv_env; cd /repo
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] launch: $*" | tee -a "$logf"
    if [ "${DETACH:-0}" = 1 ]; then
      nohup bash -c 'set -o pipefail; "$@" 2>&1 | tee -a "'"$logf"'"; echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] exit ${PIPESTATUS[0]}" | tee -a "'"$logf"'"' bash "$@" >/dev/null 2>&1 &
      echo "detached (pid $!). tail: tail -f $logf   stop: pkill -f torch.distributed.run"
    else
      set -o pipefail; "$@" 2>&1 | tee -a "$logf"; rc=${PIPESTATUS[0]}
      echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] exit $rc" | tee -a "$logf"; exit $rc
    fi
  )
}

# ----------------------------------------------------------------------------- dispatch
[ "$#" -ge 1 ] || usage
case "$1" in
  -h|--help) usage 0 ;;
  preflight) preflight ;;
  pip) [ "$#" -ge 2 ] || usage; if [ "$MODE" = venv ]; then pip_deps_venv; else pip_deps "$2"; fi ;;
  *)
    NAME="$1"; shift
    [ "${1:-}" = "--" ] || { echo "expected '--' after the container name" >&2; usage; }
    shift
    if [ "$MODE" = venv ]; then run_cmd_venv "$NAME" "$@"; else run_cmd "$NAME" "$@"; fi
    ;;
esac
