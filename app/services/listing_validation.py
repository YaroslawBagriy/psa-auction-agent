from __future__ import annotations

from app.models.config import SearchConfig
from app.models.listing import Listing, RawListing
from app.models.pokemon import Pokemon
from app.models.validation import ValidationResult
from app.utils.text import contains_normalized_phrase, normalize_text


class ListingValidationService:
    def validate_raw(self, raw_listing: RawListing, search_config: SearchConfig) -> ValidationResult:
        reasons: list[str] = []
        seller_name = raw_listing.seller_name.strip().lower()
        if seller_name not in search_config.official_seller_names:
            reasons.append("Seller is not in the official PSA seller allow-list.")

        if not raw_listing.is_auction:
            reasons.append("Listing is not an auction.")

        if (
            search_config.target_rules.max_minutes_remaining is not None
            and raw_listing.minutes_remaining() > search_config.target_rules.max_minutes_remaining
        ):
            reasons.append("Listing is not within the configured max_minutes_remaining bidding window.")

        combined = " ".join(part for part in [raw_listing.title, raw_listing.category_name] if part)
        is_pokemon_related = contains_normalized_phrase(combined, "pokemon") or any(
            contains_normalized_phrase(raw_listing.title, alias)
            for pokemon in Pokemon
            for alias in pokemon.aliases
        )
        if not is_pokemon_related:
            reasons.append("Raw listing does not appear to be Pokemon-related.")

        return ValidationResult(stage="pre_validation", passed=not reasons, reasons=reasons)

    def validate_listing(self, listing: Listing, search_config: SearchConfig) -> ValidationResult:
        reasons: list[str] = []
        rules = search_config.target_rules

        seller_name = listing.seller_name.strip().lower()
        if seller_name not in search_config.official_seller_names:
            reasons.append("Seller is not in the official PSA seller allow-list.")

        if not listing.is_auction:
            reasons.append("Listing is not an auction.")

        if listing.grading_company != "PSA":
            reasons.append("Listing is not clearly PSA graded.")

        if not listing.is_pokemon_related:
            reasons.append("Listing is not Pokemon-related.")

        if listing.detected_pokemon is None:
            reasons.append("Could not detect an allow-listed Pokemon in the listing details.")
        elif listing.detected_pokemon not in set(search_config.target_pokemon):
            reasons.append(f"{listing.detected_pokemon.display_name} is not in the target Pokemon allow-list.")

        if not listing.in_psa_vault:
            reasons.append('Listing page does not provide explicit "In the PSA Vault" evidence.')

        if rules.allowed_grades and listing.grade_value not in rules.allowed_grades:
            reasons.append("Listing grade is not in the allowed grades rule set.")

        if rules.allowed_sets:
            normalized_allowed_sets = {normalize_text(item) for item in rules.allowed_sets}
            normalized_set = normalize_text(listing.set_name)
            if not normalized_set or normalized_set not in normalized_allowed_sets:
                reasons.append("Listing set is not in the allowed sets rule set.")

        if rules.max_current_price is not None and listing.current_price > rules.max_current_price:
            reasons.append("Listing current price exceeds the configured max_current_price.")

        if rules.min_minutes_remaining is not None and listing.minutes_remaining() < rules.min_minutes_remaining:
            reasons.append("Listing does not meet the minimum remaining time requirement.")

        if rules.max_minutes_remaining is not None and listing.minutes_remaining() > rules.max_minutes_remaining:
            reasons.append("Listing is not within the configured max_minutes_remaining bidding window.")

        return ValidationResult(stage="listing_validation", passed=not reasons, reasons=reasons)
