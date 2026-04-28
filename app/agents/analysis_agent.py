from __future__ import annotations

import json
from abc import ABC, abstractmethod

from app.agents.base import BaseAgent
from app.agents.errors import build_llm_agent_error
from app.models.analysis import MarketAnalysisBatchResult, MarketAnalysisInput
from app.models.config import TargetRules
from app.models.listing import Listing
from app.prompts.analysis_prompt import ANALYSIS_HUMAN_PROMPT, ANALYSIS_SYSTEM_PROMPT
from app.storage.sqlite import SQLiteStorage


class AnalysisEngine(ABC):
    @abstractmethod
    def analyze(self, analysis_input: MarketAnalysisInput) -> MarketAnalysisBatchResult:
        raise NotImplementedError


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
        try:
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
        except Exception as exc:
            raise build_llm_agent_error("AnalysisAgent", exc) from exc


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
        self.logger.info(
            "Market analysis completed for %s listings",
            len(result.analyses),
        )
        return result
