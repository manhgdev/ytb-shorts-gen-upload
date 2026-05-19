"""
Chèn vài giây ảnh bìa (JPG đã render) vào đầu MP4 Shorts.

Feed Shorts thường phát từ frame đầu — hook nằm ở đầu file sẽ thấy ngay,
không phụ thuộc thumbnail tĩnh trên lưới/tìm kiếm.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.utils import ensure_ffmpeg, media_audio_stream0, media_duration_seconds, media_video_size

SHORTS_MAX_TOTAL = 60.0
INTRO_MIN = 0.35


def maybe_prepend_thumbnail_intro(
    video_path: str | Path,
    thumb_jpg: str | Path,
    settings: dict[str, Any] | None = None,
) -> str:
    """
    Ghép ~N giây slide từ thumb_jpg vào đầu video_path (ghi đè file).

    Trả về đường dẫn cuối (giữ nguyên nếu bỏ qua / lỗi).
    """
    s = settings or {}
    try:
        want = float(s.get("shorts_hook_intro_seconds", 0.85))
    except (TypeError, ValueError):
        want = 0.85

    vp = Path(video_path)
    jp = Path(thumb_jpg)
    if want <= 0 or not vp.is_file() or not jp.is_file():
        return str(vp.resolve())

    if not s.get("shorts_hook_intro_force") and not s.get("shorts_hook_intro_from_pipeline"):
        meta_path = vp.with_name(f"{vp.stem}.meta.json")
        if meta_path.is_file():
            try:
                prev = json.loads(meta_path.read_text(encoding="utf-8"))
                applied = float(prev.get("shorts_hook_intro_applied_sec") or 0)
                if applied >= INTRO_MIN - 0.05:
                    print(
                        "[shorts-intro] đã chèn intro trước (theo .meta.json) — bỏ qua. "
                        "hook-intro --force để chèn lại, hoặc xóa key shorts_hook_intro_applied_sec trong meta."
                    )
                    return str(vp.resolve())
            except (json.JSONDecodeError, ValueError, OSError):
                pass

    w, h = media_video_size(str(vp))
    is_vertical_short = (w, h) == (1080, 1920)
    if (s.get("video_mode") or "short") != "short" and not is_vertical_short:
        return str(vp.resolve())

    main_dur = media_duration_seconds(str(vp))
    if main_dur <= 0:
        return str(vp.resolve())

    intro_dur = min(max(want, INTRO_MIN), 2.5)
    if main_dur + intro_dur > SHORTS_MAX_TOTAL:
        intro_dur = max(INTRO_MIN, SHORTS_MAX_TOTAL - main_dur - 0.05)
    if intro_dur < INTRO_MIN:
        print("[shorts-intro] bỏ qua: video đã gần 60s")
        return str(vp.resolve())

    ensure_ffmpeg()
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return str(vp.resolve())

    sr, _ch = media_audio_stream0(str(vp))
    # Luôn stereo im lặng cho intro — concat ổn với AAC stereo của scene
    sr = max(8000, sr)
    a_ch = 2

    tmp_intro = vp.with_name(f"{vp.stem}_intro_seg.mp4")
    tmp_out = vp.with_name(f"{vp.stem}_with_intro_tmp.mp4")

    for p in (tmp_intro, tmp_out):
        try:
            if p.is_file():
                p.unlink()
        except OSError:
            pass

    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,format=yuv420p,fps=30"
    )

    cmd_intro = [
        ffmpeg,
        "-y",
        "-loop",
        "1",
        "-framerate",
        "30",
        "-i",
        str(jp.resolve()),
        "-f",
        "lavfi",
        "-i",
        f"anullsrc=channel_layout=stereo:sample_rate={sr}",
        "-t",
        f"{intro_dur:.3f}",
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-ar",
        str(sr),
        "-ac",
        str(a_ch),
        "-shortest",
        str(tmp_intro.resolve()),
    ]

    try:
        subprocess.run(cmd_intro, capture_output=True, text=True, timeout=180, check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        err = getattr(e, "stderr", None) or str(e)
        print(f"[shorts-intro] tạo intro lỗi: {err[:400]}")
        tmp_intro.unlink(missing_ok=True)
        return str(vp.resolve())

    cmd_cat = [
        ffmpeg,
        "-y",
        "-i",
        str(tmp_intro.resolve()),
        "-i",
        str(vp.resolve()),
        "-filter_complex",
        (
            f"[0:a]aresample={sr},aformat=sample_rates={sr}:channel_layouts=stereo[a0];"
            f"[1:a]aresample={sr},aformat=sample_rates={sr}:channel_layouts=stereo[a1];"
            "[0:v][a0][1:v][a1]concat=n=2:v=1:a=1[v][a]"
        ),
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(tmp_out.resolve()),
    ]

    try:
        subprocess.run(cmd_cat, capture_output=True, text=True, timeout=600, check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        err = getattr(e, "stderr", None) or str(e)
        print(f"[shorts-intro] ghép intro lỗi: {err[:400]}")
        tmp_intro.unlink(missing_ok=True)
        tmp_out.unlink(missing_ok=True)
        return str(vp.resolve())

    tmp_intro.unlink(missing_ok=True)
    try:
        os.replace(tmp_out, vp)
    except OSError as e:
        print(f"[shorts-intro] không thay file: {e}")
        tmp_out.unlink(missing_ok=True)
        return str(vp.resolve())

    new_dur = media_duration_seconds(str(vp))
    print(f"[shorts-intro] đã chèn {intro_dur:.2f}s ảnh bìa đầu video → {vp.name} (≈{new_dur:.1f}s)")
    return str(vp.resolve())
