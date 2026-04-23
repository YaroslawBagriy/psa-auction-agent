from datetime import datetime

from app.models.config import SearchConfig, TargetRules
from app.models.listing import Listing
from app.models.pokemon import Pokemon
from app.services.listing_validation import ListingValidationService


def _build_listing(**overrides) -> Listing:
    payload = {
        "listing_id": "1001",
        "title": "Pokemon Charizard PSA 10 - In the PSA Vault",
        "seller_name": "psa-dna",
        "url": "https://www.ebay.com/itm/1001",
        "is_auction": True,
        "current_price": 120.0,
        "end_time": datetime.fromisoformat("2030-01-01T18:00:00+00:00"),
        "grading_company": "PSA",
        "grade_value": "10",
        "detected_pokemon": Pokemon.CHARIZARD,
        "set_name": "Phantasmal Flames",
        "card_number": "109",
        "in_psa_vault": True,
        "is_pokemon_related": True,
        "normalized_title": "pokemon charizard psa 10 in the psa vault",
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


def test_validation_rejects_missing_vault_phrase() -> None:
    validator = ListingValidationService()
    config = SearchConfig(
        target_pokemon=[Pokemon.CHARIZARD],
        target_rules=TargetRules(allowed_grades={"10"}),
    )

    result = validator.validate_listing(_build_listing(in_psa_vault=False), config)

    assert result.passed is False
    assert any("PSA Vault" in reason for reason in result.reasons)

