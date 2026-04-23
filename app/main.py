from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - depends on local environment
    def load_dotenv() -> bool:
        return False

from app import DATA_DIR
from app.agents.analysis_agent import AnalysisAgent, HeuristicAnalysisEngine, OpenAIAnalysisEngine
from app.agents.bidding_agent import BiddingAgent, DryRunBidExecutor, RealEbayBidExecutor
from app.agents.parsing_agent import ParsingAgent
from app.agents.price_research_agent import PriceResearchAgent
from app.agents.scanner_agent import ScannerAgent
from app.agents.supervisor_agent import SupervisorAgent
from app.agents.validation_agent import ValidationAgent
from app.clients.ebay import MockEbayClient, OfficialEbayApiClient
from app.clients.pricecharting import MockPriceChartingClient, ScrapingPriceChartingClient
from app.models.config import SearchConfig, TargetRules
from app.models.pokemon import Pokemon
from app.models.state import WorkflowSummary
from app.services.bid_guardrails import BidGuardrailService
from app.services.listing_parser import ListingParser
from app.services.listing_validation import ListingValidationService
from app.storage.sqlite import SQLiteStorage
from app.utils.logging import configure_logging
from app.workflows.mvp_workflow import build_candidate_workflow


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


def run_mvp(
    target_pokemon: list[Pokemon],
    target_rules: TargetRules,
    dry_run: bool = True,
    database_path: str | Path | None = None,
    sample_ebay_path: str | Path | None = None,
    sample_pricecharting_path: str | Path | None = None,
    use_live_ebay: bool | None = None,
    use_live_pricecharting: bool | None = None,
    use_openai_analysis: bool | None = None,
) -> WorkflowSummary:
    load_dotenv()
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))

    resolved_use_live_ebay = _env_flag("USE_LIVE_EBAY") if use_live_ebay is None else use_live_ebay
    resolved_use_live_pricecharting = (
        _env_flag("USE_LIVE_PRICECHARTING")
        if use_live_pricecharting is None
        else use_live_pricecharting
    )
    resolved_use_openai_analysis = (
        _env_flag("USE_OPENAI_ANALYSIS")
        if use_openai_analysis is None
        else use_openai_analysis
    )

    search_config = SearchConfig(
        target_pokemon=target_pokemon,
        target_rules=target_rules,
        dry_run=dry_run,
    )

    database = Path(database_path or os.getenv("APP_DATABASE_PATH", DATA_DIR / "psa_pokemon_bidder.db"))
    ebay_sample = Path(sample_ebay_path or DATA_DIR / "sample_ebay_listings.json")
    price_sample = Path(sample_pricecharting_path or DATA_DIR / "sample_pricecharting.json")

    storage = SQLiteStorage(database)
    try:
        ebay_client = (
            OfficialEbayApiClient(app_id=os.getenv("EBAY_APP_ID", ""))
            if resolved_use_live_ebay
            else MockEbayClient(ebay_sample)
        )
        price_client = (
            ScrapingPriceChartingClient()
            if resolved_use_live_pricecharting
            else MockPriceChartingClient(price_sample)
        )
        analysis_engine = _build_analysis_engine(use_openai_analysis=resolved_use_openai_analysis)
        bid_executor = DryRunBidExecutor() if dry_run else RealEbayBidExecutor()

        scanner_agent = ScannerAgent(client=ebay_client, storage=storage)
        parsing_agent = ParsingAgent(parser=ListingParser())
        validation_agent = ValidationAgent(
            service=ListingValidationService(),
            storage=storage,
        )
        price_research_agent = PriceResearchAgent(client=price_client, storage=storage)
        analysis_agent = AnalysisAgent(storage=storage, engine=analysis_engine)
        bidding_agent = BiddingAgent(
            storage=storage,
            guardrail_service=BidGuardrailService(storage=storage),
            executor=bid_executor,
        )
        workflow = build_candidate_workflow(
            parsing_agent=parsing_agent,
            validation_agent=validation_agent,
            price_research_agent=price_research_agent,
            analysis_agent=analysis_agent,
            bidding_agent=bidding_agent,
        )
        supervisor_agent = SupervisorAgent(
            scanner_agent=scanner_agent,
            workflow=workflow,
            storage=storage,
        )
        return supervisor_agent.run(search_config=search_config)
    finally:
        storage.close()


__all__ = ["run_mvp", "Pokemon", "SearchConfig", "TargetRules"]
