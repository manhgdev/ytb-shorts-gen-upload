# ytb-shorts-gen-upload

Tạo YouTube Shorts: Gemini + edge-tts + Pexels + FFmpeg (Linux CLI).

## Cấu trúc

```text
main.py                 # CLI
app/
  config.py             # model, video, voice
  settings.py           # user_settings.json
  pipeline.py           # run(settings)
  brain.py              # Gemini
  audio.py              # TTS
  stock.py              # Pexels
  composer.py           # FFmpeg
  utils.py              # paths, ffmpeg, duration
assets/avatar/
```

## Cài đặt

```bash
sudo apt update && sudo apt install -y python3 python3-venv ffmpeg
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp user_settings.example.json user_settings.json
# Điền gemini_api_key, pexels_api_key trong user_settings.json
```

## Chạy CLI

```bash
python main.py create --topic "Why is the sky blue?"
python main.py list
python main.py upload <id> --youtube-account TEN_KENH
```

Chi tiết: **`docs/CLI.md`**

## Chạy API (bot Telegram)

```bash
uvicorn api_server:app --host 0.0.0.0 --port 8000
```

Tài liệu bot: `docs/BOT_TELEGRAM.md`

**Upload YouTube:** Google Cloud làm trên **điện thoại**, chỉ cần file `credentials/youtube_client_secret.json` trên máy chạy repo → `docs/YOUTUBE_SETUP.md`

Dùng từ code / API sau này:

```python
from app import run, load_settings
import asyncio
asyncio.run(run(load_settings()))
```

## `user_settings.json`

| Field | Mô tả |
|-------|--------|
| `gemini_api_key` | string hoặc `["k1","k2"]` |
| `pexels_api_key` | string hoặc mảng |
| `gemini_model` | `"auto"` hoặc tên model |
| `use_manual_topic` / `manual_topic` | Topic cố định |
| `topic_prompt` | Prompt sinh topic (khi auto topic) |
| `script_extra_instructions` | Thêm vào prompt kịch bản |
| `video_mode` | `short` \| `long` |
| `avatar_mode` | `off` \| `default` \| `custom` |
| `avatar_*_path` | Đường dẫn avatar (custom) |
| `output_dir` | Thư mục file MP4 |
| `api_secret` | (chỉ server) Bảo vệ API — header `X-API-Key` |

Key Gemini/Pexels: `user_settings.json` (CLI) hoặc body `POST /v1/generate` (bot).
