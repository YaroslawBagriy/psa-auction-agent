from __future__ import annotations

import json
from abc import ABC, abstractmethod

from app.agents.base import BaseAgent
from app.agents.errors import build_llm_agent_error
from app.models.listing import Listing
from app.models.market import MarketResearchQueryPlan, MarketResearchQueryPlanBatch
from app.prompts.market_query_prompt import MARKET_QUERY_HUMAN_PROMPT, MARKET_QUERY_SYSTEM_PROMPT


class MarketQueryPlannerEngine(ABC):
    @abstractmethod
    def plan(self, listings: list[Listing]) -> MarketResearchQueryPlanBatch:
        raise NotImplementedError


class OpenAIMarketQueryPlannerEngine(MarketQueryPlannerEngine):
    def __init__(self, model_name: str) -> None:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", MARKET_QUERY_SYSTEM_PROMPT),
                ("human", MARKET_QUERY_HUMAN_PROMPT),
            ]
        )
        model = ChatOpenAI(model=model_name, temperature=0.0)
        self.chain = prompt | model.with_structured_output(MarketResearchQueryPlanBatch)

    def plan(self, listings: list[Listing]) -> MarketResearchQueryPlanBatch:
        try:
            return self.chain.invoke(
                {
                    "listings_json": json.dumps(
                        [
                            {
                                "listing_id": listing.listing_id,
                                "title": listing.title,
                                "normalized_title": listing.normalized_title,
                                "detected_pokemon": (
                                    listing.detected_pokemon.display_name
                                    if listing.detected_pokemon
                                    else None
                                ),
                                "set_name": listing.set_name,
                                "card_number": listing.card_number,
                                "grading_company": listing.grading_company,
                                "grade_value": listing.grade_value,
                            }
                            for listing in listings
                        ],
                        indent=2,
                        sort_keys=True,
                    )
                }
            )
        except Exception as exc:
            raise build_llm_agent_error("MarketQueryPlannerAgent", exc) from exc


class MarketQueryPlannerAgent(BaseAgent):
    name = "market_query_planner"

    def __init__(self, engine: MarketQueryPlannerEngine) -> None:
        super().__init__()
        self.engine = engine

    def run(self, listings: list[Listing]) -> dict[str, MarketResearchQueryPlan]:
        if not listings:
            return {}
        batch = self.engine.plan(listings)
        plans_by_listing_id = batch.by_listing_id()
        for listing in listings:
            plan = plans_by_listing_id.get(listing.listing_id)
            query_count = len(plan.queries) if plan else 0
            self.logger.debug(
                "Market query plan listing_id=%s query_count=%s",
                listing.listing_id,
                query_count,
            )
        return plans_by_listing_id
