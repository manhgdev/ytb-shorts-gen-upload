from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.settings import ROOT, merge_settings
from app.utils import media_duration_seconds, media_video_size, resolve_path

VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv"}
CATALOG_FILE = ROOT / "assets" / "final" / ".videos_catalog.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _meta_sidecar_path(video_path: Path | str) -> Path:
    p = Path(video_path)
    return p.with_name(f"{p.stem}.meta.json")


def output_dir(settings: dict[str, Any] | None = None) -> Path:
    s = merge_settings(settings)
    raw = (s.get("output_dir") or "assets/final").strip()
    return Path(resolve_path(raw) if raw else str(ROOT / "assets" / "final"))


def _load_catalog_raw() -> dict[str, Any]:
    if not CATALOG_FILE.is_file():
        return {"version": 1, "updated_at": _now_iso(), "videos": []}
    try:
        data = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "updated_at": _now_iso(), "videos": []}
    if not isinstance(data, dict):
        return {"version": 1, "updated_at": _now_iso(), "videos": []}
    data.setdefault("videos", [])
    return data


def _save_catalog_raw(data: dict[str, Any]) -> None:
    CATALOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _now_iso()
    CATALOG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_sidecar(video_path: str | Path, meta: dict[str, Any]) -> Path:
    sidecar = _meta_sidecar_path(video_path)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(meta)
    payload["updated_at"] = _now_iso()
    sidecar.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return sidecar


def load_sidecar(video_path: str | Path) -> dict[str, Any] | None:
    sidecar = _meta_sidecar_path(video_path)
    if not sidecar.is_file():
        return None
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _rel_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def _video_stats(path: Path) -> dict[str, Any]:
    s = str(path)
    dur = media_duration_seconds(s)
    w, h = media_video_size(s)
    st = path.stat()
    return {
        "duration_sec": round(dur, 1) if dur else 0,
        "width": w,
        "height": h,
        "size_bytes": st.st_size,
        "modified_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
    }


def build_metadata(
    *,
    topic: str,
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    hashtags: list[str] | None = None,
    title_variants: list[str] | None = None,
    language: str = "en",
    model_used: str = "",
    script: list | None = None,
    thumbnail_path: str = "",
    shorts_hook_intro_applied_sec: float = 0.0,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "topic": topic.strip(),
        "title": title.strip(),
        "title_variants": list(title_variants or []),
        "description": (description or "").strip(),
        "tags": list(tags or []),
        "hashtags": list(hashtags or []),
        "language": language,
        "model_used": model_used,
        "script": script,
        "thumbnail_path": thumbnail_path,
        "created_at": _now_iso(),
    }
    try:
        sec = float(shorts_hook_intro_applied_sec or 0)
    except (TypeError, ValueError):
        sec = 0.0
    if sec > 0.05:
        out["shorts_hook_intro_applied_sec"] = round(sec, 3)
    return out


