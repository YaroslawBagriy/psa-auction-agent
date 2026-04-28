from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models.analysis import AnalysisResult
from app.models.bidding import BidDecision, BidExecutionResult
from app.models.listing import Listing, RawListing
from app.models.review import AuctionSearchDecision
from app.models.validation import ValidationResult


class SQLiteStorage:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.execute("PRAGMA journal_mode=WAL;")
        self._create_tables()

    def _create_tables(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS fetched_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                listing_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS candidate_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                listing_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS auction_search_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                listing_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS analysis_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                listing_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS bid_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                listing_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS bid_action_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                listing_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS bid_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                listing_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                listing_id TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
        ]
        for statement in statements:
            self.connection.execute(statement)
        self.connection.commit()

    def _insert_payload(self, table: str, run_id: str, listing_id: str | None, payload: dict[str, Any]) -> None:
        created_at = datetime.now(UTC).isoformat()
        payload_json = json.dumps(payload, sort_keys=True)
        with self.connection:
            self.connection.execute(
                f"INSERT INTO {table} (run_id, listing_id, payload_json, created_at) VALUES (?, ?, ?, ?)",
                (run_id, listing_id, payload_json, created_at),
            )

    def record_fetched_listing(self, run_id: str, listing: RawListing) -> None:
        self._insert_payload(
            "fetched_listings",
            run_id,
            listing.listing_id,
            listing.model_dump(mode="json"),
        )

    def record_candidate_listing(
        self,
        run_id: str,
        listing: Listing,
        validation: ValidationResult,
    ) -> None:
        self._insert_payload(
            "candidate_listings",
            run_id,
            listing.listing_id,
            {
                "listing": listing.model_dump(mode="json"),
                "validation": validation.model_dump(mode="json"),
            },
        )

    def record_search_decision(self, run_id: str, decision: AuctionSearchDecision) -> None:
        self._insert_payload(
            "auction_search_results",
            run_id,
            decision.listing_id,
            decision.model_dump(mode="json"),
        )

    def record_analysis(self, run_id: str, listing_id: str, analysis: AnalysisResult) -> None:
        self._insert_payload(
            "analysis_results",
            run_id,
            listing_id,
            analysis.model_dump(mode="json"),
        )

    def record_bid_decision(self, run_id: str, decision: BidDecision) -> None:
        self._insert_payload(
            "bid_decisions",
            run_id,
            decision.listing_id,
            decision.model_dump(mode="json"),
        )

    def record_bid_attempt(self, run_id: str, attempt: BidExecutionResult) -> None:
        self._insert_payload(
            "bid_action_results",
            run_id,
            attempt.listing_id,
            attempt.model_dump(mode="json"),
        )
        if not attempt.attempted:
            return
        self._insert_payload(
            "bid_attempts",
            run_id,
            attempt.listing_id,
            attempt.model_dump(mode="json"),
        )

    def record_error(self, run_id: str, listing_id: str | None, stage: str, message: str) -> None:
        self._insert_payload(
            "errors",
            run_id,
            listing_id,
            {"stage": stage, "message": message},
        )

    def has_bid_attempt(self, listing_id: str) -> bool:
        cursor = self.connection.execute(
            "SELECT COUNT(*) FROM bid_attempts WHERE listing_id = ?",
            (listing_id,),
        )
        result = cursor.fetchone()
        return bool(result and result[0])

    def close(self) -> None:
        self.connection.close()
