from datetime import datetime

from app.models.listing import RawListing
from app.models.pokemon import Pokemon
from app.services.listing_parser import ListingParser


def test_parser_extracts_grade_pokemon_and_vault() -> None:
    parser = ListingParser()
    raw_listing = RawListing(
        listing_id="abc123",
        title="2025 Pokemon PFL EN-Phantasmal Flames Ultra Rare #109 Mega Charizard X EX PSA 10 - In the PSA Vault",
        seller_name="psa-dna",
        url="https://www.ebay.com/itm/abc123",
        listing_type="AUCTION",
        current_price=100.0,
        end_time=datetime.fromisoformat("2030-01-01T18:00:00+00:00"),
        subtitle="In the PSA Vault",
        set_name="Phantasmal Flames",
        category_name="Pokemon TCG",
    )

    listing = parser.parse(raw_listing)

    assert listing.grading_company == "PSA"
    assert listing.grade_value == "10"
    assert listing.detected_pokemon == Pokemon.CHARIZARD
    assert listing.card_number == "109"
    assert listing.in_psa_vault is True
    assert listing.is_pokemon_related is True


def test_parser_returns_none_for_unknown_pokemon() -> None:
    parser = ListingParser()
    raw_listing = RawListing(
        listing_id="sports1",
        title="2021 Topps Chrome Mike Trout PSA 10",
        seller_name="psa-dna",
        url="https://www.ebay.com/itm/sports1",
        listing_type="AUCTION",
        current_price=50.0,
        end_time=datetime.fromisoformat("2030-01-01T18:00:00+00:00"),
        category_name="Sports Trading Cards",
    )

    listing = parser.parse(raw_listing)

    assert listing.detected_pokemon is None
    assert listing.is_pokemon_related is False

