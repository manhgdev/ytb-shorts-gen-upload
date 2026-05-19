from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.avatar_store import default_avatar_info, save_avatar_upload
from app.output_store import delete_video, list_videos, output_dir_from_settings
from app.pipeline import run
from app.settings import api_secret, merge_settings
from app.schemas import (
    AvatarDefaultsResponse,
    AvatarUploadResponse,
    DefaultsResponse,
    GenerateRequest,
    GenerateResponse,
    JobResponse,
    VideoDeleteResponse,
    VideoListResponse,
    YouTubeAccountStatusResponse,
    YouTubeAccountRegisterRequest,
    YouTubeAccountRegisterResponse,
    YouTubeAccountsResponse,
    YouTubeChannelsResponse,
    YouTubeStatusResponse,
    YouTubeSeoRequest,
    YouTubeSeoResponse,
    YouTubeUploadRequest,
    YouTubeUploadResponse,
    request_to_settings,
    schema_defaults,
)
from app.youtube_seo import generate_youtube_metadata, pick_title
from app.youtube import (
    account_status,
    apply_youtube_options,
    list_accounts,
    list_channels_info,
    prepare_youtube_account,
    upload_video,
)
from app.utils import ensure_ffmpeg

_jobs: dict[str, dict[str, Any]] = {}


def _check_auth(x_api_key: str | None) -> None:
    secret = api_secret()
    if secret and x_api_key != secret:
        raise HTTPException(status_code=401, detail="Invalid API key")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_ffmpeg()
    yield


