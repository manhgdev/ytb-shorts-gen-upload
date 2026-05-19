# Telegram Bot (Node.js) ↔ YT Shorts Gen API

Tài liệu API + **triển khai thực tế** trong repo `mxh_checker_bot` (Bun/Node, ESM).

**Base URL:** `config.json` → `YTB_SHORTS.apiUrl` (vd `http://127.0.0.1:8000`)  
**Auth:** `YTB_SHORTS.apiSecret` → header `X-API-Key` (trùng `api_secret` trên server Python)  
**OpenAPI:** `{BASE_URL}/docs`

Module bot: `server/apis/youtube/` · Lệnh: `scripts/cmds/youtube.js`, `scripts/cmds/uploadYtb.js`

Chạy API:

```bash
uvicorn api_server:app --host 0.0.0.0 --port 8000
```

---

## 1. Bảng tổng quan (quan trọng)

| Tính năng | HTTP API | Ghi chú |
|-----------|----------|---------|
| Health / defaults | ✅ | `GET /health`, `GET /v1/defaults` |
| Tạo video async (generate) | ✅ | `POST /v1/generate` + poll job |
| Poll job | ✅ | `GET /v1/jobs/{id}` — job **RAM**, restart API mất job |
| Avatar upload (multipart) | ✅ | `POST /v1/avatar/upload` |
| Avatar mặc định server | ✅ | `GET /v1/avatar/defaults` |
| List / xóa file MP4 | ✅ | `GET /v1/videos`, `DELETE /v1/videos/{filename}`, `DELETE /v1/videos` (xóa hết nếu server hỗ trợ) |
| YouTube OAuth accounts / channels | ✅ | `GET /v1/youtube/accounts`, `.../channels` |
| YouTube SEO preview (Gemini) | ✅ | `POST /v1/youtube/seo` |
| Upload MP4 có sẵn lên YouTube | ✅ | `POST /v1/youtube/upload` |
| Tạo video + upload YouTube 1 lần | ✅ | `youtube_upload: true` trong `/generate` |
| Tag **Video location** (Studio, vd United States) | ⚠️ | Field API: `youtube_recording_location` — gửi lúc upload; **không** chặn quốc gia, **không** target audience. Sửa tay trên app vẫn ổn. Cần OAuth scope đủ (xem mục YouTube) |
| Catalog metadata (id, pending/uploaded, show, edit) | ❌ | Chỉ **CLI** `list` / `show` / `edit` / `upload <id>` |
| Tải MP4 qua HTTP (download file) | ❌ | Job trả `path` **trên máy API** — bot cùng máy hoặc mount volume |
| Tạo thumbnail riêng | ❌ | Pipeline tự tạo `*_thumb.jpg` theo **server** `user_settings.json` |
| Hook intro đầu MP4 | ❌ | `shorts_hook_intro_seconds` — **chỉ server settings** (`0` = tắt) |
| Chỉnh vị trí sau upload (`set-location`) | ❌ | Chỉ CLI; API upload gửi lúc insert nếu có setting |
| Gắn thumbnail JPG lên Shorts (API) | ⚠️ | Server **cố** gọi YouTube `thumbnails.set` — Shorts thường **403**; bìa lưới = frame trong video / app |
| Import MP4 + sinh metadata | ❌ | Chỉ CLI `import` |
| Reshuffle clip / `--seed` | ❌ | Chỉ CLI `create --reshuffle` |

**Kết luận bot:** Dùng API cho **generate**, **YouTube**, **avatar upload**, **list/delete file**. Metadata catalog / sửa title sau render → lưu DB bot hoặc chờ thêm endpoint. Gửi video Telegram: đọc `job.path` nếu bot **cùng server** với API.

---

## 2. Endpoints (đầy đủ)

