from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod

import requests

from app.models.analysis import AnalysisResult
from app.models.bidding import BidDecision, BidExecutionResult
from app.models.config import SearchConfig
from app.models.listing import Listing
from app.services.bid_guardrails import BidGuardrailService
from app.storage.sqlite import SQLiteStorage


class BidExecutor(ABC):
    @abstractmethod
    def place_bid(self, listing: Listing, bid_amount: float, dry_run: bool) -> BidExecutionResult:
        raise NotImplementedError


class DryRunBidExecutor(BidExecutor):
    def place_bid(self, listing: Listing, bid_amount: float, dry_run: bool) -> BidExecutionResult:
        return BidExecutionResult(
            listing_id=listing.listing_id,
            attempted=True,
            success=True,
            dry_run=dry_run,
            bid_amount=round(bid_amount, 2),
            message=f"Dry-run only. Would place bid of ${bid_amount:.2f} on {listing.title}.",
        )


class RealEbayBidExecutor(BidExecutor):
    def __init__(
        self,
        user_access_token: str | None = None,
        environment: str = "production",
        site_id: str = "0",
        compatibility_level: str = "1423",
        session: requests.Session | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.user_access_token = user_access_token
        self.environment = environment.strip().lower()
        self.site_id = site_id
        self.compatibility_level = compatibility_level
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds
        self.logger = logging.getLogger(self.__class__.__name__)

    @property
    def trading_endpoint(self) -> str:
        if self.environment == "sandbox":
            return "https://api.sandbox.ebay.com/ws/api.dll"
        return "https://api.ebay.com/ws/api.dll"

    def place_bid(self, listing: Listing, bid_amount: float, dry_run: bool) -> BidExecutionResult:
        if dry_run:
            return BidExecutionResult(
                listing_id=listing.listing_id,
                attempted=True,
                success=True,
                dry_run=True,
                bid_amount=round(bid_amount, 2),
                message=f"Dry-run only. Would place live eBay bid of ${bid_amount:.2f}.",
            )

        if not self.user_access_token:
            return BidExecutionResult(
                listing_id=listing.listing_id,
                attempted=True,
                success=False,
                dry_run=False,
                bid_amount=round(bid_amount, 2),
                message="Live bidding requires EBAY_USER_ACCESS_TOKEN for eBay Trading API PlaceOffer.",
            )

        legacy_item_id = self._legacy_item_id(listing)
        body = self._build_place_offer_xml(
            item_id=legacy_item_id,
            bid_amount=bid_amount,
            currency=listing.raw_payload.get("summary", {}).get("currentBidPrice", {}).get("currency", "USD")
            if isinstance(listing.raw_payload.get("summary"), dict)
            else "USD",
        )
        response = self.session.post(
            self.trading_endpoint,
            headers={
                "Content-Type": "text/xml",
                "X-EBAY-API-CALL-NAME": "PlaceOffer",
                "X-EBAY-API-SITEID": self.site_id,
                "X-EBAY-API-COMPATIBILITY-LEVEL": self.compatibility_level,
                "X-EBAY-API-IAF-TOKEN": self.user_access_token,
            },
            data=body,
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            return BidExecutionResult(
                listing_id=listing.listing_id,
                attempted=True,
                success=False,
                dry_run=False,
                bid_amount=round(bid_amount, 2),
                message=f"eBay PlaceOffer HTTP failure: {exc} {getattr(response, 'text', '')}",
            )

        return self._parse_place_offer_response(
            listing_id=listing.listing_id,
            bid_amount=bid_amount,
            response_text=response.text,
        )

    def _legacy_item_id(self, listing: Listing) -> str:
        summary = listing.raw_payload.get("summary")
        if isinstance(summary, dict) and summary.get("legacyItemId"):
            return str(summary["legacyItemId"])

        if listing.listing_id.startswith("v1|"):
            parts = listing.listing_id.split("|")
            if len(parts) >= 2 and parts[1]:
                return parts[1]

        return listing.listing_id

    def _build_place_offer_xml(self, item_id: str, bid_amount: float, currency: str) -> str:
        namespace = "urn:ebay:apis:eBLBaseComponents"
        ET.register_namespace("", namespace)
        root = ET.Element(f"{{{namespace}}}PlaceOfferRequest")
        ET.SubElement(root, "ErrorLanguage").text = "en_US"
        ET.SubElement(root, "WarningLevel").text = "High"
        ET.SubElement(root, "ItemID").text = item_id
        offer = ET.SubElement(root, "Offer")
        ET.SubElement(offer, "Action").text = "Bid"
        max_bid = ET.SubElement(offer, "MaxBid", {"currencyID": currency})
        max_bid.text = f"{bid_amount:.2f}"
        ET.SubElement(offer, "Quantity").text = "1"
        return ET.tostring(root, encoding="unicode", xml_declaration=True)

    def _parse_place_offer_response(
        self,
        listing_id: str,
        bid_amount: float,
        response_text: str,
    ) -> BidExecutionResult:
        try:
            root = ET.fromstring(response_text)
        except ET.ParseError as exc:
            return BidExecutionResult(
                listing_id=listing_id,
                attempted=True,
                success=False,
                dry_run=False,
                bid_amount=round(bid_amount, 2),
                message=f"Could not parse eBay PlaceOffer response: {exc}",
            )

        ack = self._find_text(root, "Ack")
        errors = self._extract_errors(root)
        success = ack in {"Success", "Warning"}
        message = "eBay PlaceOffer accepted." if success else "eBay PlaceOffer rejected."
        if errors:
            message = f"{message} {' '.join(errors)}"

        return BidExecutionResult(
            listing_id=listing_id,
            attempted=True,
            success=success,
            dry_run=False,
            bid_amount=round(bid_amount, 2),
            message=message,
        )

    def _find_text(self, root: ET.Element, local_name: str) -> str | None:
        for element in root.iter():
            if element.tag.split("}")[-1] == local_name:
                return element.text
        return None

    def _extract_errors(self, root: ET.Element) -> list[str]:
        messages: list[str] = []
        for error in root.iter():
            if error.tag.split("}")[-1] != "Errors":
                continue
            short_message = self._child_text(error, "ShortMessage")
            long_message = self._child_text(error, "LongMessage")
            message = long_message or short_message
            if message:
                messages.append(message)
        return messages

    def _child_text(self, root: ET.Element, local_name: str) -> str | None:
        for child in root:
            if child.tag.split("}")[-1] == local_name:
                return child.text
        return None


class BidExecutionTool:
    """Deterministic LangChain workflow tool for final bid guardrails and execution."""

    name = "bid_execution_tool"

    def __init__(
        self,
        storage: SQLiteStorage,
        guardrail_service: BidGuardrailService,
        executor: BidExecutor,
    ) -> None:
        self.storage = storage
        self.guardrail_service = guardrail_service
        self.executor = executor
        self.logger = logging.getLogger(self.__class__.__name__)

    def run(
        self,
        run_id: str,
        listing: Listing,
        analysis: AnalysisResult,
        search_config: SearchConfig,
    ) -> tuple[BidDecision, BidExecutionResult | None]:
        decision = self.guardrail_service.decide(listing, analysis, search_config)
        self.storage.record_bid_decision(run_id, decision)
        self.logger.debug(
            "Bid decision for listing %s approved=%s",
            listing.listing_id,
            decision.approved,
        )

        if not decision.approved or decision.approved_max_bid is None:
            return decision, None

        execution = self.executor.place_bid(
            listing=listing,
            bid_amount=decision.approved_max_bid,
            dry_run=search_config.dry_run,
        )
        self.storage.record_bid_attempt(run_id, execution)
        return decision, execution
