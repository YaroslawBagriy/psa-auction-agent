from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.config import SearchConfig
from app.models.listing import Listing, RawListing
from app.models.validation import ValidationResult
from app.services.listing_validation import ListingValidationService
from app.storage.sqlite import SQLiteStorage


class ValidationAgent(BaseAgent):
    name = "validation"

    def __init__(self, service: ListingValidationService, storage: SQLiteStorage) -> None:
        super().__init__()
        self.service = service
        self.storage = storage

    def pre_validate(self, raw_listing: RawListing, search_config: SearchConfig) -> ValidationResult:
        result = self.service.validate_raw(raw_listing, search_config)
        self.logger.debug(
            "Pre-validation for listing %s passed=%s",
            raw_listing.listing_id,
            result.passed,
        )
        return result

    def validate(self, run_id: str, listing: Listing, search_config: SearchConfig) -> ValidationResult:
        result = self.service.validate_listing(listing, search_config)
        self.logger.debug(
            "Validation for listing %s passed=%s",
            listing.listing_id,
            result.passed,
        )
        if result.passed:
            self.storage.record_candidate_listing(run_id, listing, result)
        return result

