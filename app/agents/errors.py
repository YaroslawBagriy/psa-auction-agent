from __future__ import annotations


class LLMAgentError(RuntimeError):
    """Raised when a required LLM agent cannot complete its prompt call."""


def build_llm_agent_error(stage: str, exc: BaseException) -> LLMAgentError:
    error_name = exc.__class__.__name__
    detail = " ".join(str(exc).split())
    if len(detail) > 700:
        detail = f"{detail[:700]}..."

    searchable = f"{error_name} {detail}".lower()
    if "insufficient_quota" in searchable or "exceeded your current quota" in searchable:
        hint = (
            "OpenAI rejected the request because the configured API key has insufficient "
            "quota or billing is not active."
        )
    elif "rate" in searchable and "limit" in searchable:
        hint = "OpenAI rate-limited the request. Retry later or use a key/model with more available capacity."
    elif "authentication" in searchable or "api key" in searchable or "unauthorized" in searchable:
        hint = "OpenAI authentication failed. Check OPENAI_API_KEY and the configured OPENAI_MODEL."
    else:
        hint = "The LLM call failed before it could return the required structured output."

    return LLMAgentError(f"{stage} failed. {hint} Provider error: {error_name}: {detail}")
