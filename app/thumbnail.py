from __future__ import annotations

import re
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any

from app.settings import resolve_avatar_image_path
from app.utils import ensure_ffmpeg, media_duration_seconds

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Impact.ttf",
    "/Library/Fonts/Impact.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

ACCENT_GOLD = (255, 204, 0)


def thumbnail_path_for(video_path: str | Path) -> Path:
    p = Path(video_path)
    return p.with_name(f"{p.stem}_thumb.jpg")


def _pick_timestamp(settings: dict[str, Any], duration: float) -> float:
    custom = settings.get("youtube_thumbnail_at_sec")
    if custom is not None:
        try:
            t = float(custom)
            if duration > 0:
                return max(0.5, min(t, duration - 0.5))
            return max(0.5, t)
        except (TypeError, ValueError):
            pass

    mode = (settings.get("youtube_thumbnail_mode") or "auto").strip().lower()
    if duration <= 0:
        return 2.0
    if mode == "middle":
        return max(1.0, duration * 0.5)
    if mode == "hook":
        return max(1.0, min(3.0, duration * 0.15))
    return max(1.0, duration * 0.15)


def _scale_enhance_vf() -> str:
    return (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "eq=contrast=1.18:brightness=0.02:saturation=1.35,"
        "unsharp=5:5:1.0:5:5:0.0"
    )


def _enhance_vf() -> str:
    return f"thumbnail,{_scale_enhance_vf()}"


def _extract_frame(video: Path, out: Path, settings: dict[str, Any]) -> bool:
    ensure_ffmpeg()
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False

    duration = media_duration_seconds(str(video))
    start = _pick_timestamp(settings, duration)
    scan_len = min(max(duration * 0.4, 3.0), max(duration - start, 3.0)) if duration > 0 else 8.0

    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        str(start),
        "-i",
        str(video.resolve()),
        "-t",
        str(scan_len),
        "-vf",
        _enhance_vf(),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(out.resolve()),
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=True)
        return out.is_file() and out.stat().st_size > 500
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"[thumbnail] cắt frame lỗi: {e}")
        return False


def _extract_frame_from_image(image: Path, out: Path, settings: dict[str, Any]) -> bool:
    ensure_ffmpeg()
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not image.is_file():
        return False
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(image.resolve()),
        "-vf",
        _scale_enhance_vf(),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(out.resolve()),
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=True)
        return out.is_file() and out.stat().st_size > 500
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"[thumbnail] avatar image lỗi: {e}")
        return False


def _wrap_lines(text: str, *, max_chars: int = 16, max_lines: int = 3) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    if "|" in raw or "\n" in raw:
        parts = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"[|\n]+", raw) if p.strip()]
        return [p.upper() for p in parts[:max_lines]]
    t = re.sub(r"\s+", " ", raw)
    parts = textwrap.wrap(t, width=max_chars, break_long_words=True, break_on_hyphens=True)
    return [p.upper() for p in parts[:max_lines]]


def _lines_from_title(title: str, topic: str, custom: str) -> list[str]:
    if custom.strip():
        return _wrap_lines(custom)

    raw = (title or topic or "WATCH THIS").strip()
    m = re.search(r"\*([^*]+)\*", raw)
    if m and len(m.group(1).strip()) >= 4:
        core = m.group(1).strip()
    else:
        core = re.sub(r"#\w+", "", raw, flags=re.I)
        core = core.split(".")[0].split("?")[0].strip()

    core = re.sub(r"\s+", " ", core)
    if len(core) > 42:
        words = core.split()
        core = " ".join(words[:6])

    lines = _wrap_lines(core, max_chars=18, max_lines=3)
    if not lines:
        lines = _wrap_lines(topic or "SHORTS", max_chars=18, max_lines=2)
    return lines


def _thumbnail_lines(
    settings: dict[str, Any],
    *,
    topic: str,
    title: str,
    brain: Any = None,
) -> tuple[list[str], str]:
    custom = str(settings.get("youtube_thumbnail_text") or "").strip()
    accent = str(settings.get("youtube_thumbnail_accent") or "WATCH").strip().upper()

    if custom:
        return _wrap_lines(custom), accent

    use_ai = settings.get("youtube_thumbnail_ai_text", True)
    if use_ai and brain is not None:
        try:
            data = brain.thumbnail_hook(topic, title)
            if isinstance(data, dict) and isinstance(data.get("lines"), list):
                lines = [
                    str(x).strip().upper()
                    for x in data["lines"]
                    if str(x).strip()
                ][:3]
                if lines:
                    acc = str(data.get("accent") or accent).strip().upper()[:12]
                    return lines, acc
        except Exception as e:
            print(f"[thumbnail-text] fallback: {e}")

    return _lines_from_title(title, topic, custom), accent


