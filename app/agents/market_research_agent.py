from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from app.agents.base import BaseAgent
from app.agents.errors import build_llm_agent_error
from app.models.config import MarketResearchConfig
from app.models.listing import Listing
from app.models.market import LLMMarketResearchOutput, MarketResearchResult
from app.prompts.market_research_prompt import MARKET_RESEARCH_HUMAN_PROMPT, MARKET_RESEARCH_SYSTEM_PROMPT


class MarketResearchEngine(ABC):
    @abstractmethod
    def research(
        self,
        listing: Listing,
        config: MarketResearchConfig,
        query_strings: list[str],
    ) -> MarketResearchResult:
        raise NotImplementedError


class OpenAIWebMarketResearchEngine(MarketResearchEngine):
    def __init__(
        self,
        model_name: str,
        responses_client: Any | None = None,
    ) -> None:
        if responses_client is None:
            from openai import OpenAI

            responses_client = OpenAI().responses
        self.model_name = model_name
        self.responses_client = responses_client
        self.logger = logging.getLogger(self.__class__.__name__)

    def research(
        self,
        listing: Listing,
        config: MarketResearchConfig,
        query_strings: list[str],
    ) -> MarketResearchResult:
        try:
            response, domain_filters_applied = self._create_response(
                listing=listing,
                config=config,
                query_strings=query_strings,
                include_domain_filters=True,
            )
            output = LLMMarketResearchOutput.model_validate_json(response.output_text)
            source_urls = output.source_urls or self._extract_source_urls(response)
            return MarketResearchResult(
                listing_id=listing.listing_id,
                query=output.query or (query_strings[0] if query_strings else listing.title),
                active_listing_count=output.active_listing_count,
                sold_listing_count=output.sold_listing_count,
                sell_through_rate=output.sell_through_rate,
                recent_sold_prices=output.recent_sold_prices,
                estimated_market_value=output.estimated_market_value,
                evidence_summary=output.evidence_summary,
                source_urls=source_urls,
                warnings=output.warnings,
                raw_payload={
                    "provider": "openai_responses_web_search",
                    "model": self.model_name,
                    "queries": query_strings,
                    "response_id": getattr(response, "id", None),
                    "domain_filters_applied": domain_filters_applied,
                },
            )
        except Exception as exc:
            raise build_llm_agent_error("MarketResearchAgent", exc) from exc

    def _create_response(
        self,
        listing: Listing,
        config: MarketResearchConfig,
        query_strings: list[str],
        include_domain_filters: bool,
    ) -> tuple[Any, bool]:
        domain_filters_applied = bool(
            config.web_search_enabled
            and include_domain_filters
            and config.web_search_domain_filters_enabled
            and config.web_search_allowed_domains
        )
        try:
            response = self.responses_client.create(
                model=self.model_name,
                instructions=MARKET_RESEARCH_SYSTEM_PROMPT,
                input=MARKET_RESEARCH_HUMAN_PROMPT.format(
                    listing_json=json.dumps(
                        listing.model_dump(mode="json"),
                        indent=2,
                        sort_keys=True,
                    ),
                    queries_json=json.dumps(query_strings, indent=2, sort_keys=True),
                ),
                tools=self._web_search_tools(config, include_domain_filters=include_domain_filters),
                tool_choice="auto" if config.web_search_enabled else "none",
                include=["web_search_call.action.sources"],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "market_research_result",
                        "schema": self._strict_market_research_schema(),
                        "strict": True,
                    }
                },
                temperature=0.0,
            )
        except Exception as exc:
            if domain_filters_applied and self._is_unsupported_tool_filter_error(exc):
                self.logger.warning(
                    "OpenAI web-search domain filters are unsupported for model=%s; retrying without filters.",
                    self.model_name,
                )
                return self._create_response(
                    listing=listing,
                    config=config,
                    query_strings=query_strings,
                    include_domain_filters=False,
                )
            raise
        return response, domain_filters_applied

    def _strict_market_research_schema(self) -> dict[str, Any]:
        """Return an OpenAI strict-mode JSON schema for market research output.

        The Responses API requires `additionalProperties: false` and, in strict
        mode, every property must be listed as required. Optional values are
        represented as nullable fields instead of omitted keys.
        """
        nullable_int = {"anyOf": [{"type": "integer"}, {"type": "null"}]}
        nullable_number = {"anyOf": [{"type": "number"}, {"type": "null"}]}
        properties: dict[str, Any] = {
            "listing_id": {"type": "string"},
            "query": {"type": "string"},
            "active_listing_count": nullable_int,
            "sold_listing_count": nullable_int,
            "sell_through_rate": nullable_number,
            "recent_sold_prices": {
                "type": "array",
                "items": {"type": "number"},
            },
            "estimated_market_value": nullable_number,
            "evidence_summary": {"type": "string"},
            "source_urls": {
                "type": "array",
                "items": {"type": "string"},
            },
            "warnings": {
                "type": "array",
                "items": {"type": "string"},
            },
        }
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": properties,
            "required": list(properties),
        }

    def _web_search_tools(
        self,
        config: MarketResearchConfig,
        include_domain_filters: bool = True,
    ) -> list[dict[str, Any]]:
        if not config.web_search_enabled:
            return []
        tool: dict[str, Any] = {
            "type": "web_search",
            "user_location": {
                "type": "approximate",
                "country": "US",
            },
        }
        if (
            include_domain_filters
            and config.web_search_domain_filters_enabled
            and config.web_search_allowed_domains
        ):
            tool["filters"] = {
                "allowed_domains": config.web_search_allowed_domains,
            }
        return [tool]

    def _is_unsupported_tool_filter_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return "filters" in message and "not supported" in message and "tools" in message

    def _extract_source_urls(self, response: Any) -> list[str]:
        urls: list[str] = []
        for output_item in getattr(response, "output", []) or []:
            item = output_item.model_dump() if hasattr(output_item, "model_dump") else output_item
            if not isinstance(item, dict):
                continue
            action = item.get("action")
            if isinstance(action, dict):
                for source in action.get("sources") or []:
                    if isinstance(source, dict) and source.get("url"):
                        urls.append(str(source["url"]))
            for content in item.get("content") or []:
                if not isinstance(content, dict):
                    continue
                for annotation in content.get("annotations") or []:
                    if isinstance(annotation, dict) and annotation.get("url"):
                        urls.append(str(annotation["url"]))
        return list(dict.fromkeys(urls))


class MarketResearchAgent(BaseAgent):
    name = "market_research"

    def __init__(self, engine: MarketResearchEngine) -> None:
        super().__init__()
        self.engine = engine

    def run(
        self,
        listing: Listing,
        config: MarketResearchConfig,
        query_strings: list[str],
    ) -> MarketResearchResult:
        result = self.engine.research(listing, config, query_strings)
        self.logger.debug(
            "LLM market research listing_id=%s active=%s sold=%s sell_through=%s value=%s",
            listing.listing_id,
            result.active_listing_count,
            result.sold_listing_count,
            result.sell_through_rate,
            result.estimated_market_value,
        )
        return result
