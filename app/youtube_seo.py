from __future__ import annotations

import random
from typing import Any

from app.brain import ContentBrain
from app.settings import gemini_keys, model_chain, topic_prompt, video_cfg


def _parse_tags(raw: Any) -> list[str]:
    if isinstance(raw, str):
        return [t.strip() for t in raw.replace(",", " ").split() if t.strip()]
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    return []


def needs_youtube_seo(settings: dict[str, Any]) -> bool:
    if not settings.get("youtube_auto_seo", True):
        return False
    has_title = bool((settings.get("youtube_title") or "").strip())
    has_desc = bool((settings.get("youtube_description") or "").strip())
    has_tags = bool(_parse_tags(settings.get("youtube_tags")))
    return not (has_title and has_desc and has_tags)


def _brain_from_settings(settings: dict[str, Any]) -> ContentBrain:
    gkeys = gemini_keys(settings)
    if not gkeys:
        raise ValueError("Thiếu gemini_api_key cho YouTube SEO")
    return ContentBrain(
        api_keys=gkeys,
        model_chain=model_chain(settings),
        topic_prompt=topic_prompt(settings) or "trending science",
        video_cfg=video_cfg(settings),
        script_extra_instructions=str(settings.get("script_extra_instructions") or ""),
        language=settings.get("language") if settings.get("language") in ("en", "vi") else "en",
        retry_delay_seconds=int(settings.get("gemini_retry_delay_seconds") or 60),
        max_retries=int(settings.get("gemini_max_retries") or 4),
    )


def generate_youtube_metadata(
    settings: dict[str, Any],
    topic: str,
    script: list | None = None,
    *,
    brain: ContentBrain | None = None,
) -> dict[str, Any] | None:
    """Gọi Gemini; trả title, title_variants, description, tags, hashtags."""
    if not needs_youtube_seo(settings):
        return None
    own_brain = brain is None
    b = brain or _brain_from_settings(settings)
    extra = str(settings.get("youtube_seo_extra_instructions") or "")
    payload = script if script else [{"text": topic}]
    data = b.youtube_seo(topic.strip() or "YouTube Short", payload, extra)
    if own_brain:
        pass
    if not data:
        return None
    return _normalize_seo(data)


def _normalize_seo(data: dict[str, Any]) -> dict[str, Any]:
    title = str(data.get("title") or "").strip()
    variants = data.get("title_variants")
    if not isinstance(variants, list):
        variants = []
    clean_variants = []
    for v in variants:
        s = str(v).strip()
        if s and s not in clean_variants:
            clean_variants.append(s[:100])
    if title and title not in clean_variants:
        clean_variants.insert(0, title[:100])
    if not title and clean_variants:
        title = clean_variants[0]
    if not clean_variants and title:
        clean_variants = [title[:100]]

    desc = str(data.get("description") or "").strip()
    tags = data.get("tags")
    if not isinstance(tags, list):
        tags = []
    tags = [str(t).strip().lstrip("#") for t in tags if str(t).strip()][:30]

    hashtags = data.get("hashtags")
    if not isinstance(hashtags, list):
        hashtags = []
    hashtags = [_ensure_hash(str(h).strip()) for h in hashtags if str(h).strip()]

    if desc and "#shorts" not in desc.lower():
        if hashtags:
            desc = f"{desc}\n\n" + " ".join(hashtags[:18])
        else:
            desc = f"{desc}\n\n#Shorts"
    elif desc and hashtags:
        missing = [h for h in hashtags if h.lower() not in desc.lower()]
        if missing:
            desc = f"{desc}\n\n" + " ".join(missing[:10])

    if title and "#shorts" not in title.lower() and len(title) < 88:
        title = f"{title} #Shorts"

    return {
        "title": title[:100],
        "title_variants": clean_variants[:8],
        "description": desc[:5000],
        "tags": tags,
        "hashtags": hashtags[:20],
    }


def _ensure_hash(tag: str) -> str:
    return tag if tag.startswith("#") else f"#{tag}"


def fallback_metadata(topic: str, language: str = "en") -> dict[str, Any]:
    """Khi Gemini SEO lỗi — title từ topic."""
    t = topic.strip() or "YouTube Short"
    title = t if len(t) <= 88 else t[:85] + "..."
    if "#shorts" not in title.lower():
        title = f"{title} #Shorts"
    desc = f"{t}\n\n#Shorts #YouTubeShorts"
    return {
        "title": title[:100],
        "title_variants": [title[:100]],
        "description": desc[:5000],
        "tags": ["shorts", "youtubeshorts"],
        "hashtags": ["#Shorts", "#YouTubeShorts"],
    }


def prepare_video_metadata(
    settings: dict[str, Any],
    topic: str,
    script: list | None = None,
    *,
    brain: ContentBrain | None = None,
) -> dict[str, Any]:
    """Sinh metadata lúc render; fallback nếu Gemini lỗi."""
    manual_title = (settings.get("youtube_title") or "").strip()
    manual_desc = (settings.get("youtube_description") or "").strip()
    manual_tags = _parse_tags(settings.get("youtube_tags"))

    if manual_title and manual_desc and manual_tags:
        title = manual_title
        if "#shorts" not in title.lower() and len(title) < 88:
            title = f"{title} #Shorts"
        return {
            "title": title[:100],
            "title_variants": [title[:100]],
            "description": manual_desc[:5000],
            "tags": manual_tags[:30],
            "hashtags": [],
        }

    seo = None
    if settings.get("youtube_auto_seo", True) and brain is not None:
        try:
            seo = generate_youtube_metadata(settings, topic, script, brain=brain)
        except Exception as e:
            print(f"[youtube-seo] fallback: {e}")

    if not seo:
        lang = settings.get("language") if settings.get("language") in ("en", "vi") else "en"
        seo = fallback_metadata(topic, lang)

    title = manual_title or pick_title(seo, settings)
    desc = manual_desc or seo["description"]
    tags = manual_tags or seo["tags"]
    if "#shorts" not in title.lower() and len(title) < 88:
        title = f"{title} #Shorts"

    return {
        "title": title[:100],
        "title_variants": seo.get("title_variants") or [title[:100]],
        "description": desc[:5000],
        "tags": tags[:30],
        "hashtags": seo.get("hashtags") or [],
    }


def pick_title(seo: dict[str, Any], settings: dict[str, Any]) -> str:
    variants = seo.get("title_variants") or []
    if settings.get("youtube_random_title", True) and len(variants) > 1:
        return random.choice(variants)[:100]
    return (seo.get("title") or (variants[0] if variants else "YouTube Short"))[:100]


def apply_seo_to_meta(
    settings: dict[str, Any],
    topic: str,
    script: list | None = None,
    *,
    brain: ContentBrain | None = None,
) -> dict[str, str | list[str]] | None:
    """Trả meta đã merge SEO + override từ settings."""
    seo = generate_youtube_metadata(settings, topic, script, brain=brain)
    if not seo:
        return None

    title = (settings.get("youtube_title") or "").strip() or pick_title(seo, settings)
    desc = (settings.get("youtube_description") or "").strip() or seo["description"]
    tags = _parse_tags(settings.get("youtube_tags")) or seo["tags"]

    if "#shorts" not in title.lower():
        title = f"{title} #Shorts" if len(title) < 88 else title
    if desc and "#shorts" not in desc.lower():
        desc = f"{desc}\n\n#Shorts"

    return {
        "title": title[:100],
        "description": desc[:5000],
        "tags": tags[:30],
        "title_variants": seo.get("title_variants") or [],
        "hashtags": seo.get("hashtags") or [],
    }
