from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.settings import AVATAR_IMAGE, AVATAR_VIDEO, ROOT

VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MAX_VIDEO_BYTES = 80 * 1024 * 1024
MAX_IMAGE_BYTES = 15 * 1024 * 1024

UPLOAD_ROOT = ROOT / "assets" / "uploads" / "avatars"


def _safe_user_id(raw: str) -> str:
    s = re.sub(r"[^\w\-]", "_", (raw or "").strip())[:64]
    return s or "anon"


def _kind_from_name(name: str) -> str | None:
    ext = Path(name or "").suffix.lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in IMAGE_EXT:
        return "image"
    return None


def default_avatar_info() -> dict:
    video = ROOT / AVATAR_VIDEO
    image = ROOT / AVATAR_IMAGE
    return {
        "avatar_mode": "default",
        "avatar_video_path": AVATAR_VIDEO,
        "avatar_image_path": AVATAR_IMAGE,
        "video_exists": video.is_file(),
        "image_exists": image.is_file(),
    }


async def save_avatar_upload(
    file: UploadFile,
    *,
    user_id: str = "",
    kind: str = "",
) -> dict:
    if not file.filename:
        raise HTTPException(400, "Thiếu tên file")

    detected = _kind_from_name(file.filename)
    k = (kind or "").strip().lower() or detected
    if k not in ("video", "image"):
        raise HTTPException(
            400,
            f"Định dạng không hỗ trợ. Video: {', '.join(sorted(VIDEO_EXT))}; "
            f"ảnh: {', '.join(sorted(IMAGE_EXT))}",
        )

    ext = Path(file.filename).suffix.lower()
    allowed = VIDEO_EXT if k == "video" else IMAGE_EXT
    if ext not in allowed:
        raise HTTPException(400, f"Extension {ext} không khớp loại {k}")

    limit = MAX_VIDEO_BYTES if k == "video" else MAX_IMAGE_BYTES
    data = await file.read()
    if len(data) > limit:
        raise HTTPException(400, f"File quá lớn (tối đa {limit // (1024 * 1024)}MB)")

    folder = UPLOAD_ROOT / _safe_user_id(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    dest_name = "avatar_video" + ext if k == "video" else "avatar_image" + ext
    dest = folder / dest_name
    dest.write_bytes(data)

    rel = str(dest.relative_to(ROOT))
    video_path = rel if k == "video" else ""
    image_path = rel if k == "image" else ""

    return {
        "avatar_mode": "custom",
        "kind": k,
        "path": rel,
        "absolute_path": str(dest.resolve()),
        "avatar_video_path": video_path,
        "avatar_image_path": image_path,
        "user_id": _safe_user_id(user_id),
    }
