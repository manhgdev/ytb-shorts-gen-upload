"""Seed + parse cảnh avatar cho pipeline render."""

from __future__ import annotations

import random
import secrets
from typing import Any


def make_render_rng(merged: dict[str, Any], overrides: dict[str, Any] | None) -> tuple[random.Random, int]:
    """
    Trả về (Random, seed_int).

    - overrides có key `render_seed` (vd CLI --seed) → dùng trước.
    - None / rỗng / "random" → seed ngẫu nhiên mỗi lần chạy.
    """
    o = overrides or {}
    if "render_seed" in o:
        raw = o["render_seed"]
    else:
        raw = merged.get("render_seed")
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        seed_int = secrets.randbits(31)
    else:
        s = str(raw).strip().lower()
        if s in ("random", "reshuffle", "new"):
            seed_int = secrets.randbits(31)
        else:
            seed_int = int(raw)
    return random.Random(seed_int), seed_int


def parse_avatar_scene_numbers(raw: Any) -> list[int]:
    """Danh sách số cảnh 1-based từ list hoặc chuỗi \"3, 7\"."""
    if raw is None:
        return []
    if isinstance(raw, list):
        out = []
        for x in raw:
            try:
                n = int(x)
                if n > 0:
                    out.append(n)
            except (TypeError, ValueError):
                continue
        return out
    s = str(raw).strip()
    if not s:
        return []
    return [int(p.strip()) for p in s.split(",") if p.strip().isdigit()]
