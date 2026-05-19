from __future__ import annotations

import asyncio

import edge_tts
from mutagen.mp3 import MP3

from app.settings import ROOT


class AudioEngine:
    def __init__(self, voice: str, speech_rate: str) -> None:
        self.voice = voice
        self.rate = speech_rate
        self.out_dir = ROOT / "assets" / "audio_clips"
        self.out_dir.mkdir(parents=True, exist_ok=True)

    async def _tts(self, text: str, name: str, retries: int = 3) -> str:
        path = self.out_dir / name
        for i in range(retries):
            try:
                await edge_tts.Communicate(text, self.voice, rate=self.rate).save(str(path))
                return str(path)
            except Exception:
                if i < retries - 1:
                    await asyncio.sleep(2)
                    continue
                raise
        raise RuntimeError("audio failed")

    @staticmethod
    def _duration(path: str) -> float:
        try:
            return MP3(path).info.length
        except Exception:
            return 0.0

    async def process(self, script: list) -> list:
        print(f"[audio] {len(script)} scenes | {self.voice}")
        for scene in script:
            sid = scene["id"]
            try:
                path = await self._tts(scene["text"], f"voice_{sid}.mp3")
                scene["audio_path"] = path
                scene["duration"] = self._duration(path)
                print(f"  scene {sid}: {scene['duration']:.1f}s")
                await asyncio.sleep(1)
            except Exception as e:
                print(f"  scene {sid} skip: {e}")
        return script
