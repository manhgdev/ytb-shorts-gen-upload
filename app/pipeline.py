from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from app.audio import AudioEngine
from app.brain import ContentBrain
from app.composer import Composer
from app.settings import (
    ROOT,
    audio_cfg,
    gemini_keys,
    locale,
    merge_settings,
    model_chain,
    output_filename,
    pexels_keys,
    topic_prompt,
    video_cfg,
)
from app.render_random import make_render_rng
from app.stock import StockFootage
from app.utils import ensure_ffmpeg, media_duration_seconds
from app.video_catalog import build_metadata, mark_uploaded, register_video
from app.shorts_intro import maybe_prepend_thumbnail_intro
from app.thumbnail import generate_thumbnail
from app.youtube import maybe_upload
from app.youtube_seo import prepare_video_metadata


def _rel_thumb(abs_path: str) -> str:
    if not abs_path:
        return ""
    p = Path(abs_path)
    try:
        return str(p.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(p)


def _clean_cache() -> None:
    for name in ("audio_clips", "video_clips", "temp"):
        folder = ROOT / "assets" / name
        if not folder.is_dir():
            continue
        for item in folder.iterdir():
            try:
                if item.is_file() or item.is_symlink():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            except OSError as e:
                print(f"[clean] skip {item}: {e}")


async def run(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Chạy pipeline. Nhận dict tùy chọn (API / bot); thiếu field → mặc định.
    Trả về: path, topic, model_used.
    """
    settings = merge_settings(overrides)
    os.chdir(ROOT)
    ensure_ffmpeg()

    gkeys, pkeys = gemini_keys(settings), pexels_keys(settings)
    if not gkeys:
        raise ValueError("Thiếu gemini_api_key")
    if not pkeys:
        raise ValueError("Thiếu pexels_api_key")

    loc = locale(settings)
    vcfg = video_cfg(settings)
    voice, rate = audio_cfg(settings)

    brain = ContentBrain(
        api_keys=gkeys,
        model_chain=model_chain(settings),
        topic_prompt=topic_prompt(settings),
        video_cfg=vcfg,
        script_extra_instructions=str(settings.get("script_extra_instructions") or ""),
        language=loc["code"],
        retry_delay_seconds=int(settings.get("gemini_retry_delay_seconds") or 60),
        max_retries=int(settings.get("gemini_max_retries") or 4),
    )

    if settings.get("use_manual_topic"):
        topic = (settings.get("manual_topic") or "").strip()
        if not topic:
            raise ValueError("use_manual_topic=true nhưng manual_topic trống")
        brain.topic_used = topic
    else:
        topic = brain.topic()

    script = brain.script(topic)
    if not script:
        raise RuntimeError("Không tạo được kịch bản")

    script = await AudioEngine(voice, rate).process(script)

    rng, seed_int = make_render_rng(settings, overrides)
    print(f"[render] seed={seed_int}")
    force = bool(settings.get("stock_force_refresh"))
    try:
        pp = int(settings.get("pexels_per_page") or 5)
    except (TypeError, ValueError):
        pp = 5
    pairs = StockFootage(pkeys, rng=rng, force_refresh=force, per_page=pp).fetch_pairs(script)

    print("[metadata] sinh title / mô tả / tags...")
    video_meta = prepare_video_metadata(settings, topic, script, brain=brain)
    print(f"[title] {video_meta['title']}")
    for i, v in enumerate(video_meta.get("title_variants") or [], 1):
        if v != video_meta["title"]:
            print(f"  variant {i}: {v}")

    composer = Composer(settings, rng=rng)
    scenes = composer.render(script, pairs)
    if not scenes:
        raise RuntimeError("Không render được cảnh nào")

    out_name = output_filename(settings)
    path = composer.stitch(scenes, out_name)
    if settings.get("clean_cache", True):
        _clean_cache()

    thumb_path = (
        generate_thumbnail(
            path,
            settings,
            topic=topic,
            title=video_meta["title"],
            brain=brain,
        )
        or ""
    )
    if thumb_path:
        print(f"[thumbnail] ảnh bìa: {Path(thumb_path).name}")

    before_intro = media_duration_seconds(path)
    if thumb_path:
        path = maybe_prepend_thumbnail_intro(
            path,
            thumb_path,
            {**settings, "shorts_hook_intro_from_pipeline": True},
        )
    intro_delta = max(0.0, media_duration_seconds(path) - before_intro) if thumb_path else 0.0

    catalog_meta = build_metadata(
        topic=topic,
        title=video_meta["title"],
        description=video_meta["description"],
        tags=video_meta["tags"],
        hashtags=video_meta.get("hashtags") or [],
        title_variants=video_meta.get("title_variants") or [],
        language=loc["code"],
        model_used=brain.model_name,
        script=script,
        thumbnail_path=_rel_thumb(thumb_path),
        shorts_hook_intro_applied_sec=intro_delta,
    )
    catalog_entry = register_video(path, catalog_meta)

    upload_settings = {
        **settings,
        "youtube_title": video_meta["title"],
        "youtube_description": video_meta["description"],
        "youtube_tags": video_meta["tags"],
        "youtube_auto_seo": False,
    }

    result = {
        "path": path,
        "topic": topic,
        "model_used": brain.model_name,
        "language": loc["code"],
        "output_filename": out_name,
        "video_id": catalog_entry.get("id"),
        "title": video_meta["title"],
        "title_variants": video_meta.get("title_variants") or [],
        "description": video_meta["description"],
        "tags": video_meta["tags"],
        "hashtags": video_meta.get("hashtags") or [],
        "meta_path": str(Path(path).with_name(f"{Path(path).stem}.meta.json")),
        "thumbnail_path": thumb_path,
    }
    upload_result = maybe_upload(
        path,
        {**upload_settings, "youtube_thumbnail_path": thumb_path},
        topic,
        script=script,
        brain=brain,
    )
    if upload_result.get("youtube_video_id"):
        mark_uploaded(
            path,
            youtube_video_id=upload_result["youtube_video_id"],
            youtube_url=upload_result["youtube_url"],
            youtube_title=upload_result.get("youtube_title") or video_meta["title"],
            youtube_privacy=upload_result.get("youtube_privacy") or settings.get("youtube_privacy", "private"),
            youtube_account_id=upload_result.get("youtube_account_id") or settings.get("youtube_account_id") or "",
            youtube_description=upload_result.get("youtube_description") or video_meta["description"],
            youtube_tags=upload_result.get("youtube_tags") or video_meta["tags"],
        )
    result.update(upload_result)
    return result
