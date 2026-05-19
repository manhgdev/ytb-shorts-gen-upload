"""Giá trị mặc định hệ thống — có thể ghi đè qua settings / API body."""

DEFAULT_GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-flash-lite",
]

VIDEO_PRESETS = {
    "short": {"min_scenes": 8, "max_scenes": 9, "words_per_scene": "10-15"},
    "long": {"min_scenes": 10, "max_scenes": 12, "words_per_scene": "15-20"},
}

LOCALES = {
    "en": {
        "voice": "en-US-AvaNeural",
        "speech_rate": "+10%",
        "output_filename": "final_short.mp4",
        "topic_prompt": (
            "Give me 1 specific, viral, engaging topic for a Short Documentary. "
            "Did-you-know fact or intriguing news. Return ONLY the topic name."
        ),
    },
    "vi": {
        "voice": "vi-VN-HoaiMyNeural",
        "speech_rate": "+5%",
        "output_filename": "final_short_vi.mp4",
        "topic_prompt": (
            "Cho tôi 1 chủ đề cụ thể, dễ viral cho Short Documentary tiếng Việt. "
            "Dạng 'Bạn có biết' hoặc tin lạ hấp dẫn. CHỈ trả về tên chủ đề, không giải thích."
        ),
    },
}