| Method | Path | Mô tả |
|--------|------|--------|
| GET | `/health` | `{ "ok": true }` |
| GET | `/v1/defaults` | Toàn bộ key + giá trị mặc định server (`SETTING_KEYS`) |
| GET | `/v1/avatar/defaults` | Path avatar mặc định `assets/avatar/` |
| POST | `/v1/avatar/upload` | Multipart: video/ảnh avatar user |
| POST | `/v1/generate` | Tạo video → **202** + `job_id` |
| GET | `/v1/jobs/{job_id}` | `pending` \| `running` \| `done` \| `error` |
| GET | `/v1/videos` | List MP4 (`?output_dir=assets/final`) |
| DELETE | `/v1/videos/{filename}` | Xóa 1 file (vd `final_short.mp4`) |
| DELETE | `/v1/videos` | Xóa **toàn bộ** MP4 trong `output_dir` (`?output_dir=…`) — nếu server chưa có, bot fallback xóa lần lượt |
| GET | `/v1/youtube/accounts` | Accounts đã OAuth |
| GET | `/v1/youtube/accounts/{account_id}` | Status + channels |
| GET | `/v1/youtube/accounts/{account_id}/channels` | List kênh |
| GET | `/v1/youtube/channels` | `?account_id=` hoặc `?token_path=` |
| GET | `/v1/youtube/status` | Giống account status (query) |
| POST | `/v1/youtube/seo` | Xem trước title / mô tả / tags / hashtags |
| POST | `/v1/youtube/upload` | Upload file đã có lên YouTube |

---

## 3. Cấu hình server vs body bot

Server đọc `user_settings.json` (có thể **gom nhóm**: `api`, `gemini`, `content`, `youtube_account`, …).  
`POST /v1/generate` chỉ **ghi đè** field có trong body (xem bảng dưới).

| Nhóm | Ví dụ key (chỉ trên server, bot **không** gửi qua API) |
|------|------------------------------------------------------|
| Render | `render_seed`, `stock_force_refresh`, `pexels_per_page`, `avatar_scene_numbers` |
| Thumbnail JPG | `youtube_thumbnail_enabled`, `youtube_thumbnail_source`, `youtube_thumbnail_mode`, `youtube_thumbnail_text`, `youtube_thumbnail_text_zone_top`, `youtube_thumbnail_text_align`, `youtube_thumbnail_ai_text`, … |
| Hook đầu MP4 | `shorts_hook_intro_seconds` (`0` = không chèn ảnh bìa vào đầu file) |
| YouTube khác | `youtube_made_for_kids`, `youtube_category_id` (trừ khi thêm vào schema sau) |

Bot muốn đổi các key trên → sửa `user_settings.json` trên máy API hoặc mở rộng `GenerateRequest` trong Python.

`GET /v1/defaults` → copy `defaults` để biết server đang dùng gì.

---

## 4. Flow chuẩn (chỉ tạo video)

```
1. (Tuỳ chọn) POST /v1/avatar/upload
2. POST /v1/generate
3. Poll GET /v1/jobs/{job_id} mỗi 15–30s (timeout ~20 phút)
4. status === "done":
     - Gửi MP4: đọc job.path (cùng máy API) HOẶC chỉ báo path / youtube_url
5. status === "error" → job.error
```

**Bắt buộc:** Bot lưu `job_id` + kết quả trong DB — API restart = mất job.

---

## 5. Flow: tạo + đăng YouTube

```
1. GET /v1/youtube/accounts → user chọn account_id
2. GET /v1/youtube/accounts/{id}/channels → chọn youtube_channel_id
3. POST /v1/generate với youtube_upload: true + account_id + channel_id
4. Poll job → youtube_url, youtube_title, ...
```

Hoặc tách bước: generate xong → `POST /v1/youtube/upload` với `filename` + `topic` + SEO fields.

OAuth trên server (một lần / account) — **không làm trên Telegram**:

```bash
python3 scripts/youtube_auth.py --account-id @LylyTaks1199
```

Token → `credentials/youtube_tokens/<account_id>.json`. API **đọc file mỗi request** → **không cần restart uvicorn** sau OAuth. Chỉ OAuth lại khi thiếu scope (`force-ssl`), thu hồi quyền Google, hoặc đổi client secret.

Chi tiết: [YOUTUBE_SETUP.md](./YOUTUBE_SETUP.md)

---

## 6. Topic — không nhầm field

| Field | Vai trò |
|-------|---------|
| `use_manual_topic: true` + `manual_topic` | User **đã chọn** chủ đề |
| `use_manual_topic: false` | Gemini **tự sinh** topic (`topic_prompt` tùy chọn) |
| `topic_prompt` | Prompt sinh topic — **không** phải `manual_topic` |
| `script_extra_instructions` | Ghi chú thêm cho **kịch bản** |

