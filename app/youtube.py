from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from app.settings import ROOT
from app.utils import media_duration_seconds, media_video_size, resolve_path
from app.thumbnail import generate_thumbnail, upload_thumbnail
from app.youtube_seo import apply_seo_to_meta

SHORTS_MAX_SECONDS = 60

SCOPE_UPLOAD = "https://www.googleapis.com/auth/youtube.upload"
SCOPE_FORCE_SSL = "https://www.googleapis.com/auth/youtube.force-ssl"
SCOPE_READONLY = "https://www.googleapis.com/auth/youtube.readonly"
SCOPE_YOUTUBE = "https://www.googleapis.com/auth/youtube"

# OAuth mới: upload + force-ssl (metadata). Token cũ chỉ upload vẫn upload được — list kênh tuỳ chọn.
SCOPES = [SCOPE_UPLOAD, SCOPE_FORCE_SSL]
_SCOPES_CAN_LIST = frozenset({SCOPE_FORCE_SSL, SCOPE_READONLY, SCOPE_YOUTUBE})
DEFAULT_SECRETS = "credentials/youtube_client_secret.json"
DEFAULT_TOKEN = "credentials/youtube_token.json"
TOKENS_DIR = ROOT / "credentials" / "youtube_tokens"
VALID_PRIVACY = frozenset({"private", "public", "unlisted"})


def reauth_hint(
    settings: dict[str, Any],
    *,
    missing: list[str] | None = None,
    account_id: str | None = None,
) -> str:
    aid = normalize_account_id(
        account_id or settings.get("youtube_account_id") or "default"
    )
    msg = f"Chạy lại OAuth: python3 scripts/youtube_auth.py --account-id {aid}"
    if missing:
        short = [s.rsplit("/", 1)[-1] for s in missing]
        msg += f" (thiếu scope: {', '.join(short)})"
    return msg


def _read_token_scopes(token: Path) -> list[str]:
    try:
        data = json.loads(token.read_text(encoding="utf-8"))
        scopes = data.get("scopes")
        if isinstance(scopes, list) and scopes:
            return [str(s) for s in scopes]
    except (OSError, json.JSONDecodeError):
        pass
    return list(SCOPES)


def _token_scopes_set(settings: dict[str, Any]) -> set[str]:
    token = _token_path(settings)
    if not token.is_file():
        return set()
    return set(_read_token_scopes(token))


def has_upload_scope(settings: dict[str, Any]) -> bool:
    have = _token_scopes_set(settings)
    return SCOPE_UPLOAD in have or SCOPE_YOUTUBE in have


def has_list_scope(settings: dict[str, Any]) -> bool:
    return bool(_token_scopes_set(settings) & _SCOPES_CAN_LIST)


def missing_oauth_scopes(settings: dict[str, Any]) -> list[str]:
    """Scope thiếu so với SCOPES chuẩn (OAuth mới). Không chặn upload nếu chỉ thiếu force-ssl."""
    token = _token_path(settings)
    if not token.is_file():
        return list(SCOPES)
    have = _token_scopes_set(settings)
    return [s for s in SCOPES if s not in have]


def channels_list_hint(settings: dict[str, Any]) -> str:
    aid = normalize_account_id(settings.get("youtube_account_id") or "default")
    return (
        f"Upload OK — gửi youtube_channel_id (UC…) trong request. "
        f"Muốn list kênh tự động: python3 scripts/youtube_auth.py --account-id {aid}"
    )


def _safe_id(raw: str) -> str:
    s = re.sub(r"[^\w\-]", "_", (raw or "").strip())[:64]
    return s or "default"


def normalize_account_id(raw: str) -> str:
    """
    ID lưu token (tên file), không phải @handle YouTube.
    Cho phép gõ @Branch hoặc Branch — cùng file credentials/youtube_tokens/Branch.json
    """
    s = (raw or "").strip()
    if s.startswith("@"):
        s = s[1:].strip()
    return _safe_id(s) if s else "default"