app = FastAPI(title="YT Shorts Gen API", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/v1/defaults", response_model=DefaultsResponse)
def get_defaults():
    return schema_defaults()


@app.get("/v1/avatar/defaults", response_model=AvatarDefaultsResponse)
def avatar_defaults():
    """Avatar mặc định trong repo (assets/avatar/)."""
    return AvatarDefaultsResponse(default=default_avatar_info())


@app.post("/v1/avatar/upload", response_model=AvatarUploadResponse)
async def avatar_upload(
    file: UploadFile = File(...),
    user_id: str = Form(default=""),
    kind: str = Form(default=""),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    """
    Upload video/ảnh avatar cho user (bot gửi từ Telegram).
    Trả path dùng trong POST /v1/generate: avatar_mode=custom + avatar_*_path.
    """
    _check_auth(x_api_key)
    result = await save_avatar_upload(file, user_id=user_id, kind=kind)
    return AvatarUploadResponse(**result)


@app.get("/v1/videos", response_model=VideoListResponse)
def videos_list(
    output_dir: str = "",
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    """Danh sách video trong output (mặc định assets/final)."""
    _check_auth(x_api_key)
    data = list_videos(output_dir or None)
    return VideoListResponse(**data)


@app.delete("/v1/videos/{filename}", response_model=VideoDeleteResponse)
def videos_delete(
    filename: str,
    output_dir: str = "",
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    """Xóa 1 file video theo tên (vd final_short.mp4)."""
    _check_auth(x_api_key)
    return VideoDeleteResponse(**delete_video(filename, output_dir or None))


@app.get("/v1/youtube/accounts", response_model=YouTubeAccountsResponse)
def youtube_list_accounts(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    """Danh sách tài khoản YouTube đã OAuth (nhiều kênh)."""
    _check_auth(x_api_key)
    return YouTubeAccountsResponse(**list_accounts())


@app.post("/v1/youtube/accounts", response_model=YouTubeAccountRegisterResponse)
def youtube_register_account(
    body: YouTubeAccountRegisterRequest,
    public_base: str = "",
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    """
    Đăng ký / liên kết account. Trả auth_url — user mở link Google (không SSH).
    Query tuỳ chọn: ?public_base=http://IP:8000 (trùng redirect trong Google Cloud).
    """
    _check_auth(x_api_key)
    try:
        return YouTubeAccountRegisterResponse(
            **prepare_youtube_account(
                body.account_id,
                public_base=public_base or None,
            )
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/v1/youtube/oauth/callback")
def youtube_oauth_callback(code: str = "", state: str = "", error: str = ""):
    """Google redirect sau khi user Allow — hiển thị trang thành công/lỗi."""
    if error:
        return HTMLResponse(
            f"<h2>OAuth bị hủy</h2><p>{error}</p><p>Quay lại Telegram và thử lại.</p>",
            status_code=400,
        )
    if not code or not state:
        return HTMLResponse("<h2>Thiếu code/state</h2>", status_code=400)
    try:
        from app.youtube_oauth import complete_youtube_oauth

        result = complete_youtube_oauth(state=state, code=code)
        aid = result["account_id"]
        return HTMLResponse(
            f"""<!DOCTYPE html><html><head><meta charset="utf-8">
            <meta name="viewport" content="width=device-width,initial-scale=1">
            <title>OK</title></head><body style="font-family:sans-serif;padding:24px">
            <h2>✅ Đã liên kết YouTube</h2>
            <p>Account: <b>{aid}</b></p>
            <p>Quay lại <b>Telegram</b> → 🔄 Làm mới → chọn account → 📡 Kênh.</p>
            </body></html>"""
        )
    except Exception as e:
        return HTMLResponse(
            f"<h2>Lỗi OAuth</h2><pre>{e}</pre><p>Tạo link mới từ bot.</p>",
            status_code=400,
        )


@app.get("/v1/youtube/accounts/{account_id}", response_model=YouTubeAccountStatusResponse)
def youtube_account_detail(
    account_id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_auth(x_api_key)
    return YouTubeAccountStatusResponse(**account_status(merge_settings(None), account_id=account_id))


@app.get("/v1/youtube/accounts/{account_id}/channels", response_model=YouTubeChannelsResponse)
def youtube_account_channels(
    account_id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    """Các kênh trong 1 tài khoản Google (chọn youtube_channel_id khi upload)."""
    _check_auth(x_api_key)
    s = apply_youtube_options(merge_settings(None), account_id=account_id)
    try:
        info = list_channels_info(s)
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    if not info.get("can_upload", True) and info.get("message"):
        raise HTTPException(404, info["message"])
    return YouTubeChannelsResponse(
        account_id=account_id,
        token_path=s["youtube_token_path"],
        count=len(info["channels"]),
        channels=info["channels"],
        message=info.get("message"),
        can_upload=info.get("can_upload"),
    )


@app.get("/v1/youtube/status", response_model=YouTubeStatusResponse)
def youtube_auth_status(
    account_id: str = "",
    token_path: str = "",
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_auth(x_api_key)
    return YouTubeStatusResponse(
        **account_status(
            merge_settings(None),
            account_id=account_id or None,
            token_path=token_path or None,
        )
    )


@app.get("/v1/youtube/channels", response_model=YouTubeChannelsResponse)
def youtube_channels_query(
    account_id: str = "",
    token_path: str = "",
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    """List kênh — query ?account_id=kenh_a hoặc ?token_path=..."""
    _check_auth(x_api_key)
    s = apply_youtube_options(
        merge_settings(None),
        account_id=account_id or None,
        token_path=token_path or None,
    )
    try:
        info = list_channels_info(s)
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    if not info.get("can_upload", True) and info.get("message"):
        raise HTTPException(404, info["message"])
    return YouTubeChannelsResponse(
        account_id=account_id or None,
        token_path=s["youtube_token_path"],
        count=len(info["channels"]),
        channels=info["channels"],
        message=info.get("message"),
        can_upload=info.get("can_upload"),
    )


@app.post("/v1/youtube/seo", response_model=YouTubeSeoResponse)
def youtube_seo_preview(
    body: YouTubeSeoRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    """Gemini sinh title (5 biến thể), mô tả, tag, hashtag — bot có thể random title rồi mới upload."""
    _check_auth(x_api_key)
    settings = merge_settings(body.model_dump(exclude_unset=True))
    topic = (body.topic or "").strip()
    if not topic:
        raise HTTPException(400, "Cần topic")
    try:
        seo = generate_youtube_metadata(settings, topic, body.script)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    if not seo:
        raise HTTPException(
            400,
            "SEO tắt hoặc đã có đủ youtube_title + youtube_description + youtube_tags",
        )
    picked = pick_title(seo, settings) if settings.get("youtube_random_title", True) else seo["title"]
    return YouTubeSeoResponse(
        title=seo["title"],
        title_variants=seo.get("title_variants") or [],
        description=seo["description"],
        tags=seo.get("tags") or [],
        hashtags=seo.get("hashtags") or [],
        picked_title=picked,
    )


@app.post("/v1/youtube/upload", response_model=YouTubeUploadResponse)
def youtube_upload_video(
    body: YouTubeUploadRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    """Upload file MP4 đã có lên YouTube."""
    _check_auth(x_api_key)
    settings = apply_youtube_options(
        merge_settings(body.model_dump(exclude_unset=True)),
        account_id=body.youtube_account_id,
        token_path=body.youtube_token_path,
        channel_id=body.youtube_channel_id,
    )
    path = (body.path or "").strip()
    if not path and body.filename:
        folder = output_dir_from_settings(body.output_dir)
        path = str(folder / body.filename)
    if not path:
        raise HTTPException(400, "Cần path hoặc filename")
    try:
        result = upload_video(
            path,
            settings,
            topic=body.topic or "",
            script=body.script,
            title=body.youtube_title,
            description=body.youtube_description,
            tags=body.youtube_tags,
            privacy=body.youtube_privacy,
            account_id=body.youtube_account_id,
            token_path=body.youtube_token_path,
            channel_id=body.youtube_channel_id,
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    return YouTubeUploadResponse(**result)


@app.post("/v1/generate", response_model=GenerateResponse, status_code=202)
async def generate(
    body: GenerateRequest,
    background_tasks: BackgroundTasks,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_auth(x_api_key)
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "pending"}
    settings = request_to_settings(body)
    background_tasks.add_task(_run_job, job_id, settings)
    return GenerateResponse(job_id=job_id, status="pending")


@app.get("/v1/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    _check_auth(x_api_key)
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    keys = (
        "status",
        "path",
        "topic",
        "model_used",
        "youtube_video_id",
        "youtube_url",
        "youtube_title",
        "youtube_description",
        "youtube_tags",
        "youtube_title_variants",
        "youtube_hashtags",
        "error",
    )
    return JobResponse(job_id=job_id, **{k: job.get(k) for k in keys})


async def _run_job(job_id: str, settings: dict[str, Any]) -> None:
    _jobs[job_id] = {"status": "running"}
    try:
        result = await run(settings)
        _jobs[job_id] = {
            "status": "done",
            "path": result.get("path"),
            "topic": result.get("topic"),
            "model_used": result.get("model_used"),
            "youtube_video_id": result.get("youtube_video_id"),
            "youtube_url": result.get("youtube_url"),
            "youtube_title": result.get("youtube_title"),
            "youtube_description": result.get("youtube_description"),
            "youtube_tags": result.get("youtube_tags"),
            "youtube_title_variants": result.get("youtube_title_variants"),
            "youtube_hashtags": result.get("youtube_hashtags"),
        }
    except Exception as e:
        _jobs[job_id] = {"status": "error", "error": str(e)}


@app.exception_handler(Exception)
async def unhandled(_request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": str(exc)})
