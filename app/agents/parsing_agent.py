from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.listing import Listing, RawListing
from app.services.listing_parser import ListingParser


class ParsingAgent(BaseAgent):
    name = "parser"

    def __init__(self, parser: ListingParser) -> None:
        super().__init__()
        self.parser = parser

    def run(self, raw_listing: RawListing) -> Listing:
        self.logger.debug("Parsing listing %s", raw_listing.listing_id)
        return self.parser.parse(raw_listing)

