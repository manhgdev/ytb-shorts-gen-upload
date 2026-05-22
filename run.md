# Chạy nhanh

## 1. API (bắt buộc trước khi dùng bot)

### Chạy tay (dev)

```bash
cd /path/to/ytb-shorts-gen-upload
source venv/bin/activate
pip install -r requirements.txt   # lần đầu
uvicorn api_server:app --host 0.0.0.0 --port 8000
```

### PM2 trên Linux (VPS / server)

**Cài lần đầu (Ubuntu/Debian):**

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg
sudo npm install -g pm2   # hoặc: curl -fsSL https://get.pnpm.io/install.sh …
```

**Trong thư mục repo** (vd `~/ytb-shorts-gen-upload` — path tuỳ máy):

```bash
cd ~/ytb-shorts-gen-upload
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
mkdir -p logs
chmod +x scripts/start_api.sh

pm2 delete ytb-shorts-api 2>/dev/null || true
pm2 start pm2.config.json    # phải chạy từ đúng thư mục repo (cwd .)
pm2 save
pm2 startup                  # in lệnh sudo, chạy theo hướng dẫn — tự bật sau reboot
pm2 logs ytb-shorts-api
```

`pm2.config.json` dùng `scripts/start_api.sh` — **không** hardcode path Mac; clone repo ở đâu cũng được nếu `pm2 start` trong thư mục đó.

Mở firewall port **8000** nếu bot gọi từ máy khác: `sudo ufw allow 8000/tcp`

Bot `apiUrl`: `http://IP_VPS:8000` (không phải 127.0.0.1 nếu bot không cùng máy).

Kiểm tra: http://127.0.0.1:8000/health → `{"ok":true}`

**Lưu ý:** `pm2 restart` cắt job generate đang chạy (job lưu RAM). OAuth/token YouTube trên disk không mất.

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

## Linux — PM2 **1 app** auto đăng `LylyTaks1199` (3 video/ngày)

```bash
chmod +x scripts/install_linux.sh
./scripts/install_linux.sh
pm2 startup && pm2 save
```

Chỉ `ytb-shorts` trong `pm2 status`. Chi tiết: [docs/LINUX_INSTALL.md](./docs/LINUX_INSTALL.md)

## CLI (tuỳ chọn, không bắt buộc)

```bash
python3 scripts/youtube_auth.py --account-id LylyTaks1199
```
