# user_settings.json — cấu trúc theo nhóm

File có thể **gom theo section** (khuyên dùng) hoặc **phẳng một tầng** (cũ) — code tự gộp lại.

Chi tiết từng key: `python main.py` không có lệnh riêng; xem `app/settings.py` → `default_settings()`.

---

## `api` — khóa & bảo mật

| Key | Mô tả |
|-----|--------|
| `api_secret` | Mật khẩu API HTTP (uvicorn) |
| `gemini_api_key` | Gemini (string hoặc mảng) |
| `pexels_api_key` | Pexels stock |

---

## `gemini` — model AI

| Key | Mô tả |
|-----|--------|
| `gemini_model` | `auto` hoặc tên model |
| `gemini_models` | Model dự phòng |
| `gemini_retry_delay_seconds` | Chờ khi rate limit |
| `gemini_max_retries` | Số lần thử |

---

## `content` — chủ đề & kịch bản

| Key | Mô tả |
|-----|--------|
| `language` | Mặc định **`en`**; `vi` nếu cần tiếng Việt |
| `topic_prompt` | Prompt sinh topic |
| `use_manual_topic` | `true` = dùng `manual_topic` |
| `manual_topic` | Chủ đề cố định |
| `script_extra_instructions` | Ghi chú cho Gemini script |

---

## `video` — định dạng & cảnh

| Key | Mô tả |
|-----|--------|
| `video_mode` | `short` (≤60s) |
| `min_scenes` / `max_scenes` / `words_per_scene` | `null` = mặc định |

---

## `tts` — giọng đọc

| Key | Mô tả |
|-----|--------|
| `voice` | `null` = theo ngôn ngữ |
| `speech_rate` | Tốc độ đọc |

---

## `output` — file xuất

| Key | Mô tả |
|-----|--------|
| `output_dir` | Thư mục MP4 |
| `output_filename` | Tên file; `null` = tự đặt |

---

## `avatar` — người dẫn

| Key | Mô tả |
|-----|--------|
| `avatar_mode` | `default` \| `custom` \| `off` |
| `avatar_video_path` / `avatar_image_path` | Khi `custom` |
| `avatar_scenes` | Số cảnh có avatar |
| `avatar_scene_numbers` | Cảnh cố định (1-based), `[]` = random |

---

## `render` — clip Pexels & random

| Key | Mô tả |
|-----|--------|
| `render_seed` | `null` = khác mỗi lần; số = lặp lại |
| `stock_force_refresh` | Tải lại clip |
| `pexels_per_page` | Pool clip (3–30) |

---

## `pipeline` — sau render

| Key | Mô tả |
|-----|--------|
| `clean_cache` | Xóa `assets/temp` |

---

## `youtube_account` — OAuth & đăng

| Key | Mô tả |
|-----|--------|
| `youtube_upload` | Đăng sau `create` |
| `youtube_account_id` | Token `credentials/youtube_tokens/<id>.json` |
| `youtube_channel_id` | Kênh cụ thể (tùy chọn) |
| `youtube_client_secrets_path` / `youtube_token_path` | OAuth |
| `youtube_privacy` | `private` \| `unlisted` \| `public` |
| `youtube_category_id` | `22` = People & Blogs |
| `youtube_made_for_kids` | COPPA |
| `youtube_recording_location` | Metadata **vị trí quay** (`recordingDetails`); `""` = không gửi. **Không** phải “target audience US”. Studio: Chi tiết video → có thể thấy mục địa điểm / filming location (nếu API ghi được). Sửa video đã đăng: `python main.py set-location <ref>` |

---

## `youtube_seo` — title / mô tả

| Key | Mô tả |
|-----|--------|
| `youtube_title` / `description` / `tags` | Rỗng = SEO lúc render |
| `youtube_auto_seo` | Gemini SEO |
| `youtube_random_title` | Chọn ngẫu title variants |
| `youtube_seo_extra_instructions` | Gợi ý thêm |

---

## `youtube_thumbnail` — ảnh bìa file JPG

| Key | Mô tả |
|-----|--------|
| `youtube_thumbnail_enabled` | Tạo `*_thumb.jpg` |
| `youtube_thumbnail_source` | `avatar_image` \| `video` |
| `youtube_thumbnail_mode` | `auto` \| `hook` \| `middle` |
| `youtube_thumbnail_at_sec` | Giây cắt (khi `video`) |
| `youtube_thumbnail_text` | Chữ cố định |
| `youtube_thumbnail_accent` | Nút `WATCH` |
| `youtube_thumbnail_text_zone_top` | Vị trí chữ (`0.52` = giữa-dưới) |
| `youtube_thumbnail_text_align` | `center` \| `top` \| `bottom` |
| `youtube_thumbnail_text_top_padding` | Khi `align: top` |
| `youtube_thumbnail_ai_text` | Gemini sinh chữ |

Shorts: JPG **không** gắn bìa Studio qua API; xem [YOUTUBE_SETUP.md](YOUTUBE_SETUP.md).

---

## `shorts_feed` — intro đầu MP4

| Key | Mô tả |
|-----|--------|
| `shorts_hook_intro_seconds` | Giây ghép ảnh bìa (`*_thumb.jpg`) im lặng vào **đầu** MP4. **`0` = không chèn**; ví dụ `0.85` ≈ 4/5 giây rồi mới vào nội dung |

Chèn lại trên file đã có intro: `python main.py hook-intro <file> --force` (không cần key trong settings).
