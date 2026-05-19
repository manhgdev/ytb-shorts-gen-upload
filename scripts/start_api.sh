#!/usr/bin/env bash
# Chạy API (dùng cho PM2 hoặc tay). Đặt trong repo root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec "$ROOT/venv/bin/python" -m uvicorn api_server:app --host 0.0.0.0 --port 8000
