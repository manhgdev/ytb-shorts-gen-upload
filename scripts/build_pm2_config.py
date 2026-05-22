#!/usr/bin/env python3
"""Sinh pm2.config.json — 1 app: ytb-shorts (auto đăng theo lịch)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "pm2.config.json"

apps = [
    {
        "name": "ytb-shorts",
        "script": "./scripts/pm2_main.sh",
        "interpreter": "bash",
        "cwd": ".",
        "watch": False,
        "autorestart": True,
        "log_date_format": "YYYY-MM-DD HH:mm:ss",
        "error_file": "logs/pm2-error.log",
        "out_file": "logs/pm2-out.log",
        "merge_logs": True,
        "env": {"PYTHONUNBUFFERED": "1"},
    }
]
OUT.write_text(json.dumps({"apps": apps}, indent=2) + "\n", encoding="utf-8")
print(f"Wrote {OUT.name} (1 app: ytb-shorts)")
