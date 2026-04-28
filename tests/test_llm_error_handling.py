import pytest

from app.agents.analysis_agent import OpenAIAnalysisEngine
from app.agents.auction_search_agent import OpenAIAuctionSearchEngine
from app.agents.errors import LLMAgentError
from app.models.analysis import MarketAnalysisInput
from app.models.config import SearchConfig, TargetRules
from app.models.pokemon import Pokemon


class ExplodingChain:
    def invoke(self, payload):
        raise RuntimeError("Error code: 429 - insufficient_quota")


def test_auction_search_engine_wraps_provider_quota_errors() -> None:
    engine = object.__new__(OpenAIAuctionSearchEngine)
    engine.chain = ExplodingChain()
    search_config = SearchConfig(
        target_pokemon=[Pokemon.CHARIZARD],
        target_rules=TargetRules(allowed_grades={"10"}),
    )

    with pytest.raises(LLMAgentError, match="AuctionSearchAgent.*insufficient quota"):
        engine.search([], search_config)


def test_analysis_engine_wraps_provider_quota_errors() -> None:
    engine = object.__new__(OpenAIAnalysisEngine)
    engine.chain = ExplodingChain()
    analysis_input = MarketAnalysisInput(
        listings=[],
        target_rules=TargetRules(allowed_grades={"10"}),
    )

    with pytest.raises(LLMAgentError, match="AnalysisAgent.*insufficient quota"):
        engine.analyze(analysis_input)
