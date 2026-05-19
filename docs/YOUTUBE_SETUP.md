# YouTube upload — hướng dẫn ngắn

## Tóm tắt

| Việc | Làm ở đâu |
|------|-----------|
| Bật API + tạo OAuth + **tải JSON** | **Điện thoại** (trình duyệt → Google Cloud Console) |
| Đặt file `youtube_client_secret.json` | Máy **đang chạy repo** này |
| Đăng nhập kênh (`youtube_auth.py`) | Máy **đang chạy repo** (cần mở link Google) |
| Bot / API | Sau |

Chỉ cần **1 file config** từ Google: đặt tên đúng `youtube_client_secret.json`.

---

## Phần A — Trên điện thoại (Google Cloud)

Mở Chrome/Safari, đăng nhập Google **cùng tài khoản** dùng tạo project.

### A1. Bật YouTube Data API v3

Link (URL đầy đủ — dòng dưới, Cmd+click):

https://console.cloud.google.com/apis/library/youtube.googleapis.com

→ chọn project (hoặc tạo mới) → **Enable**.

### A2. OAuth consent screen (lần đầu)

Link:

https://console.cloud.google.com/apis/credentials/consent

- User type: **External** → điền tên app, email → Save  
- **Scopes** → thêm `youtube.upload` + `youtube.force-ssl` (list kênh / metadata)  
- **Test users** → thêm **email** của kênh YouTube sẽ đăng video  

(App đang **Testing** thì bắt buộc có bước Test users.)

### A3. Tạo OAuth Client + tải JSON

Link:

https://console.cloud.google.com/apis/credentials

→ **Create Credentials** → **OAuth client ID**  
→ loại **Desktop app** (không chọn Web)  
→ **Create** → **Download JSON** (lưu vào máy / Files / Drive).

### A4. Đưa file lên máy chạy project

Đổi tên file tải về thành:

```text
youtube_client_secret.json
```

Copy vào thư mục repo:

```text
ytb-shorts-gen-upload/credentials/youtube_client_secret.json
```

Cách chuyển từ điện thoại (chọn một):

- AirDrop / cable → Mac  
- Gửi **Drive / Telegram “Saved”** → tải trên máy Linux/Mac  
- `scp` từ máy bạn lên VPS  

Không cần làm OAuth trên điện thoại — chỉ cần **file JSON** đúng tên và đúng chỗ.

---

## Phần B — Trên máy đang chạy repo

```bash
cd /path/to/ytb-shorts-gen-upload
source venv/bin/activate

# Kiểm tra file đã có
ls -la credentials/youtube_client_secret.json

python3 scripts/youtube_auth.py --account-id @LylyTaks1199
# @LylyTaks1199 và LylyTaks1199 → cùng file LylyTaks1199.json (bỏ @ khi lưu tên file)
```

`--account-id` = **tên file token** trên máy (nick tuỳ chọn), **không** bắt buộc trùng @handle YouTube. `@Branch` và `Branch` cho cùng một file.

Terminal in **nhãn + URL OAuth đầy đủ ở dòng dưới** (Cmd+click) → đăng nhập kênh → Allow.

Token:

```text
credentials/youtube_tokens/LylyTaks1199.json
```

**Token trên disk — API đọc mỗi request.** Sau `youtube_auth.py` **không cần** restart `uvicorn`; gọi ngay `GET /v1/youtube/accounts/<id>/channels` (hoặc bot `/yt_channels`).

Kiểm tra scope trong file token (phải có `youtube.upload` **và** `youtube.force-ssl` — list kênh / sửa metadata cần `force-ssl`):

```bash
python3 -c "import json; print(json.load(open('credentials/youtube_tokens/LylyTaks1199.json'))['scopes'])"
```

### Thử upload (CLI, chưa cần API)

`user_settings.json`:

```json
"youtube_upload": true,
"youtube_account_id": "LylyTaks1199"
```

**Vị trí quay (metadata):** `youtube_recording_location` trong `user_settings.json` → gửi lúc **upload** (`recordingDetails.locationDescription`). **Không** phải “target audience US”. Studio: Chi tiết video → địa điểm / filming location (nếu có).

- Lúc upload terminal phải in: `[youtube] vị trí quay (metadata): United States`
- Sửa video đã đăng: `python main.py set-location final_short.mp4` (cần OAuth scope `youtube.force-ssl` — nếu 403, chạy lại `python3 scripts/youtube_auth.py --account-id ...`)
- Để tắt: `"youtube_recording_location": ""`

```bash
python main.py create --topic "Your topic"
```

### Sau — API cho bot

```bash
uvicorn api_server:app --host 0.0.0.0 --port 8000
```

Body generate: `"youtube_account_id": "LylyTaks1199"`.

---

## Checklist

