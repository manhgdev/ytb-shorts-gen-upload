from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.settings import SETTING_KEYS, default_settings


class GenerateRequest(BaseModel):
    """Body POST /v1/generate — chỉ field gửi lên mới ghi đè mặc định."""

    model_config = ConfigDict(extra="ignore")

    gemini_api_key: str | list[str] | None = None
    pexels_api_key: str | list[str] | None = None
    gemini_model: str | None = None
    gemini_models: list[str] | None = None
    gemini_retry_delay_seconds: int | None = None
    gemini_max_retries: int | None = None
    language: str | None = None
    topic_prompt: str | None = None
    use_manual_topic: bool | None = None
    manual_topic: str | None = None
    script_extra_instructions: str | None = None
    video_mode: str | None = None
    min_scenes: int | None = None
    max_scenes: int | None = None
    words_per_scene: str | None = None
    voice: str | None = None
    speech_rate: str | None = None
    output_dir: str | None = None
    output_filename: str | None = None
    avatar_mode: str | None = None
    avatar_video_path: str | None = None
    avatar_image_path: str | None = None
    avatar_scenes: int | None = None
    clean_cache: bool | None = None
    youtube_upload: bool | None = None
    youtube_title: str | None = None
    youtube_description: str | None = None
    youtube_tags: list[str] | None = None
    youtube_privacy: str | None = None
    youtube_category_id: str | None = None
    youtube_recording_location: str | None = None
    youtube_thumbnail_source: str | None = None
    youtube_account_id: str | None = None
    youtube_token_path: str | None = None
    youtube_channel_id: str | None = None
    youtube_auto_seo: bool | None = None
    youtube_random_title: bool | None = None
    youtube_seo_extra_instructions: str | None = None


class YouTubeSeoRequest(BaseModel):
    """POST /v1/youtube/seo — xem trước title/mô tả/hashtag trước khi đăng."""

    model_config = ConfigDict(extra="ignore")

    gemini_api_key: str | list[str] | None = None
    language: str | None = None
    topic: str
    script: list[dict[str, Any]] | None = None
    youtube_title: str | None = None
    youtube_description: str | None = None
    youtube_tags: list[str] | None = None
    youtube_auto_seo: bool | None = None
    youtube_random_title: bool | None = None
    youtube_seo_extra_instructions: str | None = None


class YouTubeSeoResponse(BaseModel):
    title: str
    title_variants: list[str] = []
    description: str
    tags: list[str] = []
    hashtags: list[str] = []
    picked_title: str | None = None


class YouTubeUploadRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str = ""
    filename: str = ""
    output_dir: str | None = None
    topic: str = ""
    script: list[dict[str, Any]] | None = None
    gemini_api_key: str | list[str] | None = None
    language: str | None = None
    youtube_title: str | None = None
    youtube_description: str | None = None
    youtube_tags: list[str] | None = None
    youtube_auto_seo: bool | None = None
    youtube_random_title: bool | None = None
    youtube_seo_extra_instructions: str | None = None
    youtube_privacy: str | None = None
    youtube_recording_location: str | None = None
    youtube_account_id: str | None = None
    youtube_token_path: str | None = None
    youtube_channel_id: str | None = None


class YouTubeChannelItem(BaseModel):
    channel_id: str
    title: str
    custom_url: str = ""
    thumbnail: str = ""


class YouTubeAccountItem(BaseModel):
    account_id: str
    token_path: str
    token_exists: bool
    authenticated: bool | None = None
    channel_title: str | None = None
    channels_count: int | None = None
    message: str | None = None


class YouTubeAccountsResponse(BaseModel):
    accounts_dir: str
    count: int
    accounts: list[YouTubeAccountItem]


class YouTubeAccountRegisterRequest(BaseModel):
    account_id: str


class YouTubeAccountRegisterResponse(BaseModel):
    account_id: str
    token_path: str
    token_exists: bool
    client_secrets_exists: bool
    authenticated: bool
    can_upload: bool = False
    status: str
    oauth_command: str = ""
    auth_url: str | None = None
    setup_hint: str | None = None
    message: str
    channels_count: int = 0
    channel_title: str | None = None


class YouTubeAccountStatusResponse(BaseModel):
    account_id: str
    client_secrets_path: str
    token_path: str
    client_secrets_exists: bool
    token_exists: bool
    authenticated: bool
    channel_title: str | None = None
    channels_count: int = 0
    channels: list[YouTubeChannelItem] = []
    message: str | None = None


class YouTubeChannelsResponse(BaseModel):
    account_id: str | None = None
    token_path: str
    count: int
    channels: list[YouTubeChannelItem]
    message: str | None = None
    can_upload: bool | None = None


class YouTubeStatusResponse(YouTubeAccountStatusResponse):
    """Alias — dùng ?account_id= hoặc ?token_path="""


class YouTubeUploadResponse(BaseModel):
    youtube_video_id: str
    youtube_url: str
    youtube_title: str
    youtube_description: str = ""
    youtube_tags: list[str] = []
    youtube_title_variants: list[str] = []
    youtube_hashtags: list[str] = []
    youtube_privacy: str
    youtube_channel_id: str | None = None
    youtube_account_id: str | None = None
    youtube_token_path: str | None = None


class GenerateResponse(BaseModel):
    job_id: str
    status: str


class JobResponse(BaseModel):
    job_id: str
    status: str
    path: str | None = None
    topic: str | None = None
    model_used: str | None = None
    youtube_video_id: str | None = None
    youtube_url: str | None = None
    youtube_title: str | None = None
    youtube_description: str | None = None
    youtube_tags: list[str] | None = None
    youtube_title_variants: list[str] | None = None
    youtube_hashtags: list[str] | None = None
    error: str | None = None


class DefaultsResponse(BaseModel):
    defaults: dict[str, Any]
    keys: list[str]


class AvatarDefaultsResponse(BaseModel):
    default: dict[str, Any]


class VideoItem(BaseModel):
    name: str
    path: str
    relative_path: str
    size_bytes: int
    modified_at: str


class VideoListResponse(BaseModel):
    output_dir: str
    absolute_dir: str
    count: int
    videos: list[VideoItem]


class VideoDeleteResponse(BaseModel):
    deleted: bool
    name: str
    relative_path: str


class AvatarUploadResponse(BaseModel):
    avatar_mode: str
    kind: str
    path: str
    absolute_path: str
    avatar_video_path: str
    avatar_image_path: str
    user_id: str


def request_to_settings(body: GenerateRequest) -> dict[str, Any]:
    return body.model_dump(exclude_unset=True)


def schema_defaults() -> DefaultsResponse:
    return DefaultsResponse(defaults=default_settings(), keys=sorted(SETTING_KEYS))
