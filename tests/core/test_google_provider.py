"""Gemini provider (spec 09). No network: request shaping and reply handling only."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from core.models.providers.google import (
    MAX_ATTEMPTS,
    RETRY_STATUSES,
    GoogleProvider,
    _strip_fence,
)
from core.models.types import Message


class Label(BaseModel):
    label: str


def provider(key: str = "test-key") -> GoogleProvider:
    return GoogleProvider("gemini-3.8-flash", key)


def test_reports_unavailable_without_a_key() -> None:
    assert provider("").available is False
    assert provider().available is True


def test_key_never_appears_in_repr() -> None:
    assert "test-key" not in repr(provider())


def test_system_messages_become_system_instruction() -> None:
    body = provider()._body(
        [Message(role="system", content="be brief"), Message(role="user", content="hello")],
        None,
        100,
    )
    assert body["systemInstruction"]["parts"][0]["text"] == "be brief"
    assert body["contents"] == [{"role": "user", "parts": [{"text": "hello"}]}]


def test_assistant_turns_are_relabelled_for_gemini() -> None:
    body = provider()._body([Message(role="assistant", content="hi")], None, 100)
    assert body["contents"][0]["role"] == "model"


def test_schema_requests_json_and_states_the_shape() -> None:
    body = provider()._body([Message(role="user", content="x")], Label, 100)
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    instruction = body["systemInstruction"]["parts"][0]["text"]
    assert "JSON only" in instruction
    assert json.loads(instruction.split("schema exactly:\n")[1])["title"] == "Label"


def test_max_tokens_is_passed_through() -> None:
    assert (
        provider()._body([Message(role="user", content="x")], None, 2048)["generationConfig"][
            "maxOutputTokens"
        ]
        == 2048
    )


def test_text_extraction_skips_thought_parts() -> None:
    payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "thinking out loud", "thought": True},
                        {"text": "the answer"},
                    ]
                }
            }
        ]
    }
    assert GoogleProvider._text_of(payload) == "the answer"


def test_text_extraction_survives_an_empty_reply() -> None:
    assert GoogleProvider._text_of({"candidates": []}) == ""
    assert GoogleProvider._text_of({}) == ""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"a":1}', '{"a":1}'),
        ('```json\n{"a":1}\n```', '{"a":1}'),
        ('```\n{"a":1}\n```', '{"a":1}'),
        ('  {"a":1}  ', '{"a":1}'),
    ],
)
def test_strip_fence(raw: str, expected: str) -> None:
    assert _strip_fence(raw) == expected


def test_overload_and_rate_limit_are_retried_but_bad_requests_are_not() -> None:
    assert 503 in RETRY_STATUSES
    assert 429 in RETRY_STATUSES
    assert 400 not in RETRY_STATUSES
    assert 404 not in RETRY_STATUSES
    assert MAX_ATTEMPTS >= 2
