from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import DEFAULT_GEMINI_MODELS, LOCALES, VIDEO_PRESETS

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = ROOT / "user_settings.json"

AVATAR_VIDEO = "assets/avatar/avatars.mp4"
AVATAR_IMAGE = "assets/avatar/avatars.png"

_IMG_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp"})


def resolve_avatar_image_path(settings: dict[str, Any] | None = None) -> Path | None:
    """Ảnh tĩnh avatar (PNG/JPG) — dùng cho thumbnail, không lấy từ .mp4."""
    from app.utils import resolve_path

    s = settings or {}
    mode = (s.get("avatar_mode") or "default").strip().lower()

    def _as_image(raw: str) -> Path | None:
        if not (raw or "").strip():
            return None
        p = Path(resolve_path(raw.strip()))
        if p.is_file() and p.suffix.lower() in _IMG_SUFFIXES:
            return p
        return None

    def _sibling_png(video_raw: str) -> Path | None:
        if not (video_raw or "").strip():
            return None
        vp = Path(resolve_path(video_raw.strip()))
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            sib = vp.with_suffix(ext)
            if sib.is_file():
                return sib
        return None

    if mode == "custom":
        img = _as_image(str(s.get("avatar_image_path") or ""))
        if img:
            return img
        return _sibling_png(str(s.get("avatar_video_path") or ""))
    if mode == "default":
        img = _as_image(AVATAR_IMAGE)
        if img:
            return img
        return _sibling_png(AVATAR_VIDEO)
    return None


def default_settings() -> dict[str, Any]:
    return {
        # API keys: user_settings.json hoặc body POST /v1/generate
        "gemini_api_key": "",
        "pexels_api_key": "",
        # Bảo vệ HTTP API (chỉ trên server, bot không cần gửi)
        "api_secret": "",
        # URL công khai của API (OAuth redirect) — trùng bot YTB_SHORTS.apiUrl
        "youtube_oauth_public_base": "http://127.0.0.1:8000",
        # Gemini
        "gemini_model": "auto",
        "gemini_models": [],
        "gemini_retry_delay_seconds": 60,
        "gemini_max_retries": 4,
        # Ngôn ngữ & nội dung
        "language": "en",
        "topic_prompt": "",
        "use_manual_topic": False,
        "manual_topic": "",
        "script_extra_instructions": "",
        # Kịch bản / video
        "video_mode": "short",
        "min_scenes": None,
        "max_scenes": None,
        "words_per_scene": None,
        # TTS (None → theo language)
        "voice": None,
        "speech_rate": None,
        # Output
        "output_dir": "assets/final",
        "output_filename": None,
        # Avatar
        "avatar_mode": "default",
        "avatar_video_path": "",
        "avatar_image_path": "",
        "avatar_scenes": 2,
        # Phân cảnh / clip: seed + làm mới Pexels; avatar_scene_numbers = cảnh cố định (1-based, không đầu/cuối)
        "render_seed": None,
        "stock_force_refresh": False,
        "pexels_per_page": 5,
        "avatar_scene_numbers": [],
        # Pipeline
        "clean_cache": True,
        # YouTube upload (OAuth: scripts/youtube_auth.py)
        "youtube_upload": False,
        "youtube_account_id": "",
        "youtube_channel_id": "",
        "youtube_client_secrets_path": "credentials/youtube_client_secret.json",
        "youtube_token_path": "credentials/youtube_token.json",
        "youtube_title": "",
        "youtube_description": "",
        "youtube_tags": [],
        "youtube_auto_seo": True,
        "youtube_random_title": True,
        "youtube_seo_extra_instructions": "",
        "youtube_privacy": "private",
        "youtube_category_id": "22",
        # false = không phải "Made for Kids" (nội dung đại chúng / teen OK)
        "youtube_made_for_kids": False,
        # Vị trí quay (hiển thị trên Studio): mô tả văn bản, vd "United States". Rỗng = không gửi.
        "youtube_recording_location": "",
        # Thumbnail: frame + chữ hook lớn (Pillow) → upload YouTube
        "youtube_thumbnail_enabled": True,
        # avatar_image = assets/avatar/avatars.png (hoặc avatar_image_path); video = cắt frame MP4
        "youtube_thumbnail_source": "avatar_image",
        "youtube_thumbnail_mode": "auto",
        "youtube_thumbnail_at_sec": None,
        "youtube_thumbnail_text": "",
        "youtube_thumbnail_accent": "WATCH",
        "youtube_thumbnail_text_zone_top": 0.52,
        "youtube_thumbnail_text_align": "center",
        "youtube_thumbnail_text_top_padding": 0.05,
        "youtube_thumbnail_ai_text": True,
        # Shorts: chèn ~N giây ảnh *_thumb.jpg im lặng đầu MP4. 0 = tắt (chỉ còn biến này)
        "shorts_hook_intro_seconds": 0.85,
    }


SETTING_KEYS = frozenset(default_settings().keys())

# user_settings.json có thể gom theo nhóm (object lồng) hoặc phẳng một tầng (cũ).
USER_SETTING_SECTIONS = frozenset(
    {
        "api",
        "gemini",
        "content",
        "video",
        "tts",
        "output",
        "avatar",
        "render",
        "pipeline",
        "youtube_account",
        "youtube_seo",
        "youtube_thumbnail",
        "shorts_feed",
    }
)


