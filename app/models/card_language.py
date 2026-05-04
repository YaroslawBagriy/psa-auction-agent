from __future__ import annotations

from enum import Enum


class CardLanguage(str, Enum):
    ENGLISH = "English"
    JAPANESE = "Japanese"
    KOREAN = "Korean"
    CHINESE_SIMPLIFIED = "Chinese Simplified"
    CHINESE_TRADITIONAL = "Chinese Traditional"
    CHINESE = "Chinese"
    SPANISH = "Spanish"
    FRENCH = "French"
    GERMAN = "German"
    ITALIAN = "Italian"
    PORTUGUESE = "Portuguese"
    THAI = "Thai"
    INDONESIAN = "Indonesian"

    @property
    def display_name(self) -> str:
        return self.value
