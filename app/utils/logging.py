from __future__ import annotations

import logging
import warnings


def configure_logging(level: str | int = "INFO") -> None:
    if isinstance(level, str):
        numeric_level = getattr(logging, level.upper(), logging.INFO)
    else:
        numeric_level = level

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s | %(message)s",
        force=True,
    )

    for noisy_logger in (
        "httpx",
        "httpcore",
        "openai",
        "urllib3",
        "langchain",
        "langsmith",
    ):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    warnings.filterwarnings(
        "ignore",
        message="Pydantic serializer warnings:*",
        category=UserWarning,
        module="pydantic.main",
    )
