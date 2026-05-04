from __future__ import annotations

import re
from typing import Any

from app.models.card_language import CardLanguage
from app.models.listing import Listing, RawListing
from app.models.pokemon import Pokemon
from app.utils.text import contains_normalized_phrase, normalize_text

GRADE_PATTERN = re.compile(r"\bpsa[\s:-]*(\d{1,2}(?:\.\d)?)\b", re.IGNORECASE)
CARD_NUMBER_PATTERNS = (
    re.compile(r"#\s*([A-Z0-9-]+)", re.IGNORECASE),
    re.compile(r"\b(\d{1,3}/\d{1,3})\b", re.IGNORECASE),
)
CARD_SUBJECT_STOP_PATTERN = re.compile(
    r"\b(?:psa|cgc|bgs|sgc|gem mint|mint|auth|auto|autograph)\b",
    re.IGNORECASE,
)
LANGUAGE_KEY_PATTERN = re.compile(r"\blanguage\b", re.IGNORECASE)
LANGUAGE_PATTERNS: tuple[tuple[CardLanguage, re.Pattern[str]], ...] = (
    (CardLanguage.CHINESE_SIMPLIFIED, re.compile(r"\bsimplified\s+chinese\b", re.IGNORECASE)),
    (CardLanguage.CHINESE_TRADITIONAL, re.compile(r"\btraditional\s+chinese\b", re.IGNORECASE)),
    (CardLanguage.JAPANESE, re.compile(r"\b(?:japanese|jpn|jp)\b", re.IGNORECASE)),
    (CardLanguage.ENGLISH, re.compile(r"\benglish\b", re.IGNORECASE)),
    (CardLanguage.KOREAN, re.compile(r"\b(?:korean|kor|kr)\b", re.IGNORECASE)),
    (CardLanguage.CHINESE, re.compile(r"\bchinese\b", re.IGNORECASE)),
    (CardLanguage.SPANISH, re.compile(r"\b(?:spanish|spa|sp)\b", re.IGNORECASE)),
    (CardLanguage.FRENCH, re.compile(r"\b(?:french|fre)\b", re.IGNORECASE)),
    (CardLanguage.GERMAN, re.compile(r"\b(?:german|ger)\b", re.IGNORECASE)),
    (CardLanguage.ITALIAN, re.compile(r"\b(?:italian|ita)\b", re.IGNORECASE)),
    (CardLanguage.PORTUGUESE, re.compile(r"\b(?:portuguese|por)\b", re.IGNORECASE)),
    (CardLanguage.THAI, re.compile(r"\bthai\b", re.IGNORECASE)),
    (CardLanguage.INDONESIAN, re.compile(r"\bindonesian\b", re.IGNORECASE)),
)
PSA_ENGLISH_SET_CODE_PATTERN = re.compile(r"\b[A-Z0-9]{2,5}\s+EN[-\s][A-Z0-9]", re.IGNORECASE)


