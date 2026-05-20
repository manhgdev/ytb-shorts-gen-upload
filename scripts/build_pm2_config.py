#!/usr/bin/env python3
"""Sinh pm2.config.json từ schedule.config.json (API + 3 slot cron PM2)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEDULE = ROOT / "schedule.config.json"
EXAMPLE = ROOT / "schedule.config.example.json"
OUT = ROOT / "pm2.config.json"


def _load_schedule() -> dict:
    path = SCHEDULE if SCHEDULE.is_file() else EXAMPLE
    return json.loads(path.read_text(encoding="utf-8"))


def _cron(minute: int, hour: int) -> str:
    return f"{minute} {hour} * * *"


def main() -> None:
    cfg = _load_schedule()
    tz = cfg.get("timezone", "America/New_York")
    apps: list[dict] = [
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
        }
    ]

    if cfg.get("enabled", True):
        for i, slot in enumerate(cfg.get("slots") or [], start=1):
            h = int(slot["hour"])
            m = int(slot.get("minute", 0))
            label = str(slot.get("label", f"slot{i}"))
            safe = f"{h:02d}{m:02d}"
            apps.append(
                {
                    "name": f"ytb-schedule-{safe}",
                    "script": "./scripts/scheduled_create.sh",
                    "args": label,
                    "interpreter": "bash",
                    "cwd": ".",
                    "cron_restart": _cron(m, h),
                    "autorestart": False,
                    "watch": False,
                    "log_date_format": "YYYY-MM-DD HH:mm:ss",
                    "out_file": f"logs/pm2-schedule-{safe}.log",
                    "error_file": f"logs/pm2-schedule-{safe}-error.log",
                    "merge_logs": True,
                    "env": {"TZ": tz, "PYTHONUNBUFFERED": "1"},
                }
            )

    OUT.write_text(json.dumps({"apps": apps}, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(apps)} apps, tz={tz})")


if __name__ == "__main__":
    main()
