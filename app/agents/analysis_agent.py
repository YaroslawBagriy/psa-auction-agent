from __future__ import annotations

import json
from abc import ABC, abstractmethod

from app.agents.base import BaseAgent
from app.models.analysis import AnalysisResult, MarketAnalysisBatchResult, MarketAnalysisInput
from app.models.config import TargetRules
from app.models.listing import Listing
from app.prompts.analysis_prompt import ANALYSIS_HUMAN_PROMPT, ANALYSIS_SYSTEM_PROMPT
from app.storage.sqlite import SQLiteStorage


class AnalysisEngine(ABC):
    @abstractmethod
    def analyze(self, analysis_input: MarketAnalysisInput) -> MarketAnalysisBatchResult:
        raise NotImplementedError


class HeuristicAnalysisEngine(AnalysisEngine):
    def analyze(self, analysis_input: MarketAnalysisInput) -> MarketAnalysisBatchResult:
        analyses = [
            self._analyze_listing(listing)
            for listing in analysis_input.listings
        ]
        return MarketAnalysisBatchResult(analyses=analyses)

    def _analyze_listing(self, listing: Listing) -> AnalysisResult:
        market_context = listing.market_context
        risk_flags: list[str] = []

        recent_sales = [
            float(value)
            for value in market_context.get("recent_sales", [])
            if isinstance(value, (int, float))
        ]
        estimated_market_value = float(market_context.get("estimated_market_value") or 0.0)
        if estimated_market_value <= 0 and recent_sales:
            estimated_market_value = round(sum(recent_sales) / len(recent_sales), 2)
        if estimated_market_value <= 0:
            estimated_market_value = round(listing.current_price * 1.08, 2)
            risk_flags.append("limited_market_context")

        trend_outlook = str(market_context.get("trend_outlook", "uncertain")).strip().lower() or "uncertain"
        if trend_outlook not in {"upward", "steady", "downward", "uncertain"}:
            trend_outlook = "uncertain"
            risk_flags.append("unknown_trend_outlook")

        ratio_by_trend = {
            "upward": 0.90,
            "steady": 0.85,
            "downward": 0.75,
            "uncertain": 0.80,
        }
        recommended_max_bid = round(estimated_market_value * ratio_by_trend[trend_outlook], 2)
        should_bid = (
            trend_outlook in {"upward", "steady"}
            and recommended_max_bid > listing.current_price
            and estimated_market_value > listing.current_price
        )

        confidence = 0.58
        if recent_sales:
            confidence += 0.12
        if trend_outlook in {"upward", "steady"}:
            confidence += 0.10
        if "limited_market_context" in risk_flags:
            confidence -= 0.18
        confidence = max(0.0, min(round(confidence, 3), 0.95))

        if trend_outlook == "downward":
            risk_flags.append("downward_price_trend")
        if recommended_max_bid <= listing.current_price:
            risk_flags.append("insufficient_margin_above_current_bid")

        reasoning = market_context.get("trend_summary") or (
            f"Current price is ${listing.current_price:.2f}, estimated market value is "
            f"${estimated_market_value:.2f}, trend outlook is {trend_outlook}, and the "
            f"recommended max bid is ${recommended_max_bid:.2f}."
        )

        return AnalysisResult(
            listing_id=listing.listing_id,
            url=listing.url,
            should_bid=should_bid,
            confidence=confidence,
            estimated_market_value=estimated_market_value,
            recommended_max_bid=recommended_max_bid,
            trend_outlook=trend_outlook,  # type: ignore[arg-type]
            reasoning=reasoning,
            risk_flags=risk_flags,
        )


class OpenAIAnalysisEngine(AnalysisEngine):
    def __init__(self, model_name: str) -> None:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", ANALYSIS_SYSTEM_PROMPT),
                ("human", ANALYSIS_HUMAN_PROMPT),
            ]
        )
        model = ChatOpenAI(model=model_name, temperature=0.0)
        self.chain = prompt | model.with_structured_output(MarketAnalysisBatchResult)

    def analyze(self, analysis_input: MarketAnalysisInput) -> MarketAnalysisBatchResult:
        return self.chain.invoke(
            {
                "listings_json": json.dumps(
                    [listing.model_dump(mode="json") for listing in analysis_input.listings],
                    indent=2,
                    sort_keys=True,
                ),
                "rules_json": json.dumps(
                    analysis_input.target_rules.model_dump(mode="json"),
                    indent=2,
                    sort_keys=True,
                ),
            }
        )


class AnalysisAgent(BaseAgent):
    name = "analysis"

    def __init__(self, storage: SQLiteStorage, engine: AnalysisEngine) -> None:
        super().__init__()
        self.storage = storage
        self.engine = engine

    def run(
        self,
        run_id: str,
        listings: list[Listing],
        target_rules: TargetRules,
    ) -> MarketAnalysisBatchResult:
        if not listings:
            return MarketAnalysisBatchResult()

        analysis_input = MarketAnalysisInput(
            listings=listings,
            target_rules=target_rules,
        )
        result = self.engine.analyze(analysis_input)
        for analysis in result.analyses:
            self.storage.record_analysis(run_id, analysis.listing_id, analysis)
        self.logger.debug(
            "Market analysis completed for %s listings",
            len(result.analyses),
        )
        return result
