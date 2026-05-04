from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agents.errors import LLMAgentError
from app.main import LLMConfigurationError, run_mvp, run_mvp_loop
from app.models.config import BidGuardrails, TargetRules
from app.models.pokemon import Pokemon
from app.models.state import ListingWorkflowResult, WorkflowSummary


DEFAULT_TARGET_POKEMON = list(Pokemon)
DEFAULT_ALLOWED_GRADES = {"8", "9", "10"}
DEMO_ALLOWED_GRADES = {"6", "7", "8", "9", "10"}


def build_target_rules(
    allowed_grades: set[str] | None = None,
    max_current_price: float = 1500.0,
) -> TargetRules:
    return TargetRules(
        allowed_grades=allowed_grades or DEFAULT_ALLOWED_GRADES,
        max_current_price=max_current_price,
    )


def build_bid_guardrails(
    *,
    demo_mode: bool,
    confidence_threshold: float | None,
    min_expected_margin: float | None,
    max_bid_cap: float | None,
    allow_uncertain_trend: bool,
) -> BidGuardrails:
    allowed_trends = {"steady", "upward"}
    if demo_mode or allow_uncertain_trend:
        allowed_trends.add("uncertain")

    return BidGuardrails(
        confidence_threshold=(
            confidence_threshold
            if confidence_threshold is not None
            else (0.55 if demo_mode else 0.65)
        ),
        min_expected_margin=(
            min_expected_margin
            if min_expected_margin is not None
            else (0.0 if demo_mode else 20.0)
        ),
        max_bid_cap=max_bid_cap,
        allowed_trend_outlooks=allowed_trends,
    )


