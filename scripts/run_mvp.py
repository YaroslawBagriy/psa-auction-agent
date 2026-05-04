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
from app.models.config import TargetRules
from app.models.pokemon import Pokemon
from app.models.state import ListingWorkflowResult, WorkflowSummary


DEFAULT_TARGET_POKEMON = list(Pokemon)


def build_target_rules() -> TargetRules:
    return TargetRules(
        allowed_grades={"9", "10"},
        max_current_price=1500.0,
    )


def parse_target_pokemon(values: list[str] | None, use_all: bool) -> list[Pokemon]:
    if use_all or not values:
        return DEFAULT_TARGET_POKEMON

    by_name = {pokemon.name.lower(): pokemon for pokemon in Pokemon}
    by_value = {pokemon.value.lower(): pokemon for pokemon in Pokemon}
    targets: list[Pokemon] = []
    for value in values:
        key = value.strip().lower().replace("-", "_").replace(" ", "_")
        pokemon = by_name.get(key) or by_value.get(key.replace("_", " "))
        if pokemon is None:
            supported = ", ".join(sorted(item.value for item in Pokemon))
            raise SystemExit(f"Unknown Pokemon '{value}'. Supported values: {supported}")
        targets.append(pokemon)
    return list(dict.fromkeys(targets))


def print_recommendations(summary: WorkflowSummary) -> None:
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

    print(
        json.dumps(
            {
                "run_id": summary.run_id,
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
                "reviewed_auctions": [
                    {
                        "title": result.listing.title if result.listing else result.raw_listing.title,
                        "item_id": result.listing.listing_id if result.listing else result.raw_listing.listing_id,
                        "pipeline_status": pipeline_status(result),
                        "pipeline_stage": pipeline_stage(result),
                        "pokemon": (
                            result.listing.detected_pokemon.display_name
                            if result.listing and result.listing.detected_pokemon
                            else None
                        ),
                        "grade": result.listing.grade_value if result.listing else None,
                        "language": (
                            result.listing.card_language.display_name
                            if result.listing and result.listing.card_language
                            else None
                        ),
                        "current_price": result.listing.current_price if result.listing else result.raw_listing.current_price,
                        "end_time": (
                            result.listing.end_time.isoformat()
                            if result.listing
                            else result.raw_listing.end_time.isoformat()
                        ),
                        "estimated_market_value": (
                            result.analysis.estimated_market_value if result.analysis else None
                        ),
                        "recommended_max_bid": (
                            result.analysis.recommended_max_bid if result.analysis else None
                        ),
                        "active_listing_count": active_listing_count(result),
                        "sold_listing_count": sold_listing_count(result),
                        "sell_through_rate": sell_through_rate(result),
                        "recent_sold_prices": recent_sold_prices(result),
                        "decision": decision_text(result),
                        "market_evidence": market_evidence(result),
                        "url": result.listing.url if result.listing else result.raw_listing.url,
                    }
                    for result in reviewed_auctions
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


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
    args = parser.parse_args()

    target_pokemon = parse_target_pokemon(args.pokemon, args.all_pokemon)
    target_rules = build_target_rules()

    if args.once:
        summary = run_mvp(
            target_pokemon=target_pokemon,
            target_rules=target_rules,
            dry_run=True,
            poll_interval_minutes=args.poll_interval_minutes,
            scan_limit=args.scan_limit,
        )
        if args.recommendations_only:
            print_recommendations(summary)
        else:
            print(json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True))
        return

    def print_cycle(summary) -> None:
        if args.recommendations_only:
            print_recommendations(summary)
        else:
            print(json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True), flush=True)

    run_mvp_loop(
        target_pokemon=target_pokemon,
        target_rules=target_rules,
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
