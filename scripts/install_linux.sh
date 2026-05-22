#!/usr/bin/env bash
# Cài trên Linux: venv + PM2 (1 app) — auto 3 Shorts/ngày → kênh LylyTaks1199.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ACCOUNT_ID="LylyTaks1199"
TOKEN_FILE="$ROOT/credentials/youtube_tokens/${ACCOUNT_ID}.json"

echo "=== ytb-shorts-gen-upload — cài Linux ==="

# --- hệ thống (Ubuntu/Debian) ---
if command -v apt-get >/dev/null 2>&1; then
  echo "[1/6] apt: python3, venv, ffmpeg..."
  sudo apt-get update -qq
  sudo apt-get install -y python3 python3-venv python3-pip ffmpeg curl
fi

# --- Node + PM2 ---
if ! command -v pm2 >/dev/null 2>&1; then
  echo "[2/6] cài PM2..."
  if ! command -v npm >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then
      sudo apt-get install -y nodejs npm || true
    fi
  fi
  if command -v npm >/dev/null 2>&1; then
    sudo npm install -g pm2
  else
    echo "Cần npm: sudo npm install -g pm2"
    exit 1
  fi
else
  echo "[2/6] PM2 đã có"
fi

# --- Python venv ---
echo "[3/6] venv + pip..."
if [[ ! -x "$ROOT/venv/bin/python" ]]; then
  python3 -m venv venv
fi
./venv/bin/pip install -q -r requirements.txt

# --- config ---
echo "[4/6] config..."
mkdir -p logs credentials/youtube_tokens assets/final
chmod +x scripts/pm2_main.sh scripts/scheduled_create.sh scripts/schedule_daemon.py

if [[ ! -f "$ROOT/user_settings.json" ]]; then
  cp "$ROOT/user_settings.example.json" "$ROOT/user_settings.json"
  echo "  → tạo user_settings.json — điền gemini_api_key, pexels_api_key"
fi

if [[ ! -f "$ROOT/schedule.config.json" ]]; then
  cp "$ROOT/schedule.config.example.json" "$ROOT/schedule.config.json"
fi

if [[ ! -f "$ROOT/credentials/youtube_client_secret.json" ]]; then
  echo "  ⚠ Thiếu credentials/youtube_client_secret.json (OAuth Google Cloud)"
fi

if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "  ⚠ Thiếu $TOKEN_FILE"
  echo "  Chạy OAuth (một lần, trên máy này):"
  echo "    ./venv/bin/python scripts/youtube_auth.py --account-id @${ACCOUNT_ID}"
  exit 1
fi

echo "  ✓ Token: $TOKEN_FILE"

# --- PM2: 1 app ---
echo "[5/6] PM2 (1 process: ytb-shorts)..."
./venv/bin/python scripts/build_pm2_config.py

for name in ytb-shorts ytb-shorts-api ytb-schedule ytb-schedule-1200 ytb-schedule-1700 ytb-schedule-2100; do
  pm2 delete "$name" 2>/dev/null || true
done

pm2 start pm2.config.json
pm2 save

echo "[6/6] xong"
echo ""
pm2 status
echo ""
echo "Kênh:     youtube_account_id = ${ACCOUNT_ID}"
echo "Lịch:     12:00 / 17:00 / 21:00 (America/New_York) — sửa schedule.config.json"
echo "Log:      pm2 logs ytb-shorts"
echo "Thử ngay: ./scripts/scheduled_create.sh test-run"
echo "Sau reboot: pm2 startup  (chạy lệnh sudo PM2 in ra)"
echo ""
echo "Gỡ cron cũ (nếu có): crontab -l | grep -v ytb-shorts | crontab - || true"
