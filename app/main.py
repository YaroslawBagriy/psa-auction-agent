from __future__ import annotations

import logging
import os
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - depends on local environment
    def load_dotenv() -> bool:
        return False

from app import DATA_DIR
from app.agents.analysis_agent import AnalysisAgent, HeuristicAnalysisEngine, OpenAIAnalysisEngine
from app.agents.auction_search_agent import (
    AuctionSearchAgent,
    HeuristicAuctionSearchEngine,
    OpenAIAuctionSearchEngine,
)
from app.agents.bidding_agent import BiddingAgent, DryRunBidExecutor, RealEbayBidExecutor
from app.agents.parsing_agent import ParsingAgent
from app.agents.scanner_agent import ScannerAgent
from app.agents.supervisor_agent import SupervisorAgent
from app.agents.validation_agent import ValidationAgent
from app.clients.ebay import MockEbayClient, OfficialEbayApiClient
from app.models.config import SearchConfig, TargetRules
from app.models.pokemon import Pokemon
from app.models.state import WorkflowSummary
from app.services.bid_guardrails import BidGuardrailService
from app.services.listing_parser import ListingParser
from app.services.listing_validation import ListingValidationService
from app.storage.sqlite import SQLiteStorage
from app.utils.logging import configure_logging

LOGGER = logging.getLogger(__name__)


def _env_flag(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _build_analysis_engine(use_openai_analysis: bool):
    if use_openai_analysis:
        model_name = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        return OpenAIAnalysisEngine(model_name=model_name)
    return HeuristicAnalysisEngine()


def _build_auction_search_engine(use_openai_search_agent: bool):
    if use_openai_search_agent:
        model_name = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        return OpenAIAuctionSearchEngine(model_name=model_name)
    return HeuristicAuctionSearchEngine()


def _build_search_config(
    target_pokemon: list[Pokemon],
    target_rules: TargetRules,
    dry_run: bool,
    poll_interval_minutes: int,
) -> SearchConfig:
    return SearchConfig(
        target_pokemon=target_pokemon,
        target_rules=target_rules,
        dry_run=dry_run,
        scan_limit=100,
        poll_interval_minutes=poll_interval_minutes,
    )


def run_mvp(
    target_pokemon: list[Pokemon],
    target_rules: TargetRules,
    dry_run: bool = True,
    database_path: str | Path | None = None,
    sample_ebay_path: str | Path | None = None,
    use_live_ebay: bool | None = None,
    use_openai_search_agent: bool | None = None,
    use_openai_analysis: bool | None = None,
    poll_interval_minutes: int | None = None,
) -> WorkflowSummary:
    load_dotenv()
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))

    resolved_use_live_ebay = _env_flag("USE_LIVE_EBAY") if use_live_ebay is None else use_live_ebay
    resolved_use_openai_analysis = (
        bool(os.getenv("OPENAI_API_KEY")) or _env_flag("USE_OPENAI_ANALYSIS")
        if use_openai_analysis is None
        else use_openai_analysis
    )
    resolved_use_openai_search_agent = (
        bool(os.getenv("OPENAI_API_KEY")) or _env_flag("USE_OPENAI_SEARCH_AGENT")
        if use_openai_search_agent is None
        else use_openai_search_agent
    )

    resolved_poll_interval_minutes = (
        poll_interval_minutes
        if poll_interval_minutes is not None
        else int(os.getenv("POLL_INTERVAL_MINUTES", "15"))
    )
    search_config = _build_search_config(
        target_pokemon=target_pokemon,
        target_rules=target_rules,
        dry_run=dry_run,
        poll_interval_minutes=resolved_poll_interval_minutes,
    )

    database = Path(database_path or os.getenv("APP_DATABASE_PATH", DATA_DIR / "psa_pokemon_bidder.db"))
    ebay_sample = Path(sample_ebay_path or DATA_DIR / "sample_ebay_listings.json")

    storage = SQLiteStorage(database)
    try:
        LOGGER.info(
            "Starting MVP run with live_ebay=%s openai_search_agent=%s openai_analysis=%s dry_run=%s",
            resolved_use_live_ebay,
            resolved_use_openai_search_agent,
            resolved_use_openai_analysis,
            dry_run,
        )
        ebay_client = (
            OfficialEbayApiClient(app_id=os.getenv("EBAY_APP_ID", ""))
            if resolved_use_live_ebay
            else MockEbayClient(ebay_sample)
        )
        analysis_engine = _build_analysis_engine(use_openai_analysis=resolved_use_openai_analysis)
        auction_search_engine = _build_auction_search_engine(
            use_openai_search_agent=resolved_use_openai_search_agent
        )
        bid_executor = DryRunBidExecutor() if dry_run else RealEbayBidExecutor()

        scanner_agent = ScannerAgent(client=ebay_client, storage=storage)
        parsing_agent = ParsingAgent(parser=ListingParser())
        validation_agent = ValidationAgent(
            service=ListingValidationService(),
            storage=storage,
        )
        auction_search_agent = AuctionSearchAgent(storage=storage, engine=auction_search_engine)
        analysis_agent = AnalysisAgent(storage=storage, engine=analysis_engine)
        bidding_agent = BiddingAgent(
            storage=storage,
            guardrail_service=BidGuardrailService(storage=storage),
            executor=bid_executor,
        )
        supervisor_agent = SupervisorAgent(
            scanner_agent=scanner_agent,
            parsing_agent=parsing_agent,
            validation_agent=validation_agent,
            auction_search_agent=auction_search_agent,
            analysis_agent=analysis_agent,
            bidding_agent=bidding_agent,
            storage=storage,
        )
        return supervisor_agent.run(search_config=search_config)
    finally:
        storage.close()


def run_mvp_loop(
    target_pokemon: list[Pokemon],
    target_rules: TargetRules,
    dry_run: bool = True,
    database_path: str | Path | None = None,
    sample_ebay_path: str | Path | None = None,
    use_live_ebay: bool | None = None,
    use_openai_search_agent: bool | None = None,
    use_openai_analysis: bool | None = None,
    poll_interval_minutes: int = 15,
    max_cycles: int | None = None,
    sleep_seconds_fn=time.sleep,
    on_cycle=None,
) -> list[WorkflowSummary]:
    summaries: list[WorkflowSummary] = []
    cycle = 0
    while max_cycles is None or cycle < max_cycles:
        LOGGER.info(
            "Polling cycle %s started (interval=%s minutes)",
            cycle + 1,
            poll_interval_minutes,
        )
        summaries.append(
            run_mvp(
                target_pokemon=target_pokemon,
                target_rules=target_rules,
                dry_run=dry_run,
                database_path=database_path,
                sample_ebay_path=sample_ebay_path,
                use_live_ebay=use_live_ebay,
                use_openai_search_agent=use_openai_search_agent,
                use_openai_analysis=use_openai_analysis,
                poll_interval_minutes=poll_interval_minutes,
            )
        )
        if on_cycle is not None:
            on_cycle(summaries[-1])
        cycle += 1
        if max_cycles is not None and cycle >= max_cycles:
            break
        sleep_seconds_fn(max(1, poll_interval_minutes * 60))
    return summaries


__all__ = ["run_mvp", "run_mvp_loop", "Pokemon", "SearchConfig", "TargetRules"]
