from __future__ import annotations

from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    stage: str
    passed: bool
    reasons: list[str] = Field(default_factory=list)

