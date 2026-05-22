#!/usr/bin/env bash
# Một process PM2 duy nhất: lịch 3 video/ngày + upload kênh LylyTaks1199 (schedule.config.json).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec "$ROOT/venv/bin/python" "$ROOT/scripts/schedule_daemon.py"
