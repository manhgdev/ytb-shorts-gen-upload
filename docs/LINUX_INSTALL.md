# Cài trên Linux — 1 PM2, auto đăng kênh `LylyTaks1199`

## Chuẩn bị (một lần)

1. Copy repo lên VPS (có sẵn `user_settings.json`, keys Gemini/Pexels).
2. File OAuth Google: `credentials/youtube_client_secret.json`
3. Token kênh (đã đăng nhập Google):

```text
credentials/youtube_tokens/LylyTaks1199.json
```

Chưa có token:

```bash
./venv/bin/python scripts/youtube_auth.py --account-id @LylyTaks1199
```

## Cài một lệnh

```bash
cd ~/ytb-shorts-gen-upload
chmod +x scripts/install_linux.sh
./scripts/install_linux.sh
pm2 startup    # làm theo hướng dẫn sudo → tự chạy sau reboot
```

`pm2 status` chỉ còn **1 dòng**:

```text
ytb-shorts   …   online
```

## Hoạt động

- Đọc `schedule.config.json` → `youtube_account_id`: **LylyTaks1199**
- Mỗi ngày **3 lần** (giờ Mỹ): 12:00, 17:00, 21:00 ET
- Mỗi lần: `main.py create --shorts` → upload **public** (đổi trong config)

## Lệnh hữu ích

```bash
pm2 logs ytb-shorts
pm2 restart ytb-shorts
./scripts/scheduled_create.sh test-run    # 1 video ngay
tail -f logs/schedule-$(date +%Y%m%d).log
```

## API bot Telegram (tuỳ chọn, tách riêng)

Auto đăng **không cần** API. Nếu cần bot:

```bash
./venv/bin/python -m uvicorn api_server:app --host 0.0.0.0 --port 8000
```

Hoặc chạy tay khi cần — **không** gộp vào PM2 `ytb-shorts`.
