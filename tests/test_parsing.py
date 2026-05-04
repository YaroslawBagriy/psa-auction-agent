from datetime import datetime

from app.models.card_language import CardLanguage
from app.models.listing import RawListing
from app.models.pokemon import Pokemon
from app.services.listing_parser import ListingParser


def test_parser_extracts_grade_pokemon_and_vault_from_page_evidence() -> None:
    parser = ListingParser()
    raw_listing = RawListing(
        listing_id="abc123",
        title="2025 Pokemon PFL EN-Phantasmal Flames Ultra Rare #109 Mega Charizard X EX PSA 10",
        seller_name="psa",
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
    assert listing.card_language == CardLanguage.ENGLISH
    assert listing.card_number == "109"
    assert listing.in_psa_vault is True
    assert "page_badges[0]: In the PSA Vault" in listing.vault_evidence
    assert any("page_highlights[0]" in evidence for evidence in listing.vault_evidence)
    assert listing.is_pokemon_related is True


def test_parser_does_not_treat_generic_vaulted_seller_copy_as_item_vault_evidence() -> None:
    parser = ListingParser()
    raw_listing = RawListing(
        listing_id="abc124",
        title="2025 Pokemon PFL EN-Phantasmal Flames Ultra Rare #109 Mega Charizard X EX PSA 10",
        seller_name="psa",
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
        seller_name="psa",
        url="https://www.ebay.com/itm/sports1",
        listing_type="AUCTION",
        current_price=50.0,
        end_time=datetime.fromisoformat("2030-01-01T18:00:00+00:00"),
        category_name="Sports Trading Cards",
    )

    listing = parser.parse(raw_listing)

    assert listing.detected_pokemon is None
    assert listing.is_pokemon_related is False


def test_parser_prefers_longer_pokemon_aliases() -> None:
    parser = ListingParser()
    raw_listing = RawListing(
        listing_id="mewtwo1",
        title="Pokemon Mewtwo PSA 10",
        seller_name="psa",
        url="https://www.ebay.com/itm/mewtwo1",
        listing_type="AUCTION",
        current_price=50.0,
        end_time=datetime.fromisoformat("2030-01-01T18:00:00+00:00"),
        category_name="Pokemon TCG",
    )

    listing = parser.parse(raw_listing)

    assert listing.detected_pokemon == Pokemon.MEWTWO


def test_parser_uses_card_subject_after_card_number_for_pokemon_identity() -> None:
    parser = ListingParser()
    raw_listing = RawListing(
        listing_id="deck-card-1",
        title="2023 POKEMON JAPANESE CLASSIC CHARIZARD & HO-OH EX DECK #013 CLEFAIRY PSA 10",
        seller_name="psa",
        url="https://www.ebay.com/itm/deck-card-1",
        listing_type="AUCTION",
        current_price=50.0,
        end_time=datetime.fromisoformat("2030-01-01T18:00:00+00:00"),
        page_badges=["In the PSA Vault"],
        category_name="Pokemon TCG",
    )

    listing = parser.parse(raw_listing)

    assert listing.detected_pokemon == Pokemon.CLEFAIRY
    assert listing.card_number == "013"
    assert listing.is_pokemon_related is True


def test_parser_detects_target_pokemon_when_card_subject_follows_card_number() -> None:
    parser = ListingParser()
    raw_listing = RawListing(
        listing_id="actual-card-1",
        title="2023 POKEMON TRICK OR TRADE #066 GENGAR PSA 10",
        seller_name="psa",
        url="https://www.ebay.com/itm/actual-card-1",
        listing_type="AUCTION",
        current_price=50.0,
        end_time=datetime.fromisoformat("2030-01-01T18:00:00+00:00"),
        page_badges=["In the PSA Vault"],
        category_name="Pokemon TCG",
    )

    listing = parser.parse(raw_listing)

    assert listing.detected_pokemon == Pokemon.GENGAR
    assert listing.card_number == "066"


def test_parser_detects_japanese_language_from_psa_title() -> None:
    parser = ListingParser()
    raw_listing = RawListing(
        listing_id="jp-card-1",
        title="2022 POKEMON JAPANESE SWORD & SHIELD DARK PHANTASMA #074 FULL ART/GENGAR PSA 9",
        seller_name="psa",
        url="https://www.ebay.com/itm/jp-card-1",
        listing_type="AUCTION",
        current_price=50.0,
        end_time=datetime.fromisoformat("2030-01-01T18:00:00+00:00"),
        page_badges=["In the PSA Vault"],
        category_name="Pokemon TCG",
    )

    listing = parser.parse(raw_listing)

    assert listing.detected_pokemon == Pokemon.GENGAR
    assert listing.card_language == CardLanguage.JAPANESE


def test_parser_detects_jpn_abbreviation_as_japanese() -> None:
    parser = ListingParser()
    raw_listing = RawListing(
        listing_id="jpn-card-1",
        title="2017 POKEMON JPN SUN & MOON TO HAVE SEEN THE BATTLE RAINBOW CHARMANDER PSA 9",
        seller_name="psa",
        url="https://www.ebay.com/itm/jpn-card-1",
        listing_type="AUCTION",
        current_price=50.0,
        end_time=datetime.fromisoformat("2030-01-01T18:00:00+00:00"),
        page_badges=["In the PSA Vault"],
        category_name="Pokemon TCG",
    )

    listing = parser.parse(raw_listing)

    assert listing.card_language == CardLanguage.JAPANESE


def test_parser_detects_language_from_item_specifics() -> None:
    parser = ListingParser()
    raw_listing = RawListing(
        listing_id="specifics-card-1",
        title="Pokemon Mew PSA 9",
        seller_name="psa",
        url="https://www.ebay.com/itm/specifics-card-1",
        listing_type="AUCTION",
        current_price=50.0,
        end_time=datetime.fromisoformat("2030-01-01T18:00:00+00:00"),
        page_badges=["In the PSA Vault"],
        category_name="Pokemon TCG",
        item_specifics={"Language": "Japanese"},
    )

    listing = parser.parse(raw_listing)

    assert listing.card_language == CardLanguage.JAPANESE