---

## 7. POST /v1/generate — body (field API nhận)

Chỉ gửi field cần đổi (`extra: ignore` — field lạ bị bỏ qua).

```ts
interface GenerateBody {
  // --- API keys (bot thường gửi từ DB user) ---
  gemini_api_key?: string | string[];
  pexels_api_key?: string | string[];

  // --- Gemini ---
  gemini_model?: string;              // "auto"
  gemini_models?: string[];
  gemini_retry_delay_seconds?: number;
  gemini_max_retries?: number;

  // --- Nội dung ---
  language?: "en" | "vi";
  topic_prompt?: string;
  use_manual_topic?: boolean;
  manual_topic?: string;
  script_extra_instructions?: string;

  // --- Video / TTS ---
  video_mode?: "short" | "long";
  min_scenes?: number | null;
  max_scenes?: number | null;
  words_per_scene?: string | null;
  voice?: string | null;
  speech_rate?: string | null;

  // --- Output ---
  output_dir?: string;                // "assets/final"
  output_filename?: string;           // nên unique: tg_{userId}_{Date.now()}.mp4

  // --- Avatar ---
  avatar_mode?: "off" | "default" | "custom";
  avatar_video_path?: string;
  avatar_image_path?: string;
  avatar_scenes?: number;
  clean_cache?: boolean;

  // --- YouTube (khi youtube_upload: true) ---
  youtube_upload?: boolean;
  youtube_account_id?: string;
  youtube_token_path?: string;
  youtube_channel_id?: string;
  youtube_title?: string;
  youtube_description?: string;
  youtube_tags?: string[];
  youtube_auto_seo?: boolean;
  youtube_random_title?: boolean;
  youtube_seo_extra_instructions?: string;
  youtube_privacy?: "private" | "unlisted" | "public";
  youtube_category_id?: string;
  youtube_recording_location?: string;  // vd "United States" — Video location metadata; "" = không gửi
  youtube_thumbnail_source?: "avatar_image" | "video";  // ít khi cần gửi từ bot
}
```

### Avatar `avatar_mode`

| Giá trị | Hành vi |
|---------|---------|
| `default` | `assets/avatar/` trên server |
| `custom` | `avatar_video_path` / `avatar_image_path` (sau upload) |
| `off` | Chỉ stock Pexels, không avatar |

### Ví dụ — topic cố định, không upload YT

```json
{
  "gemini_api_key": ["KEY_FROM_DB"],
  "pexels_api_key": ["KEY_FROM_DB"],
  "language": "vi",
  "video_mode": "short",
  "use_manual_topic": true,
  "manual_topic": "Vì sao bầu trời màu xanh?",
  "output_filename": "tg_12345_1716123456789.mp4",
  "avatar_mode": "custom",
  "avatar_video_path": "assets/uploads/avatars/12345/avatar_video.mp4",
  "avatar_scenes": 2
}
```

### Ví dụ — tạo + đăng YouTube + location tag

```json
{
  "gemini_api_key": ["..."],
  "pexels_api_key": ["..."],
  "language": "en",
  "use_manual_topic": true,
  "manual_topic": "Main character syndrome",
  "youtube_upload": true,
  "youtube_account_id": "LylyTaks1199",
  "youtube_channel_id": "UCxxxx",
  "youtube_privacy": "public",
  "youtube_auto_seo": true,
  "youtube_random_title": true,
  "youtube_recording_location": "United States"
}
```

---

## 8. POST /v1/avatar/upload (multipart)

```bash
curl -X POST "$SHORTS_API_URL/v1/avatar/upload" \
  -H "X-API-Key: $SECRET" \
  -F "file=@avatar.mp4" \
  -F "user_id=123456789" \
  -F "kind=video"
```

Response (rút gọn):

```json
{
  "avatar_mode": "custom",
  "kind": "video",
  "path": "assets/uploads/avatars/12345/avatar_video.mp4",
  "absolute_path": "/.../avatar_video.mp4",
  "avatar_video_path": "assets/uploads/avatars/12345/avatar_video.mp4",
  "avatar_image_path": "",
  "user_id": "123456789"
}
```

