"""OAuth YouTube qua trình duyệt — không cần SSH (link cho Telegram / điện thoại)."""
from __future__ import annotations

import secrets
import time
from pathlib import Path
from typing import Any

from google_auth_oauthlib.flow import Flow

from app.settings import ROOT
from app.youtube import SCOPES, TOKENS_DIR, _secrets_path, normalize_account_id

# state → {account_id, redirect_uri, created}
_pending: dict[str, dict[str, Any]] = {}
_PENDING_TTL_SEC = 30 * 60


def oauth_public_base(explicit: str | None = None) -> str:
    if explicit and str(explicit).strip():
        return str(explicit).strip().rstrip("/")
    from app.settings import load_settings

    s = load_settings()
    raw = str(s.get("youtube_oauth_public_base") or "").strip()
    if raw:
        return raw.rstrip("/")
    return "http://127.0.0.1:8000"


def _cleanup_pending() -> None:
    now = time.time()
    dead = [k for k, v in _pending.items() if now - float(v.get("created", 0)) > _PENDING_TTL_SEC]
    for k in dead:
        _pending.pop(k, None)


def _token_dest(account_id: str) -> Path:
    aid = normalize_account_id(account_id)
    if aid == "default":
        return ROOT / "credentials" / "youtube_token.json"
    return TOKENS_DIR / f"{aid}.json"


def start_youtube_oauth(account_id: str, *, public_base: str | None = None) -> dict[str, Any]:
    """
    Tạo link Google OAuth. User/admin mở link trên điện thoại hoặc máy tính.
    Cần redirect URI trong Google Cloud:
      {public_base}/v1/youtube/oauth/callback
    """
    _cleanup_pending()
    aid = normalize_account_id(account_id)
    if not aid:
        raise ValueError("account_id không hợp lệ")

    secret_file = _secrets_path({})
    if not secret_file.is_file():
        raise FileNotFoundError("Thiếu credentials/youtube_client_secret.json")

    base = oauth_public_base(public_base)
    redirect_uri = f"{base}/v1/youtube/oauth/callback"

    flow = Flow.from_client_secrets_file(
        str(secret_file),
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )
    state = secrets.token_urlsafe(24)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )

    _pending[state] = {
        "account_id": aid,
        "redirect_uri": redirect_uri,
        "created": time.time(),
    }

    return {
        "account_id": aid,
        "auth_url": auth_url,
        "state": state,
        "redirect_uri": redirect_uri,
        "expires_in_sec": _PENDING_TTL_SEC,
        "setup_hint": (
            f"Trên Google Cloud → OAuth client → thêm Redirect URI:\n{redirect_uri}"
        ),
    }


def complete_youtube_oauth(*, state: str, code: str) -> dict[str, Any]:
    _cleanup_pending()
    meta = _pending.pop(state, None)
    if not meta:
        raise ValueError("Phiên OAuth hết hạn hoặc không hợp lệ — tạo link mới từ bot.")

    aid = meta["account_id"]
    redirect_uri = meta["redirect_uri"]
    secret_file = _secrets_path({})

    flow = Flow.from_client_secrets_file(
        str(secret_file),
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )
    flow.fetch_token(code=code)
    creds = flow.credentials
    if not creds or not creds.valid:
        raise RuntimeError("OAuth xong nhưng token không hợp lệ.")

    dest = _token_dest(aid)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(creds.to_json(), encoding="utf-8")

    rel = str(dest.relative_to(ROOT)) if dest.is_relative_to(ROOT) else str(dest)
    return {
        "account_id": aid,
        "token_path": rel,
        "ok": True,
    }
