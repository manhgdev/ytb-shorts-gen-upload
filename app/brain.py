from __future__ import annotations

import json
import time

from google import genai

# Key bị flag tạm — bỏ qua đến hết cooldown (giây)
_COOLDOWN_QUOTA = 15 * 60
_COOLDOWN_OVERLOAD = 3 * 60
_COOLDOWN_BAD_KEY = 24 * 60 * 60


class ContentBrain:
    def __init__(
        self,
        api_keys: list[str],
        model_chain: list[str],
        topic_prompt: str,
        video_cfg: dict,
        script_extra_instructions: str = "",
        language: str = "en",
        retry_delay_seconds: int = 60,
        max_retries: int = 4,
    ):
        keys = [k.strip() for k in api_keys if k.strip()]
        models = [m.strip() for m in model_chain if m.strip()]
        if not keys:
            raise ValueError("Thiếu Gemini API key.")
        if not models:
            raise ValueError("Không có model Gemini.")

        self.api_keys = keys
        self.model_chain = models
        self.video_cfg = video_cfg
        self._key_idx = 0
        self._model_idx = 0
        self.model_name = models[0]
        self.topic_used: str | None = None
        self._clients: dict[str, genai.Client] = {}
        self.topic_prompt = topic_prompt.strip()
        self.script_extra_instructions = script_extra_instructions.strip()
        self.language = language if language in ("en", "vi") else "en"
        self._retry_delay = max(1, int(retry_delay_seconds))
        self._max_retries = max(1, int(max_retries))
        self._key_cooldown: dict[str, float] = {}
        print(f"[brain] {' -> '.join(models)} | {len(keys)} key(s) | lang={self.language}")

    def _client(self, key: str) -> genai.Client:
        if key not in self._clients:
            self._clients[key] = genai.Client(api_key=key)
        return self._clients[key]

    @staticmethod
    def _quota(err: str) -> bool:
        low = err.lower()
        return (
            "429" in err
            or "RESOURCE_EXHAUSTED" in err
            or "quota" in low
            or "rate limit" in low
            or "rate_limit" in low
        )

    @staticmethod
    def _overload(err: str) -> bool:
        low = err.lower()
        return (
            "503" in err
            or "unavailable" in low
            or "high demand" in low
            or "overloaded" in low
            or "temporarily" in low and "try again" in low
        )

    @staticmethod
    def _bad_key(err: str) -> bool:
        low = err.lower()
        return any(x in err or x in low for x in ("401", "403", "API_KEY", "PERMISSION_DENIED", "invalid api key"))

    @staticmethod
    def _bad_model(err: str) -> bool:
        low = err.lower()
        return any(x in err or x in low for x in ("404", "NOT_FOUND", "unsupported"))

    def _mask_key(self, key: str) -> str:
        if len(key) <= 12:
            return key[:4] + "…"
        return f"{key[:6]}…{key[-4:]}"

    def _flag_key(self, key: str, seconds: float, reason: str) -> None:
        until = time.time() + seconds
        self._key_cooldown[key] = max(self._key_cooldown.get(key, 0), until)
        print(f"[brain] flag key {self._mask_key(key)} ({reason}, ~{int(seconds)}s)")

    def _key_ready(self, key: str) -> bool:
        return time.time() >= self._key_cooldown.get(key, 0)

    def _next_ready_key_index(self, start: int) -> int | None:
        n = len(self.api_keys)
        for offset in range(n):
            ki = (start + offset) % n
            if self._key_ready(self.api_keys[ki]):
                return ki
        return None

    def _wait_for_any_key(self) -> None:
        if not self._key_cooldown:
            return
        now = time.time()
        wait = min(until - now for until in self._key_cooldown.values() if until > now)
        if wait > 0:
            print(f"[brain] tất cả key đang flag — đợi {int(wait) + 1}s…")
            time.sleep(min(wait + 1, self._retry_delay))

    def _generate(self, contents: str):
        last_err: Exception | None = None
        delay = self._retry_delay

        for mi in range(self._model_idx, len(self.model_chain)):
            model = self.model_chain[mi]
            ki = self._key_idx if mi == self._model_idx else 0
            keys_tried = 0

            while keys_tried < len(self.api_keys):
                ready = self._next_ready_key_index(ki)
                if ready is None:
                    self._wait_for_any_key()
                    ready = self._next_ready_key_index(0)
                    if ready is None:
                        break

                ki = ready
                key = self.api_keys[ki]
                keys_tried += 1

                for attempt in range(self._max_retries):
                    try:
                        resp = self._client(key).models.generate_content(model=model, contents=contents)
                        self._model_idx, self._key_idx, self.model_name = mi, ki, model
                        return resp
                    except Exception as e:
                        last_err = e
                        err = str(e)

                        if self._bad_key(err):
                            self._flag_key(key, _COOLDOWN_BAD_KEY, "key lỗi")
                            print(f"[brain] đổi key ({keys_tried}/{len(self.api_keys)})")
                            break

                        if self._quota(err):
                            self._flag_key(key, _COOLDOWN_QUOTA, "quota")
                            print(f"[brain] đổi key — quota ({keys_tried}/{len(self.api_keys)})")
                            break

                        if self._overload(err):
                            self._flag_key(key, _COOLDOWN_OVERLOAD, "503/busy")
                            print(f"[brain] đổi key — 503 ({keys_tried}/{len(self.api_keys)})")
                            break

                        if self._bad_model(err):
                            print(f"[brain] model không khả dụng: {model}")
                            break

                        if attempt < self._max_retries - 1:
                            print(f"[brain] thử lại {delay}s ({attempt + 1}/{self._max_retries})")
                            time.sleep(delay)
                            continue
                        raise

                if last_err and self._bad_model(str(last_err)):
                    break

            self._key_idx = 0
            if mi + 1 < len(self.model_chain):
                print(f"[brain] đổi model -> {self.model_chain[mi + 1]}")
                time.sleep(min(delay, 5))

        if last_err:
            raise last_err
        raise RuntimeError("generate_content failed — hết key/model khả dụng")

    def topic(self) -> str:
        if not self.topic_prompt:
            raise ValueError("topic_prompt trống.")
        t = self._generate(self.topic_prompt).text.strip()
        self.topic_used = t
        print(f"[topic] {t}")
        return t

    def script(self, topic: str) -> list | None:
        cfg = self.video_cfg
        extra = ""
        if self.script_extra_instructions:
            extra = f"\n### USER INSTRUCTIONS:\n{self.script_extra_instructions}\n"
        if self.language == "vi":
            lang_block = """
- Lời thoại (field "text") viết hoàn toàn bằng tiếng Việt tự nhiên, ngắn gọn, dễ nghe.
- visual_1 và visual_2: cụm tìm kiếm tiếng Anh ngắn cho Pexels (ví dụ "ocean waves", "scientist lab").
"""
            header = "Bạn là biên kịch YouTube Shorts giáo dụng giải trí, giữ chân người xem cao."
        else:
            lang_block = """
- Narration ("text") in natural English.
- visual_1 and visual_2: short English Pexels search terms.
"""
            header = "You are the lead scriptwriter for a high-retention Edutainment YouTube Shorts channel."
        prompt = f"""
{header}
Topic: {topic}

Create a script where every scene has TWO stock video search terms (visual_1, visual_2).
- Fast-paced, {cfg["min_scenes"]}-{cfg["max_scenes"]} scenes, {cfg["words_per_scene"]} words per scene.
- Structure: Hook -> Context -> Mechanism -> Twist -> Outro.
{lang_block}
{extra}
Output strict JSON array only:
[{{"id": 1, "text": "...", "visual_1": "...", "visual_2": "...", "mood": "..."}}]
"""
        print(f"[script] {topic}")
        raw = self._generate(prompt).text.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            print("[script] JSON lỗi:", raw[:500])
            return None

    def youtube_seo(self, topic: str, script: list, extra_instructions: str = "") -> dict | None:
        """Tiêu đề / mô tả / tag tối ưu Shorts (SEO + hashtag)."""
        lines = []
        for scene in script:
            if isinstance(scene, dict):
                t = str(scene.get("text") or "").strip()
                if t:
                    lines.append(t)
        summary = " ".join(lines)[:1400]
        extra = ""
        if extra_instructions.strip():
            extra = f"\n### EXTRA:\n{extra_instructions.strip()}\n"
        if self.language == "vi":
            lang = "Tiếng Việt (title, description, hashtags); tags YouTube có thể mix EN niche."
            examples = (
                'Ví dụ hook title: "99% người không biết...", "Sự thật về...", "3 điều khiến bạn..."'
            )
        else:
            lang = "English"
            examples = 'Title hooks e.g. "Nobody talks about...", "The real reason...", "3 facts that..."'
        prompt = f"""
You are a YouTube Shorts SEO specialist (CTR + search keywords + hashtags). Be accurate to the video—no false clickbait.

Topic: {topic}
Narration (from script):
{summary or topic}

Language for title & description: {lang}
{examples}

Requirements:
- title_variants: exactly 5 different titles (max 95 chars each). Vary formula: curiosity gap, number/list, how-to, shock-but-true, question. Include main keyword. At most one variant may end with #Shorts.
- title: your single best pick from those variants.
- description: 2 hook lines with keywords; blank line; 12–18 hashtags on their own lines (#Shorts #shortsfeed #fyp + niche + topic); short CTA (subscribe/comment).
- tags: 18–25 YouTube API tags (no #), mix broad + niche + long-tail.
- hashtags: same hashtag strings as in description (with #), for UI.

Trending style: use phrases people search (how/why/secret/facts), not generic spam only.
{extra}
Output strict JSON only:
{{"title":"","title_variants":["","","","",""],"description":"","tags":[],"hashtags":[]}}
"""
        print(f"[youtube-seo] {topic[:60]}")
        raw = self._generate(prompt).text.replace("```json", "").replace("```", "").strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            print("[youtube-seo] JSON lỗi:", raw[:400])
            return None
        if not isinstance(data, dict):
            return None
        return data

    def thumbnail_hook(self, topic: str, title: str) -> dict | None:
        """2–3 dòng chữ ngắn cho ảnh bìa Shorts (CTR)."""
        clean_title = (title or "").replace("*", "").replace("#Shorts", "").strip()[:120]
        if self.language == "vi":
            lang = "Tiếng Việt, CHỮ IN HOA, tối đa 3 dòng, mỗi dòng ≤18 ký tự"
            ex = '{"lines":["DÒNG 1","DÒNG 2"],"accent":"#Shorts"}'
        else:
            lang = "English, ALL CAPS, max 3 lines, ≤18 chars per line"
            ex = '{"lines":["LINE ONE","LINE TWO"],"accent":"WATCH"}'
        prompt = f"""
You write YouTube Shorts THUMBNAIL text only — huge bold text on image, must pop and match video.

Topic: {topic}
Video title: {clean_title}

Rules:
- 2 or 3 short lines, {lang}
- Curiosity hook, keyword from topic, NO false clickbait
- No emoji, no quotes inside lines
- accent: 1 short word (WATCH / NEW / #Shorts style)

Output strict JSON only:
{ex}
"""
        print(f"[thumbnail-text] {topic[:50]}")
        raw = self._generate(prompt).text.replace("```json", "").replace("```", "").strip()
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and isinstance(data.get("lines"), list):
                return data
        except json.JSONDecodeError:
            print("[thumbnail-text] JSON lỗi:", raw[:200])
        return None