Node.js:

```javascript
const FormData = require("form-data");
const fs = require("fs");

async function uploadAvatar(telegramId, filePath, kind = "video") {
  const form = new FormData();
  form.append("file", fs.createReadStream(filePath));
  form.append("user_id", String(telegramId));
  form.append("kind", kind);
  const r = await fetch(`${process.env.SHORTS_API_URL}/v1/avatar/upload`, {
    method: "POST",
    headers: { ...form.getHeaders(), "X-API-Key": process.env.SHORTS_API_SECRET || "" },
    body: form,
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
```

---

## 9. GET /v1/jobs/{job_id}

```ts
interface JobResponse {
  job_id: string;
  status: "pending" | "running" | "done" | "error";
  path?: string | null;           // absolute path MP4 trên máy API
  topic?: string | null;
  model_used?: string | null;
  youtube_video_id?: string | null;
  youtube_url?: string | null;
  youtube_title?: string | null;
  youtube_description?: string | null;
  youtube_tags?: string[] | null;
  youtube_title_variants?: string[] | null;
  youtube_hashtags?: string[] | null;
  error?: string | null;
}
```

**Chưa trả qua API (có trong pipeline nội bộ / CLI):** `video_id` catalog, `meta_path`, `thumbnail_path`, `title`/`description` đầy đủ từ `.meta.json`. Bot nên lưu `topic`, `youtube_*` từ job khi `done`.

---

## 10. GET /v1/videos & DELETE

```bash
curl -s "$SHORTS_API_URL/v1/videos"
curl -s "$SHORTS_API_URL/v1/videos?output_dir=assets/final"
curl -X DELETE "$SHORTS_API_URL/v1/videos/final_short.mp4"
curl -X DELETE "$SHORTS_API_URL/v1/videos?output_dir=assets/final"
```

Response list (rút gọn):

```json
{
  "output_dir": "assets/final",
  "absolute_dir": "/.../assets/final",
  "count": 2,
  "videos": [
    {
      "name": "tg_12345_1716123456789.mp4",
      "path": "/.../tg_12345_1716123456789.mp4",
      "relative_path": "assets/final/tg_12345_1716123456789.mp4",
      "size_bytes": 16148480,
      "modified_at": "2026-05-19T12:00:00+00:00"
    }
  ]
}
```

Xóa 1 file:

```json
{ "deleted": true, "name": "final_short.mp4", "relative_path": "assets/final/final_short.mp4" }
```

List **không** có trạng thái `uploaded` / `pending` (catalog chỉ CLI). Bot tự lưu `youtube_url` sau upload.

**Bot (admin):** `/youtube videos` — UI inline phân trang, xóa từng file, **Xóa tất cả**, làm mới. `/delvideo all` — xóa hết qua API (bulk hoặc loop).

---

## 11. YouTube API

### Accounts & channels

```bash
curl -s "$SHORTS_API_URL/v1/youtube/accounts"
curl -s "$SHORTS_API_URL/v1/youtube/accounts/LylyTaks1199/channels"
```

### POST /v1/youtube/seo

```json
{
  "gemini_api_key": ["KEY_FROM_DB"],
  "language": "vi",
  "topic": "Vì sao bầu trời màu xanh?",
  "script": [{ "text": "..." }],
  "youtube_seo_extra_instructions": "Kênh khoa học, hashtag tiếng Việt"
}
```

Response: `title`, `title_variants[]`, `description`, `tags[]`, `hashtags[]`, `picked_title`.

### POST /v1/youtube/upload

Upload MP4 **đã render** (trong `output_dir` server). Cần `gemini_api_key` nếu bật SEO tự động.

```json
{
  "filename": "tg_123.mp4",
  "output_dir": "assets/final",
  "gemini_api_key": ["KEY_FROM_DB"],
  "pexels_api_key": ["KEY_FROM_DB"],
  "topic": "Chủ đề video",
  "youtube_account_id": "LylyTaks1199",
  "youtube_channel_id": "UCxxxx",
  "youtube_token_path": "",
  "youtube_privacy": "unlisted",
  "youtube_auto_seo": true,
  "youtube_random_title": true,
  "youtube_seo_extra_instructions": "Kênh khoa học, hashtag VI",
  "youtube_recording_location": "United States"
}
```

