from __future__ import annotations

import os
import random

import ffmpeg

from app.settings import AVATAR_IMAGE, AVATAR_VIDEO, ROOT
from app.utils import media_duration_seconds, resolve_path

_IMG = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


class Composer:
    def __init__(self, settings: dict | None = None, rng: random.Random | None = None) -> None:
        s = settings or {}
        self._rng = rng if rng is not None else random.Random()
        self.temp = ROOT / "assets" / "temp"
        out = (s.get("output_dir") or "").strip()
        self.final_dir = resolve_path(out) if out else str(ROOT / "assets" / "final")

        mode = (s.get("avatar_mode") or "default").strip().lower()
        if mode not in ("off", "default", "custom"):
            mode = "default"

        self.avatar_video = self.avatar_image = None
        if mode == "default":
            for rel, attr in ((AVATAR_VIDEO, "avatar_video"), (AVATAR_IMAGE, "avatar_image")):
                p = resolve_path(rel)
                if os.path.isfile(p):
                    setattr(self, attr, p)
        elif mode == "custom":
            for key, attr in (("avatar_video_path", "avatar_video"), ("avatar_image_path", "avatar_image")):
                raw = (s.get(key) or "").strip()
                if raw:
                    p = resolve_path(raw)
                    if os.path.isfile(p):
                        setattr(self, attr, p)

        try:
            self.avatar_scenes = max(0, int(s.get("avatar_scenes", 2)))
        except (TypeError, ValueError):
            self.avatar_scenes = 2

        self._settings = s
        self.temp.mkdir(parents=True, exist_ok=True)
        os.makedirs(self.final_dir, exist_ok=True)
        self._xfade = ["fade", "diagbr", "diagtl"]

    def _avatar_scene_indices_0based(self, n_scenes: int) -> list[int] | None:
        """Trả về index 0-based cho cảnh avatar, hoặc None → random."""
        from app.render_random import parse_avatar_scene_numbers

        nums = parse_avatar_scene_numbers(self._settings.get("avatar_scene_numbers"))
        if not nums:
            return None
        mid = set(range(1, n_scenes - 1))
        out: list[int] = []
        for one_based in nums:
            i = int(one_based) - 1
            if i in mid and i not in out:
                out.append(i)
            if len(out) >= self.avatar_scenes:
                break
        return sorted(out) if out else None

    def _avatar(self) -> str | None:
        if self.avatar_video and os.path.isfile(self.avatar_video):
            return self.avatar_video
        if self.avatar_image and os.path.isfile(self.avatar_image):
            return self.avatar_image
        return None

    def _render_scene(self, scene: dict, pair: tuple, avatar: bool) -> str | None:
        sid, audio, dur = scene["id"], scene["audio_path"], scene["duration"]
        out = self.temp / f"scene_{sid}.mp4"
        try:
            ain = ffmpeg.input(audio)
            if avatar:
                ap = pair[0]
                vin = (
                    ffmpeg.input(ap, loop=1, framerate=30)
                    if os.path.splitext(ap)[1].lower() in _IMG
                    else ffmpeg.input(ap, stream_loop=-1)
                )
                vid = (
                    vin.trim(duration=dur + 0.5)
                    .setpts("PTS-STARTPTS")
                    .filter("crop", "iw", "ih-150", 0, 0)
                    .filter("scale", 1080, 1920, force_original_aspect_ratio="increase")
                    .filter("crop", 1080, 1920)
                    .filter("fps", fps=30, round="up")
                )
            else:
                a, b = pair
                da, db = dur / 2, dur / 2 + 0.5
                sa = (
                    ffmpeg.input(a, stream_loop=-1)
                    .trim(duration=da)
                    .setpts("PTS-STARTPTS")
                    .filter("scale", 1080, 1920)
                    .filter("crop", 1080, 1920)
                    .filter("fps", fps=30, round="up")
                )
                sb = (
                    ffmpeg.input(b, stream_loop=-1)
                    .trim(duration=db)
                    .setpts("PTS-STARTPTS")
                    .filter("scale", 1080, 1920)
                    .filter("crop", 1080, 1920)
                    .filter("fps", fps=30, round="up")
                )
                vid = ffmpeg.concat(sa, sb, v=1, a=0)
            ffmpeg.output(
                vid, ain, str(out), vcodec="libx264", acodec="aac", pix_fmt="yuv420p", shortest=None
            ).run(overwrite_output=True, quiet=True)
            return str(out)
        except ffmpeg.Error as e:
            err = e.stderr.decode("utf8") if e.stderr else str(e)
            print(f"[render] scene {sid}: {err[:200]}")
            return None

    def render(self, script: list, pairs: list) -> list[str]:
        paths: list[str] = []
        av = self._avatar()
        av_idx: list[int] = []
        if len(script) >= 4 and av and self.avatar_scenes > 0:
            mid = list(range(1, len(script) - 1))
            n = min(self.avatar_scenes, len(mid))
            explicit = self._avatar_scene_indices_0based(len(script))
            if explicit is not None:
                av_idx = explicit
            else:
                av_idx = sorted(self._rng.sample(mid, n))
            print(f"[avatar] scenes {[i + 1 for i in av_idx]}")

        for i, scene in enumerate(script):
            pair = pairs[i]
            use_av = i in av_idx
            if use_av:
                pair = (av, None)
            elif pair is None:
                continue
            p = self._render_scene(scene, pair, use_av)
            if p:
                paths.append(p)
        return paths

    def stitch(self, scenes: list[str], name: str = "final_short.mp4") -> str | None:
        if not scenes:
            return None
        out = os.path.join(self.final_dir, name)
        print("[stitch] ghép video...")
        if os.path.isfile(out):
            try:
                os.remove(out)
            except OSError:
                pass

        v = ffmpeg.input(scenes[0]).video
        a = ffmpeg.input(scenes[0]).audio
        cur = media_duration_seconds(scenes[0])
        for path in scenes[1:]:
            nxt = ffmpeg.input(path)
            td, off = 0.5, cur - 0.5
            v = ffmpeg.filter([v, nxt.video], "xfade", transition=self._rng.choice(self._xfade), duration=td, offset=off)
            a = ffmpeg.filter([a, nxt.audio], "acrossfade", d=td)
            cur += media_duration_seconds(path) - td

        ffmpeg.output(
            v, a, out, vcodec="libx264", acodec="aac", pix_fmt="yuv420p", movflags="faststart", preset="medium"
        ).run(overwrite_output=True, quiet=False)
        print(f"[done] {out}")
        return out
