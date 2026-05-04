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
from app.agents.analysis_agent import AnalysisAgent, AnalysisEngine, OpenAIAnalysisEngine
from app.agents.auction_search_agent import (
    AuctionSearchAgent,
    AuctionSearchEngine,
    OpenAIAuctionSearchEngine,
)
from app.agents.market_query_agent import (
    MarketQueryPlannerAgent,
    MarketQueryPlannerEngine,
    OpenAIMarketQueryPlannerEngine,
)
from app.agents.market_research_agent import (
    MarketResearchAgent,
    MarketResearchEngine,
    OpenAIWebMarketResearchEngine,
)
from app.agents.supervisor_agent import SupervisorAgent
from app.clients.ebay import MockEbayClient, OfficialEbayApiClient
from app.clients.ebay_market import MockEbayMarketResearchClient, OfficialEbayMarketResearchClient
from app.models.bidding import BiddingMode
from app.models.config import BidGuardrails, MarketResearchMode, SearchConfig, TargetRules
from app.models.pokemon import Pokemon
from app.models.state import WorkflowSummary
from app.services.bid_guardrails import BidGuardrailService
from app.services.listing_parser import ListingParser
from app.services.listing_validation import ListingValidationService
from app.storage.sqlite import SQLiteStorage
from app.tools.bid_execution_tool import BidExecutionTool, OfficialApiBiddingCredentials, select_bidding_service
from app.tools.listing_preparation_tool import ListingPreparationTool
from app.tools.market_research_tool import MarketResearchTool
from app.tools.scanner_tool import ScannerTool
from app.utils.logging import configure_logging

LOGGER = logging.getLogger(__name__)


class LLMConfigurationError(RuntimeError):
    pass