Hoặc `"path": "/absolute/path/to/file.mp4"` thay `filename`.

Response (có thể khác tùy server): `youtube_video_id`, `youtube_url`, `youtube_title`, `youtube_description`, `youtube_tags`, `youtube_hashtags`, `youtube_title_variants`.

### Video location (app: Show more → Location)

- Giống tag địa điểm trên Short — **mọi người vẫn xem được**, không phải “chỉ US”.
- API: `youtube_recording_location` → `recordingDetails.locationDescription`.
- App chọn từ ô tìm kiếm địa điểm có thể khác chút so với chuỗi `"United States"`.
- Sau upload, user vẫn có thể sửa Location trên **app YouTube** (khuyên dùng nếu Studio chưa hiện).
- OAuth: cần token với scope `youtube.upload` + `youtube.force-ssl` (đổi scope → chạy lại `youtube_auth.py`).

### Shorts thumbnail (JPG)

- Server tạo `*_thumb.jpg` khi render (theo `user_settings.json`).
- Upload YouTube: gọi `thumbnails.set` — **Shorts thường không nhận** → bình thường.
- Bìa hiển thị trên feed: YouTube **chọn frame** trong video; `shorts_hook_intro_seconds > 0` nhét ảnh bìa vào **đầu MP4** (chỉ server config).

---

## 12. Module Node.js mẫu

`services/shortsApi.js`:

```javascript
const BASE = process.env.SHORTS_API_URL || "http://127.0.0.1:8000";
const API_KEY = process.env.SHORTS_API_SECRET || "";

function headers(json = true) {
  const h = {};
  if (json) h["Content-Type"] = "application/json";
  if (API_KEY) h["X-API-Key"] = API_KEY;
  return h;
}

async function createJob(body) {
  const r = await fetch(`${BASE}/v1/generate`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
  });
  if (r.status !== 202) throw new Error(await r.text());
  return r.json();
}

async function getJob(jobId) {
  const r = await fetch(`${BASE}/v1/jobs/${jobId}`, { headers: headers(false) });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function waitForJob(jobId, { intervalMs = 20000, timeoutMs = 1200000 } = {}) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const job = await getJob(jobId);
    if (job.status === "done" || job.status === "error") return job;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error("Timeout waiting for job");
}

async function getDefaults() {
  const r = await fetch(`${BASE}/v1/defaults`, { headers: headers(false) });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function listYoutubeAccounts() {
  const r = await fetch(`${BASE}/v1/youtube/accounts`, { headers: headers(false) });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function listYoutubeChannels(accountId) {
  const r = await fetch(`${BASE}/v1/youtube/accounts/${encodeURIComponent(accountId)}/channels`, {
    headers: headers(false),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function previewSeo(body) {
  const r = await fetch(`${BASE}/v1/youtube/seo`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function uploadToYoutube(body) {
  const r = await fetch(`${BASE}/v1/youtube/upload`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function buildGenerateBody(dbUser, opts = {}) {
  const {
    manualTopic,
    language,
    videoMode,
    youtubeUpload = false,
    youtubeAccountId,
    youtubeChannelId,
    youtubePrivacy,
  } = opts;

  const mode = dbUser.avatar_mode || "default";
  const body = {
    gemini_api_key: dbUser.gemini_keys,
    pexels_api_key: dbUser.pexels_keys,
    language: language || dbUser.language || "vi",
    video_mode: videoMode || dbUser.video_mode || "short",
    avatar_mode: mode,
    output_filename: `tg_${dbUser.telegram_id}_${Date.now()}.mp4`,
  };

  if (mode === "custom") {
    if (dbUser.avatar_video_path) body.avatar_video_path = dbUser.avatar_video_path;
    if (dbUser.avatar_image_path) body.avatar_image_path = dbUser.avatar_image_path;
  }

  if (manualTopic?.trim()) {
    body.use_manual_topic = true;
    body.manual_topic = manualTopic.trim();
  } else {
    body.use_manual_topic = false;
  }

  if (dbUser.script_extra_instructions) {
    body.script_extra_instructions = dbUser.script_extra_instructions;
  }

  if (youtubeUpload) {
    body.youtube_upload = true;
    body.youtube_account_id = youtubeAccountId || dbUser.youtube_account_id;
    body.youtube_channel_id = youtubeChannelId || dbUser.youtube_channel_id;
    body.youtube_privacy = youtubePrivacy || dbUser.youtube_privacy || "private";
    body.youtube_auto_seo = dbUser.youtube_auto_seo !== false;
    body.youtube_random_title = dbUser.youtube_random_title !== false;
    if (dbUser.youtube_recording_location) {
      body.youtube_recording_location = dbUser.youtube_recording_location;
    }
  }

  return body;
}

module.exports = {
  createJob,
  getJob,
  waitForJob,
  getDefaults,
  listYoutubeAccounts,
  listYoutubeChannels,
  previewSeo,
  uploadToYoutube,
  buildGenerateBody,
};
```