class ListingParser:
    def parse(self, raw_listing: RawListing) -> Listing:
        searchable_fragments = self.collect_searchable_fragments(raw_listing)
        combined_text = " ".join(fragment for _, fragment in searchable_fragments)
        vault_evidence = self.detect_vault_evidence(raw_listing)

        normalized_title = normalize_text(raw_listing.title)
        detected_pokemon = self.detect_pokemon(raw_listing.title)
        if detected_pokemon is None and self.extract_card_subject_fragment(raw_listing.title) is None:
            detected_pokemon = self.detect_pokemon(combined_text)
        grading_company = self.detect_grading_company(raw_listing.title)
        grade_value = self.extract_grade(raw_listing.title)
        card_language = self.detect_card_language(raw_listing, combined_text)
        set_name = raw_listing.set_name or self.extract_set_name(raw_listing.title, detected_pokemon)
        card_number = self.extract_card_number(raw_listing.title)
        is_pokemon_related = self.is_pokemon_related(raw_listing, detected_pokemon)

        return Listing(
            listing_id=raw_listing.listing_id,
            ebay_restful_item_id=raw_listing.ebay_restful_item_id,
            title=raw_listing.title,
            seller_name=raw_listing.seller_name,
            url=raw_listing.url,
            is_auction=raw_listing.is_auction,
            current_price=raw_listing.current_price,
            currency=raw_listing.currency,
            end_time=raw_listing.end_time,
            grading_company=grading_company,
            grade_value=grade_value,
            detected_pokemon=detected_pokemon,
            card_language=card_language,
            set_name=set_name,
            card_number=card_number,
            in_psa_vault=bool(vault_evidence),
            vault_evidence=vault_evidence,
            market_context=raw_listing.market_context,
            is_pokemon_related=is_pokemon_related,
            normalized_title=normalized_title,
            raw_payload=raw_listing.model_dump(mode="json", exclude={"raw_payload"}),
        )

    def collect_searchable_fragments(self, raw_listing: RawListing) -> list[tuple[str, str]]:
        fragments: list[tuple[str, str]] = []
        for field_name, value in (
            ("title", raw_listing.title),
            ("subtitle", raw_listing.subtitle),
            ("description", raw_listing.description),
            ("condition_description", raw_listing.condition_description),
            ("category_name", raw_listing.category_name),
            ("set_name", raw_listing.set_name),
        ):
            if value:
                fragments.append((field_name, value))

        for index, value in enumerate(raw_listing.page_badges):
            if value:
                fragments.append((f"page_badges[{index}]", value))

        for index, value in enumerate(raw_listing.page_highlights):
            if value:
                fragments.append((f"page_highlights[{index}]", value))

        for key, value in raw_listing.item_specifics.items():
            if isinstance(value, str) and value:
                fragments.append((f"item_specifics.{key}", value))

        return fragments

    def detect_vault_evidence(self, raw_listing: RawListing) -> list[str]:
        evidence: list[str] = []
        seen: set[str] = set()
        fragments = self.collect_searchable_fragments(raw_listing)
        fragments.extend(self.extract_nested_strings(raw_listing.raw_payload, prefix="raw_payload"))

        for source, text in fragments:
            if not contains_normalized_phrase(text, "in the psa vault"):
                continue
            normalized_text = normalize_text(text)
            if normalized_text in seen:
                continue
            seen.add(normalized_text)
            evidence.append(f"{source}: {text.strip()}")

        return evidence

    def extract_nested_strings(self, value: Any, prefix: str) -> list[tuple[str, str]]:
        if isinstance(value, str):
            return [(prefix, value)]

        if isinstance(value, dict):
            results: list[tuple[str, str]] = []
            for key, nested_value in value.items():
                results.extend(self.extract_nested_strings(nested_value, f"{prefix}.{key}"))
            return results

        if isinstance(value, list):
            results = []
            for index, nested_value in enumerate(value):
                results.extend(self.extract_nested_strings(nested_value, f"{prefix}[{index}]"))
            return results

        return []

    def detect_grading_company(self, title: str) -> str | None:
        if contains_normalized_phrase(title, "psa"):
            return "PSA"
        return None

    def extract_grade(self, title: str) -> str | None:
        match = GRADE_PATTERN.search(title)
        if not match:
            return None
        return match.group(1)

    def detect_pokemon(self, text: str) -> Pokemon | None:
        subject_fragment = self.extract_card_subject_fragment(text)
        if subject_fragment is not None:
            return self.detect_pokemon_alias(subject_fragment)
        return self.detect_pokemon_alias(text)

    def detect_pokemon_alias(self, text: str) -> Pokemon | None:
        alias_pairs = [
            (pokemon, alias)
            for pokemon in Pokemon
            for alias in pokemon.aliases
        ]
        for pokemon, alias in sorted(alias_pairs, key=lambda item: len(item[1]), reverse=True):
            if contains_normalized_phrase(text, alias):
                return pokemon
        return None

    def detect_card_language(self, raw_listing: RawListing, combined_text: str) -> CardLanguage | None:
        for key, value in raw_listing.item_specifics.items():
            if LANGUAGE_KEY_PATTERN.search(str(key)) and isinstance(value, str):
                language = self.detect_card_language_alias(value)
                if language is not None:
                    return language

        title_language = self.detect_card_language_alias(raw_listing.title)
        if title_language is not None:
            return title_language

        if PSA_ENGLISH_SET_CODE_PATTERN.search(raw_listing.title):
            return CardLanguage.ENGLISH

        return self.detect_card_language_alias(combined_text)

    def detect_card_language_alias(self, text: str) -> CardLanguage | None:
        for language, pattern in LANGUAGE_PATTERNS:
            if pattern.search(text):
                return language
        return None

    def extract_card_subject_fragment(self, title: str) -> str | None:
        for pattern in CARD_NUMBER_PATTERNS:
            match = pattern.search(title)
            if not match:
                continue
            fragment = title[match.end():]
            stop_match = CARD_SUBJECT_STOP_PATTERN.search(fragment)
            if stop_match:
                fragment = fragment[: stop_match.start()]
            fragment = fragment.strip(" -:/|")
            if re.search(r"[A-Za-z]", fragment):
                return fragment
        return None

    def extract_card_number(self, title: str) -> str | None:
        for pattern in CARD_NUMBER_PATTERNS:
            match = pattern.search(title)
            if match:
                return match.group(1).strip().upper()
        return None

    def extract_set_name(self, title: str, detected_pokemon: Pokemon | None) -> str | None:
        normalized = normalize_text(title)
        if "pokemon" not in normalized:
            return None

        candidate = normalized.split("pokemon", 1)[1]
        if detected_pokemon:
            marker = normalize_text(detected_pokemon.value)
            if marker in candidate:
                candidate = candidate.split(marker, 1)[0]

        candidate = re.sub(r"\b(?:psa|ultra rare|secret rare|holo|reverse holo|english|japanese)\b", " ", candidate)
        candidate = re.sub(r"\b\d{1,4}\b", " ", candidate)
        candidate = re.sub(r"\ben\b", " ", candidate)
        candidate = re.sub(r"\b[a-z]{2,4}\b(?=\s)", " ", candidate, count=1)
        candidate = " ".join(candidate.split())
        if not candidate:
            return None
        return candidate.title()

    def is_pokemon_related(self, raw_listing: RawListing, detected_pokemon: Pokemon | None) -> bool:
        if detected_pokemon is not None:
            return True
        combined = " ".join(fragment for _, fragment in self.collect_searchable_fragments(raw_listing))
        return contains_normalized_phrase(combined, "pokemon")
