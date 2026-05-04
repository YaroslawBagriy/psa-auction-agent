from app.prompts.analysis_prompt import ANALYSIS_SYSTEM_PROMPT
from app.prompts.auction_search_prompt import AUCTION_SEARCH_SYSTEM_PROMPT
from app.prompts.market_query_prompt import MARKET_QUERY_SYSTEM_PROMPT
from app.prompts.market_research_prompt import MARKET_RESEARCH_SYSTEM_PROMPT


def test_core_agent_prompts_use_role_private_reasoning_and_one_shot_examples() -> None:
    prompts = [
        AUCTION_SEARCH_SYSTEM_PROMPT,
        MARKET_QUERY_SYSTEM_PROMPT,
        MARKET_RESEARCH_SYSTEM_PROMPT,
        ANALYSIS_SYSTEM_PROMPT,
    ]

    for prompt in prompts:
        lowered = prompt.lower()
        assert "role/persona" in lowered
        assert "private reasoning process" in lowered
        assert "one-shot example" in lowered
        assert "do not reveal hidden chain-of-thought" in lowered


def test_market_research_prompt_treats_language_as_hard_comp_field() -> None:
    prompt = MARKET_RESEARCH_SYSTEM_PROMPT.lower()

    assert "listing.card_language" in prompt
    assert "hard matching field" in prompt
    assert "japanese and english" in prompt
