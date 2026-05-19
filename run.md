# Chạy nhanh

## API (bot)

```bash
source venv/bin/activate
uvicorn api_server:app --host 0.0.0.0 --port 8000
```

## YouTube OAuth (một lần / account, trên máy API)

```bash
python3 scripts/youtube_auth.py --account-id @LylyTaks1199
```

Token: `credentials/youtube_tokens/<account_id>.json` — API đọc file, **không cần restart uvicorn** sau OAuth.

Kiểm tra: `curl -s http://127.0.0.1:8000/v1/youtube/accounts/LylyTaks1199/channels`
