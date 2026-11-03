#!/usr/bin/env bash
# Restart the final60 supervisor until it exits 0 (all rows terminal or deadline passed).
#
#   scripts/final60_supervise.sh RUN_DIR [run options...]
#   e.g. scripts/final60_supervise.sh "$RUN" --key-file "$KEY" --rows 1-60 --compiler-slots 6
#
# Start detached:  nohup setsid scripts/final60_supervise.sh "$RUN" ... > "$RUN.watchdog.out" 2>&1 < /dev/null &
# Stop cleanly:    touch "$RUN/supervisor/STOP"   (row workers finish their current step on their own)
# Environment:     FINAL60_PYTHON (default: python3), FINAL60_RESTART_SECONDS (default: 30).
set -u
if [ "$#" -lt 1 ]; then
  echo "usage: $0 RUN_DIR [run options...]" >&2
  exit 2
fi
run_dir=$1
shift
here=$(cd "$(dirname "$0")/.." && pwd)
python=${FINAL60_PYTHON:-python3}
pause=${FINAL60_RESTART_SECONDS:-30}
mkdir -p "$run_dir/supervisor"
log="$run_dir/supervisor/watchdog.log"
export PYTHONPATH="$here/src${PYTHONPATH:+:$PYTHONPATH}"
cd "$here" || exit 2
while :; do
  if [ -e "$run_dir/supervisor/STOP" ]; then
    echo "$(date -u +%FT%TZ) STOP file present; watchdog exits" >> "$log"
    exit 0
  fi
  echo "$(date -u +%FT%TZ) start supervisor" >> "$log"
  "$python" -m lean_agent.final60 run --run-dir "$run_dir" "$@" >> "$log" 2>&1
  code=$?
  echo "$(date -u +%FT%TZ) supervisor exit $code" >> "$log"
  if [ "$code" -eq 0 ]; then
    exit 0
  fi
  sleep "$pause"
done