def _format_channel_handle(custom_url: str) -> str:
    """Handle hiển thị kiểu @TenKenh (YouTube customUrl có/không có @)."""
    s = (custom_url or "").strip()
    if not s:
        return ""
    return s if s.startswith("@") else f"@{s}"


def _secrets_path(settings: dict[str, Any]) -> Path:
    raw = (settings.get("youtube_client_secrets_path") or DEFAULT_SECRETS).strip()
    return Path(resolve_path(raw))


def resolve_token_path(
    settings: dict[str, Any],
    *,
    account_id: str | None = None,
    token_path: str | None = None,
) -> Path:
    if token_path and str(token_path).strip():
        return Path(resolve_path(str(token_path).strip()))

    aid_raw = (account_id or settings.get("youtube_account_id") or "").strip()
    if aid_raw:
        aid = normalize_account_id(aid_raw)
        legacy = _safe_id(aid_raw)
        for candidate in (
            TOKENS_DIR / f"{aid}.json",
            TOKENS_DIR / f"{legacy}.json" if legacy != aid else None,
            TOKENS_DIR / f"{aid_raw}.json" if aid_raw != aid and aid_raw != legacy else None,
            Path(resolve_path(DEFAULT_TOKEN)) if aid == "default" else None,
        ):
            if candidate and candidate.is_file():
                return candidate
        return TOKENS_DIR / f"{aid}.json"

    tp = (settings.get("youtube_token_path") or "").strip()
    if tp:
        return Path(resolve_path(tp))

    return Path(resolve_path(DEFAULT_TOKEN))


def _token_path(settings: dict[str, Any]) -> Path:
    aid = (settings.get("youtube_account_id") or "").strip()
    if aid:
        return resolve_token_path(settings, account_id=aid)
    tp = (settings.get("youtube_token_path") or "").strip()
    if tp:
        return resolve_token_path(settings, token_path=tp)
    return resolve_token_path(settings)


def _settings_with_token(settings: dict[str, Any], token: Path) -> dict[str, Any]:
    s = dict(settings)
    rel = str(token.relative_to(ROOT)) if token.is_relative_to(ROOT) else str(token)
    s["youtube_token_path"] = rel
    if not (s.get("youtube_account_id") or "").strip():
        if token.parent == TOKENS_DIR:
            s["youtube_account_id"] = token.stem
        else:
            s["youtube_account_id"] = "default"
    return s


def list_accounts() -> dict[str, Any]:
    TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    accounts: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(account_id: str, path: Path) -> None:
        key = str(path.resolve())
        if key in seen:
            return
        seen.add(key)
        rel = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name
        entry: dict[str, Any] = {
            "account_id": account_id,
            "token_path": rel,
            "token_exists": path.is_file(),
        }
        if path.is_file():
            try:
                st = account_status(
                    {"youtube_token_path": rel, "youtube_account_id": account_id}
                )
                entry["authenticated"] = st.get("authenticated", False)
                entry["channel_title"] = st.get("channel_title")
                entry["channels_count"] = st.get("channels_count", 0)
            except Exception as e:
                entry["authenticated"] = False
                entry["message"] = str(e)
        accounts.append(entry)

    default_p = ROOT / DEFAULT_TOKEN
    _add("default", default_p)
    for p in sorted(TOKENS_DIR.glob("*.json")):
        _add(p.stem, p)

    return {"accounts_dir": str(TOKENS_DIR.relative_to(ROOT)), "count": len(accounts), "accounts": accounts}