Gửi file Telegram từ `job.path` (chỉ khi bot đọc được filesystem API):

```javascript
const fs = require("fs");
const FormData = require("form-data");

async function sendVideoToChat(bot, chatId, absolutePath) {
  await bot.sendVideo(chatId, fs.createReadStream(absolutePath));
}
```

---

## 13. DB bot gợi ý

**users**

| Column | Ghi chú |
|--------|---------|
| `telegram_id` | PK |
| `gemini_keys` | JSON array |
| `pexels_keys` | JSON array |
| `language` | `vi` / `en` |
| `video_mode` | `short` / `long` |
| `avatar_mode` | `off` / `default` / `custom` |
| `avatar_video_path` | Sau upload API |
| `avatar_image_path` | |
| `script_extra_instructions` | |
| `youtube_account_id` | |
| `youtube_channel_id` | |
| `youtube_privacy` | |
| `youtube_recording_location` | Tùy chọn, vd `United States` |

**jobs**

| Column | Ghi chú |
|--------|---------|
| `job_id` | Từ API |
| `telegram_id`, `chat_id` | |
| `status` | pending / running / done / error |
| `path` | Từ `job.path` |
| `topic`, `model_used` | |
| `youtube_video_id`, `youtube_url`, `youtube_title` | Nếu đã upload |
| `error` | |
| `created_at`, `updated_at` | |

---

## 14. Lệnh bot gợi ý

| Lệnh | API / hành vi |
|------|----------------|
| `/shorts` | `use_manual_topic: false` → generate |
| `/shorts <chủ đề>` | `manual_topic` |
| `/shorts_lang vi\|en` | Lưu DB → `language` |
| `/shorts_mode short\|long` | `video_mode` |
| `/avatar` | Upload file → `POST /avatar/upload` → `custom` |
| `/noavatar` | `avatar_mode: off` |
| `/yt_accounts` | `GET /youtube/accounts` |
| `/yt_channels` | Chọn `channel_id` |
| `/yt_seo <topic>` | `POST /youtube/seo` (preview) |
| `/settings` | Key, YouTube account (DM) |

---

## 15. Việc có thể thêm sau (chưa có API)

Nếu bot cần, mở rộng Python trước:

1. `GET /v1/catalog` — list pending/uploaded + `id`, title, `youtube_url`
2. `GET /v1/catalog/{id}` — chi tiết `.meta.json`
3. `PATCH /v1/catalog/{id}` — sửa title/description/tags
4. `GET /v1/videos/{filename}/file` — tải MP4 (bot khác máy)
5. Thêm field render/thumbnail/hook vào `GenerateRequest`
6. `POST /v1/jobs/{id}` mở rộng response: `video_id`, `thumbnail_path`, `meta_path`

---

## 16. Tham chiếu CLI (không gọi từ bot)

| CLI | Thay thế tạm cho bot |
|-----|---------------------|
| `python main.py create ...` | `POST /v1/generate` |
| `python main.py upload <file>` | `POST /v1/youtube/upload` |
| `python main.py list` | `GET /v1/videos` + DB bot lưu upload state |
| `python main.py show/edit` | Chưa có API |
| `python main.py hook-intro` | Chỉnh `shorts_hook_intro_seconds` trên server |

Settings server: [SETTINGS.md](./SETTINGS.md) · YouTube OAuth: [YOUTUBE_SETUP.md](./YOUTUBE_SETUP.md) · CLI: [CLI.md](./CLI.md)
