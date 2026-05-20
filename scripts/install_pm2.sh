#!/usr/bin/env bash
# PM2: API + lịch 3 video/ngày (cron_restart). Chạy từ thư mục repo.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v pm2 >/dev/null 2>&1; then
  echo "Cài PM2: npm install -g pm2   hoặc: sudo npm install -g pm2"
  exit 1
fi

if [[ ! -f "$ROOT/schedule.config.json" ]]; then
  cp "$ROOT/schedule.config.example.json" "$ROOT/schedule.config.json"
  echo "Đã tạo schedule.config.json — sửa account_id / slots nếu cần."
fi

mkdir -p logs
chmod +x scripts/start_api.sh scripts/scheduled_create.sh

# venv
if [[ ! -x "$ROOT/venv/bin/python" ]]; then
  echo "Tạo venv..."
  python3 -m venv venv
  ./venv/bin/pip install -r requirements.txt
fi

./venv/bin/python scripts/build_pm2_config.py

# Gỡ app cũ cùng prefix (tránh trùng tên)
pm2 delete ytb-shorts-api 2>/dev/null || true
pm2 jlist 2>/dev/null | ./venv/bin/python -c "
import json, sys, subprocess
try:
    apps = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for a in apps:
    n = a.get('name', '')
    if n.startswith('ytb-schedule-'):
        subprocess.run(['pm2', 'delete', n], check=False)
" 2>/dev/null || true

pm2 start pm2.config.json
pm2 save

echo ""
echo "=== PM2 đã cài ==="
pm2 status
echo ""
echo "API:      pm2 logs ytb-shorts-api"
echo "Lịch:     pm2 logs ytb-schedule-1200  (và 1700, 2100)"
echo "Thử 1 video ngay: ./scripts/scheduled_create.sh test-run"
echo "Sau reboot: pm2 startup  (chạy lệnh sudo in ra, rồi pm2 save)"
echo ""
echo "Gỡ cron hệ thống (nếu cài trước): crontab -l | grep -v ytb-shorts | crontab - || true"