def _env_flag(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _require_openai_api_key() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise LLMConfigurationError(
            "OPENAI_API_KEY is required. Auction search and market analysis are always "
            "LLM prompt-driven; there is no heuristic fallback."
        )


def _build_analysis_engine() -> AnalysisEngine:
    _require_openai_api_key()
    model_name = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    return OpenAIAnalysisEngine(model_name=model_name)


def _build_auction_search_engine() -> AuctionSearchEngine:
    _require_openai_api_key()
    model_name = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    return OpenAIAuctionSearchEngine(model_name=model_name)


def _build_market_query_planner_engine() -> MarketQueryPlannerEngine:
    _require_openai_api_key()
    model_name = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    return OpenAIMarketQueryPlannerEngine(model_name=model_name)


def _build_market_research_engine() -> MarketResearchEngine:
    _require_openai_api_key()
    model_name = os.getenv("OPENAI_MARKET_RESEARCH_MODEL", os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    return OpenAIWebMarketResearchEngine(model_name=model_name)


def _build_search_config(
    target_pokemon: list[Pokemon],
    target_rules: TargetRules,
    bid_guardrails: BidGuardrails | None,
    dry_run: bool,
    poll_interval_minutes: int,
    scan_limit: int,
) -> SearchConfig:
    payload = {
        "target_pokemon": target_pokemon,
        "target_rules": target_rules,
        "dry_run": dry_run,
        "scan_limit": scan_limit,
        "poll_interval_minutes": poll_interval_minutes,
        "bidding": {
            "mode": BiddingMode(os.getenv("EBAY_BIDDING_MODE", BiddingMode.MANUAL.value)),
            "enabled": _env_flag("EBAY_BIDDING_ENABLED", False),
            "require_human_confirmation": _env_flag("EBAY_REQUIRE_HUMAN_CONFIRMATION", True),
            "open_listing_in_browser": _env_flag("EBAY_OPEN_LISTING_ON_MANUAL", False),
            "browser_automation_enabled": _env_flag("EBAY_BROWSER_AUTOMATION_ENABLED", False),
            "buy_offer_api_enabled": _env_flag("EBAY_BUY_OFFER_API_ENABLED", False),
            "buy_offer_scope": os.getenv(
                "EBAY_BUY_OFFER_SCOPE",
                "https://api.ebay.com/oauth/api_scope/buy.offer.auction",
            ),
            "marketplace_id": os.getenv("EBAY_MARKETPLACE_ID", "EBAY_US"),
            "environment": os.getenv("EBAY_ENVIRONMENT", "production"),
            "currency": os.getenv("EBAY_BID_CURRENCY", "USD"),
            "offer_api_timeout_seconds": float(os.getenv("EBAY_OFFER_API_TIMEOUT_SECONDS", "20")),
        },
        "market_research": {
            "enabled": _env_flag("EBAY_MARKET_RESEARCH_ENABLED", True),
            "mode": MarketResearchMode(os.getenv("MARKET_RESEARCH_MODE", MarketResearchMode.LLM_WEB.value)),
            "active_limit": int(os.getenv("EBAY_MARKET_RESEARCH_ACTIVE_LIMIT", "50")),
            "sold_limit": int(os.getenv("EBAY_MARKET_RESEARCH_SOLD_LIMIT", "50")),
            "marketplace_insights_enabled": _env_flag("EBAY_MARKETPLACE_INSIGHTS_ENABLED", False),
            "marketplace_insights_scope": os.getenv(
                "EBAY_MARKETPLACE_INSIGHTS_SCOPE",
                "https://api.ebay.com/oauth/api_scope/buy.marketplace.insights",
            ),
            "timeout_seconds": float(os.getenv("EBAY_MARKET_RESEARCH_TIMEOUT_SECONDS", "20")),
            "web_search_enabled": _env_flag("OPENAI_MARKET_RESEARCH_WEB_SEARCH_ENABLED", True),
            "web_search_domain_filters_enabled": _env_flag(
                "OPENAI_MARKET_RESEARCH_DOMAIN_FILTERS_ENABLED",
                False,
            ),
            "web_search_allowed_domains": os.getenv(
                "OPENAI_MARKET_RESEARCH_ALLOWED_DOMAINS",
                "ebay.com,pricecharting.com,130point.com,psacard.com,tcgplayer.com",
            ),
        },
    }
    if bid_guardrails is not None:
        payload["bid_guardrails"] = bid_guardrails

    return SearchConfig(**payload)


def run_mvp(
    target_pokemon: list[Pokemon],
    target_rules: TargetRules,
    bid_guardrails: BidGuardrails | None = None,
    dry_run: bool = True,
    database_path: str | Path | None = None,
    sample_ebay_path: str | Path | None = None,
    use_live_ebay: bool | None = None,
    poll_interval_minutes: int | None = None,
    scan_limit: int | None = None,
    auction_search_engine: AuctionSearchEngine | None = None,
    analysis_engine: AnalysisEngine | None = None,
    market_query_planner_engine: MarketQueryPlannerEngine | None = None,
    market_research_engine: MarketResearchEngine | None = None,
) -> WorkflowSummary:
    load_dotenv()
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))

    resolved_use_live_ebay = _env_flag("USE_LIVE_EBAY") if use_live_ebay is None else use_live_ebay

    resolved_poll_interval_minutes = (
        poll_interval_minutes
        if poll_interval_minutes is not None
        else int(os.getenv("POLL_INTERVAL_MINUTES", "15"))
    )
    resolved_scan_limit = scan_limit if scan_limit is not None else int(os.getenv("EBAY_SCAN_LIMIT", "100"))
    search_config = _build_search_config(
        target_pokemon=target_pokemon,
        target_rules=target_rules,
        bid_guardrails=bid_guardrails,
        dry_run=dry_run,
        poll_interval_minutes=resolved_poll_interval_minutes,
        scan_limit=resolved_scan_limit,
    )

    database = Path(database_path or os.getenv("APP_DATABASE_PATH", DATA_DIR / "psa_pokemon_bidder.db"))
    ebay_sample = Path(sample_ebay_path or DATA_DIR / "sample_ebay_listings.json")

    storage = SQLiteStorage(database)
    try:
        LOGGER.info(
            "Starting PSA Pokemon auction review. Source=%s. Bidding mode=%s.",
            "live eBay" if resolved_use_live_ebay else "sample data",
            search_config.bidding.mode.value,
        )
        ebay_client = (
            OfficialEbayApiClient(
                app_id=os.getenv("EBAY_APP_ID", ""),
                client_id=os.getenv("EBAY_CLIENT_ID"),
                client_secret=os.getenv("EBAY_CLIENT_SECRET"),
                access_token=os.getenv("EBAY_ACCESS_TOKEN"),
                official_seller_name=os.getenv("EBAY_OFFICIAL_SELLER_NAME", "psa"),
                marketplace_id=os.getenv("EBAY_MARKETPLACE_ID", "EBAY_US"),
                environment=os.getenv("EBAY_ENVIRONMENT", "production"),
                enrich_listing_page=_env_flag("EBAY_ENRICH_LISTING_PAGE", True),
                listing_page_timeout_seconds=float(os.getenv("EBAY_LISTING_PAGE_TIMEOUT_SECONDS", "5")),
            )
            if resolved_use_live_ebay
            else MockEbayClient(ebay_sample)
        )
        market_research_client = (
            OfficialEbayMarketResearchClient(
                client_id=os.getenv("EBAY_CLIENT_ID"),
                client_secret=os.getenv("EBAY_CLIENT_SECRET"),
                access_token=os.getenv("EBAY_ACCESS_TOKEN"),
                marketplace_insights_access_token=os.getenv("EBAY_MARKETPLACE_INSIGHTS_ACCESS_TOKEN"),
                marketplace_id=os.getenv("EBAY_MARKETPLACE_ID", "EBAY_US"),
                environment=os.getenv("EBAY_ENVIRONMENT", "production"),
                timeout_seconds=search_config.market_research.timeout_seconds,
            )
            if resolved_use_live_ebay
            else MockEbayMarketResearchClient()
        )
        resolved_analysis_engine = analysis_engine or _build_analysis_engine()
        resolved_auction_search_engine = auction_search_engine or _build_auction_search_engine()
        resolved_market_query_planner_engine = (
            market_query_planner_engine
            or (_build_market_query_planner_engine() if resolved_use_live_ebay else None)
        )
        resolved_market_research_engine = (
            market_research_engine
            or (
                _build_market_research_engine()
                if resolved_use_live_ebay
                and search_config.market_research.mode == MarketResearchMode.LLM_WEB
                else None
            )
        )
        bidding_service = select_bidding_service(
            bidding_config=search_config.bidding,
            credentials=OfficialApiBiddingCredentials(
                client_id=os.getenv("EBAY_CLIENT_ID"),
                client_secret=os.getenv("EBAY_CLIENT_SECRET"),
                user_access_token=os.getenv("EBAY_USER_ACCESS_TOKEN"),
                user_refresh_token=os.getenv("EBAY_USER_REFRESH_TOKEN"),
            ),
        )

        scanner_tool = ScannerTool(client=ebay_client, storage=storage)
        listing_preparation_tool = ListingPreparationTool(
            parser=ListingParser(),
            validator=ListingValidationService(),
            storage=storage,
        )
        auction_search_agent = AuctionSearchAgent(storage=storage, engine=resolved_auction_search_engine)
        market_query_planner_agent = (
            MarketQueryPlannerAgent(engine=resolved_market_query_planner_engine)
            if resolved_market_query_planner_engine
            else None
        )
        market_research_agent = (
            MarketResearchAgent(engine=resolved_market_research_engine)
            if resolved_market_research_engine
            else None
        )
        market_research_tool = MarketResearchTool(
            storage=storage,
            client=(
                market_research_client
                if market_research_agent is None
                or search_config.market_research.mode == MarketResearchMode.OFFICIAL_EBAY_API
                else None
            ),
            query_planner_agent=market_query_planner_agent,
            market_research_agent=market_research_agent,
        )
        analysis_agent = AnalysisAgent(storage=storage, engine=resolved_analysis_engine)
        bid_execution_tool = BidExecutionTool(
            storage=storage,
            guardrail_service=BidGuardrailService(storage=storage),
            bidding_service=bidding_service,
        )
        supervisor_agent = SupervisorAgent(
            scanner_tool=scanner_tool,
            listing_preparation_tool=listing_preparation_tool,
            auction_search_agent=auction_search_agent,
            market_research_tool=market_research_tool,
            analysis_agent=analysis_agent,
            bid_execution_tool=bid_execution_tool,
            storage=storage,
        )
        return supervisor_agent.run(search_config=search_config)
    finally:
        storage.close()


def run_mvp_loop(
    target_pokemon: list[Pokemon],
    target_rules: TargetRules,
    bid_guardrails: BidGuardrails | None = None,
    dry_run: bool = True,
    database_path: str | Path | None = None,
    sample_ebay_path: str | Path | None = None,
    use_live_ebay: bool | None = None,
    poll_interval_minutes: int = 15,
    scan_limit: int | None = None,
    max_cycles: int | None = None,
    sleep_seconds_fn=time.sleep,
    on_cycle=None,
    auction_search_engine: AuctionSearchEngine | None = None,
    analysis_engine: AnalysisEngine | None = None,
    market_query_planner_engine: MarketQueryPlannerEngine | None = None,
    market_research_engine: MarketResearchEngine | None = None,
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
                bid_guardrails=bid_guardrails,
                dry_run=dry_run,
                database_path=database_path,
                sample_ebay_path=sample_ebay_path,
                use_live_ebay=use_live_ebay,
                poll_interval_minutes=poll_interval_minutes,
                scan_limit=scan_limit,
                auction_search_engine=auction_search_engine,
                analysis_engine=analysis_engine,
                market_query_planner_engine=market_query_planner_engine,
                market_research_engine=market_research_engine,
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