- [ ] Điện thoại: API bật, consent + test user, Desktop app, **đã tải JSON**  
- [ ] Máy repo: `credentials/youtube_client_secret.json`  
- [ ] `python3 scripts/youtube_auth.py --account-id ...`  
- [ ] `credentials/youtube_tokens/<account-id>.json` tồn tại  

---

## Lỗi 403 `access_denied` — app đang Testing

Thông báo kiểu:

> *YTB SHORT UPLOAD has not completed the Google verification process... can only be accessed by developer-approved testers*

**Nguyên nhân:** OAuth app chưa publish, chỉ email trong **Test users** được phép.

**Cách sửa (5 phút, trên điện thoại hoặc máy tính):**

1. Mở link (URL dòng dưới):

https://console.cloud.google.com/apis/credentials/consent

2. Chọn **đúng project** (cùng project đã tạo `client_secret`)  
3. Kéo xuống **Test users** → **+ ADD USERS**  
4. Thêm **đúng email Google** bạn dùng khi bấm Allow trong `youtube_auth`  
   - Phải trùng 100% (vd `lyly@gmail.com`, không phải alias khác)  
5. **Save** → đợi 1–2 phút  
6. Chạy lại:

```bash
python3 scripts/youtube_auth.py --account-id @LylyTaks1199
```

**Lưu ý:** Email đăng nhập trình duyệt khi OAuth = email kênh YouTube (hoặc email sở hữu kênh Brand account).

**Không cần** “Publish app” / xác minh Google nếu chỉ dùng vài kênh của bạn — Test users là đủ.

Nếu vẫn lỗi: thử trình duyệt ẩn danh, đăng nhập đúng 1 tài khoản Google, hoặc xóa quyền cũ:

https://myaccount.google.com/permissions

rồi OAuth lại.

---

<details>
<summary>Lỗi khác</summary>

| Lỗi | Xử lý |
|-----|--------|
| `Thiếu: youtube_client_secret.json` | Chưa copy file vào `credentials/` hoặc sai tên |
| `403` API | Chưa Enable YouTube Data API v3 |
| `invalid_client` | OAuth phải là **Desktop app** |
| `[thumbnail] 403` / custom thumbnails | Kênh chưa bật **Ảnh thu nhỏ tùy chỉnh** — xem mục dưới |

</details>

---

## Ảnh bìa — upload video OK nhưng API/Studio không gắn được file JPG

### Quan trọng: video **Shorts** (repo này)

Google ghi rõ ([trợ giúp chính thức](https://support.google.com/youtube/answer/72431?hl=vi)):

> *Không giống video dài — **bạn không thể tải hình thu nhỏ tùy chỉnh lên Shorts**.*  
> Chỉ chọn **một khung hình** trong video. Sau khi đã đăng, **không đổi** được (trên desktop thường báo *"For now, you can't change the thumbnail on your Short"*).

Vì vậy:

- `python main.py set-thumbnail ...` / API `thumbnails.set` → **403 là bình thường** với Shorts, kể cả kênh đã xác minh SĐT.
- Menu **Feature eligibility / Custom thumbnails** có thể **không hiện** hoặc chỉ áp dụng **video dài**, không phải Shorts.

File `*_thumb.jpg` vẫn hữu ích: xem trước, Telegram, hoặc **nhúng khung vào video** (xem workaround bên dưới).

### Xác minh SĐT (video dài / một số tính năng kênh)

Nếu muốn tìm màn hình xác minh (UI đổi thường xuyên):

1. Link xác minh (URL dòng dưới — đăng nhập đúng kênh):

https://www.youtube.com/verify
2. Hoặc Studio → **Cài đặt** (⚙ góc dưới trái) → **Kênh** → **Trạng thái và tính năng** / **Channel status and features** (tên có thể khác *Feature eligibility*).
3. Trên **điện thoại**: app YouTube → Tạo → đôi khi hiện bước xác minh khi upload.

Không thấy mục “Custom thumbnails” → với **Shorts** là điều bình thường, không phải bạn làm sai.

### Cách làm với Shorts (thực tế)

| Cách | Ghi chú |
|------|--------|
| **Chọn khung khi đăng (mobile)** | iOS/Android khi upload Short → biểu tượng bút/chỉnh ảnh bìa → chọn frame đẹp |
| **Khung “đẹp” sẵn trong video** | Pipeline có thể chèn ~0,5s ảnh `*_thumb.jpg` đầu video → YouTube lấy đúng khung đó |
| **Video dài (không Shorts)** | Upload dạng video thường (16:9 hoặc dọc) → mới upload JPG bìa qua Studio/API |

### Chỉ áp dụng video **dài** (không phải Shorts)

```bash
python main.py set-thumbnail <video-dai-da-upload>
```

Studio (thay `VIDEO_ID`):

https://studio.youtube.com/video/VIDEO_ID/edit

→ **Tải hình thu nhỏ lên**.
