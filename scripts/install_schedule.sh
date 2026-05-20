#!/usr/bin/env bash
# Cài cron: 3 video/ngày theo giờ Mỹ (America/New_York). Chạy từ thư mục repo.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="$ROOT/schedule.config.json"
EXAMPLE="$ROOT/schedule.config.example.json"
CREATE_SH="$ROOT/scripts/scheduled_create.sh"
MARKER="# ytb-shorts-gen-upload schedule"

if [[ ! -f "$CONFIG" ]]; then
  cp "$EXAMPLE" "$CONFIG"
  echo "Đã tạo $CONFIG — sửa youtube_account_id / slots nếu cần."
fi

chmod +x "$CREATE_SH" "$ROOT/scripts/start_api.sh" 2>/dev/null || true

read -r TZ_NAME <<< "$("$ROOT/venv/bin/python" -c "
import json
from pathlib import Path
c=json.loads(Path('$CONFIG').read_text())
print(c.get('timezone','America/New_York'))
" 2>/dev/null || echo "America/New_York")"

# Build cron lines from slots
CRON_LINES="$("$ROOT/venv/bin/python" - <<PY "$CONFIG" "$CREATE_SH" "$MARKER"
import json, sys
from pathlib import Path
config_path, script, marker = sys.argv[1], sys.argv[2], sys.argv[3]
c = json.loads(Path(config_path).read_text(encoding="utf-8"))
tz = c.get("timezone", "America/New_York")
for slot in c.get("slots") or []:
    h, m = int(slot["hour"]), int(slot.get("minute", 0))
    label = slot.get("label", f"{h}:{m:02d}").replace('"', "'")
    print(f'{m} {h} * * * TZ={tz} {script} "{label}" >> {Path(script).parent.parent}/logs/cron-schedule.log 2>&1')
print(f'# timezone={tz} | 3 slots US peak | {marker}')
PY
)"

echo ""
echo "=== Cron sẽ thêm (3 lần/ngày, giờ $TZ_NAME) ==="
echo "$CRON_LINES"
echo ""

# Remove old marker lines, append new
TMP="$(mktemp)"
( crontab -l 2>/dev/null | grep -v "$MARKER" | grep -v "scripts/scheduled_create.sh" || true ) >"$TMP"
echo "$CRON_LINES" >>"$TMP"
crontab "$TMP"
rm -f "$TMP"

echo "Đã cài crontab. Kiểm tra:"
echo "  crontab -l | grep ytb-shorts"
echo ""
echo "Log:"
echo "  tail -f $ROOT/logs/schedule-\$(date +%Y%m%d).log"
echo "  tail -f $ROOT/logs/cron-schedule.log"
echo ""
echo "Chạy thử ngay (1 video):"
echo "  $CREATE_SH test-run"