def prepare_youtube_account(account_id: str, *, public_base: str | None = None) -> dict[str, Any]:
    """
    Đăng ký / kiểm tra account.
    Chưa OAuth → trả auth_url (mở trình duyệt, không cần SSH).
    """
    raw = (account_id or "").strip()
    if not raw:
        raise ValueError("account_id trống")
    aid = normalize_account_id(raw)
    if not aid:
        raise ValueError("account_id không hợp lệ")

    TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    token = resolve_token_path({"youtube_account_id": aid}, account_id=aid)
    rel = str(token.relative_to(ROOT)) if token.is_relative_to(ROOT) else str(token)
    secrets = _secrets_path({})

    st = account_status({"youtube_account_id": aid}, account_id=aid)
    token_exists = bool(st.get("token_exists"))
    authenticated = bool(st.get("authenticated"))
    can_upload = has_upload_scope({"youtube_account_id": aid, "youtube_token_path": rel})

    if token_exists and authenticated and can_upload:
        status = "ready"
    elif not token_exists:
        status = "pending"
    else:
        status = "incomplete"

    oauth_cmd = f"python3 scripts/youtube_auth.py --account-id {aid}"
    auth_url: str | None = None
    setup_hint: str | None = None

    if not secrets.is_file():
        msg = "Thiếu credentials/youtube_client_secret.json trên máy API."
    elif status == "ready":
        msg = st.get("message") or "OK — sẵn sàng upload."
    else:
        try:
            from app.youtube_oauth import start_youtube_oauth

            oauth = start_youtube_oauth(aid, public_base=public_base)
            auth_url = oauth.get("auth_url")
            setup_hint = oauth.get("setup_hint")
            msg = (
                f"Account '{aid}' — mở link đăng nhập Google "
                f"(điện thoại hoặc máy tính, ~2 phút)."
            )
        except Exception as e:
            msg = f"Không tạo được link OAuth: {e}"

    return {
        "account_id": aid,
        "token_path": rel,
        "token_exists": token_exists,
        "client_secrets_exists": secrets.is_file(),
        "authenticated": authenticated,
        "can_upload": can_upload,
        "status": status,
        "oauth_command": oauth_cmd,
        "auth_url": auth_url,
        "setup_hint": setup_hint,
        "message": msg,
        "channels_count": int(st.get("channels_count") or 0),
        "channel_title": st.get("channel_title"),
    }


def account_status(
    settings: dict[str, Any] | None = None,
    *,
    account_id: str | None = None,
    token_path: str | None = None,
) -> dict[str, Any]:
    s = dict(settings or {})
    token = resolve_token_path(s, account_id=account_id, token_path=token_path)
    secrets = _secrets_path(s)
    account = account_id or (token.stem if token.parent == TOKENS_DIR else "default")

    out: dict[str, Any] = {
        "account_id": account,
        "client_secrets_path": str(secrets.relative_to(ROOT)) if secrets.is_relative_to(ROOT) else str(secrets),
        "token_path": str(token.relative_to(ROOT)) if token.is_relative_to(ROOT) else str(token),
        "client_secrets_exists": secrets.is_file(),
        "token_exists": token.is_file(),
        "authenticated": False,
        "channel_title": None,
        "channels_count": 0,
        "channels": [],
    }
    if not secrets.is_file():
        out["message"] = "Thiếu youtube_client_secret.json"
        return out
    if not token.is_file():
        out["message"] = f"Chưa OAuth — chạy: python scripts/youtube_auth.py --account-id {account}"
        return out
    try:
        s["youtube_account_id"] = account
        stoken = _settings_with_token(s, token)
        _load_credentials(stoken)
        out["authenticated"] = True
        if not has_upload_scope(stoken):
            missing = missing_oauth_scopes(stoken)
            out["message"] = reauth_hint(stoken, missing=missing, account_id=account)
        else:
            info = list_channels_info(stoken)
            out["channels"] = info["channels"]
            out["channels_count"] = len(info["channels"])
            if info["channels"]:
                out["channel_title"] = info["channels"][0]["title"]
            out["message"] = info["message"] or "OK — upload được"
    except Exception as e:
        out["message"] = str(e)
    return out


