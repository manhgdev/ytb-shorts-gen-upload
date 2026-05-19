#!/usr/bin/env python3
"""
CLI quản lý Shorts: tạo video → metadata → upload YouTube.

  python main.py create --topic "..." [--lang en] [--shorts]
  python main.py list [--pending|--uploaded]
  python main.py show <id|filename>
  python main.py upload <id|filename> --youtube-account ...
  python main.py edit <id> --title "..."
  python main.py delete <id|filename>
  python main.py create --reshuffle --topic "..."   # chọn lại phân cảnh / clip
  python main.py check-youtube --youtube-account ...
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

from app.pipeline import run
from app.brain import ContentBrain
from app.settings import (
    gemini_keys,
    load_settings,
    locale,
    merge_settings,
    model_chain,
    topic_prompt,
    video_cfg,
)
from app.video_catalog import (
    delete_video_entry,
    get_video,
    list_catalog,
    mark_uploaded,
    metadata_for_upload,
    register_video,
    sync_catalog,
    update_metadata,
)
from app.shorts_intro import maybe_prepend_thumbnail_intro
from app.thumbnail import generate_thumbnail, upload_thumbnail
from app.youtube import account_status, apply_recording_location, upload_video
from app.youtube_seo import prepare_video_metadata
from app.utils import media_duration_seconds, resolve_path


def _brain_for_thumbnail(settings: dict[str, Any]) -> ContentBrain | None:
    if not settings.get("youtube_thumbnail_ai_text", True):
        return None
    gkeys = gemini_keys(settings)
    if not gkeys:
        return None
    loc = locale(settings)
    return ContentBrain(
        api_keys=gkeys,
        model_chain=model_chain(settings),
        topic_prompt=topic_prompt(settings),
        video_cfg=video_cfg(settings),
        script_extra_instructions=str(settings.get("script_extra_instructions") or ""),
        language=loc["code"],
        retry_delay_seconds=int(settings.get("gemini_retry_delay_seconds") or 60),
        max_retries=int(settings.get("gemini_max_retries") or 4),
    )


def _settings_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "settings", None):
        path = Path(args.settings).resolve()
        if not path.is_file():
            raise SystemExit(f"ERROR: không tìm thấy {path}")
        overrides = load_settings(path)
    else:
        overrides = load_settings()

    if getattr(args, "lang", None):
        overrides["language"] = args.lang
    if getattr(args, "topic", None):
        overrides["use_manual_topic"] = True
        overrides["manual_topic"] = args.topic
    if getattr(args, "video_mode", None):
        overrides["video_mode"] = args.video_mode
    if getattr(args, "output", None):
        overrides["output_filename"] = args.output
    if getattr(args, "avatar_mode", None):
        overrides["avatar_mode"] = args.avatar_mode
    if getattr(args, "youtube_account", None):
        overrides["youtube_account_id"] = args.youtube_account
    if getattr(args, "youtube_channel", None):
        overrides["youtube_channel_id"] = args.youtube_channel
    if getattr(args, "youtube_privacy", None):
        overrides["youtube_privacy"] = args.youtube_privacy
    if getattr(args, "no_youtube_seo", False):
        overrides["youtube_auto_seo"] = False
    return overrides


def _apply_youtube_flags(args: argparse.Namespace, overrides: dict[str, Any]) -> None:
    if getattr(args, "shorts", False) or getattr(args, "youtube", False):
        overrides["youtube_upload"] = True
    if getattr(args, "no_youtube", False):
        overrides["youtube_upload"] = False


def _print_youtube_status(st: dict[str, Any]) -> None:
    print(f"account_id:     {st['account_id']}")
    print(f"client_secret:  {'OK' if st['client_secrets_exists'] else 'THIẾU'}")
    print(f"token:          {'OK' if st['token_exists'] else 'THIẾU'} ({st['token_path']})")
    print(f"authenticated:  {st['authenticated']}")
    if st.get("message"):
        print(f"message:        {st['message']}")
    for ch in st.get("channels") or []:
        print(f"  channel: {ch['title']}  id={ch['channel_id']}")


def _ensure_youtube_ready(settings: dict[str, Any]) -> None:
    aid = (settings.get("youtube_account_id") or "").strip() or "default"
    settings["youtube_account_id"] = aid
    st = account_status(merge_settings(settings), account_id=aid)
    _print_youtube_status(st)
    if not st["client_secrets_exists"]:
        raise SystemExit("\nThiếu credentials/youtube_client_secret.json")
    if not st["token_exists"]:
        raise SystemExit(f"\nChạy: python3 scripts/youtube_auth.py --account-id {aid}")
    if not st["authenticated"]:
        raise SystemExit(f"\nYouTube chưa sẵn sàng: {st.get('message')}")


def _print_video_row(v: dict[str, Any]) -> None:
    yt = v.get("youtube") or {}
    status = yt.get("status") or "pending"
    mark = "✓" if status == "uploaded" else "○"
    print(
        f"{mark} [{v.get('id', '?')}] {v.get('filename', '?')}  "
        f"| {v.get('title', v.get('topic', ''))[:50]}  "
        f"| {status}"
    )
    if yt.get("url"):
        print(f"     {yt['url']}")


def _print_video_detail(v: dict[str, Any]) -> None:
    yt = v.get("youtube") or {}
    print(f"id:           {v.get('id')}")
    print(f"file:         {v.get('relative_path')}")
    print(f"topic:        {v.get('topic')}")
    print(f"title:        {v.get('title')}")
    print(f"description:  {(v.get('description') or '')[:120]}...")
    print(f"tags:         {', '.join(v.get('tags') or [])[:80]}")
    print(f"duration:     {v.get('duration_sec')}s  {v.get('width')}x{v.get('height')}")
    print(f"language:     {v.get('language')}")
    print(f"model:        {v.get('model_used')}")
    print(f"youtube:      {yt.get('status', 'pending')}")
    if yt.get("url"):
        print(f"url:          {yt['url']}")
    if yt.get("uploaded_at"):
        print(f"uploaded_at:  {yt['uploaded_at']}")
    if v.get("thumbnail_path"):
        print(f"thumbnail:    {v['thumbnail_path']}")
    variants = v.get("title_variants") or []
    if len(variants) > 1:
        print("title_variants:")
        for i, t in enumerate(variants, 1):
            print(f"  {i}. {t}")


def _print_create_summary(result: dict[str, Any], *, wanted_youtube: bool) -> None:
    print("\n" + "=" * 55)
    print(f"Video ID:    {result.get('video_id', '')}")
    print(f"File:        {result.get('path')}")
    print(f"Topic:       {result.get('topic')}")
    print(f"Title:       {result.get('title')}")
    print(f"Meta file:   {result.get('meta_path')}")
    if result.get("youtube_url"):
        print(f"YouTube:     {result['youtube_url']}")
        print(f"Privacy:     {result.get('youtube_privacy')}")
        print("=" * 55)
        print("Trạng thái:  ĐÃ UPLOAD")
    else:
        print("=" * 55)
        if wanted_youtube:
            print("Trạng thái:  CHƯA UPLOAD (lỗi hoặc thiếu --shorts)")
        else:
            print("Trạng thái:  CHƯA UPLOAD — chạy: python main.py upload <id>")


def _apply_render_shuffle_flags(args: argparse.Namespace, overrides: dict[str, Any]) -> None:
    """--reshuffle / --seed: chọn lại clip + phân cảnh avatar + hiệu nối."""
    import secrets

    if getattr(args, "reshuffle", False):
        overrides["stock_force_refresh"] = True
    if getattr(args, "seed", None) is not None:
        overrides["render_seed"] = int(args.seed)
    elif getattr(args, "reshuffle", False):
        overrides["render_seed"] = secrets.randbits(31)


async def cmd_create(args: argparse.Namespace) -> int:
    overrides = _settings_from_args(args)
    _apply_render_shuffle_flags(args, overrides)
    _apply_youtube_flags(args, overrides)
    wanted = bool(getattr(args, "shorts", False) or getattr(args, "youtube", False))
    if wanted:
        print("[youtube] kiểm tra OAuth...")
        _ensure_youtube_ready(overrides)
    print("[create] topic → script → metadata → render" + (" → upload" if wanted else ""))
    result = await run(overrides)
    _print_create_summary(result, wanted_youtube=wanted)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    if wanted and not result.get("youtube_url"):
        return 1
    return 0 if result.get("path") else 1


def cmd_list(args: argparse.Namespace) -> int:
    status = "all"
    if args.pending:
        status = "pending"
    elif args.uploaded:
        status = "uploaded"
    videos = list_catalog(status=status)  # type: ignore[arg-type]
    pending_n = len(list_catalog(status="pending"))
    uploaded_n = len(list_catalog(status="uploaded"))
    print(f"Videos: {len(videos)} hiển thị | {pending_n} chưa upload | {uploaded_n} đã upload\n")
    for v in videos:
        _print_video_row(v)
    if args.json:
        print(json.dumps(videos, ensure_ascii=False, indent=2))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    v = get_video(args.ref)
    if not v:
        print(f"Không tìm thấy: {args.ref}", file=sys.stderr)
        return 1
    _print_video_detail(v)
    if args.json:
        print(json.dumps(v, ensure_ascii=False, indent=2))
    return 0


def cmd_upload(args: argparse.Namespace) -> int:
    overrides = _settings_from_args(args)
    v = get_video(args.ref)
    if not v:
        print(f"Không tìm thấy: {args.ref}", file=sys.stderr)
        return 1
    if (v.get("youtube") or {}).get("status") == "uploaded" and not args.force:
        print(f"Đã upload: {(v.get('youtube') or {}).get('url')}")
        print("Dùng --force để upload lại")
        return 0

    path = v.get("absolute_path") or v.get("relative_path")
    if not path or not Path(path).is_file():
        path = str(Path(v.get("relative_path", "")))
    print("[upload] kiểm tra OAuth...")
    _ensure_youtube_ready(overrides)

    meta = metadata_for_upload(v)
    print(f"[upload] {path}")
    print(f"[title]  {meta['title']}")

    thumb = (v.get("thumbnail_path") or "").strip()
    if not thumb or not Path(resolve_path(thumb) if thumb else "").is_file():
        s = merge_settings(overrides)
        thumb = (
            generate_thumbnail(
                path,
                s,
                topic=meta.get("topic") or "",
                title=meta.get("title") or "",
                brain=_brain_for_thumbnail(s),
            )
            or ""
        )
        if thumb:
            update_metadata(args.ref, {"thumbnail_path": thumb})

    settings = merge_settings(
        {
            **overrides,
            "youtube_title": meta["title"],
            "youtube_description": meta["description"],
            "youtube_tags": meta["tags"],
            "youtube_auto_seo": False,
            "youtube_upload": True,
            "youtube_thumbnail_path": thumb,
        }
    )
    out = upload_video(
        path,
        settings,
        topic=meta["topic"],
        title=meta["title"],
        description=meta["description"],
        tags=meta["tags"],
        thumbnail_path=thumb or None,
    )
    mark_uploaded(
        path,
        youtube_video_id=out["youtube_video_id"],
        youtube_url=out["youtube_url"],
        youtube_title=out.get("youtube_title") or meta["title"],
        youtube_privacy=out.get("youtube_privacy") or settings.get("youtube_privacy", "private"),
        youtube_account_id=out.get("youtube_account_id") or settings.get("youtube_account_id") or "",
        youtube_description=out.get("youtube_description") or meta["description"],
        youtube_tags=out.get("youtube_tags") or meta["tags"],
    )
    print(f"\nUpload OK: {out['youtube_url']}")
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_set_location(args: argparse.Namespace) -> int:
    """Cập nhật vị trí quay (recordingDetails) cho video đã upload."""
    v = get_video(args.ref)
    if not v:
        print(f"Không tìm thấy: {args.ref}", file=sys.stderr)
        return 1
    yt = v.get("youtube") or {}
    vid = (yt.get("video_id") or "").strip()
    if not vid and yt.get("url"):
        m = re.search(r"(?:shorts/|v=)([A-Za-z0-9_-]{6,})", yt["url"])
        vid = m.group(1) if m else ""
    if not vid:
        print("Video chưa upload", file=sys.stderr)
        return 1

    overrides = _settings_from_args(args)
    s = merge_settings(overrides)
    loc = (getattr(args, "location", None) or "").strip() or (
        s.get("youtube_recording_location") or ""
    ).strip()
    if not loc:
        print("Thiếu vị trí — đặt youtube_recording_location trong settings hoặc --location", file=sys.stderr)
        return 1

    print(f"[set-location] video={vid}")
    _ensure_youtube_ready(s)
    ok = apply_recording_location(s, vid, loc)
    return 0 if ok else 1


def cmd_edit(args: argparse.Namespace) -> int:
    patch: dict[str, Any] = {}
    if args.title:
        patch["title"] = args.title
    if args.description:
        patch["description"] = args.description
    if args.tags:
        patch["tags"] = [t.strip() for t in args.tags.split(",") if t.strip()]
    if not patch:
        print("Cần --title, --description hoặc --tags", file=sys.stderr)
        return 1
    try:
        entry = update_metadata(args.ref, patch)
    except KeyError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"Đã cập nhật: {entry.get('id')} — {entry.get('title')}")
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    try:
        result = delete_video_entry(args.ref, remove_file=not args.keep_file)
    except KeyError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"Đã xóa: {result.get('filename')} (id={result.get('id')})")
    return 0


def cmd_set_thumbnail(args: argparse.Namespace) -> int:
    """Gắn ảnh bìa lên video đã upload (cần quyền Custom thumbnails trên kênh)."""
    v = get_video(args.ref)
    if not v:
        print(f"Không tìm thấy: {args.ref}", file=sys.stderr)
        return 1
    yt = v.get("youtube") or {}
    vid = (yt.get("video_id") or yt.get("youtube_video_id") or "").strip()
    if not vid and yt.get("url"):
        m = re.search(r"(?:shorts/|v=)([A-Za-z0-9_-]{6,})", yt["url"])
        vid = m.group(1) if m else ""
    if not vid:
        print("Video chưa upload — chạy: python main.py upload <ref>", file=sys.stderr)
        return 1

    overrides = _settings_from_args(args)
    s = merge_settings(overrides)
    thumb = (v.get("thumbnail_path") or "").strip()
    if thumb:
        thumb = str(resolve_path(thumb))
    path = v.get("absolute_path") or v.get("relative_path")
    if not thumb or not Path(thumb).is_file():
        if path and Path(path).is_file():
            thumb = generate_thumbnail(
                path,
                s,
                topic=v.get("topic") or "",
                title=v.get("title") or "",
                brain=_brain_for_thumbnail(s),
            )
        if not thumb:
            print("Không có file thumbnail — chạy: python main.py thumbnail <ref>", file=sys.stderr)
            return 1
        update_metadata(args.ref, {"thumbnail_path": thumb})

    print(f"[set-thumbnail] video={vid}")
    _ensure_youtube_ready(s)
    ok = upload_thumbnail(s, vid, thumb)
    return 0 if ok else 1


def cmd_hook_intro(args: argparse.Namespace) -> int:
    """Chèn slide *_thumb.jpg im lặng vào đầu MP4 (feed Shorts xem từ frame 0)."""
    v = get_video(args.ref)
    path = (v.get("absolute_path") if v else None) or args.ref
    p = Path(path)
    if not p.is_file():
        print(f"Không tìm thấy: {path}", file=sys.stderr)
        return 1

    overrides = _settings_from_args(args)
    if getattr(args, "hook_force", False):
        overrides["shorts_hook_intro_force"] = True
    if getattr(args, "hook_seconds", None) is not None:
        try:
            overrides["shorts_hook_intro_seconds"] = float(args.hook_seconds)
        except (TypeError, ValueError):
            pass
    s = merge_settings(overrides)

    thumb = ""
    if v:
        thumb = (v.get("thumbnail_path") or "").strip()
    if thumb:
        thumb = str(resolve_path(thumb))
    if not thumb or not Path(thumb).is_file():
        thumb = (
            generate_thumbnail(
                p,
                s,
                topic=(v or {}).get("topic") or "",
                title=(v or {}).get("title") or "",
                brain=_brain_for_thumbnail(s),
            )
            or ""
        )
        if thumb and v:
            update_metadata(args.ref, {"thumbnail_path": thumb})
    if not thumb:
        print("Không có thumbnail — chạy: python main.py thumbnail <ref>", file=sys.stderr)
        return 1

    before = media_duration_seconds(str(p))
    out = maybe_prepend_thumbnail_intro(p, thumb, s)
    after = media_duration_seconds(str(p))
    delta = max(0.0, after - before)
    if v and delta > 0.05:
        update_metadata(args.ref, {"shorts_hook_intro_applied_sec": round(delta, 3)})
    elif delta <= 0.02:
        print("[hook-intro] Không đổi độ dài — có thể đã intro hoặc bị bỏ qua (xem log shorts-intro).")
    print(f"OK: {out}")
    return 0


def cmd_thumbnail(args: argparse.Namespace) -> int:
    """Frame + chữ hook lớn trên ảnh bìa (không upload)."""
    v = get_video(args.ref)
    path = (v.get("absolute_path") if v else None) or args.ref
    p = Path(path)
    if not p.is_file():
        print(f"Không tìm thấy: {path}", file=sys.stderr)
        return 1
    overrides = _settings_from_args(args)
    if getattr(args, "thumb_text", None):
        overrides["youtube_thumbnail_text"] = args.thumb_text
    s = merge_settings(overrides)
    topic = (v or {}).get("topic") or ""
    title = (v or {}).get("title") or ""
    thumb = generate_thumbnail(
        p,
        s,
        topic=topic,
        title=title,
        brain=_brain_for_thumbnail(s),
    )
    if not thumb:
        print("Không tạo được thumbnail", file=sys.stderr)
        return 1
    if v:
        update_metadata(args.ref, {"thumbnail_path": thumb})
    print(f"Thumbnail: {thumb}")
    return 0


def cmd_import_meta(args: argparse.Namespace) -> int:
    """Đăng ký file có sẵn + sinh metadata từ topic."""
    path = Path(args.file)
    if not path.is_file():
        print(f"Không tìm thấy: {path}", file=sys.stderr)
        return 1
    overrides = _settings_from_args(args)
    topic = args.topic or path.stem.replace("_", " ")
    overrides["use_manual_topic"] = True
    overrides["manual_topic"] = topic
    from app.brain import ContentBrain
    from app.settings import gemini_keys, model_chain, topic_prompt, video_cfg, locale

    loc = locale(overrides)
    gkeys = gemini_keys(overrides)
    brain = None
    if gkeys:
        brain = ContentBrain(
            api_keys=gkeys,
            model_chain=model_chain(overrides),
            topic_prompt=topic_prompt(overrides),
            video_cfg=video_cfg(overrides),
            language=loc["code"],
        )
    meta = prepare_video_metadata(overrides, topic, brain=brain)
    from app.video_catalog import build_metadata

    entry = register_video(
        path,
        build_metadata(
            topic=topic,
            title=meta["title"],
            description=meta["description"],
            tags=meta["tags"],
            hashtags=meta.get("hashtags") or [],
            title_variants=meta.get("title_variants") or [],
            language=loc["code"],
        ),
    )
    print(f"Import OK: id={entry['id']} title={entry['title']}")
    return 0


def cmd_check_youtube(args: argparse.Namespace) -> int:
    overrides = _settings_from_args(args)
    aid = (args.youtube_account or overrides.get("youtube_account_id") or "default").strip()
    st = account_status(merge_settings({**overrides, "youtube_account_id": aid}), account_id=aid)
    _print_youtube_status(st)
    return 0 if st.get("authenticated") else 1


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--settings", default="", help="user_settings.json")
    p.add_argument("--json", action="store_true", help="In JSON")


def _add_youtube(p: argparse.ArgumentParser) -> None:
    p.add_argument("--youtube-account", default="", help="account-id OAuth")
    p.add_argument("--youtube-channel", default="", help="UC...")
    p.add_argument("--youtube-privacy", choices=("private", "unlisted", "public"), default="")


def main() -> int:
    parser = argparse.ArgumentParser(description="YT Shorts CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Tạo video + metadata (+ upload với --shorts)")
    _add_common(p_create)
    p_create.add_argument("--lang", choices=("en", "vi"), default=None, help="Ngôn ngữ (mặc định en trong user_settings)")
    p_create.add_argument("--topic", default="", help="Chủ đề")
    p_create.add_argument("--video-mode", choices=("short", "long"), default="")
    p_create.add_argument("--output", default="", help="Tên file MP4")
    p_create.add_argument("--avatar-mode", choices=("off", "default", "custom"), default="")
    p_create.add_argument("--shorts", action="store_true", help="Upload YouTube sau render")
    p_create.add_argument("--youtube", action="store_true", help="Giống --shorts")
    p_create.add_argument("--no-youtube", action="store_true")
    p_create.add_argument("--no-youtube-seo", action="store_true")
    p_create.add_argument(
        "--reshuffle",
        action="store_true",
        help="Chọn lại clip Pexels + cảnh avatar + xfade (xóa cache clip theo cảnh, seed ngẫu nhiên)",
    )
    p_create.add_argument(
        "--seed",
        type=int,
        default=None,
        metavar="N",
        help="Seed render cố định (lặp lại được); kèm --reshuffle để vẫn tải lại clip",
    )
    _add_youtube(p_create)

    p_list = sub.add_parser("list", help="Danh sách video")
    _add_common(p_list)
    p_list.add_argument("--pending", action="store_true", help="Chưa upload")
    p_list.add_argument("--uploaded", action="store_true", help="Đã upload")

    p_show = sub.add_parser("show", help="Chi tiết 1 video")
    _add_common(p_show)
    p_show.add_argument("ref", help="id hoặc filename")

    p_upload = sub.add_parser("upload", help="Upload video đã có (dùng metadata đã lưu)")
    _add_common(p_upload)
    p_upload.add_argument("ref", help="id hoặc filename")
    p_upload.add_argument("--force", action="store_true", help="Upload lại dù đã có")
    _add_youtube(p_upload)

    p_loc = sub.add_parser(
        "set-location",
        help="Cập nhật vị trí quay (recordingDetails) cho video đã upload",
    )
    _add_common(p_loc)
    _add_youtube(p_loc)
    p_loc.add_argument("ref", help="id hoặc filename đã upload")
    p_loc.add_argument(
        "--location",
        default="",
        help='Mô tả vị trí (mặc định youtube_recording_location), VD: "United States"',
    )

    p_edit = sub.add_parser("edit", help="Sửa title/mô tả/tags")
    p_edit.add_argument("ref", help="id hoặc filename")
    p_edit.add_argument("--title", default="")
    p_edit.add_argument("--description", default="")
    p_edit.add_argument("--tags", default="", help="tag1, tag2")

    p_del = sub.add_parser("delete", help="Xóa video + metadata")
    p_del.add_argument("ref", help="id hoặc filename")
    p_del.add_argument("--keep-file", action="store_true", help="Chỉ xóa catalog, giữ MP4")

    p_import = sub.add_parser("import", help="Đăng ký MP4 có sẵn + sinh metadata")
    _add_common(p_import)
    p_import.add_argument("file", help="Đường dẫn MP4")
    p_import.add_argument("--topic", default="")
    p_import.add_argument("--lang", choices=("en", "vi"), default=None)

    p_thumb = sub.add_parser("thumbnail", help="Ảnh bìa: frame + chữ hook lớn")
    _add_common(p_thumb)
    p_thumb.add_argument("ref", help="id hoặc filename MP4")
    p_thumb.add_argument("--lang", choices=("en", "vi"), default=None)
    p_thumb.add_argument(
        "--thumb-text",
        default="",
        help="Chữ cố định trên ảnh (bỏ qua AI); VD: 'YOU WON'T BELIEVE THIS'",
    )

    p_set_thumb = sub.add_parser(
        "set-thumbnail",
        help="Gắn *_thumb.jpg lên video đã upload (cần Custom thumbnails trên kênh)",
    )
    _add_common(p_set_thumb)
    _add_youtube(p_set_thumb)
    p_set_thumb.add_argument("ref", help="id hoặc filename đã upload")

    p_hook = sub.add_parser(
        "hook-intro",
        help="Chèn ảnh *_thumb.jpg ~0,85s im lặng vào đầu MP4 Shorts (ghi đè file)",
    )
    _add_common(p_hook)
    p_hook.add_argument("ref", help="id hoặc filename MP4")
    p_hook.add_argument(
        "--force",
        dest="hook_force",
        action="store_true",
        help="Chèn lại dù .meta.json đã ghi intro (cẩn thận: sẽ thêm thêm một đoạn intro)",
    )
    p_hook.add_argument(
        "--seconds",
        dest="hook_seconds",
        type=float,
        default=None,
        help="Độ dài intro (giây); mặc định shorts_hook_intro_seconds trong settings",
    )

    p_check = sub.add_parser("check-youtube", help="Kiểm tra OAuth")
    _add_common(p_check)
    _add_youtube(p_check)

    args = parser.parse_args()
    sync_catalog()

    handlers = {
        "create": lambda: asyncio.run(cmd_create(args)),
        "list": lambda: cmd_list(args),
        "show": lambda: cmd_show(args),
        "upload": lambda: cmd_upload(args),
        "set-location": lambda: cmd_set_location(args),
        "edit": lambda: cmd_edit(args),
        "delete": lambda: cmd_delete(args),
        "import": lambda: cmd_import_meta(args),
        "thumbnail": lambda: cmd_thumbnail(args),
        "set-thumbnail": lambda: cmd_set_thumbnail(args),
        "hook-intro": lambda: cmd_hook_intro(args),
        "check-youtube": lambda: cmd_check_youtube(args),
    }
    try:
        return handlers[args.command]()
    except SystemExit:
        raise
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
