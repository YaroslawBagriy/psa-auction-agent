from pathlib import Path

from app.main import run_mvp, run_mvp_loop
from app.models.config import TargetRules
from app.models.pokemon import Pokemon


def test_run_mvp_dry_run_processes_sample_data(tmp_path: Path) -> None:
    summary = run_mvp(
        target_pokemon=[Pokemon.PIKACHU, Pokemon.CHARIZARD, Pokemon.GENGAR],
        target_rules=TargetRules(
            allowed_grades={"9", "10"},
            max_current_price=1500.0,
        ),
        dry_run=True,
        database_path=tmp_path / "workflow.db",
        use_openai_search_agent=False,
        use_openai_analysis=False,
    )

    assert summary.scanned_count == 7
    assert summary.candidate_count == 2
    assert summary.selected_link_count == 2
    assert summary.analyses_completed == 2
    assert summary.bids_approved == 1
    assert summary.bid_attempts == 1

    approved = [result for result in summary.results if result.bid_decision and result.bid_decision.approved]
    assert len(approved) == 1
    assert approved[0].raw_listing.listing_id == "1001"
    assert approved[0].listing is not None
    assert approved[0].listing.in_psa_vault is True
    assert approved[0].search_decision is not None
    assert approved[0].search_decision.should_track is True
    assert approved[0].bid_execution is not None
    assert approved[0].bid_execution.dry_run is True


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
        use_openai_search_agent=False,
        use_openai_analysis=False,
        poll_interval_minutes=15,
        max_cycles=2,
        sleep_seconds_fn=fake_sleep,
        on_cycle=on_cycle,
    )

    assert len(summaries) == 2
    assert [summary.scanned_count for summary in summaries] == [7, 7]
    assert len(cycle_ids) == 2
    assert slept == [900]
