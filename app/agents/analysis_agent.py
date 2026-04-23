from __future__ import annotations

import json
from abc import ABC, abstractmethod

from app.agents.base import BaseAgent
from app.models.analysis import AnalysisResult, AnalyzerInput
from app.models.config import TargetRules
from app.models.listing import Listing
from app.models.price_research import PriceResearchResult
from app.prompts.analysis_prompt import ANALYSIS_HUMAN_PROMPT, ANALYSIS_SYSTEM_PROMPT
from app.storage.sqlite import SQLiteStorage


class AnalysisEngine(ABC):
    @abstractmethod
    def analyze(self, analyzer_input: AnalyzerInput) -> AnalysisResult:
        raise NotImplementedError


class HeuristicAnalysisEngine(AnalysisEngine):
    def analyze(self, analyzer_input: AnalyzerInput) -> AnalysisResult:
        listing = analyzer_input.listing
        price_research = analyzer_input.price_research
        risk_flags: list[str] = []

        estimated_market_value = price_research.target_grade_price or 0.0
        if estimated_market_value <= 0:
            risk_flags.append("missing_exact_grade_comp")
            reasoning = "No exact grade-specific PriceCharting comp was found, so the card stays out of bidding range."
            return AnalysisResult(
                should_bid=False,
                confidence=0.30,
                estimated_market_value=0.0,
                recommended_max_bid=0.0,
                reasoning=reasoning,
                risk_flags=risk_flags,
            )

        if price_research.match_confidence < 0.60:
            risk_flags.append("weak_price_match")

        recommended_max_bid = min(estimated_market_value * 0.82, estimated_market_value - 15.0)
        recommended_max_bid = max(round(recommended_max_bid, 2), 0.0)
        current_price = listing.current_price
        expected_margin = recommended_max_bid - current_price
        should_bid = expected_margin > 0 and price_research.match_confidence >= 0.60

        confidence = 0.55 + (price_research.match_confidence * 0.25)
        if expected_margin > 0:
            confidence += min(expected_margin / 200.0, 0.15)
        if "weak_price_match" in risk_flags:
            confidence -= 0.15
        confidence = max(0.0, min(round(confidence, 3), 0.98))

        if current_price >= estimated_market_value:
            risk_flags.append("current_price_at_or_above_market")
        elif expected_margin < 20:
            risk_flags.append("thin_margin")

        reasoning = (
            f"Current price is ${current_price:.2f}, grade-adjusted market value is "
            f"${estimated_market_value:.2f}, and the conservative max bid is "
            f"${recommended_max_bid:.2f}."
        )
        return AnalysisResult(
            should_bid=should_bid,
            confidence=confidence,
            estimated_market_value=round(estimated_market_value, 2),
            recommended_max_bid=recommended_max_bid,
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
        self.chain = prompt | model.with_structured_output(AnalysisResult)

    def analyze(self, analyzer_input: AnalyzerInput) -> AnalysisResult:
        return self.chain.invoke(
            {
                "listing_json": json.dumps(
                    analyzer_input.listing.model_dump(mode="json"),
                    indent=2,
                    sort_keys=True,
                ),
                "price_json": json.dumps(
                    analyzer_input.price_research.model_dump(mode="json"),
                    indent=2,
                    sort_keys=True,
                ),
                "rules_json": json.dumps(
                    analyzer_input.target_rules.model_dump(mode="json"),
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
        listing: Listing,
        price_research: PriceResearchResult,
        target_rules: TargetRules,
    ) -> AnalysisResult:
        analyzer_input = AnalyzerInput(
            listing=listing,
            price_research=price_research,
            target_rules=target_rules,
        )
        result = self.engine.analyze(analyzer_input)
        self.storage.record_analysis(run_id, listing.listing_id, result)
        self.logger.debug(
            "Analysis for listing %s should_bid=%s confidence=%.3f",
            listing.listing_id,
            result.should_bid,
            result.confidence,
        )
        return result