def _load_font(size: int):
    from PIL import ImageFont

    size = max(24, int(size))
    for path in FONT_CANDIDATES:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _measure(draw, text: str, font, *, anchor: str = "mm") -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font, anchor=anchor)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _fit_font(
    draw,
    text: str,
    max_w: int,
    start_px: int,
    *,
    min_px: int = 36,
    anchor: str = "mm",
):
    for size in range(start_px, min_px - 1, -2):
        font = _load_font(size)
        tw, _ = _measure(draw, text, font, anchor=anchor)
        if tw <= max_w:
            return font, size
    return _load_font(min_px), min_px


def _draw_centered_stroke(
    draw,
    cx: int,
    cy: int,
    text: str,
    font,
    *,
    fill: tuple[int, ...],
    stroke: tuple[int, ...] = (0, 0, 0),
    stroke_w: int = 5,
) -> None:
    """Vẽ chữ căn giữa (anchor mm) + viền đen (không phủ nền tối)."""
    for dx in range(-stroke_w, stroke_w + 1):
        for dy in range(-stroke_w, stroke_w + 1):
            if dx == 0 and dy == 0:
                continue
            draw.text(
                (cx + dx, cy + dy),
                text,
                font=font,
                fill=stroke + (255,) if len(stroke) == 3 else stroke,
                anchor="mm",
            )
    draw.text((cx, cy), text, font=font, fill=fill + (255,) if len(fill) == 3 else fill, anchor="mm")


def _draw_accent_pill(draw, cx: int, cy: int, text: str, font) -> None:
    tw, th = _measure(draw, text, font, anchor="mm")
    pad_x, pad_y = int(tw * 0.18) + 12, int(th * 0.35) + 6
    left = cx - tw // 2 - pad_x
    top = cy - th // 2 - pad_y
    right = cx + tw // 2 + pad_x
    bottom = cy + th // 2 + pad_y
    draw.rounded_rectangle(
        [left, top, right, bottom],
        radius=min(14, pad_y),
        fill=ACCENT_GOLD + (255,),
    )
    draw.text((cx, cy), text, font=font, fill=(18, 18, 18, 255), anchor="mm")


