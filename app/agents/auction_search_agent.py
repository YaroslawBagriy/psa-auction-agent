from __future__ import annotations

import json
from abc import ABC, abstractmethod

from app.agents.base import BaseAgent
from app.agents.errors import build_llm_agent_error
from app.models.config import SearchConfig
from app.models.listing import Listing
from app.models.review import AuctionSearchResult
from app.prompts.auction_search_prompt import (
    AUCTION_SEARCH_HUMAN_PROMPT,
    AUCTION_SEARCH_SYSTEM_PROMPT,
)
from app.storage.sqlite import SQLiteStorage


class AuctionSearchEngine(ABC):
    @abstractmethod
    def search(self, listings: list[Listing], search_config: SearchConfig) -> AuctionSearchResult:
        raise NotImplementedError


class OpenAIAuctionSearchEngine(AuctionSearchEngine):
    def __init__(self, model_name: str) -> None:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", AUCTION_SEARCH_SYSTEM_PROMPT),
                ("human", AUCTION_SEARCH_HUMAN_PROMPT),
            ]
        )
        model = ChatOpenAI(model=model_name, temperature=0.0)
        self.chain = prompt | model.with_structured_output(AuctionSearchResult)

    def search(self, listings: list[Listing], search_config: SearchConfig) -> AuctionSearchResult:
        try:
            return self.chain.invoke(
                {
                    "rules_json": json.dumps(
                        search_config.target_rules.model_dump(mode="json"),
                        indent=2,
                        sort_keys=True,
                    ),
                    "listings_json": json.dumps(
                        [listing.model_dump(mode="json") for listing in listings],
                        indent=2,
                        sort_keys=True,
                    ),
                }
            )
        except Exception as exc:
            raise build_llm_agent_error("AuctionSearchAgent", exc) from exc


class AuctionSearchAgent(BaseAgent):
    name = "auction_search"

    def __init__(self, storage: SQLiteStorage, engine: AuctionSearchEngine) -> None:
        super().__init__()
        self.storage = storage
        self.engine = engine

    def run(
        self,
        run_id: str,
        listings: list[Listing],
        search_config: SearchConfig,
    ) -> AuctionSearchResult:
        if not listings:
            return AuctionSearchResult()
        result = self.engine.search(listings, search_config)
        for decision in result.decisions:
            self.storage.record_search_decision(run_id, decision)
        self.logger.info("Auction search selected %s of %s listings", len(result.selected_listing_ids()), len(listings))
        return result
