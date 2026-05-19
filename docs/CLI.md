# CLI — tạo video → metadata → upload YouTube

## Workflow chính

```bash
# 1. OAuth (một lần)
python3 scripts/youtube_auth.py --account-id @LylyTaks1199

# 2. Tạo video — sinh title lúc render, lưu .meta.json + catalog
python main.py create --topic "Why is the sky blue?"

# 3. Xem danh sách (chưa / đã upload)
python main.py list
python main.py list --pending
python main.py list --uploaded

# 4. Chi tiết 1 video
python main.py show final_short.mp4

# 5. Upload lên YouTube (dùng title đã lưu)
python main.py upload final_short.mp4 --youtube-account LylyTaks1199 --youtube-privacy private

# Hoặc tạo + upload một lệnh
python main.py create --topic "Your topic" --shorts --youtube-account LylyTaks1199
```

**Vị trí quay trên YouTube:** `user_settings.json` → `youtube_recording_location` (mặc định `"United States"`) gửi metadata `recordingDetails` khi upload — không đổi địa điểm mạng hay máy chủ. Đặt `""` để không gửi.

## Lệnh

| Lệnh | Mô tả |
|------|--------|
| `create` | Topic → script → **title SEO** → render MP4 (+ `--reshuffle` chọn lại clip/avatar/xfade) |
| `list` | Catalog: ○ chưa upload / ✓ đã upload |
| `show <id\|file>` | Title, mô tả, tags, URL YouTube |
| `upload <id\|file>` | Đăng Shorts (metadata đã lưu) |
| `edit <id>` | Sửa `--title`, `--description`, `--tags` |
| `delete <id>` | Xóa MP4 + `.meta.json` |
| `import <file>` | MP4 có sẵn → sinh metadata |
| `thumbnail` | Tạo / cập nhật `*_thumb.jpg` |
| `set-thumbnail` | Gắn `*_thumb.jpg` lên video đã upload (YouTube API) |
| `hook-intro` | Chèn slide ảnh bìa im lặng vào **đầu** MP4 Shorts (ghi đè file) |
| `check-youtube` | Kiểm tra OAuth |

## File lưu metadata

Mỗi video có sidecar:

```text
assets/final/final_short_vi.mp4
assets/final/final_short_vi.meta.json   ← title, topic, tags, youtube status
assets/final/.videos_catalog.json       ← index toàn bộ
```

**Shorts — hook ngay frame đầu (feed):** sau khi có `*_thumb.jpg`, pipeline tự chèn ~**0,85 giây** slide im lặng vào đầu MP4 (cùng kích thước 1080×1920). Feed Shorts phát từ đầu nên sẽ thấy layout giống ảnh bìa.

- `shorts_hook_intro_seconds` trong `user_settings.json` (mặc định `0.85`; đặt `0` để tắt).
- Video gần 60s sẽ tự rút ngắn intro để không vượt giới hạn Shorts.
- Chỉ áp dụng khi `video_mode` là `short` **hoặc** file đã là dọc 1080×1920.

```bash
python main.py hook-intro final_short.mp4          # chèn lại (có sẵn thumb hoặc tự sinh)
python main.py hook-intro final_short.mp4 --seconds 1.0
python main.py hook-intro final_short.mp4 --force  # bỏ qua chặn “đã intro” trong .meta.json (sẽ thêm thêm một đoạn)
```

Lần 2 trên **cùng file** (đã có `shorts_hook_intro_applied_sec` trong `.meta.json`): mặc định **không** chèn nữa — dùng `--force` hoặc xóa key đó trong meta. Pipeline `create` luôn chèn intro cho bản render mới (không dính meta cũ).

## Phân cảnh / clip Pexels / avatar

Mỗi lần `create`, mặc định đã **ngẫu nhiên** (clip trong pool Pexels, cảnh đặt avatar giữa video, hiệu `xfade` khi ghép). Để **chọn lại** rõ ràng (và tải lại clip từ Pexels):

