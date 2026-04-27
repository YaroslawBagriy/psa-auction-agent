from datetime import UTC, datetime, timedelta

from app.models.config import SearchConfig, TargetRules
from app.models.listing import Listing
from app.models.pokemon import Pokemon
from app.services.listing_validation import ListingValidationService


def _build_listing(**overrides) -> Listing:
    payload = {
        "listing_id": "1001",
        "title": "Pokemon Charizard PSA 10",
        "seller_name": "psa-dna",
        "url": "https://www.ebay.com/itm/1001",
        "is_auction": True,
        "current_price": 120.0,
        "end_time": datetime.now(UTC) + timedelta(minutes=5),
        "grading_company": "PSA",
        "grade_value": "10",
        "detected_pokemon": Pokemon.CHARIZARD,
        "set_name": "Phantasmal Flames",
        "card_number": "109",
        "in_psa_vault": True,
        "vault_evidence": ["page_badges[0]: In the PSA Vault"],
        "is_pokemon_related": True,
        "normalized_title": "pokemon charizard psa 10",
        "raw_payload": {},
    }
    payload.update(overrides)
    return Listing(**payload)


def test_validation_accepts_in_scope_listing() -> None:
    validator = ListingValidationService()
    config = SearchConfig(
        target_pokemon=[Pokemon.CHARIZARD, Pokemon.GENGAR],
        target_rules=TargetRules(
            allowed_grades={"9", "10"},
            max_current_price=1500.0,
        ),
    )

    result = validator.validate_listing(_build_listing(), config)

    assert result.passed is True
    assert result.reasons == []


def test_validation_rejects_non_allow_listed_pokemon() -> None:
    validator = ListingValidationService()
    config = SearchConfig(
        target_pokemon=[Pokemon.PIKACHU],
        target_rules=TargetRules(allowed_grades={"10"}),
    )

    result = validator.validate_listing(_build_listing(detected_pokemon=Pokemon.CHARIZARD), config)

    assert result.passed is False
    assert any("allow-list" in reason for reason in result.reasons)


def test_validation_rejects_missing_vault_page_evidence() -> None:
    validator = ListingValidationService()
    config = SearchConfig(
        target_pokemon=[Pokemon.CHARIZARD],
        target_rules=TargetRules(allowed_grades={"10"}),
    )

    result = validator.validate_listing(
        _build_listing(in_psa_vault=False, vault_evidence=[]),
        config,
    )

    assert result.passed is False
    assert any("PSA Vault" in reason for reason in result.reasons)


def test_validation_rejects_listing_outside_ten_minute_window() -> None:
    validator = ListingValidationService()
    config = SearchConfig(
        target_pokemon=[Pokemon.CHARIZARD],
        target_rules=TargetRules(allowed_grades={"10"}, max_minutes_remaining=10),
    )

    result = validator.validate_listing(
        _build_listing(end_time=datetime.now(UTC) + timedelta(minutes=25)),
        config,
    )

    assert result.passed is False
    assert any("max_minutes_remaining" in reason for reason in result.reasons)
