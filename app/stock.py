from __future__ import annotations

import random

import requests

from app.settings import ROOT


class StockFootage:
    def __init__(
        self,
        api_keys: list[str],
        *,
        rng: random.Random | None = None,
        force_refresh: bool = False,
        per_page: int = 5,
    ) -> None:
        self.api_keys = [k.strip() for k in api_keys if k.strip()]
        if not self.api_keys:
            raise ValueError("Thiếu Pexels API key.")
        self._key_idx = 0
        self._rng = rng if rng is not None else random.Random()
        self._force_refresh = force_refresh
        try:
            self._per_page = max(3, min(30, int(per_page)))
        except (TypeError, ValueError):
            self._per_page = 5
        self.dir = ROOT / "assets" / "video_clips"
        self.dir.mkdir(parents=True, exist_ok=True)
        if len(self.api_keys) > 1:
            print(f"[stock] {len(self.api_keys)} key(s)")

    def _search(self, query: str, min_dur: int = 4) -> str | None:
        params = {
            "query": query,
            "per_page": self._per_page,
            "orientation": "portrait",
            "size": "medium",
        }
        try:
            for ki in range(len(self.api_keys)):
                idx = (self._key_idx + ki) % len(self.api_keys)
                r = requests.get(
                    "https://api.pexels.com/videos/search",
                    headers={"Authorization": self.api_keys[idx]},
                    params=params,
                    timeout=10,
                )
                if r.status_code in (401, 403, 429):
                    if ki + 1 < len(self.api_keys):
                        print(f"[stock] đổi key ({ki + 2}/{len(self.api_keys)})")
                    continue
                if r.status_code != 200:
                    return None
                self._key_idx = idx
                videos = r.json().get("videos") or []
                if not videos and " " in query:
                    return self._search(query.split()[-1], min_dur)
                if not videos:
                    return None
                pool = [v for v in videos if v.get("duration", 0) >= min_dur] or videos
                files = sorted(
                    self._rng.choice(pool)["video_files"],
                    key=lambda x: x["width"] * x["height"],
                    reverse=True,
                )
                return files[0]["link"]
        except requests.RequestException:
            pass
        return None

    def _download(self, url: str, name: str) -> str | None:
        path = self.dir / name
        if self._force_refresh and path.is_file():
            try:
                path.unlink()
            except OSError:
                pass
        if path.is_file():
            return str(path)
        try:
            with requests.get(url, stream=True, timeout=15) as r:
                r.raise_for_status()
                with open(path, "wb") as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
            return str(path)
        except requests.RequestException:
            return None

    def fetch_pairs(self, script: list) -> list:
        print("[stock] download clips")
        if self._force_refresh:
            for scene in script:
                sid = scene["id"]
                for suffix in ("a", "b"):
                    p = self.dir / f"scene_{sid}_{suffix}.mp4"
                    if p.is_file():
                        try:
                            p.unlink()
                        except OSError:
                            pass
        pairs = []
        for scene in script:
            sid = scene["id"]
            q1 = scene.get("visual_1", scene.get("keywords", "abstract"))
            q2 = scene.get("visual_2", q1)
            pa = self._download(u, f"scene_{sid}_a.mp4") if (u := self._search(q1)) else None
            pb = self._download(u, f"scene_{sid}_b.mp4") if (u := self._search(q2)) else None
            pa = pa or pb
            pb = pb or pa
            if pa and pb:
                pairs.append((pa, pb))
                print(f"  scene {sid}: ok")
            else:
                pairs.append(None)
                print(f"  scene {sid}: fail")
        return pairs