def normalize_pokemon_lookup_key(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def parse_target_pokemon(values: list[str] | None, use_all: bool) -> list[Pokemon]:
    if use_all or not values:
        return DEFAULT_TARGET_POKEMON

    by_key: dict[str, Pokemon] = {}
    for pokemon in Pokemon:
        by_key[normalize_pokemon_lookup_key(pokemon.name)] = pokemon
        by_key[normalize_pokemon_lookup_key(pokemon.value)] = pokemon
        for alias in pokemon.aliases:
            by_key[normalize_pokemon_lookup_key(alias)] = pokemon

    targets: list[Pokemon] = []
    for value in values:
        pokemon = by_key.get(normalize_pokemon_lookup_key(value))
        if pokemon is None:
            supported = ", ".join(sorted(item.value for item in Pokemon))
            raise SystemExit(f"Unknown Pokemon '{value}'. Supported values: {supported}")
        targets.append(pokemon)
    return list(dict.fromkeys(targets))


def print_recommendations(summary: WorkflowSummary, showcase_limit: int = 8, demo_mode: bool = False) -> None:
    recommendations = actionable_auctions(summary)
    reviewed_auctions = list(summary.results)

    def active_listing_count(result) -> int | None:
        if result.analysis and result.analysis.active_listing_count is not None:
            return result.analysis.active_listing_count
        if result.market_research:
            return result.market_research.active_listing_count
        return None

    def sold_listing_count(result) -> int | None:
        if result.analysis and result.analysis.sold_listing_count is not None:
            return result.analysis.sold_listing_count
        if result.market_research:
            return result.market_research.sold_listing_count
        return None

    def sell_through_rate(result) -> float | None:
        if result.analysis and result.analysis.sell_through_rate is not None:
            return result.analysis.sell_through_rate
        if result.market_research:
            return result.market_research.sell_through_rate
        return None

    def recent_sold_prices(result) -> list[float]:
        if result.analysis and result.analysis.recent_sold_prices:
            return result.analysis.recent_sold_prices
        if result.market_research:
            return result.market_research.recent_sold_prices
        return []

    def market_evidence(result) -> str | None:
        if result.analysis and result.analysis.market_evidence:
            return result.analysis.market_evidence
        if result.market_research:
            return result.market_research.evidence_summary
        return None

    def decision_text(result) -> str | None:
        if result.bid_decision:
            return result.bid_decision.reason
        if result.errors:
            return "Workflow error: " + "; ".join(result.errors)
        if result.validation and not result.validation.passed:
            return "Listing validation rejected this listing: " + "; ".join(result.validation.reasons)
        if result.pre_validation and not result.pre_validation.passed:
            return "Pre-validation rejected this listing: " + "; ".join(result.pre_validation.reasons)
        if result.search_decision and not result.search_decision.should_track:
            return f"Auction search skipped this listing: {result.search_decision.rationale}"
        if result.search_decision and result.search_decision.should_track and result.market_research is None:
            return "Selected for market research, but no market research result was produced."
        return None

    def pipeline_status(result) -> str:
        if result.bid_decision and result.bid_decision.approved:
            return "accepted"
        return "denied"

    def pipeline_stage(result) -> str | None:
        if result.bid_decision:
            return "bid_guardrails"
        if result.analysis:
            return "analysis"
        if result.market_research:
            return "market_research"
        if result.search_decision:
            return "auction_search"
        if result.validation:
            return "listing_validation"
        if result.pre_validation:
            return "pre_validation"
        if result.errors:
            return "error"
        return None

    highlights = showcase_auctions(summary, limit=showcase_limit)

    print(
        json.dumps(
            {
                "run_id": summary.run_id,
                "demo_mode": demo_mode,
                "scanned_count": summary.scanned_count,
                "candidate_count": summary.candidate_count,
                "selected_link_count": summary.selected_link_count,
                "recommendation_count": len(recommendations),
                "actionable_auction_count": len(recommendations),
                "actionable_auctions": [
                    actionable_auction_payload(
                        result=result,
                        active_listing_count=active_listing_count(result),
                        sold_listing_count=sold_listing_count(result),
                        sell_through_rate=sell_through_rate(result),
                        recent_sold_prices=recent_sold_prices(result),
                        market_evidence=market_evidence(result),
                    )
                    for result in recommendations
                ],
                "recommendations": [
                    actionable_auction_payload(
                        result=result,
                        active_listing_count=active_listing_count(result),
                        sold_listing_count=sold_listing_count(result),
                        sell_through_rate=sell_through_rate(result),
                        recent_sold_prices=recent_sold_prices(result),
                        market_evidence=market_evidence(result),
                    )
                    for result in recommendations
                ],
                "showcase_auction_count": len(highlights),
                "showcase_auctions": [
                    reviewed_auction_payload(
                        result=result,
                        active_listing_count=active_listing_count(result),
                        sold_listing_count=sold_listing_count(result),
                        sell_through_rate=sell_through_rate(result),
                        recent_sold_prices=recent_sold_prices(result),
                        market_evidence=market_evidence(result),
                        decision=decision_text(result),
                        pipeline_status=pipeline_status(result),
                        pipeline_stage=pipeline_stage(result),
                    )
                    for result in highlights
                ],
                "reviewed_auctions": [
                    reviewed_auction_payload(
                        result=result,
                        active_listing_count=active_listing_count(result),
                        sold_listing_count=sold_listing_count(result),
                        sell_through_rate=sell_through_rate(result),
                        recent_sold_prices=recent_sold_prices(result),
                        market_evidence=market_evidence(result),
                        decision=decision_text(result),
                        pipeline_status=pipeline_status(result),
                        pipeline_stage=pipeline_stage(result),
                    )
                    for result in reviewed_auctions
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


def showcase_auctions(summary: WorkflowSummary, limit: int = 8) -> list[ListingWorkflowResult]:
    if limit <= 0:
        return []

    actionable = actionable_auctions(summary)
    actionable_ids = {result.raw_listing.listing_id for result in actionable}
    analyzed = [
        result
        for result in summary.results
        if result.raw_listing.listing_id not in actionable_ids
        and result.listing is not None
        and (result.analysis is not None or result.market_research is not None)
    ]

    def sort_key(result: ListingWorkflowResult) -> tuple[int, float, float]:
        has_bid = 1 if result.analysis and result.analysis.recommended_max_bid is not None else 0
        estimated_value = result.analysis.estimated_market_value if result.analysis else None
        current_price = result.listing.current_price if result.listing else result.raw_listing.current_price
        return (has_bid, estimated_value or 0.0, -current_price)

    ordered = actionable + sorted(analyzed, key=sort_key, reverse=True)
    return ordered[:limit]


def actionable_auctions(summary: WorkflowSummary) -> list[ListingWorkflowResult]:
    return [
        result
        for result in summary.results
        if result.bid_decision
        and result.bid_decision.approved
        and result.bid_decision.approved_max_bid is not None
        and result.bid_execution
        and result.bid_execution.listing_url
        and result.bid_execution.end_time
        and result.listing
        and result.listing.minutes_remaining() > 0
        and result.bid_execution.status in {
            "requires_user_action",
            "fallback_manual_required",
            "dry_run_official_api",
            "submitted",
        }
    ]


def actionable_auction_payload(
    result: ListingWorkflowResult,
    active_listing_count: int | None,
    sold_listing_count: int | None,
    sell_through_rate: float | None,
    recent_sold_prices: list[float],
    market_evidence: str | None,
) -> dict:
    assert result.bid_execution is not None
    action = result.bid_execution
    return {
        "title": action.title,
        "item_id": action.item_id,
        "current_price": action.current_price,
        "end_time": action.end_time.isoformat() if action.end_time else None,
        "estimated_market_value": action.estimated_market_value,
        "recommended_max_bid": action.recommended_bid,
        "expected_margin": action.expected_margin,
        "language": (
            result.listing.card_language.display_name
            if result.listing and result.listing.card_language
            else None
        ),
        "active_listing_count": active_listing_count,
        "sold_listing_count": sold_listing_count,
        "sell_through_rate": sell_through_rate,
        "recent_sold_prices": recent_sold_prices,
        "action_required": action.status,
        "status": action.status,
        "url": action.listing_url,
        "reasoning": action.reasoning,
        "market_evidence": market_evidence,
        "message": action.message,
    }


def reviewed_auction_payload(
    *,
    result: ListingWorkflowResult,
    active_listing_count: int | None,
    sold_listing_count: int | None,
    sell_through_rate: float | None,
    recent_sold_prices: list[float],
    market_evidence: str | None,
    decision: str | None,
    pipeline_status: str,
    pipeline_stage: str | None,
) -> dict:
    listing = result.listing
    return {
        "title": listing.title if listing else result.raw_listing.title,
        "item_id": listing.listing_id if listing else result.raw_listing.listing_id,
        "pipeline_status": pipeline_status,
        "pipeline_stage": pipeline_stage,
        "pokemon": (
            listing.detected_pokemon.display_name
            if listing and listing.detected_pokemon
            else None
        ),
        "grade": listing.grade_value if listing else None,
        "language": (
            listing.card_language.display_name
            if listing and listing.card_language
            else None
        ),
        "current_price": listing.current_price if listing else result.raw_listing.current_price,
        "end_time": (
            listing.end_time.isoformat()
            if listing
            else result.raw_listing.end_time.isoformat()
        ),
        "estimated_market_value": result.analysis.estimated_market_value if result.analysis else None,
        "recommended_max_bid": result.analysis.recommended_max_bid if result.analysis else None,
        "active_listing_count": active_listing_count,
        "sold_listing_count": sold_listing_count,
        "sell_through_rate": sell_through_rate,
        "recent_sold_prices": recent_sold_prices,
        "decision": decision,
        "market_evidence": market_evidence,
        "url": listing.url if listing else result.raw_listing.url,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the psa-pokemon-bidder MVP.")
    parser.add_argument("--once", action="store_true", help="Run a single scan/analyze/bid cycle.")
    parser.add_argument(
        "--scan-limit",
        type=int,
        default=None,
        help="Maximum number of PSA eBay listings to scan.",
    )
    parser.add_argument(
        "--poll-interval-minutes",
        type=int,
        default=15,
        help="Polling interval for continuous mode.",
    )
    parser.add_argument(
        "--recommendations-only",
        action="store_true",
        help="Print a compact list of manual bid recommendations instead of full workflow JSON.",
    )
    parser.add_argument(
        "--pokemon",
        nargs="+",
        help="Target Pokemon values, for example: pikachu charizard gengar.",
    )
    parser.add_argument(
        "--all-pokemon",
        action="store_true",
        help="Target every Pokemon currently supported by the enum.",
    )
    parser.add_argument(
        "--grades",
        nargs="+",
        help="Allowed PSA grades. Defaults to 8 9 10. For demos try: --grades 6 7 8 9 10.",
    )
    parser.add_argument(
        "--max-current-price",
        type=float,
        default=None,
        help="Maximum current auction price to review. Defaults to 1500, or 2500 in demo mode.",
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=None,
        help="Bid guardrail confidence threshold. Defaults to 0.65, or 0.55 in demo mode.",
    )
    parser.add_argument(
        "--min-margin",
        type=float,
        default=None,
        help="Minimum expected dollar margin. Defaults to 20, or 0 in demo mode.",
    )
    parser.add_argument(
        "--max-bid-cap",
        type=float,
        default=None,
        help="Optional hard cap for recommended max bids.",
    )
    parser.add_argument(
        "--allow-uncertain-trend",
        action="store_true",
        help="Allow uncertain trend outlooks through guardrails. Intended for exploratory demos only.",
    )
    parser.add_argument(
        "--showcase-limit",
        type=int,
        default=8,
        help="Number of analyzed/high-signal auctions to include in the compact showcase output.",
    )
    parser.add_argument(
        "--demo-mode",
        action="store_true",
        help=(
            "Presentation-friendly mode: targets all Pokemon, allows grades 6-10, "
            "raises max price to 2500, lowers confidence to 0.55, allows uncertain trends, "
            "and sets minimum margin to 0. Bidding still stays manual/dry-run."
        ),
    )
    args = parser.parse_args()

    target_pokemon = parse_target_pokemon(args.pokemon, args.all_pokemon or args.demo_mode)
    allowed_grades = (
        {str(grade).strip() for grade in args.grades if str(grade).strip()}
        if args.grades
        else (DEMO_ALLOWED_GRADES if args.demo_mode else DEFAULT_ALLOWED_GRADES)
    )
    max_current_price = (
        args.max_current_price
        if args.max_current_price is not None
        else (2500.0 if args.demo_mode else 1500.0)
    )
    target_rules = build_target_rules(
        allowed_grades=allowed_grades,
        max_current_price=max_current_price,
    )
    bid_guardrails = build_bid_guardrails(
        demo_mode=args.demo_mode,
        confidence_threshold=args.confidence_threshold,
        min_expected_margin=args.min_margin,
        max_bid_cap=args.max_bid_cap,
        allow_uncertain_trend=args.allow_uncertain_trend,
    )

    if args.once:
        summary = run_mvp(
            target_pokemon=target_pokemon,
            target_rules=target_rules,
            bid_guardrails=bid_guardrails,
            dry_run=True,
            poll_interval_minutes=args.poll_interval_minutes,
            scan_limit=args.scan_limit,
        )
        if args.recommendations_only:
            print_recommendations(
                summary,
                showcase_limit=args.showcase_limit,
                demo_mode=args.demo_mode,
            )
        else:
            print(json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True))
        return

    def print_cycle(summary) -> None:
        if args.recommendations_only:
            print_recommendations(
                summary,
                showcase_limit=args.showcase_limit,
                demo_mode=args.demo_mode,
            )
        else:
            print(json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True), flush=True)

    run_mvp_loop(
        target_pokemon=target_pokemon,
        target_rules=target_rules,
        bid_guardrails=bid_guardrails,
        dry_run=True,
        poll_interval_minutes=args.poll_interval_minutes,
        scan_limit=args.scan_limit,
        on_cycle=print_cycle,
    )


if __name__ == "__main__":
    try:
        main()
    except (LLMConfigurationError, LLMAgentError) as exc:
        print(f"LLM agent error: {exc}", file=sys.stderr)
        print(
            "The scan can still work, but recommendations require a working OpenAI key "
            "because the project is configured to use prompt-driven agents with no "
            "heuristic analysis fallback.",
            file=sys.stderr,
        )
        sys.exit(2)