```bash
python main.py create --reshuffle --topic "Chủ đề"
python main.py create --reshuffle --seed 20260219 --topic "..."   # lặp lại được cùng bố cục ngẫu nhiên đó
```

`user_settings.json` (tùy chọn):

```json
"render_seed": null,
"stock_force_refresh": false,
"pexels_per_page": 12,
"avatar_scene_numbers": [3, 7]
```

- `avatar_scene_numbers`: cảnh **1-based** dùng avatar (không gồm cảnh 1 và cảnh cuối); rỗng → random như cũ.
- `stock_force_refresh`: `true` → mỗi lần create xóa `scene_*_{a,b}.mp4` rồi tải lại (nặng API).
- `pexels_per_page`: 3–30, mặc định 5 — pool lớn hơn → clip khác nhiều hơn.
- `render_seed`: số nguyên → cùng script + cùng seed → cùng lựa chọn ngẫu nhiên (clip/avatar/xfade); `null` → seed khác mỗi lần.

---

## Ảnh bìa (thumbnail)

Sau render: mặc định lấy **`assets/avatar/avatars.png`** (hoặc `avatar_image_path` / file `.png` cùng tên với `avatar_video_path`) làm nền ảnh bìa, rồi vẽ chữ hook → `*_thumb.jpg`. Đặt `"youtube_thumbnail_source": "video"` để cắt frame từ MP4 như trước.

```bash
python main.py thumbnail final_short.mp4   # chỉ tạo ảnh
python main.py upload final_short.mp4      # tạo thumb nếu chưa có + upload
```

`user_settings.json`:

```json
"youtube_thumbnail_enabled": true,
"youtube_thumbnail_mode": "auto",
"youtube_thumbnail_at_sec": null,
"youtube_thumbnail_text": "",
"youtube_thumbnail_accent": "WATCH",
"youtube_thumbnail_ai_text": true,
"shorts_hook_intro_seconds": 0.85
```

- **Ảnh bìa**: cắt frame (FFmpeg) + **chữ hook lớn** (viền đen, nút WATCH).
- `youtube_thumbnail_ai_text`: Gemini sinh 2–3 dòng ngắn từ topic/title; tắt `false` → tách chữ từ title đã lưu.
- `youtube_thumbnail_text`: chữ cố định (ưu tiên cao nhất). CLI: `--thumb-text "LINE ONE"`.
- `youtube_thumbnail_accent`: từ nhỏ dưới cùng (mặc định `WATCH`).

`mode`: `auto` | `hook` (~15% đầu) | `middle` | `youtube_thumbnail_at_sec` (số giây).

**API không gắn được ảnh (403)?** Kênh phải bật **Custom thumbnails** trong YouTube Studio → xem [YOUTUBE_SETUP.md](YOUTUBE_SETUP.md). Sau khi bật:

```bash
python main.py set-thumbnail final_short.mp4
```

---


Khi **render xong**, terminal in:

```text
[title] Vì sao bầu trời lại màu xanh? #Shorts
  variant 1: ...
Trạng thái: CHƯA UPLOAD — chạy: python main.py upload <id>
```

## MP4 có sẵn (vd final_short.mp4)

```bash
python main.py import assets/final/final_short.mp4 --topic "Actual video topic"
python main.py show final_short.mp4
python main.py upload final_short.mp4 --youtube-account LylyTaks1199
```

## Sửa title trước khi upload

```bash
python main.py edit abc123 --title "Tiêu đề mới #Shorts"
python main.py upload abc123 --youtube-account LylyTaks1199
```

## Tùy chọn `create`

```bash
python main.py create \
  --topic "..." \
  --video-mode short \
  --avatar-mode off \
  --output my_short.mp4 \
  --shorts \
  --youtube-account LylyTaks1199 \
  --youtube-privacy unlisted
```

OAuth: [YOUTUBE_SETUP.md](./YOUTUBE_SETUP.md)
