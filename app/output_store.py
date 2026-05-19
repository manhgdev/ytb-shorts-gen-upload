from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from app.settings import ROOT, merge_settings
from app.utils import resolve_path

VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv"}


def output_dir_from_settings(output_dir: str | None = None) -> Path:
    if output_dir and str(output_dir).strip():
        resolved = resolve_path(str(output_dir).strip())
        if not resolved:
            raise HTTPException(400, "output_dir không hợp lệ")
        return Path(resolved)
    settings = merge_settings(None)
    raw = (settings.get("output_dir") or "assets/final").strip()
    return Path(resolve_path(raw) if raw else str(ROOT / "assets" / "final"))


def _ensure_under_root(path: Path) -> Path:
    root = ROOT.resolve()
    try:
        path.resolve().relative_to(root)
    except ValueError:
        raise HTTPException(403, "Không được truy cập ngoài thư mục project")
    return path


def list_videos(output_dir: str | None = None) -> dict:
    folder = _ensure_under_root(output_dir_from_settings(output_dir))
    if not folder.is_dir():
        rel = str(folder.relative_to(ROOT)) if folder.is_relative_to(ROOT) else str(folder)
        return {"output_dir": rel, "absolute_dir": str(folder), "count": 0, "videos": []}

    items = []
    for entry in sorted(folder.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not entry.is_file() or entry.suffix.lower() not in VIDEO_EXT:
            continue
        st = entry.stat()
        rel = str(entry.relative_to(ROOT)) if entry.is_relative_to(ROOT) else entry.name
        items.append(
            {
                "name": entry.name,
                "path": str(entry.resolve()),
                "relative_path": rel,
                "size_bytes": st.st_size,
                "modified_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            }
        )

    rel_dir = str(folder.relative_to(ROOT)) if folder.is_relative_to(ROOT) else str(folder)
    return {
        "output_dir": rel_dir,
        "absolute_dir": str(folder.resolve()),
        "count": len(items),
        "videos": items,
    }


def delete_video(name: str, output_dir: str | None = None) -> dict:
    if not name or name != Path(name).name or ".." in name:
        raise HTTPException(400, "Tên file không hợp lệ")

    folder = _ensure_under_root(output_dir_from_settings(output_dir))
    target = folder / name
    _ensure_under_root(target)

    if not target.is_file():
        raise HTTPException(404, f"Không tìm thấy: {name}")
    if target.suffix.lower() not in VIDEO_EXT:
        raise HTTPException(400, "Chỉ xóa file video (.mp4, .mov, .webm, .mkv)")

    try:
        os.remove(target)
    except OSError as e:
        raise HTTPException(500, f"Không xóa được: {e}") from e

    rel = str(target.relative_to(ROOT)) if target.is_relative_to(ROOT) else name
    return {"deleted": True, "name": name, "relative_path": rel}
