from app.prompts.market_query_prompt import MARKET_QUERY_SYSTEM_PROMPT


def test_market_query_prompt_requires_exact_title_first_and_web_query_guidance() -> None:
    prompt = MARKET_QUERY_SYSTEM_PROMPT.lower()

    assert "exact ebay listing title as the first query" in prompt
    assert "normalized identity queries" in prompt
    assert "card subject after the card number" in prompt
    assert "pricecharting" in prompt
    assert "130point" in prompt
    assert "web-research agent" in prompt
    assert "include words like \"sold\" or \"completed\"" in prompt
    assert "do not add them to the exact-title query" in prompt
    assert "role/persona" in prompt
    assert "private reasoning process" in prompt
    assert "one-shot example" in prompt
    assert "do not reveal hidden chain-of-thought" in prompt
    assert "listing.card_language" in prompt
    assert "do not mix" in prompt
