from __future__ import annotations

import logging

from app.models.config import SearchConfig
from app.models.listing import Listing, RawListing
from app.models.state import ListingWorkflowResult
from app.services.listing_parser import ListingParser
from app.services.listing_validation import ListingValidationService
from app.storage.sqlite import SQLiteStorage


class ListingPreparationTool:
    """Deterministic LangChain workflow tool for parsing and hard scope validation."""

    name = "listing_preparation_tool"

    def __init__(
        self,
        parser: ListingParser,
        validator: ListingValidationService,
        storage: SQLiteStorage,
    ) -> None:
        self.parser = parser
        self.validator = validator
        self.storage = storage
        self.logger = logging.getLogger(self.__class__.__name__)

    def run(
        self,
        run_id: str,
        raw_listings: list[RawListing],
        search_config: SearchConfig,
    ) -> tuple[list[ListingWorkflowResult], dict[str, ListingWorkflowResult], list[Listing]]:
        results: list[ListingWorkflowResult] = []
        results_by_listing_id: dict[str, ListingWorkflowResult] = {}
        validated_listings: list[Listing] = []

        for raw_listing in raw_listings:
            try:
                result = ListingWorkflowResult(raw_listing=raw_listing)
                pre_validation = self.validator.validate_raw(raw_listing, search_config)
                result.pre_validation = pre_validation
                if pre_validation.passed:
                    listing = self.parser.parse(raw_listing)
                    result.listing = listing
                    validation = self.validator.validate_listing(listing, search_config)
                    result.validation = validation
                    if validation.passed:
                        self.storage.record_candidate_listing(run_id, listing, validation)
                        validated_listings.append(listing)
                        self.logger.info(
                            "Validated candidate listing_id=%s pokemon=%s grade=%s price=%.2f ends_in=%.1fm title=%s",
                            listing.listing_id,
                            listing.detected_pokemon.display_name if listing.detected_pokemon else "unknown",
                            listing.grade_value,
                            listing.current_price,
                            listing.minutes_remaining(),
                            listing.title[:120],
                        )
                    else:
                        self.logger.info(
                            "Rejected parsed listing_id=%s reasons=%s title=%s",
                            raw_listing.listing_id,
                            "; ".join(validation.reasons),
                            raw_listing.title[:120],
                        )
                else:
                    self.logger.info(
                        "Rejected raw listing_id=%s reasons=%s title=%s",
                        raw_listing.listing_id,
                        "; ".join(pre_validation.reasons),
                        raw_listing.title[:120],
                    )
                results.append(result)
                results_by_listing_id[raw_listing.listing_id] = result
            except Exception as exc:  # pragma: no cover - defensive workflow boundary
                self.logger.exception("Listing preparation failed for %s", raw_listing.listing_id)
                self.storage.record_error(run_id, raw_listing.listing_id, "listing_preparation", str(exc))
                failed = ListingWorkflowResult(raw_listing=raw_listing, errors=[str(exc)])
                results.append(failed)
                results_by_listing_id[raw_listing.listing_id] = failed

        self.logger.info(
            "Listing preparation produced %s validated candidates from %s raw listings",
            len(validated_listings),
            len(raw_listings),
        )
        return results, results_by_listing_id, validated_listings
