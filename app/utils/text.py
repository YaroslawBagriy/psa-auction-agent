from __future__ import annotations

import re
from difflib import SequenceMatcher


NON_ALPHANUMERIC_PATTERN = re.compile(r"[^a-z0-9]+")


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = NON_ALPHANUMERIC_PATTERN.sub(" ", value.lower())
    return " ".join(normalized.split())


def contains_normalized_phrase(text: str | None, phrase: str) -> bool:
    normalized_text = normalize_text(text)
    normalized_phrase = normalize_text(phrase)
    return normalized_phrase in normalized_text


def similarity_score(left: str | None, right: str | None) -> float:
    return SequenceMatcher(a=normalize_text(left), b=normalize_text(right)).ratio()
