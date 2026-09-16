#!/usr/bin/env bash
# launch.sh — persistent Neuron DLC container for pwm on one trn2 box (trn2.48xlarge or trn2.3xlarge).
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
# Required: PWM_IMAGE=<container image> — a Neuron Deep Learning Container whose PyTorch runs natively on
#   Trainium (torch_neuronx with device="neuron" and torch.compile(backend="neuron"); torch_neuronx >= 2.11.3).
#   pwm was developed on a pre-release build of that runtime from the AWS Neuron team; ask them for the image
#   or use the public release once it ships. Pull it by digest and pass the pinned reference here.
# Knobs: DRY_RUN=1 (print docker commands only) · DETACH=1 (docker exec -d; tail the log yourself)
#        RECREATE=1 (docker rm -f the container first) · NEURONX_CC_SLOTS=8 (parallel neuronx-cc bound)
#        ALLOW_BUSY=1 (preflight: report device occupancy but do not fail on it)
#        EXPECT_DEVICES=N (preflight: expected /dev/neuron* count; default by instance type)
#
# Deliberately NOT exported: NEURON_RT_NUM_CORES / NEURON_RT_VISIBLE_CORES — the torch_neuronx c10d
# backend binds one logical core per torchrun rank; setting either makes 64 ranks fight over cores.
set -euo pipefail

DIGEST="${PWM_IMAGE:?set PWM_IMAGE to the Neuron native-PyTorch container image (see header)}"
DKMS_REQUIRED="${DKMS_REQUIRED:-2.28.0.0}"  # host driver verified with the runtime pwm was developed on (async h2d CQ interface)
VENV=/opt/torch-neuronx/.venv/bin           # the DLC's native-torch venv; bare `python` mixes interpreters
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_HOST="${REPO_HOST:-$(cd "$SCRIPT_DIR/.." && pwd)}"
WEIGHTS_HOST="${WEIGHTS_HOST:-$HOME/weights}"
OUT_HOST="${OUT_HOST:-$HOME/out}"
NEFF_HOST="${NEFF_HOST:-$HOME/neff_cache}"
NEURONX_CC_SLOTS="${NEURONX_CC_SLOTS:-8}"
DRY_RUN="${DRY_RUN:-0}"

usage() { sed -n '2,23p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit "${1:-2}"; }
log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
run() { if [ "$DRY_RUN" = 1 ]; then printf '+ %q' "$1"; shift; for a in "$@"; do printf ' %q' "$a"; done; printf '\n'; else "$@"; fi; }

# ----------------------------------------------------------------------------- preflight (host)
preflight() {
  local fail=0 busy=0
  echo "== pwm preflight $(date -u +%Y-%m-%dT%H:%M:%SZ) host=$(hostname) =="

  # 1. host driver row. /sys/module/neuron/version works on Ubuntu DLAMI and AL2023 alike.
  local drv=""
  [ -r /sys/module/neuron/version ] && drv="$(cat /sys/module/neuron/version)"
  [ -z "$drv" ] && command -v modinfo >/dev/null && drv="$(modinfo neuron 2>/dev/null | awk '$1=="version:"{print $2}' || true)"
  if [ "$drv" = "$DKMS_REQUIRED" ]; then
    echo "driver      : aws-neuronx-dkms $drv  OK"
  else
    echo "driver      : aws-neuronx-dkms '${drv:-not loaded}'  FAIL (need $DKMS_REQUIRED)"
    echo "  fix (DLAMI holds the package; --allow-change-held-packages is required; then reboot or reload the module):"
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

  # 3. image pulled by digest.
  if ! command -v docker >/dev/null; then echo "docker      : MISSING"; fail=1
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
  if command -v docker >/dev/null && docker image inspect "$DIGEST" >/dev/null 2>&1; then
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
  echo "PREFLIGHT OK — $ndev device(s), driver $DKMS_REQUIRED, image + cache + weights present, box idle"
}

# ----------------------------------------------------------------------------- container
ensure_container() {
  local name="$1"
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
CC='"$VENV"'/neuronx-cc
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
chmod +x "$CC"; echo "compile throttle installed"'
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

# ----------------------------------------------------------------------------- dispatch
[ "$#" -ge 1 ] || usage
case "$1" in
  -h|--help) usage 0 ;;
  preflight) preflight ;;
  pip) [ "$#" -ge 2 ] || usage; pip_deps "$2" ;;
  *)
    NAME="$1"; shift
    [ "${1:-}" = "--" ] || { echo "expected '--' after the container name" >&2; usage; }
    shift
    run_cmd "$NAME" "$@"
    ;;
esac