def youtube_status(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    return account_status(settings)


def list_channels(settings: dict[str, Any], *, strict: bool = False) -> list[dict[str, str]]:
    """
    List kênh YouTube. Không raise khi token chỉ có youtube.upload (trả []).
    strict=True → raise như cũ (CLI).
    """
    token = _token_path(settings)
    if not token.is_file():
        raise FileNotFoundError(f"Chưa có token: {token}")
    if not has_upload_scope(settings):
        missing = missing_oauth_scopes(settings)
        raise RuntimeError(reauth_hint(settings, missing=missing))

    service = _service(settings)
    items: list[dict] = []
    last_http: HttpError | None = None
    for kwargs in ({"mine": True}, {"managedByMe": True}):
        try:
            resp = service.channels().list(part="snippet", maxResults=50, **kwargs).execute()
            items.extend(resp.get("items") or [])
        except HttpError as e:
            last_http = e
            if e.resp.status == 403 and strict:
                raise RuntimeError(
                    f"{reauth_hint(settings, missing=missing_oauth_scopes(settings))} "
                    f"(YouTube API: insufficientPermissions)"
                ) from e
            continue
    seen: set[str] = set()
    channels: list[dict[str, str]] = []
    for it in items:
        cid = it.get("id", "")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        sn = it.get("snippet") or {}
        handle = _format_channel_handle(sn.get("customUrl") or "")
        display_name = (sn.get("title") or "").strip()
        channels.append(
            {
                "channel_id": cid,
                "title": handle or display_name,
                "custom_url": handle,
                "thumbnail": (sn.get("thumbnails") or {}).get("default", {}).get("url", ""),
            }
        )
    if not channels and last_http is not None and strict:
        raise RuntimeError(reauth_hint(settings, missing=missing_oauth_scopes(settings))) from last_http
    return channels


def list_channels_info(settings: dict[str, Any]) -> dict[str, Any]:
    """API/bot: luôn trả channels + message (không HTTP 403 vì thiếu force-ssl)."""
    try:
        channels = list_channels(settings, strict=False)
    except FileNotFoundError as e:
        return {"channels": [], "message": str(e), "can_upload": False}
    except RuntimeError as e:
        return {"channels": [], "message": str(e), "can_upload": False}

    msg: str | None = None
    if not channels and has_upload_scope(settings) and not has_list_scope(settings):
        msg = channels_list_hint(settings)
    elif not channels and has_upload_scope(settings):
        msg = channels_list_hint(settings)

    return {
        "channels": channels,
        "message": msg,
        "can_upload": has_upload_scope(settings),
    }


def _load_credentials(settings: dict[str, Any]) -> Credentials:
    token = _token_path(settings)
    secrets = _secrets_path(settings)
    if not secrets.is_file():
        raise FileNotFoundError(f"Thiếu {secrets}")
    if not token.is_file():
        raise FileNotFoundError(f"Chưa có token: {token}")

    scopes = _read_token_scopes(token)
    try:
        creds = Credentials.from_authorized_user_file(str(token), scopes)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token.write_text(creds.to_json(), encoding="utf-8")
    except RefreshError as e:
        raise RuntimeError(reauth_hint(settings, missing=missing_oauth_scopes(settings))) from e
    if not creds.valid:
        raise RuntimeError(f"Token hết hạn — {reauth_hint(settings)}")
    return creds


def _service(settings: dict[str, Any]):
    return build("youtube", "v3", credentials=_load_credentials(settings), cache_discovery=False)


def _validate_shorts_video(path: Path) -> None:
    """Shorts: dọc 9:16, thường ≤60s. Chỉ cảnh báo, không chặn upload."""
    dur = media_duration_seconds(str(path))
    w, h = media_video_size(str(path))
    if dur > SHORTS_MAX_SECONDS:
        print(
            f"[youtube] cảnh báo: {dur:.0f}s > {SHORTS_MAX_SECONDS}s — "
            "có thể không vào tab Shorts"
        )
    elif dur > 0:
        print(f"[youtube] Shorts: {dur:.1f}s")
    if w and h:
        if h <= w:
            print(f"[youtube] cảnh báo: {w}x{h} không dọc — Shorts nên 9:16 (vd 1080x1920)")
        else:
            print(f"[youtube] kích thước: {w}x{h} (dọc OK)")


def _apply_shorts_defaults(meta: dict[str, Any]) -> dict[str, Any]:
    title = meta.get("title") or ""
    if "#shorts" not in title.lower() and len(title) < 88:
        meta["title"] = f"{title} #Shorts"[:100]

    desc = meta.get("description") or ""
    if "#shorts" not in desc.lower():
        meta["description"] = f"{desc}\n\n#Shorts #YouTubeShorts"[:5000]

    tags = list(meta.get("tags") or [])
    for t in ("shorts", "youtubeshorts", "short"):
        if t not in [x.lower() for x in tags]:
            tags.append(t)
    meta["tags"] = tags[:30]
    return meta


def apply_youtube_options(
    base: dict[str, Any],
    *,
    account_id: str | None = None,
    token_path: str | None = None,
    channel_id: str | None = None,
) -> dict[str, Any]:
    s = dict(base)
    if account_id:
        s["youtube_account_id"] = account_id
    if token_path:
        s["youtube_token_path"] = token_path
    if channel_id:
        s["youtube_channel_id"] = channel_id
    tok = resolve_token_path(
        s,
        account_id=account_id or s.get("youtube_account_id"),
        token_path=token_path,
    )
    rel = str(tok.relative_to(ROOT)) if tok.is_relative_to(ROOT) else str(tok)
    s["youtube_token_path"] = rel
    aid = account_id or s.get("youtube_account_id")
    if not (aid or "").strip():
        aid = tok.stem if tok.parent == TOKENS_DIR else "default"
    s["youtube_account_id"] = normalize_account_id(str(aid))
    return s


def _meta_from_settings(
    settings: dict[str, Any],
    topic: str,
    *,
    script: list | None = None,
    brain: Any = None,
) -> dict[str, Any]:
    seo_meta = apply_seo_to_meta(settings, topic, script, brain=brain)
    if seo_meta:
        title = seo_meta["title"]
        desc = seo_meta["description"]
        tags = seo_meta["tags"]
        title_variants = seo_meta.get("title_variants") or []
        hashtags = seo_meta.get("hashtags") or []
    else:
        title = (settings.get("youtube_title") or "").strip() or topic.strip() or "YouTube Short"
        if "#shorts" not in title.lower():
            title = f"{title} #Shorts"

        desc = (settings.get("youtube_description") or "").strip()
        if not desc:
            desc = f"{topic}\n\n#Shorts"
        elif "#shorts" not in desc.lower():
            desc = f"{desc}\n\n#Shorts"

        tags = settings.get("youtube_tags")
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.replace(",", " ").split() if t.strip()]
        elif not isinstance(tags, list):
            tags = []
        else:
            tags = [str(t).strip() for t in tags if str(t).strip()]
        title_variants = []
        hashtags = []

    privacy = (settings.get("youtube_privacy") or "private").strip().lower()
    if privacy not in VALID_PRIVACY:
        privacy = "private"

    category = settings.get("youtube_category_id")
    try:
        category_id = str(int(category)) if category is not None else "22"
    except (TypeError, ValueError):
        category_id = "22"

    channel_id = (settings.get("youtube_channel_id") or "").strip()

    loc = (settings.get("youtube_recording_location") or "").strip()

    return {
        "title": title[:100],
        "description": desc[:5000],
        "tags": tags[:30],
        "privacy": privacy,
        "category_id": category_id,
        "channel_id": channel_id,
        "title_variants": title_variants,
        "hashtags": hashtags,
        "recording_location": loc[:1000] if loc else "",
    }