def register_video(
    video_path: str | Path,
    meta: dict[str, Any],
    *,
    video_id: str | None = None,
) -> dict[str, Any]:
    path = Path(video_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy video: {path}")

    stats = _video_stats(path)
    entry = {
        "id": video_id or str(uuid.uuid4())[:8],
        "filename": path.name,
        "relative_path": _rel_path(path),
        "absolute_path": str(path),
        **stats,
        **meta,
        "youtube": meta.get("youtube") or {
            "status": "pending",
            "video_id": "",
            "url": "",
            "title": "",
            "privacy": "",
            "account_id": "",
            "uploaded_at": "",
        },
    }
    if "youtube" in meta:
        entry["youtube"] = meta["youtube"]

    sidecar_payload = {k: v for k, v in entry.items() if k not in ("absolute_path",)}
    save_sidecar(path, sidecar_payload)

    cat = _load_catalog_raw()
    videos: list[dict] = cat["videos"]
    rel = entry["relative_path"]
    replaced = False
    for i, v in enumerate(videos):
        if v.get("relative_path") == rel or v.get("filename") == path.name:
            entry["id"] = v.get("id") or entry["id"]
            old_yt = v.get("youtube") or {}
            new_created = meta.get("created_at") or entry.get("created_at") or ""
            old_uploaded = old_yt.get("uploaded_at") or ""
            # Chỉ giữ upload cũ nếu không phải bản render mới (cùng tên file, metadata mới)
            if (
                old_yt.get("status") == "uploaded"
                and old_uploaded
                and new_created
                and new_created <= old_uploaded
            ):
                entry["youtube"] = old_yt
            videos[i] = entry
            replaced = True
            break
    if not replaced:
        videos.append(entry)
    cat["videos"] = sorted(videos, key=lambda x: x.get("created_at", ""), reverse=True)
    _save_catalog_raw(cat)
    return entry


def mark_uploaded(
    video_path: str | Path,
    *,
    youtube_video_id: str,
    youtube_url: str,
    youtube_title: str,
    youtube_privacy: str,
    youtube_account_id: str = "",
    youtube_description: str = "",
    youtube_tags: list[str] | None = None,
) -> dict[str, Any]:
    path = Path(video_path).resolve()
    sidecar = load_sidecar(path) or {}
    sidecar["youtube"] = {
        "status": "uploaded",
        "video_id": youtube_video_id,
        "url": youtube_url,
        "title": youtube_title,
        "privacy": youtube_privacy,
        "account_id": youtube_account_id,
        "uploaded_at": _now_iso(),
    }
    if youtube_description:
        sidecar["description"] = youtube_description
    if youtube_tags:
        sidecar["tags"] = youtube_tags
    save_sidecar(path, sidecar)
    return register_video(path, sidecar)


def _merge_sidecar(entry: dict[str, Any]) -> dict[str, Any]:
    """Sidecar .meta.json là nguồn đúng khi lệch catalog."""
    rel = entry.get("relative_path") or ""
    path = Path(entry.get("absolute_path") or (resolve_path(rel) if rel else ""))
    if not path.is_file():
        return entry
    sidecar = load_sidecar(path)
    if not sidecar:
        return entry
    merged = {**entry, **sidecar}
    merged["absolute_path"] = entry.get("absolute_path") or str(path.resolve())
    merged["relative_path"] = entry.get("relative_path") or _rel_path(path)
    merged["filename"] = entry.get("filename") or path.name
    return merged


def get_video(ref: str) -> dict[str, Any] | None:
    """Tìm theo id, filename, hoặc relative_path."""
    ref = (ref or "").strip()
    if not ref:
        return None
    sync_catalog()
    cat = _load_catalog_raw()
    for v in cat.get("videos") or []:
        if v.get("id") == ref or v.get("filename") == ref or v.get("relative_path") == ref:
            return _merge_sidecar(v)
        if ref in (v.get("absolute_path") or ""):
            return _merge_sidecar(v)
    # thử sidecar trực tiếp
    p = Path(ref)
    if not p.is_absolute():
        p = ROOT / ref
    if p.is_file() and p.suffix.lower() in VIDEO_EXT:
        meta = load_sidecar(p)
        if meta:
            return _merge_sidecar(register_video(p, meta))
    return None


def repair_catalog_from_sidecars(settings: dict[str, Any] | None = None) -> int:
    """Đồng bộ catalog từ .meta.json (sửa lệch upload cũ). Trả về số entry đã sửa."""
    sync_catalog(settings)
    fixed = 0
    cat = _load_catalog_raw()
    for i, v in enumerate(cat.get("videos") or []):
        merged = _merge_sidecar(v)
        if merged != v:
            cat["videos"][i] = merged
            fixed += 1
    if fixed:
        _save_catalog_raw(cat)
    return fixed


def sync_catalog(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Quét thư mục output, đăng ký file chưa có trong catalog."""
    folder = output_dir(settings)
    cat = _load_catalog_raw()
    known = {v.get("relative_path") for v in cat.get("videos") or []}
    known |= {v.get("filename") for v in cat.get("videos") or []}

    if folder.is_dir():
        for entry in sorted(folder.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not entry.is_file() or entry.suffix.lower() not in VIDEO_EXT:
                continue
            rel = _rel_path(entry)
            if rel in known or entry.name in known:
                continue
            meta = load_sidecar(entry)
            if meta:
                register_video(entry, meta)
            else:
                register_video(
                    entry,
                    build_metadata(
                        topic=entry.stem,
                        title=entry.stem.replace("_", " "),
                        language="",
                    ),
                )
            known.add(rel)
            known.add(entry.name)

    return _load_catalog_raw()


def list_catalog(
    *,
    status: Literal["all", "pending", "uploaded"] = "all",
    settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    sync_catalog(settings)
    videos = _load_catalog_raw().get("videos") or []
    if status == "pending":
        return [v for v in videos if (v.get("youtube") or {}).get("status") != "uploaded"]
    if status == "uploaded":
        return [v for v in videos if (v.get("youtube") or {}).get("status") == "uploaded"]
    return videos


def update_metadata(ref: str, patch: dict[str, Any]) -> dict[str, Any]:
    entry = get_video(ref)
    if not entry:
        raise KeyError(f"Không tìm thấy video: {ref}")
    path = Path(entry.get("absolute_path") or resolve_path(entry.get("relative_path", "")))
    sidecar = load_sidecar(path) or dict(entry)
    for key in (
        "topic",
        "title",
        "description",
        "tags",
        "hashtags",
        "title_variants",
        "thumbnail_path",
        "shorts_hook_intro_applied_sec",
    ):
        if key in patch and patch[key] is not None:
            sidecar[key] = patch[key]
    return register_video(path, sidecar)


def delete_video_entry(ref: str, *, remove_file: bool = True) -> dict[str, Any]:
    entry = get_video(ref)
    if not entry:
        raise KeyError(f"Không tìm thấy video: {ref}")
    path = Path(entry.get("absolute_path") or resolve_path(entry.get("relative_path", "")))
    sidecar = _meta_sidecar_path(path)

    if remove_file and path.is_file():
        path.unlink()
    if sidecar.is_file():
        sidecar.unlink()

    cat = _load_catalog_raw()
    rel = entry.get("relative_path")
    cat["videos"] = [v for v in cat.get("videos") or [] if v.get("relative_path") != rel]
    _save_catalog_raw(cat)
    return {"deleted": True, "id": entry.get("id"), "filename": entry.get("filename")}


def metadata_for_upload(entry: dict[str, Any]) -> dict[str, Any]:
    """Chuẩn hóa title/description/tags để gọi upload_video."""
    from app.youtube_seo import sanitize_youtube_tags

    title = (entry.get("title") or entry.get("topic") or "YouTube Short").strip()
    desc = (entry.get("description") or "").strip()
    tags = sanitize_youtube_tags(entry.get("tags") or [])
    if not desc and entry.get("topic"):
        desc = f"{entry['topic']}\n\n#Shorts"
    return {
        "topic": entry.get("topic") or title,
        "title": title,
        "description": desc,
        "tags": tags,
    }
