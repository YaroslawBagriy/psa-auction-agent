from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.analysis import AnalysisResult
from app.models.bidding import BidActionResult, BidDecision, BiddingMode
from app.models.card_language import CardLanguage
from app.models.listing import Listing, RawListing
from app.models.pokemon import Pokemon
from app.models.state import ListingWorkflowResult, WorkflowSummary
from scripts.run_mvp import (
    DEMO_ALLOWED_GRADES,
    build_bid_guardrails,
    build_target_rules,
    parse_target_pokemon,
    showcase_auctions,
    actionable_auction_payload,
    actionable_auctions,
)


def _raw_listing(**overrides) -> RawListing:
    payload = {
        "listing_id": "123",
        "title": "Pokemon Mew PSA 9",
        "seller_name": "psa",
        "url": "https://www.ebay.com/itm/123",
        "listing_type": "AUCTION",
        "current_price": 20.0,
        "currency": "USD",
        "end_time": datetime.now(UTC) + timedelta(hours=1),
        "raw_payload": {},
    }
    payload.update(overrides)
    return RawListing(**payload)


def _listing(**overrides) -> Listing:
    raw = _raw_listing(**{key: value for key, value in overrides.items() if key in {"end_time"}})
    payload = {
        "listing_id": raw.listing_id,
        "title": raw.title,
        "seller_name": raw.seller_name,
        "url": raw.url,
        "is_auction": raw.is_auction,
        "current_price": raw.current_price,
        "currency": raw.currency,
        "end_time": raw.end_time,
        "grading_company": "PSA",
        "grade_value": "9",
        "detected_pokemon": Pokemon.MEW,
        "card_language": CardLanguage.JAPANESE,
        "in_psa_vault": True,
        "is_pokemon_related": True,
        "normalized_title": "pokemon mew psa 9",
        "raw_payload": {},
    }
    payload.update(overrides)
    return Listing(**payload)


def _analysis(**overrides) -> AnalysisResult:
    payload = {
        "listing_id": "123",
        "url": "https://www.ebay.com/itm/123",
        "should_bid": True,
        "confidence": 0.85,
        "estimated_market_value": 100.0,
        "recommended_max_bid": 85.0,
        "trend_outlook": "steady",
        "reasoning": "Solid comps.",
        "risk_flags": [],
        "recent_sold_prices": [95.0, 100.0, 105.0],
        "market_evidence": "Exact sold comps support $100.",
    }
    payload.update(overrides)
    return AnalysisResult(**payload)


def _approved_result(**overrides) -> ListingWorkflowResult:
    listing = overrides.pop("listing", _listing())
    analysis = overrides.pop("analysis", _analysis())
    bid_decision = overrides.pop(
        "bid_decision",
        BidDecision(
            listing_id=listing.listing_id,
            approved=True,
            reason="Approved by deterministic bid guardrails.",
            approved_max_bid=85.0,
            expected_margin=15.0,
            risk_flags=[],
            dry_run=True,
        ),
    )
    bid_execution = overrides.pop(
        "bid_execution",
        BidActionResult(
            listing_id=listing.listing_id,
            mode=BiddingMode.MANUAL,
            status="requires_user_action",
            attempted=False,
            success=False,
            dry_run=True,
            recommended_bid=85.0,
            listing_url=listing.url,
            item_id=listing.listing_id,
            title=listing.title,
            current_price=listing.current_price,
            end_time=listing.end_time,
            estimated_market_value=analysis.estimated_market_value,
            expected_margin=15.0,
            reasoning=analysis.reasoning,
            message="Manual bidding required.",
        ),
    )
    return ListingWorkflowResult(
        raw_listing=_raw_listing(),
        listing=listing,
        analysis=analysis,
        bid_decision=bid_decision,
        bid_execution=bid_execution,
        **overrides,
    )


def _summary(results: list[ListingWorkflowResult]) -> WorkflowSummary:
    return WorkflowSummary(
        run_id="test-run",
        scanned_count=len(results),
        candidate_count=len(results),
        selected_link_count=len(results),
        analyses_completed=len(results),
        bids_approved=sum(1 for result in results if result.bid_decision and result.bid_decision.approved),
        bid_attempts=0,
        results=results,
    )


def test_actionable_auctions_include_only_live_approved_bid_actions() -> None:
    approved_live = _approved_result()
    ended = _approved_result(
        listing=_listing(end_time=datetime.now(UTC) - timedelta(minutes=1)),
    )
    denied = _approved_result(
        bid_decision=BidDecision(
            listing_id="123",
            approved=False,
            reason="Denied.",
            dry_run=True,
        ),
        bid_execution=None,
    )

    actionable = actionable_auctions(_summary([approved_live, ended, denied]))

    assert actionable == [approved_live]


def test_actionable_auction_payload_contains_manual_next_action_fields() -> None:
    result = _approved_result()

    payload = actionable_auction_payload(
        result=result,
        active_listing_count=3,
        sold_listing_count=5,
        sell_through_rate=1.67,
        recent_sold_prices=[95.0, 100.0, 105.0],
        market_evidence="Exact sold comps support $100.",
    )

    assert payload["action_required"] == "requires_user_action"
    assert payload["language"] == "Japanese"
    assert payload["recommended_max_bid"] == 85.0
    assert payload["url"] == "https://www.ebay.com/itm/123"
    assert payload["message"] == "Manual bidding required."


def test_parse_target_pokemon_accepts_hyphenated_values_and_aliases() -> None:
    targets = parse_target_pokemon(["ho-oh", "mega charizard x", "red's pikachu"], use_all=False)

    assert targets == [Pokemon.HO_OH, Pokemon.CHARIZARD, Pokemon.PIKACHU]


def test_build_target_rules_defaults_to_more_demo_friendly_grades() -> None:
    rules = build_target_rules()

    assert rules.allowed_grades == {"8", "9", "10"}


def test_demo_guardrails_are_relaxed_but_explicit() -> None:
    guardrails = build_bid_guardrails(
        demo_mode=True,
        confidence_threshold=None,
        min_expected_margin=None,
        max_bid_cap=None,
        allow_uncertain_trend=False,
    )

    assert guardrails.confidence_threshold == 0.55
    assert guardrails.min_expected_margin == 0.0
    assert "uncertain" in guardrails.allowed_trend_outlooks
    assert DEMO_ALLOWED_GRADES == {"6", "7", "8", "9", "10"}


def test_showcase_auctions_include_analyzed_near_misses() -> None:
    approved_live = _approved_result()
    near_miss = ListingWorkflowResult(
        raw_listing=_raw_listing(listing_id="near"),
        listing=_listing(listing_id="near", current_price=90.0),
        analysis=_analysis(
            listing_id="near",
            estimated_market_value=120.0,
            recommended_max_bid=80.0,
        ),
        bid_decision=BidDecision(
            listing_id="near",
            approved=False,
            reason="Approved max bid does not exceed current price.",
            dry_run=True,
        ),
    )

    showcase = showcase_auctions(_summary([near_miss, approved_live]), limit=2)

    assert showcase == [approved_live, near_miss]
