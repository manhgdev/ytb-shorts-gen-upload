#!/usr/bin/env bash
# Tạo 1 Short + upload YouTube (gọi từ cron). Cần schedule.config.json + user_settings.json.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs

CONFIG="${SCHEDULE_CONFIG:-$ROOT/schedule.config.json}"
LOCK_FILE="$ROOT/logs/.schedule_create.lock"
PYTHON="${ROOT}/venv/bin/python"
MAIN="${ROOT}/main.py"
LOG_TAG="[schedule]"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $LOG_TAG $*"; }

if [[ ! -x "$PYTHON" ]]; then
  log "ERROR: thiếu venv — chạy: python3 -m venv venv && ./venv/bin/pip install -r requirements.txt"
  exit 1
fi

if [[ ! -f "$CONFIG" ]]; then
  log "ERROR: thiếu $CONFIG — cp schedule.config.example.json schedule.config.json"
  exit 1
fi

if [[ ! -f "$ROOT/user_settings.json" ]]; then
  log "ERROR: thiếu user_settings.json"
  exit 1
fi

# Đọc config bằng Python (không cần jq)
read -r ENABLED TZ_NAME ACCOUNT CHANNEL PRIVACY LANG PREFIX USE_MANUAL MANUAL_TOPIC <<< "$(
  "$PYTHON" - <<'PY' "$CONFIG"
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
c = json.loads(p.read_text(encoding="utf-8"))
if not c.get("enabled", True):
    print("false")
    sys.exit(0)
print("true")
print(c.get("timezone", "America/New_York"))
print(c.get("youtube_account_id", "LylyTaks1199"))
print(c.get("youtube_channel_id", "") or "")
print(c.get("youtube_privacy", "public"))
print(c.get("language", "en"))
print(c.get("output_prefix", "auto"))
print("true" if c.get("use_manual_topic") else "false")
print((c.get("manual_topic") or "").replace(" ", "_")[:40])
PY
)"

if [[ "$ENABLED" != "true" ]]; then
  log "disabled in config — skip"
  exit 0
fi

export TZ="$TZ_NAME"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="${PREFIX}_${STAMP}.mp4"
DAY_LOG="$ROOT/logs/schedule-$(date +%Y%m%d).log"

exec 200>"$LOCK_FILE"
if ! flock -n 200; then
  log "skip — job khác đang chạy (lock $LOCK_FILE)"
  exit 0
fi

log "start → $OUT_FILE (tz=$TZ_NAME account=$ACCOUNT)"

CMD=(
  "$PYTHON" "$MAIN" create --shorts
  --lang "$LANG"
  --youtube-account "$ACCOUNT"
  --youtube-privacy "$PRIVACY"
  --output "$OUT_FILE"
)

if [[ -n "$CHANNEL" ]]; then
  CMD+=(--youtube-channel "$CHANNEL")
fi

if [[ "$USE_MANUAL" == "true" && -n "$MANUAL_TOPIC" ]]; then
  CMD+=(--topic "${MANUAL_TOPIC//_/ }")
fi

SLOT_LABEL="${1:-manual}"
log "slot=$SLOT_LABEL"

{
  echo "======== $(date -Iseconds) slot=$SLOT_LABEL file=$OUT_FILE ========"
  "${CMD[@]}"
  echo "======== end exit=$? ========"
} >>"$DAY_LOG" 2>&1

EXIT=$?
if [[ $EXIT -eq 0 ]]; then
  log "done — xem $DAY_LOG"
else
  log "FAILED exit=$EXIT — xem $DAY_LOG"
fi
exit "$EXIT"
