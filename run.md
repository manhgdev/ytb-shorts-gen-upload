# Chạy nhanh

## 1. API (bắt buộc trước khi dùng bot)

```bash
cd /path/to/ytb-shorts-gen-upload
source venv/bin/activate
uvicorn api_server:app --host 0.0.0.0 --port 8000
```

Kiểm tra: http://127.0.0.1:8000/health → `{"ok":true}`

## 2. Google Cloud — Redirect URI (một lần)

Mở: http://127.0.0.1:8000/v1/youtube/oauth/setup  
Hoặc xem `redirect_uri` trong JSON.

Thêm **Authorized redirect URI** (đúng y chang):

```text
http://127.0.0.1:8000/v1/youtube/oauth/callback
```

(Nếu bot dùng IP khác → sửa `youtube_oauth_public_base` trong `user_settings.json` + `config.json` bot.)

## 3. Liên kết YouTube qua Telegram (không SSH)

1. Bot: `/youtube` → **📺 Cài đặt YouTube** → **👤 Tài khoản**
2. **➕ Thêm / liên kết account** → gửi tên (vd `LylyTaks1199`)
3. Bấm **🔗 Đăng nhập Google** → Allow
4. **🔄 Làm mới** → chọn account ✅ → **📡 Kênh** (hoặc nhập `UC…`)

## 4. Bot config

`mxh_checker_bot/config.json`:

```json
"YTB_SHORTS": {
  "apiUrl": "http://127.0.0.1:8000",
  "apiSecret": ""
}
```

Reload: `/cmd load youtube` · `/cmd load uploadytb`

## CLI (tuỳ chọn, không bắt buộc)

```bash
python3 scripts/youtube_auth.py --account-id LylyTaks1199
```
