#!/usr/bin/env python3
"""OAuth YouTube — mỗi kênh/tài khoản một account-id."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from google_auth_oauthlib.flow import InstalledAppFlow

from app.settings import load_settings
from app.youtube import SCOPES, TOKENS_DIR, _secrets_path, normalize_account_id

CREDENTIALS_DIR = ROOT / "credentials"
TARGET_SECRET = CREDENTIALS_DIR / "youtube_client_secret.json"

SETUP_URLS = (
    ("1. Bật YouTube Data API v3", "https://console.cloud.google.com/apis/library/youtube.googleapis.com"),
    ("2. OAuth consent screen", "https://console.cloud.google.com/apis/credentials/consent"),
    ("3. Tạo OAuth Client → Desktop app → Download JSON", "https://console.cloud.google.com/apis/credentials"),
)


def _print_link(label: str, url: str) -> None:
    """In nhãn + URL đầy đủ dòng dưới (terminal Cmd+click)."""
    print(label)
    print(url)
    print()


def _print_setup_urls(target: Path) -> None:
    print(f"\nThiếu file: {target}\n")
    print("Làm trên trình duyệt — mỗi bước: đọc dòng chữ, URL đầy đủ ở dòng ngay dưới:\n")
    for label, url in SETUP_URLS:
        _print_link(label, url)
    print(f"Sau khi tải JSON, đặt tên và copy vào:\n{target}\n")
    print("Hoặc để file tên client_secret_....json trong credentials/ rồi chạy lại script (tự copy).\n")


def _resolve_secrets(explicit: str | None) -> Path:
    if explicit and str(explicit).strip():
        return Path(explicit).expanduser().resolve()
    settings = load_settings()
    return _secrets_path(settings)


def _ensure_secret_file(secrets: Path) -> Path | None:
    if secrets.is_file():
        return secrets
    if secrets == TARGET_SECRET or secrets.name == "youtube_client_secret.json":
        for candidate in sorted(CREDENTIALS_DIR.glob("client_secret*.json")):
            if candidate.is_file():
                CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
                shutil.copy2(candidate, TARGET_SECRET)
                print(f"Đã copy: {candidate.name} → {TARGET_SECRET.relative_to(ROOT)}")
                return TARGET_SECRET
    return None


def main() -> int:
    p = argparse.ArgumentParser(description="YouTube OAuth")
    p.add_argument("--account-id", default="default", help="ID lưu token (vd: @LylyTaks1199 — @ tuỳ chọn)")
    p.add_argument("--secrets", default="", help="Đường dẫn client JSON (mặc định credentials/youtube_client_secret.json)")
    p.add_argument(
        "--port",
        type=int,
        default=0,
        help="Cổng local OAuth (0=random). VPS: 8765 + ssh -L 8765:127.0.0.1:8765",
    )
    p.add_argument(
        "--no-browser",
        action="store_true",
        help="Không tự mở trình duyệt — chỉ in URL để bạn click",
    )
    args = p.parse_args()

    secrets = _resolve_secrets(args.secrets or None)
    secrets = _ensure_secret_file(secrets) or secrets
    if not secrets.is_file():
        _print_setup_urls(secrets if secrets != TARGET_SECRET else TARGET_SECRET)
        return 1

    TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    aid = normalize_account_id(args.account_id)
    if aid == "default":
        dest = ROOT / "credentials" / "youtube_token.json"
    else:
        dest = TOKENS_DIR / f"{aid}.json"

    flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
    print("\n════════════════════════════════════════")
    print("Đăng nhập Google (OAuth)")
    print("════════════════════════════════════════\n")
    if args.no_browser:
        print("Mở link OAuth — URL đầy đủ ở dòng dưới (Cmd+click hoặc copy):\n")
    else:
        print("Trình duyệt sẽ tự mở. Nếu không mở, dùng link — URL đầy đủ ở dòng dưới:\n")
    creds = flow.run_local_server(
        port=args.port,
        access_type="offline",
        prompt="consent",
        open_browser=not args.no_browser,
        authorization_prompt_message="{url}",
        success_message="\nĐăng nhập Google xong.\n",
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(creds.to_json(), encoding="utf-8")
    print(f"\naccount_id: {aid}")
    print(f"token_path: {dest.relative_to(ROOT)}")
    print("Token đã lưu — chưa cần chạy API.")
    print("CLI: youtube_upload + youtube_account_id trong user_settings.json → python main.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
