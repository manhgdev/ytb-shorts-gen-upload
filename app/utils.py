from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from app.settings import ROOT


def resolve_path(raw: str) -> str:
    p = (raw or "").strip()
    if not p:
        return ""
    path = Path(p)
    if path.is_absolute():
        return str(path.resolve())
    return str((ROOT / path).resolve())


def ensure_ffmpeg() -> None:
    try:
        import imageio_ffmpeg

        bindir = os.path.dirname(os.path.abspath(imageio_ffmpeg.get_ffmpeg_exe()))
        path = os.environ.get("PATH", "")
        if bindir and bindir not in path.split(os.pathsep):
            os.environ["PATH"] = bindir + os.pathsep + path
    except Exception:
        pass
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "Không tìm thấy ffmpeg. Cài: sudo apt install ffmpeg "
            "hoặc pip install imageio-ffmpeg."
        )


def media_duration_seconds(filepath: str) -> float:
    if not filepath or not os.path.isfile(filepath):
        return 0.0
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        try:
            out = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    filepath,
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if out.returncode == 0 and (out.stdout or "").strip():
                return float(out.stdout.strip())
        except (ValueError, subprocess.TimeoutExpired, OSError):
            pass
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return 0.0
    try:
        p = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", filepath],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return 0.0
    err = (p.stderr or "") + (p.stdout or "")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", err)
    if not m:
        return 0.0
    h, mi, s = float(m.group(1)), float(m.group(2)), float(m.group(3))
    return h * 3600 + mi * 60 + s


def media_video_size(filepath: str) -> tuple[int, int]:
    """(width, height) của stream video đầu tiên; (0,0) nếu không đọc được."""
    if not filepath or not os.path.isfile(filepath):
        return 0, 0
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 0, 0
    try:
        out = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=p=0:s=x",
                filepath,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if out.returncode == 0 and "x" in (out.stdout or ""):
            w, h = (out.stdout or "").strip().split("x", 1)
            return int(w), int(h)
    except (ValueError, subprocess.TimeoutExpired, OSError):
        pass
    return 0, 0


def media_audio_stream0(filepath: str) -> tuple[int, int]:
    """Luồng audio đầu tiên: (sample_rate, channels). Mặc định (48000, 2)."""
    if not filepath or not os.path.isfile(filepath):
        return 48000, 2
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 48000, 2
    try:
        out = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=sample_rate,channels",
                "-of",
                "json",
                filepath,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if out.returncode != 0 or not (out.stdout or "").strip():
            return 48000, 2
        data = json.loads(out.stdout)
        streams = data.get("streams") or []
        if not streams:
            return 48000, 2
        s0 = streams[0]
        rate = int(s0.get("sample_rate") or 48000)
        ch = int(s0.get("channels") or 2)
        return max(8000, rate), max(1, min(ch, 8))
    except (json.JSONDecodeError, ValueError, TypeError, subprocess.TimeoutExpired, OSError):
        return 48000, 2