def _overlay_thumbnail_text(
    image_path: Path,
    lines: list[str],
    accent: str,
    *,
    settings: dict[str, Any] | None = None,
) -> bool:
    from PIL import Image, ImageDraw

    img = Image.open(image_path).convert("RGBA")
    w, h = img.size
    cx = w // 2
    draw = ImageDraw.Draw(img)

    if not lines:
        lines = ["WATCH THIS"]
    lines = [re.sub(r"\s+", " ", ln.strip().upper()) for ln in lines if ln.strip()][:3]
    accent = (accent or "WATCH").strip().upper()[:14]

    max_text_w = int(w * 0.88)
    n = len(lines)
    start_main = int(w * (0.096 if n <= 2 else 0.082))

    fitted: list[tuple[str, Any, int]] = []
    for line in lines:
        font, px = _fit_font(draw, line, max_text_w, start_main, min_px=40)
        _, lh = _measure(draw, line, font, anchor="mm")
        fitted.append((line, font, lh))

    accent_font, _ = _fit_font(
        draw, accent, int(w * 0.5), int(start_main * 0.48), min_px=28
    )
    _, accent_h = _measure(draw, accent, accent_font, anchor="mm")

    line_gap = int(start_main * 0.14)
    accent_gap = int(start_main * 0.42) + 28  # khoảng cách chữ chính → nút WATCH
    block_h = sum(lh for _, _, lh in fitted) + line_gap * max(n - 1, 0) + accent_h + accent_gap + 24

    s = settings or {}
    align = (s.get("youtube_thumbnail_text_align") or "center").strip().lower()
    if align == "top":
        try:
            pad = float(s.get("youtube_thumbnail_text_top_padding", 0.05))
        except (TypeError, ValueError):
            pad = 0.05
        y = int(h * max(0.02, min(0.12, pad)))
    elif align == "bottom":
        try:
            pad = float(s.get("youtube_thumbnail_text_bottom_padding", 0.05))
        except (TypeError, ValueError):
            pad = 0.05
        y = max(0, h - block_h - int(h * max(0.02, min(0.15, pad))))
    else:
        # center: vùng từ zone_top% → đáy, căn giữa khối (0.68 = cũ; nhỏ hơn = chữ cao hơn)
        try:
            zone_frac = float(s.get("youtube_thumbnail_text_zone_top", 0.68))
        except (TypeError, ValueError):
            zone_frac = 0.68
        zone_frac = max(0.38, min(0.78, zone_frac))
        zone_top = int(h * zone_frac)
        zone_h = h - zone_top
        y = zone_top + max((zone_h - block_h) // 2, 0)

    for i, (line, font, lh) in enumerate(fitted):
        cy = y + lh // 2
        _draw_centered_stroke(
            draw,
            cx,
            cy,
            line,
            font,
            fill=(255, 255, 255),
            stroke=(0, 0, 0),
            stroke_w=5,
        )
        y += lh + (line_gap if i < n - 1 else 0)

    pill_cy = y + accent_gap + accent_h // 2
    _draw_accent_pill(draw, cx, pill_cy, accent, accent_font)

    img.convert("RGB").save(image_path, "JPEG", quality=93, optimize=True)
    return True


def generate_thumbnail(
    video_path: str | Path,
    settings: dict[str, Any] | None = None,
    *,
    out_path: str | Path | None = None,
    topic: str = "",
    title: str = "",
    brain: Any = None,
) -> str | None:
    """Ảnh bìa Shorts: nền avatar PNG hoặc frame MP4 + chữ hook."""
    s = settings or {}
    if s.get("youtube_thumbnail_enabled") is False:
        return None

    video = Path(video_path)
    if not video.is_file():
        return None

    out = Path(out_path) if out_path else thumbnail_path_for(video)
    out.parent.mkdir(parents=True, exist_ok=True)
    raw_frame = out.with_name(f"{out.stem}_frame.jpg")

    source = (s.get("youtube_thumbnail_source") or "avatar_image").strip().lower()
    use_avatar = source in ("avatar", "avatar_image", "avatar_png")
    got = False
    if use_avatar:
        av_img = resolve_avatar_image_path(s)
        if av_img:
            got = _extract_frame_from_image(av_img, raw_frame, s)
            if got:
                print(f"[thumbnail] nền avatar: {av_img.name}")
    if not got:
        got = _extract_frame(video, raw_frame, s)
        if got and use_avatar:
            print("[thumbnail] không có ảnh avatar — fallback frame từ video")
    if not got:
        return None

    lines, accent = _thumbnail_lines(s, topic=topic, title=title, brain=brain)
    print(f"[thumbnail] text: {' | '.join(lines)} + {accent}")

    shutil.copy2(raw_frame, out)
    if not _overlay_thumbnail_text(out, lines, accent, settings=s):
        return str(raw_frame.resolve())

    try:
        raw_frame.unlink(missing_ok=True)
    except OSError:
        pass

    label = "avatar + text" if use_avatar else "frame + text"
    print(f"[thumbnail] {out.name} ({label})")
    return str(out.resolve())


def studio_edit_url(video_id: str) -> str:
    return f"https://studio.youtube.com/video/{video_id}/edit"


def _print_thumbnail_denied(video_id: str, image_path: Path, *, detail: str = "") -> None:
    print(
        "[thumbnail] YouTube từ chối (403).\n"
        "  • Video **Shorts**: YouTube KHÔNG cho tải ảnh bìa JPG (chỉ chọn khung trong video).\n"
        "    → Không có menu Feature eligibility / Custom thumbnails cho Shorts.\n"
        "    → Xem docs/YOUTUBE_SETUP.md — mục Ảnh bìa Shorts.\n"
        "  • Video **dài**: cần xác minh SĐT https://www.youtube.com/verify\n"
        "    rồi upload bìa trong Studio hoặc: python main.py set-thumbnail <ref>\n"
        f"  Studio: {studio_edit_url(video_id)}\n"
        f"  File local: {image_path.resolve()}"
    )
    if detail:
        print(f"  Chi tiết API: {detail[:300]}")


def upload_thumbnail(
    settings: dict[str, Any],
    video_id: str,
    image_path: str | Path,
) -> bool:
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    from app.youtube import _service

    path = Path(image_path)
    if not path.is_file() or not video_id:
        return False
    mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    try:
        _service(settings).thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(path), mimetype=mime, resumable=True),
        ).execute()
        print(f"[thumbnail] đã gắn lên YouTube: {path.name}")
        print(f"  {studio_edit_url(video_id)}")
        return True
    except HttpError as e:
        err = e.content.decode("utf-8", errors="replace") if e.content else str(e)
        low = err.lower()
        if e.resp.status == 403 or "forbidden" in low or "custom" in low and "thumbnail" in low:
            _print_thumbnail_denied(video_id, path, detail=err)
        else:
            print(f"[thumbnail] upload thất bại (HTTP {e.resp.status}): {err[:400]}")
        return False
    except Exception as e:
        err = str(e)
        if "403" in err or "forbidden" in err.lower():
            _print_thumbnail_denied(video_id, path, detail=err)
        else:
            print(f"[thumbnail] upload thất bại: {e}")
        return False
