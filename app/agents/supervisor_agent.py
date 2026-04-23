from __future__ import annotations

from datetime import UTC, datetime

from app.agents.base import BaseAgent
from app.agents.scanner_agent import ScannerAgent
from app.models.config import SearchConfig
from app.models.state import ListingWorkflowResult, WorkflowSummary
from app.storage.sqlite import SQLiteStorage


class SupervisorAgent(BaseAgent):
    name = "supervisor"

    def __init__(self, scanner_agent: ScannerAgent, workflow, storage: SQLiteStorage) -> None:
        super().__init__()
        self.scanner_agent = scanner_agent
        self.workflow = workflow
        self.storage = storage

    def run(self, search_config: SearchConfig) -> WorkflowSummary:
        run_id = search_config.run_label or f"run-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
        raw_listings = self.scanner_agent.scan(run_id=run_id, search_config=search_config)
        results: list[ListingWorkflowResult] = []

        for raw_listing in raw_listings:
            try:
                final_state = self.workflow.invoke(
                    {
                        "run_id": run_id,
                        "search_config": search_config,
                        "raw_listing": raw_listing,
                    }
                )
                results.append(
                    ListingWorkflowResult(
                        raw_listing=raw_listing,
                        pre_validation=final_state.get("pre_validation"),
                        listing=final_state.get("listing"),
                        validation=final_state.get("validation"),
                        price_research=final_state.get("price_research"),
                        analysis=final_state.get("analysis"),
                        bid_decision=final_state.get("bid_decision"),
                        bid_execution=final_state.get("bid_execution"),
                    )
                )
            except Exception as exc:  # pragma: no cover - defensive fallback
                self.logger.exception("Workflow failed for listing %s", raw_listing.listing_id)
                self.storage.record_error(run_id, raw_listing.listing_id, "workflow", str(exc))
                results.append(
                    ListingWorkflowResult(
                        raw_listing=raw_listing,
                        errors=[str(exc)],
                    )
                )

        candidate_count = sum(
            1 for result in results if result.validation is not None and result.validation.passed
        )
        analyses_completed = sum(1 for result in results if result.analysis is not None)
        bids_approved = sum(
            1 for result in results if result.bid_decision is not None and result.bid_decision.approved
        )
        bid_attempts = sum(
            1 for result in results if result.bid_execution is not None and result.bid_execution.attempted
        )

        return WorkflowSummary(
            run_id=run_id,
            scanned_count=len(raw_listings),
            candidate_count=candidate_count,
            analyses_completed=analyses_completed,
            bids_approved=bids_approved,
            bid_attempts=bid_attempts,
            results=results,
        )
