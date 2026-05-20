#!/usr/bin/env python3
"""Một process PM2: đợi đến giờ trong schedule.config.json rồi gọi scheduled_create.sh."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "schedule.config.json"
EXAMPLE = ROOT / "schedule.config.example.json"
STATE = ROOT / "logs/schedule_state.json"
CREATE_SH = ROOT / "scripts/scheduled_create.sh"
POLL_SEC = 60


def _load_config() -> dict:
    path = CONFIG if CONFIG.is_file() else EXAMPLE
    return json.loads(path.read_text(encoding="utf-8"))


def _load_state() -> dict:
    if not STATE.is_file():
        return {}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _slot_key(hour: int, minute: int) -> str:
    return f"{hour:02d}:{minute:02d}"


def _due_now(tz: ZoneInfo, hour: int, minute: int) -> bool:
    now = datetime.now(tz)
    return now.hour == hour and now.minute == minute


def main() -> int:
    cfg = _load_config()
    if not cfg.get("enabled", True):
        print("[schedule] disabled — thoát")
        return 0

    tz_name = cfg.get("timezone", "America/New_York")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        print(f"[schedule] timezone không hợp lệ: {tz_name}", file=sys.stderr)
        return 1

    slots = cfg.get("slots") or []
    if not slots:
        print("[schedule] không có slots", file=sys.stderr)
        return 1

    if not CREATE_SH.is_file():
        print(f"[schedule] thiếu {CREATE_SH}", file=sys.stderr)
        return 1

    print(f"[schedule] daemon bật — tz={tz_name} | {len(slots)} slot/ngày | poll {POLL_SEC}s")
    for s in slots:
        print(f"  - {s.get('label', '')} @ {_slot_key(int(s['hour']), int(s.get('minute', 0)))}")

    while True:
        cfg = _load_config()
        if not cfg.get("enabled", True):
            time.sleep(POLL_SEC)
            continue

        state = _load_state()
        today = datetime.now(tz).strftime("%Y-%m-%d")

        for slot in cfg.get("slots") or []:
            hour = int(slot["hour"])
            minute = int(slot.get("minute", 0))
            key = _slot_key(hour, minute)
            label = str(slot.get("label", key))
            run_id = f"{today}:{key}"

            if state.get(key) == run_id:
                continue
            if not _due_now(tz, hour, minute):
                continue

            print(f"[schedule] chạy slot {label} ({run_id})")
            rc = subprocess.call(["bash", str(CREATE_SH), label], cwd=ROOT)
            if rc == 0:
                state[key] = run_id
                _save_state(state)
                print(f"[schedule] xong slot {label}")
            else:
                print(f"[schedule] lỗi slot {label} exit={rc}", file=sys.stderr)

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n[schedule] dừng")
        raise SystemExit(0) from None
