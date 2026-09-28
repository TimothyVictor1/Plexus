"""Asking questions about the company's own records (redesign B6)."""

from __future__ import annotations

import pytest

from core.ask import answer, suggestions
from core.ask.retrieval import _terms, search_documents
from core.language.phrases import humanise_tokens

pytestmark = pytest.mark.integration

TENANT = "demo"


async def test_a_question_about_time_is_answered_from_measured_work() -> None:
    result = await answer(TENANT, "Why does it take so long to get paid?", "tester")
    assert result.grounded is True
    assert len(result.text) > 40
    assert any(ch.isdigit() or "week" in result.text or "day" in result.text for ch in result.text)


async def test_something_the_company_has_no_record_of_is_refused() -> None:
    """Saying 'I cannot tell' is the right answer, and better than a plausible invention."""
    result = await answer(TENANT, "How many staff cars do we own?", "tester")
    assert "cannot tell" in result.text.lower() or "not" in result.text.lower()


async def test_an_organisation_with_nothing_connected_says_so() -> None:
    result = await answer("no-such-org", "How long does anything take?", "tester")
    assert result.grounded is False
    assert result.sources == []


async def test_an_empty_question_is_not_sent_anywhere() -> None:
    result = await answer(TENANT, "   ", "tester")
    assert result.grounded is False


async def test_answers_are_remembered_as_a_conversation() -> None:
    first = await answer(TENANT, "What takes the longest?", "tester")
    assert first.conversation_id
    second = await answer(TENANT, "And why is that?", "tester", first.conversation_id)
    assert second.conversation_id == first.conversation_id


async def test_sources_name_the_tool_they_came_from() -> None:
    result = await answer(TENANT, "invoice payment reminder", "tester")
    for source in result.sources:
        assert source.tool
        assert source.reference


async def test_no_placeholder_is_ever_shown_to_a_reader() -> None:
    """Tokens are the right thing to store and the wrong thing to display."""
    result = await answer(TENANT, "expense paid back", "tester")
    for source in result.sources:
        assert "<PERSON_" not in source.title
        assert "<ORG_" not in source.title
    assert "<PERSON_" not in result.text


def test_token_humanising() -> None:
    assert humanise_tokens("paid <PERSON_1a2b> at <ORG_9999>") == "paid someone at a company"


def test_search_terms_drop_filler_words() -> None:
    assert "the" not in _terms("why does the invoice take so long")
    assert "invoice" in _terms("why does the invoice take so long")


async def test_search_finds_records_by_their_words() -> None:
    found = await search_documents(TENANT, "invoice payment")
    assert found
    assert all(p.source_id and p.external_id for p in found)


async def test_suggestions_come_from_what_plexus_currently_knows() -> None:
    found = await suggestions(TENANT)
    assert 1 <= len(found) <= 3
    assert all(q.endswith("?") for q in found)
