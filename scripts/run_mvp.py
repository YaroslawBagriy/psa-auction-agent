from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import run_mvp, run_mvp_loop
from app.models.config import TargetRules
from app.models.pokemon import Pokemon


def build_target_rules() -> TargetRules:
    return TargetRules(
        allowed_grades={"9", "10"},
        max_current_price=1500.0,
        max_minutes_remaining=10,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the psa-pokemon-bidder MVP.")
    parser.add_argument("--once", action="store_true", help="Run a single scan/analyze/bid cycle.")
    parser.add_argument(
        "--poll-interval-minutes",
        type=int,
        default=15,
        help="Polling interval for continuous mode.",
    )
    args = parser.parse_args()

    target_pokemon = [Pokemon.PIKACHU, Pokemon.CHARIZARD, Pokemon.GENGAR]
    target_rules = build_target_rules()

    if args.once:
        summary = run_mvp(
            target_pokemon=target_pokemon,
            target_rules=target_rules,
            dry_run=True,
            poll_interval_minutes=args.poll_interval_minutes,
        )
        print(json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True))
        return

    def print_cycle(summary) -> None:
        print(json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True), flush=True)

    run_mvp_loop(
        target_pokemon=target_pokemon,
        target_rules=target_rules,
        dry_run=True,
        poll_interval_minutes=args.poll_interval_minutes,
        on_cycle=print_cycle,
    )


if __name__ == "__main__":
    main()
