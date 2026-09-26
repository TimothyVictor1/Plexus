"""Router types shared by providers and callers (spec 09)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Role(StrEnum):
    actor = "actor"
    verifier = "verifier"
    workhorse = "workhorse"
    classifier = "classifier"
    embedder = "embedder"


class ModelId(BaseModel):
    vendor: str
    model: str
    prompt_name: str = ""
    prompt_version: int = 0

    def __str__(self) -> str:
        return f"{self.vendor}/{self.model}"


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class Completion(BaseModel):
    text: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    model: ModelId
    usage: Usage = Field(default_factory=Usage)
    latency_ms: float = 0.0


class VendorSeparationError(RuntimeError):
    """Actor and verifier resolved to the same vendor in production."""


class ModelUnavailableError(RuntimeError):
    """The vendor is unreachable or the circuit is open."""


class SchemaValidationError(ValueError):
    """The model returned output that failed schema validation twice."""
