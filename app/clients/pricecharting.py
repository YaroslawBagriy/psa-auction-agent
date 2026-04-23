from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.models.listing import Listing
from app.models.pokemon import Pokemon
from app.models.price_research import PriceResearchResult
from app.utils.text import normalize_text, similarity_score


class PriceChartingSampleCard(BaseModel):
    title: str
    url: str
    pokemon: Pokemon
    set_name: str | None = None
    card_number: str | None = None
    prices_by_grade: dict[str, float] = Field(default_factory=dict)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class PriceChartingClient(ABC):
    @abstractmethod
    def research(self, listing: Listing) -> PriceResearchResult:
        raise NotImplementedError


class MockPriceChartingClient(PriceChartingClient):
    def __init__(self, sample_path: Path) -> None:
        self.sample_path = sample_path
        self.cards = self._load_cards()

    def _load_cards(self) -> list[PriceChartingSampleCard]:
        with self.sample_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return [PriceChartingSampleCard(**item, raw_payload=dict(item)) for item in payload]

    def research(self, listing: Listing) -> PriceResearchResult:
        search_term = " ".join(
            part
            for part in [
                listing.detected_pokemon.display_name if listing.detected_pokemon else None,
                listing.set_name,
                listing.card_number,
                f"PSA {listing.grade_value}" if listing.grade_value else None,
            ]
            if part
        )

        best_match: PriceChartingSampleCard | None = None
        best_score = 0.0
        for card in self.cards:
            score = self._score_match(listing, card)
            if score > best_score:
                best_score = score
                best_match = card

        if best_match is None:
            return PriceResearchResult(
                listing_id=listing.listing_id,
                search_term=search_term or listing.title,
                notes=["No PriceCharting match found in mock dataset."],
            )

        grade_key = f"PSA {listing.grade_value}" if listing.grade_value else None
        target_grade_price = best_match.prices_by_grade.get(grade_key) if grade_key else None
        notes: list[str] = []
        if grade_key and target_grade_price is None:
            notes.append(f"No exact grade price found for {grade_key}.")

        return PriceResearchResult(
            listing_id=listing.listing_id,
            search_term=search_term or listing.title,
            matched_title=best_match.title,
            matched_url=best_match.url,
            match_confidence=round(best_score, 3),
            prices_by_grade=best_match.prices_by_grade,
            target_grade_price=target_grade_price,
            notes=notes,
            raw_payload=best_match.raw_payload,
        )

    def _score_match(self, listing: Listing, card: PriceChartingSampleCard) -> float:
        score = 0.0
        if listing.detected_pokemon and card.pokemon == listing.detected_pokemon:
            score += 0.45

        if listing.card_number and card.card_number:
            if normalize_text(listing.card_number) == normalize_text(card.card_number):
                score += 0.30

        if listing.set_name and card.set_name:
            normalized_listing_set = normalize_text(listing.set_name)
            normalized_card_set = normalize_text(card.set_name)
            if normalized_listing_set == normalized_card_set:
                score += 0.15
            elif normalized_listing_set in normalized_card_set or normalized_card_set in normalized_listing_set:
                score += 0.08

        score += 0.10 * similarity_score(listing.title, card.title)
        return min(score, 1.0)


class ScrapingPriceChartingClient(PriceChartingClient):
    def research(self, listing: Listing) -> PriceResearchResult:
        # TODO: Implement a resilient scraper with request throttling, robots.txt review,
        # HTML structure validation, and cached match reuse before enabling live usage.
        raise NotImplementedError(
            "Live PriceCharting scraping is not wired yet. "
            "Use MockPriceChartingClient for dry-run MVP execution."
        )

