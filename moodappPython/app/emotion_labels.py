from __future__ import annotations

from typing import Literal


EmotionLabel = Literal[
    "anxious",
    "stressed",
    "sad",
    "lonely",
    "fearful",
    "angry",
    "calm",
    "unknown",
]

EMOTION_LABELS: dict[str, str] = {
    "anxious": "焦虑",
    "stressed": "压力",
    "sad": "低落",
    "lonely": "孤独",
    "fearful": "恐惧",
    "angry": "愤怒",
    "calm": "平静",
    "unknown": "未知",
}

EMOTION_ALIASES: dict[str, EmotionLabel] = {
    "anxious": "anxious",
    "anxiety": "anxious",
    "焦虑": "anxious",
    "紧张": "anxious",
    "心慌": "anxious",
    "stressed": "stressed",
    "stress": "stressed",
    "overwhelmed": "stressed",
    "压力": "stressed",
    "疲惫": "stressed",
    "累": "stressed",
    "sad": "sad",
    "depressed": "sad",
    "depression": "sad",
    "hopeless": "sad",
    "低落": "sad",
    "悲伤": "sad",
    "难过": "sad",
    "沮丧": "sad",
    "抑郁": "sad",
    "绝望": "sad",
    "lonely": "lonely",
    "loneliness": "lonely",
    "孤独": "lonely",
    "孤单": "lonely",
    "fearful": "fearful",
    "fear": "fearful",
    "afraid": "fearful",
    "恐惧": "fearful",
    "害怕": "fearful",
    "angry": "angry",
    "anger": "angry",
    "愤怒": "angry",
    "生气": "angry",
    "calm": "calm",
    "neutral": "calm",
    "平静": "calm",
    "中性": "calm",
    "正常": "calm",
    "unknown": "unknown",
    "未知": "unknown",
}


def normalize_emotion_label(value: object) -> EmotionLabel:
    text = str(value or "").strip().lower()
    return EMOTION_ALIASES.get(text, "unknown")


def emotion_display_name(value: object) -> str:
    return EMOTION_LABELS[normalize_emotion_label(value)]