def upload_video(
    file_path: str,
    settings: dict[str, Any],
    *,
    topic: str = "",
    script: list | None = None,
    brain: Any = None,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    privacy: str | None = None,
    account_id: str | None = None,
    token_path: str | None = None,
    channel_id: str | None = None,
    thumbnail_path: str | None = None,
) -> dict[str, Any]:
    s = apply_youtube_options(
        settings,
        account_id=account_id or settings.get("youtube_account_id"),
        token_path=token_path or settings.get("youtube_token_path"),
        channel_id=channel_id or settings.get("youtube_channel_id"),
    )

    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy video: {file_path}")

    meta = _meta_from_settings(s, topic, script=script, brain=brain)
    meta = _apply_shorts_defaults(meta)
    if title:
        meta["title"] = title[:100]
    if description is not None:
        meta["description"] = description[:5000]
    if tags is not None:
        meta["tags"] = [str(t).strip() for t in tags if str(t).strip()][:30]
    if privacy and privacy.lower() in VALID_PRIVACY:
        meta["privacy"] = privacy.lower()
    if channel_id:
        meta["channel_id"] = channel_id.strip()

    body = {
        "snippet": {
            "title": meta["title"],
            "description": meta["description"],
            "tags": meta["tags"],
            "categoryId": meta["category_id"],
        },
        "status": {
            "privacyStatus": meta["privacy"],
            "selfDeclaredMadeForKids": bool(s.get("youtube_made_for_kids", False)),
        },
    }
    loc_desc = (meta.get("recording_location") or "").strip()
    insert_parts = "snippet,status"
    if loc_desc:
        body["recordingDetails"] = {"locationDescription": loc_desc[:1000]}
        insert_parts = "snippet,status,recordingDetails"
        print(f"[youtube] vị trí quay (metadata): {loc_desc}")

    insert_kwargs: dict[str, Any] = {}
    if meta["channel_id"]:
        insert_kwargs["channelId"] = meta["channel_id"]

    print(f"[youtube] upload Shorts: {meta['title']} ({meta['privacy']})")
    _validate_shorts_video(path)
    media = MediaFileUpload(str(path), chunksize=8 * 1024 * 1024, resumable=True)
    try:
        request = _service(s).videos().insert(
            part=insert_parts, body=body, media_body=media, **insert_kwargs
        )
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"[youtube] {int(status.progress() * 100)}%")
        vid = response.get("id", "")
        url = f"https://www.youtube.com/shorts/{vid}" if vid else ""
        print(f"[youtube] done {url}")

        if vid and loc_desc:
            apply_recording_location(s, vid, loc_desc)

        thumb = (thumbnail_path or s.get("youtube_thumbnail_path") or "").strip()
        if not thumb and s.get("youtube_thumbnail_enabled", True):
            thumb = (
                generate_thumbnail(
                    path,
                    s,
                    topic=topic or meta.get("title", ""),
                    title=meta["title"],
                    brain=brain,
                )
                or ""
            )
        if thumb and vid:
            upload_thumbnail(s, vid, thumb)

        return {
            "youtube_video_id": vid,
            "youtube_url": url,
            "youtube_title": meta["title"],
            "youtube_description": meta["description"],
            "youtube_tags": meta["tags"],
            "youtube_title_variants": meta.get("title_variants") or [],
            "youtube_hashtags": meta.get("hashtags") or [],
            "youtube_privacy": meta["privacy"],
            "youtube_channel_id": meta["channel_id"] or None,
            "youtube_account_id": s.get("youtube_account_id"),
            "youtube_token_path": s.get("youtube_token_path"),
            "thumbnail_path": thumb or None,
            "youtube_recording_location": loc_desc or None,
        }
    except HttpError as e:
        raise RuntimeError(f"YouTube API: {e}") from e


def apply_recording_location(
    settings: dict[str, Any],
    video_id: str,
    location: str | None = None,
) -> bool:
    """Ghi recordingDetails.locationDescription (videos.update)."""
    loc = (location or settings.get("youtube_recording_location") or "").strip()
    if not video_id or not loc:
        return False
    body = {
        "id": video_id,
        "recordingDetails": {"locationDescription": loc[:1000]},
    }
    try:
        _service(settings).videos().update(part="recordingDetails", body=body).execute()
        print(f"[youtube] đã cập nhật vị trí quay: {loc}")
        return True
    except HttpError as e:
        print(f"[youtube] cập nhật vị trí quay thất bại: {e}")
        return False


def maybe_upload(
    path: str | None,
    settings: dict[str, Any],
    topic: str,
    *,
    script: list | None = None,
    brain: Any = None,
) -> dict[str, Any]:
    if not settings.get("youtube_upload"):
        return {}
    if not path:
        return {}
    thumb = (settings.get("youtube_thumbnail_path") or "").strip()
    return upload_video(
        path,
        settings,
        topic=topic,
        script=script,
        brain=brain,
        thumbnail_path=thumb or None,
    )
