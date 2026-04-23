from __future__ import annotations

import re

from app.models.listing import Listing, RawListing
from app.models.pokemon import Pokemon
from app.utils.text import contains_normalized_phrase, normalize_text

GRADE_PATTERN = re.compile(r"\bpsa[\s:-]*(\d{1,2}(?:\.\d)?)\b", re.IGNORECASE)
CARD_NUMBER_PATTERNS = (
    re.compile(r"#\s*([A-Z0-9-]+)", re.IGNORECASE),
    re.compile(r"\b(\d{1,3}/\d{1,3})\b", re.IGNORECASE),
)


class ListingParser:
    def parse(self, raw_listing: RawListing) -> Listing:
        combined_text = " ".join(
            part
            for part in [
                raw_listing.title,
                raw_listing.subtitle,
                raw_listing.description,
                raw_listing.condition_description,
            ]
            if part
        )

        normalized_title = normalize_text(raw_listing.title)
        detected_pokemon = self.detect_pokemon(combined_text)
        grading_company = self.detect_grading_company(raw_listing.title)
        grade_value = self.extract_grade(raw_listing.title)
        set_name = raw_listing.set_name or self.extract_set_name(raw_listing.title, detected_pokemon)
        card_number = self.extract_card_number(raw_listing.title)
        in_psa_vault = contains_normalized_phrase(combined_text, "in the psa vault")
        is_pokemon_related = self.is_pokemon_related(raw_listing, detected_pokemon)

        return Listing(
            listing_id=raw_listing.listing_id,
            title=raw_listing.title,
            seller_name=raw_listing.seller_name,
            url=raw_listing.url,
            is_auction=raw_listing.is_auction,
            current_price=raw_listing.current_price,
            end_time=raw_listing.end_time,
            grading_company=grading_company,
            grade_value=grade_value,
            detected_pokemon=detected_pokemon,
            set_name=set_name,
            card_number=card_number,
            in_psa_vault=in_psa_vault,
            is_pokemon_related=is_pokemon_related,
            normalized_title=normalized_title,
            raw_payload=raw_listing.model_dump(mode="json", exclude={"raw_payload"}),
        )

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
        for pokemon in Pokemon:
            for alias in sorted(pokemon.aliases, key=len, reverse=True):
                if contains_normalized_phrase(text, alias):
                    return pokemon
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
        combined = " ".join(part for part in [raw_listing.title, raw_listing.category_name] if part)
        return contains_normalized_phrase(combined, "pokemon")

