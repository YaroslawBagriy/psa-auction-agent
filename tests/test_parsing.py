from datetime import datetime

from app.models.listing import RawListing
from app.models.pokemon import Pokemon
from app.services.listing_parser import ListingParser


def test_parser_extracts_grade_pokemon_and_vault_from_page_evidence() -> None:
    parser = ListingParser()
    raw_listing = RawListing(
        listing_id="abc123",
        title="2025 Pokemon PFL EN-Phantasmal Flames Ultra Rare #109 Mega Charizard X EX PSA 10",
        seller_name="psa-dna",
        url="https://www.ebay.com/itm/abc123",
        listing_type="AUCTION",
        current_price=100.0,
        end_time=datetime.fromisoformat("2030-01-01T18:00:00+00:00"),
        subtitle="Official PSA auction",
        page_badges=["In the PSA Vault"],
        page_highlights=[
            "Items in the PSA Vault are securely stored, insured, and backed by Authenticity Guarantee."
        ],
        set_name="Phantasmal Flames",
        category_name="Pokemon TCG",
    )

    listing = parser.parse(raw_listing)

    assert listing.grading_company == "PSA"
    assert listing.grade_value == "10"
    assert listing.detected_pokemon == Pokemon.CHARIZARD
    assert listing.card_number == "109"
    assert listing.in_psa_vault is True
    assert listing.vault_evidence == ["page_badges[0]: In the PSA Vault"]
    assert listing.is_pokemon_related is True


def test_parser_does_not_treat_generic_vaulted_seller_copy_as_item_vault_evidence() -> None:
    parser = ListingParser()
    raw_listing = RawListing(
        listing_id="abc124",
        title="2025 Pokemon PFL EN-Phantasmal Flames Ultra Rare #109 Mega Charizard X EX PSA 10",
        seller_name="psa-dna",
        url="https://www.ebay.com/itm/abc124",
        listing_type="AUCTION",
        current_price=100.0,
        end_time=datetime.fromisoformat("2030-01-01T18:00:00+00:00"),
        description=(
            "PSA on eBay is where the hobby collects with confidence. "
            "Each item listed is collector-owned, vaulted, and consigned with PSA."
        ),
        set_name="Phantasmal Flames",
        category_name="Pokemon TCG",
    )

    listing = parser.parse(raw_listing)

    assert listing.in_psa_vault is False
    assert listing.vault_evidence == []


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
