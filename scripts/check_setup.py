#!/usr/bin/env python3
"""Kiểm tra setup OAuth + API — chạy: python3 scripts/check_setup.py"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.youtube_oauth import oauth_public_base, start_youtube_oauth


def main() -> int:
    base = oauth_public_base()
    redirect = f"{base}/v1/youtube/oauth/callback"
    print("=== YTB Shorts setup ===\n")
    print(f"public_base:   {base}")
    print(f"redirect_uri:  {redirect}\n")

    secret = ROOT / "credentials" / "youtube_client_secret.json"
    print(f"client_secret: {'OK' if secret.is_file() else 'MISSING'}\n")

    try:
        req = urllib.request.urlopen(f"{base}/health", timeout=3)
        print(f"API /health:   {req.read().decode()[:80]}")
    except Exception as e:
        print(f"API /health:   FAIL — {e}")
        print("→ Chạy: uvicorn api_server:app --host 0.0.0.0 --port 8000\n")

    try:
        oauth = start_youtube_oauth("_setup_test", public_base=base)
        print(f"OAuth URL:     OK (tạo link được)")
        print(f"  (test) {oauth['auth_url'][:70]}…")
    except Exception as e:
        print(f"OAuth URL:     FAIL — {e}\n")

    print("\nGoogle Cloud → thêm Redirect URI:")
    print(f"  {redirect}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