def flatten_user_settings(user: dict[str, Any]) -> dict[str, Any]:
    """Gộp các section → dict phẳng cho merge_settings."""
    if not user:
        return {}
    if not any(k in USER_SETTING_SECTIONS for k in user):
        return user
    flat: dict[str, Any] = {}
    for key, val in user.items():
        if key in USER_SETTING_SECTIONS and isinstance(val, dict):
            flat.update(val)
        elif key not in USER_SETTING_SECTIONS:
            flat[key] = val
    return flat


def _split_keys(raw: str) -> list[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.replace("\n", ",").split(",") if p.strip()]


def normalize_api_keys(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(k).strip() for k in value if str(k).strip()]
    if isinstance(value, str):
        return _split_keys(value)
    return []


_API_KEY_MERGE_FIELDS = frozenset({"gemini_api_key", "pexels_api_key"})


def _union_api_keys(*values: Any) -> list[str]:
    """Gộp key: ưu tiên thứ tự đầu (body bot), sau đó key từ user_settings.json."""
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        for k in normalize_api_keys(value):
            if k not in seen:
                seen.add(k)
                out.append(k)
    return out


def _apply_overrides(data: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    for key in SETTING_KEYS:
        if key not in overrides:
            continue
        val = overrides[key]
        if val is None:
            continue
        if key in _API_KEY_MERGE_FIELDS:
            data[key] = _union_api_keys(val, data.get(key))
        else:
            data[key] = val
    return data


def _base_settings(path: Path | None = None) -> dict[str, Any]:
    """default_settings + user_settings.json (không gọi merge_settings — tránh đệ quy)."""
    data = default_settings()
    cfg = path or SETTINGS_FILE
    if not cfg.is_file():
        return _normalize_avatar_mode(data)
    try:
        user = json.loads(cfg.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _normalize_avatar_mode(data)
    if not isinstance(user, dict):
        return _normalize_avatar_mode(data)
    return _normalize_avatar_mode(_apply_overrides(data, flatten_user_settings(user)))


def merge_settings(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Gộp overrides lên user_settings.json; gemini/pexels keys **cộng dồn**, không ghi đè hết pool."""
    data = _base_settings()
    if not overrides:
        return data
    return _normalize_avatar_mode(_apply_overrides(data, overrides))


def _normalize_avatar_mode(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("avatar_mode"):
        return data
    if str(data.get("avatar_video_path") or "").strip() or str(data.get("avatar_image_path") or "").strip():
        data["avatar_mode"] = "custom"
    return data


def load_settings(path: Path | None = None) -> dict[str, Any]:
    return _base_settings(path)


def gemini_keys(settings: dict[str, Any]) -> list[str]:
    return normalize_api_keys(settings.get("gemini_api_key"))


def pexels_keys(settings: dict[str, Any]) -> list[str]:
    return normalize_api_keys(settings.get("pexels_api_key"))


def api_secret() -> str:
    return str(load_settings().get("api_secret") or "").strip()


def locale(settings: dict[str, Any]) -> dict[str, Any]:
    lang = (settings.get("language") or "en").strip().lower()
    if lang not in LOCALES:
        lang = "en"
    return {**LOCALES[lang], "code": lang}


def topic_prompt(settings: dict[str, Any]) -> str:
    custom = (settings.get("topic_prompt") or "").strip()
    if custom:
        return custom
    return locale(settings)["topic_prompt"]


def model_chain(settings: dict[str, Any]) -> list[str]:
    custom = settings.get("gemini_models")
    if isinstance(custom, list) and custom:
        return [str(m).strip() for m in custom if str(m).strip()]
    order = list(DEFAULT_GEMINI_MODELS)
    preferred = (settings.get("gemini_model") or "").strip()
    if not preferred or preferred.lower() == "auto":
        return order
    if preferred not in order:
        return [preferred] + order
    return [preferred] + [m for m in order if m != preferred]


def video_cfg(settings: dict[str, Any]) -> dict[str, Any]:
    mode = (settings.get("video_mode") or "short").strip().lower()
    if mode not in VIDEO_PRESETS:
        mode = "short"
    base = dict(VIDEO_PRESETS[mode])
    if settings.get("min_scenes") is not None:
        base["min_scenes"] = int(settings["min_scenes"])
    if settings.get("max_scenes") is not None:
        base["max_scenes"] = int(settings["max_scenes"])
    ws = settings.get("words_per_scene")
    if ws is not None and str(ws).strip():
        base["words_per_scene"] = str(ws).strip()
    return base


def audio_cfg(settings: dict[str, Any]) -> tuple[str, str]:
    loc = locale(settings)
    voice = settings.get("voice")
    rate = settings.get("speech_rate")
    v = str(voice).strip() if voice else ""
    r = str(rate).strip() if rate else ""
    return v or loc["voice"], r or loc["speech_rate"]


def output_filename(settings: dict[str, Any]) -> str:
    custom = settings.get("output_filename")
    if custom is not None and str(custom).strip():
        return str(custom).strip()
    return locale(settings)["output_filename"]
