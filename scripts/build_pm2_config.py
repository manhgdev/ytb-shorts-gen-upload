#!/usr/bin/env python3
"""Sinh pm2.config.json: API + 1 daemon lịch (không tách 3 app)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "pm2.config.json"


def main() -> None:
    apps = [
        {
            "name": "ytb-shorts-api",
            "script": "./scripts/start_api.sh",
            "interpreter": "bash",
            "cwd": ".",
            "watch": False,
            "autorestart": True,
            "log_date_format": "YYYY-MM-DD HH:mm:ss",
            "error_file": "logs/pm2-api-error.log",
            "out_file": "logs/pm2-api-out.log",
            "merge_logs": True,
            "env": {"PYTHONUNBUFFERED": "1"},
        },
        {
            "name": "ytb-schedule",
            "script": "./scripts/schedule_daemon.py",
            "interpreter": "./venv/bin/python",
            "cwd": ".",
            "watch": False,
            "autorestart": True,
            "log_date_format": "YYYY-MM-DD HH:mm:ss",
            "error_file": "logs/pm2-schedule-error.log",
            "out_file": "logs/pm2-schedule.log",
            "merge_logs": True,
            "env": {"PYTHONUNBUFFERED": "1"},
        },
    ]
    OUT.write_text(json.dumps({"apps": apps}, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)} (2 apps: api + schedule)")


if __name__ == "__main__":
    main()
