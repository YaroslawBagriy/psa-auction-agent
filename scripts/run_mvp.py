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
from app.models.state import WorkflowSummary


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
    recommendations = [
        result
        for result in summary.results
        if result.bid_decision
        and result.bid_decision.approved
        and result.bid_execution
    ]
    reviewed_auctions = [
        result
        for result in summary.results
        if result.listing is not None
        and (
            (result.validation is not None and result.validation.passed)
            or result.analysis is not None
            or result.bid_decision is not None
        )
    ]
    print(
        json.dumps(
            {
                "run_id": summary.run_id,
                "scanned_count": summary.scanned_count,
                "candidate_count": summary.candidate_count,
                "selected_link_count": summary.selected_link_count,
                "recommendation_count": len(recommendations),
                "recommendations": [
                    {
                        "title": result.bid_execution.title,
                        "item_id": result.bid_execution.item_id,
                        "current_price": result.bid_execution.current_price,
                        "end_time": (
                            result.bid_execution.end_time.isoformat()
                            if result.bid_execution.end_time
                            else None
                        ),
                        "estimated_market_value": result.bid_execution.estimated_market_value,
                        "recommended_max_bid": result.bid_execution.recommended_bid,
                        "expected_margin": result.bid_execution.expected_margin,
                        "active_listing_count": (
                            result.analysis.active_listing_count if result.analysis else None
                        ),
                        "sold_listing_count": (
                            result.analysis.sold_listing_count if result.analysis else None
                        ),
                        "sell_through_rate": (
                            result.analysis.sell_through_rate if result.analysis else None
                        ),
                        "recent_sold_prices": (
                            result.analysis.recent_sold_prices if result.analysis else []
                        ),
                        "status": result.bid_execution.status,
                        "url": result.bid_execution.listing_url,
                        "reasoning": result.bid_execution.reasoning,
                        "market_evidence": (
                            result.analysis.market_evidence if result.analysis else None
                        ),
                    }
                    for result in recommendations
                ],
                "reviewed_auctions": [
                    {
                        "title": result.listing.title if result.listing else result.raw_listing.title,
                        "item_id": result.listing.listing_id if result.listing else result.raw_listing.listing_id,
                        "pokemon": (
                            result.listing.detected_pokemon.display_name
                            if result.listing and result.listing.detected_pokemon
                            else None
                        ),
                        "grade": result.listing.grade_value if result.listing else None,
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
                        "active_listing_count": (
                            result.analysis.active_listing_count if result.analysis else None
                        ),
                        "sold_listing_count": (
                            result.analysis.sold_listing_count if result.analysis else None
                        ),
                        "sell_through_rate": (
                            result.analysis.sell_through_rate if result.analysis else None
                        ),
                        "recent_sold_prices": (
                            result.analysis.recent_sold_prices if result.analysis else []
                        ),
                        "decision": result.bid_decision.reason if result.bid_decision else None,
                        "market_evidence": (
                            result.analysis.market_evidence if result.analysis else None
                        ),
                        "url": result.listing.url if result.listing else result.raw_listing.url,
                    }
                    for result in reviewed_auctions
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


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
