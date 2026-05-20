# Lịch tự động — 3 Shorts/ngày (giờ Mỹ)

Tạo + upload YouTube theo `user_settings.json` hiện có.

## Cài bằng PM2 (khuyến nghị — thoát SSH vẫn chạy)

```bash
cd ~/ytb-shorts-gen-upload
npm install -g pm2          # một lần
cp schedule.config.example.json schedule.config.json
chmod +x scripts/install_pm2.sh
./scripts/install_pm2.sh
pm2 startup                 # làm theo lệnh sudo → tự bật sau reboot
```

Gồm **4 process** PM2:

| Tên | Việc |
|-----|------|
| `ytb-shorts-api` | API uvicorn (bot) — luôn bật |
| `ytb-schedule-1200` | 12:00 ET — tạo + upload 1 video |
| `ytb-schedule-1700` | 17:00 ET |
| `ytb-schedule-2100` | 21:00 ET |

```bash
pm2 status
pm2 logs ytb-schedule-1200
./scripts/scheduled_create.sh test-run   # thử ngay, không đợi giờ
```

Đổi giờ: sửa `schedule.config.json` → `./venv/bin/python scripts/build_pm2_config.py` → `pm2 reload pm2.config.json`

**Không** dùng thêm `install_schedule.sh` (cron hệ thống) nếu đã dùng PM2 — tránh chạy trùng 2 lần.

---

## Giờ đăng (mặc định — `America/New_York`)

Dựa trên khung giờ người xem US thường cao (Shorts / mobile):

| Slot | Giờ ET | Lý do |
|------|--------|--------|
| 1 | **12:00** | Trưa — East + Central (giờ nghỉ trưa) |
| 2 | **17:00** | 5 PM — sau giờ làm / tan học |
| 3 | **21:00** | 9 PM — prime time tối |

Server Linux (UTC) vẫn chạy đúng nhờ `TZ=America/New_York` trong cron.

Đổi giờ: sửa `schedule.config.json` → `slots` → chạy lại `scripts/install_schedule.sh`.

## Cài cron hệ thống (tuỳ chọn, thay PM2)

```bash
./scripts/install_schedule.sh
```

## Chạy thử 1 video (không đợi giờ)

```bash
./scripts/scheduled_create.sh test-run
tail -f logs/schedule-$(date +%Y%m%d).log
```

## File

| File | Vai trò |
|------|---------|
| `schedule.config.json` | Giờ, account, privacy, prefix tên file |
| `scripts/scheduled_create.sh` | 1 lần create + `--shorts` |
| `scripts/install_schedule.sh` | Ghi crontab |
| `logs/schedule-YYYYMMDD.log` | Log từng ngày |
| `logs/.schedule_create.lock` | Không chạy 2 job cùng lúc |

Mỗi lần chạy tạo file riêng: `auto_YYYYMMDD_HHMMSS.mp4` (không ghi đè `final_short.mp4`).

## Tắt lịch

```bash
crontab -l | grep -v ytb-shorts | crontab -
```

Hoặc `"enabled": false` trong `schedule.config.json`.

## Lưu ý

- Mỗi video ~5–15 phút (Gemini + render). Lock tránh chồng lịch; nếu slot trước chưa xong, slot sau **skip**.
- Cần **OAuth YouTube** + đủ quota Gemini/Pexels cho 3 video/ngày.
- `language: en` trong config — topic tự sinh từ `user_settings.json`.
- PM2 API **không bắt buộc** cho cron CLI; bot và cron có thể chạy song song (khác file output).

## Crontab mẫu (sau install)

```cron
0 12 * * * TZ=America/New_York /path/scripts/scheduled_create.sh "US lunch peak (12:00 ET)" >> .../logs/cron-schedule.log 2>&1
0 17 * * * TZ=America/New_York /path/scripts/scheduled_create.sh "US after-work (5:00 PM ET)" >> ...
0 21 * * * TZ=America/New_York /path/scripts/scheduled_create.sh "US prime time (9:00 PM ET)" >> ...
```
