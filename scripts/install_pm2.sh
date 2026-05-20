#!/usr/bin/env bash
# PM2: 2 app — ytb-shorts-api + ytb-schedule (daemon 3 video/ngày).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v pm2 >/dev/null 2>&1; then
  echo "Cài PM2: npm install -g pm2"
  exit 1
fi

if [[ ! -f "$ROOT/schedule.config.json" ]]; then
  cp "$ROOT/schedule.config.example.json" "$ROOT/schedule.config.json"
fi

mkdir -p logs
chmod +x scripts/start_api.sh scripts/scheduled_create.sh scripts/schedule_daemon.py

if [[ ! -x "$ROOT/venv/bin/python" ]]; then
  python3 -m venv venv
  ./venv/bin/pip install -r requirements.txt
fi

./venv/bin/python scripts/build_pm2_config.py

# Gỡ app cũ (3 slot riêng hoặc tên cũ)
for name in ytb-shorts-api ytb-schedule ytb-schedule-1200 ytb-schedule-1700 ytb-schedule-2100; do
  pm2 delete "$name" 2>/dev/null || true
done

pm2 start pm2.config.json
pm2 save

echo ""
pm2 status
echo ""
echo "Chỉ 2 app: ytb-shorts-api (HTTP) + ytb-schedule (lịch 3 lần/ngày)"
echo "Log lịch: pm2 logs ytb-schedule"
echo "Thử 1 video: ./scripts/scheduled_create.sh test-run"
echo "Gỡ cron trùng: crontab -l | grep -v ytb-shorts | crontab - || true"
