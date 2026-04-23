from pathlib import Path

from app.main import run_mvp
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
    )

    assert summary.scanned_count == 7
    assert summary.candidate_count == 2
    assert summary.analyses_completed == 2
    assert summary.bids_approved == 1
    assert summary.bid_attempts == 1

    approved = [result for result in summary.results if result.bid_decision and result.bid_decision.approved]
    assert len(approved) == 1
    assert approved[0].raw_listing.listing_id == "1001"
    assert approved[0].bid_execution is not None
    assert approved[0].bid_execution.dry_run is True
