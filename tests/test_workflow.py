from pathlib import Path

import pytest

from app.agents.analysis_agent import AnalysisEngine
from app.agents.auction_search_agent import AuctionSearchEngine
from app.main import LLMConfigurationError, run_mvp, run_mvp_loop
from app.models.analysis import AnalysisResult, MarketAnalysisBatchResult, MarketAnalysisInput
from app.models.bidding import BiddingMode
from app.models.config import TargetRules
from app.models.pokemon import Pokemon
from app.models.review import AuctionSearchDecision, AuctionSearchResult


class FakeAuctionSearchEngine(AuctionSearchEngine):
    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    def search(self, listings, search_config):
        self.batch_sizes.append(len(listings))
        return AuctionSearchResult(
            decisions=[
                AuctionSearchDecision(
                    listing_id=listing.listing_id,
                    url=listing.url,
                    should_track=True,
                    confidence=0.9,
                    rationale="Selected by test LLM double.",
                )
                for listing in listings
            ]
        )


class FakeAnalysisEngine(AnalysisEngine):
    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    def analyze(self, analysis_input: MarketAnalysisInput) -> MarketAnalysisBatchResult:
        self.batch_sizes.append(len(analysis_input.listings))
        analyses: list[AnalysisResult] = []
        for listing in analysis_input.listings:
            market_context = listing.market_context
            estimated_market_value = float(market_context.get("estimated_market_value") or 0.0)
            trend_outlook = str(market_context.get("trend_outlook", "uncertain"))
            should_bid = listing.listing_id == "1001"
            analyses.append(
                AnalysisResult(
                    listing_id=listing.listing_id,
                    url=listing.url,
                    should_bid=should_bid,
                    confidence=0.9 if should_bid else 0.8,
                    estimated_market_value=estimated_market_value,
                    recommended_max_bid=round(estimated_market_value * 0.9, 2),
                    trend_outlook=trend_outlook,  # type: ignore[arg-type]
                    reasoning=str(market_context.get("trend_summary") or "Test LLM double analysis."),
                    risk_flags=[] if should_bid else ["not_selected_by_test_double"],
                )
            )
        return MarketAnalysisBatchResult(analyses=analyses)


def _fake_auction_search_engine() -> FakeAuctionSearchEngine:
    return FakeAuctionSearchEngine()


def _fake_analysis_engine() -> FakeAnalysisEngine:
    return FakeAnalysisEngine()


def test_run_mvp_dry_run_processes_sample_data(tmp_path: Path) -> None:
    auction_search_engine = _fake_auction_search_engine()
    analysis_engine = _fake_analysis_engine()

    summary = run_mvp(
        target_pokemon=[Pokemon.PIKACHU, Pokemon.CHARIZARD, Pokemon.GENGAR],
        target_rules=TargetRules(
            allowed_grades={"9", "10"},
            max_current_price=1500.0,
        ),
        dry_run=True,
        database_path=tmp_path / "workflow.db",
        use_live_ebay=False,
        auction_search_engine=auction_search_engine,
        analysis_engine=analysis_engine,
    )

    assert summary.scanned_count == 7
    assert summary.candidate_count == 2
    assert summary.selected_link_count == 2
    assert summary.analyses_completed == 2
    assert summary.bids_approved == 1
    assert summary.bid_attempts == 0
    assert auction_search_engine.batch_sizes == [1, 1]
    assert analysis_engine.batch_sizes == [1, 1]

    approved = [result for result in summary.results if result.bid_decision and result.bid_decision.approved]
    assert len(approved) == 1
    assert approved[0].raw_listing.listing_id == "1001"
    assert approved[0].listing is not None
    assert approved[0].listing.in_psa_vault is True
    assert approved[0].search_decision is not None
    assert approved[0].search_decision.should_track is True
    assert approved[0].bid_execution is not None
    assert approved[0].bid_execution.dry_run is True
    assert approved[0].bid_execution.mode == BiddingMode.MANUAL
    assert approved[0].bid_execution.status == "requires_user_action"
    assert approved[0].bid_execution.attempted is False
    assert approved[0].bid_execution.listing_url == "https://www.ebay.com/itm/1001"


def test_run_mvp_loop_runs_multiple_cycles_without_sleeping(tmp_path: Path) -> None:
    slept: list[int] = []
    cycle_ids: list[str] = []

    def fake_sleep(seconds: int) -> None:
        slept.append(seconds)

    def on_cycle(summary) -> None:
        cycle_ids.append(summary.run_id)

    summaries = run_mvp_loop(
        target_pokemon=[Pokemon.PIKACHU, Pokemon.CHARIZARD, Pokemon.GENGAR],
        target_rules=TargetRules(
            allowed_grades={"9", "10"},
            max_current_price=1500.0,
        ),
        dry_run=True,
        database_path=tmp_path / "workflow-loop.db",
        use_live_ebay=False,
        poll_interval_minutes=15,
        max_cycles=2,
        sleep_seconds_fn=fake_sleep,
        on_cycle=on_cycle,
        auction_search_engine=_fake_auction_search_engine(),
        analysis_engine=_fake_analysis_engine(),
    )

    assert len(summaries) == 2
    assert [summary.scanned_count for summary in summaries] == [7, 7]
    assert len(cycle_ids) == 2
    assert slept == [900]


def test_run_mvp_requires_llm_engines_or_openai_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")

    with pytest.raises(LLMConfigurationError, match="OPENAI_API_KEY is required"):
        run_mvp(
            target_pokemon=[Pokemon.CHARIZARD],
            target_rules=TargetRules(allowed_grades={"10"}),
            dry_run=True,
            database_path=tmp_path / "workflow-missing-key.db",
            use_live_ebay=False,
        )
