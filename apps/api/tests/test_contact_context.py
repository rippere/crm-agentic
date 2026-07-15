"""Tests for the shared contact-context assembler + fact-grounding guard
(app.services.contact_context)."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.contact_context import (
    assemble_contact_context,
    draft_is_grounded,
    find_unsupported_claims,
    safe_generic_draft,
)
from tests.conftest import _make_scalars_result


def _fake_contact() -> MagicMock:
    contact = MagicMock()
    contact.id = uuid.uuid4()
    contact.name = "Alice Smith"
    contact.email = "alice@example.com"
    contact.role = "VP Sales"
    contact.company = "Acme"
    contact.status = "lead"
    return contact


# ---------------------------------------------------------------------------
# assemble_contact_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assembles_context_from_seeded_messages_calls_deals():
    """The helper gathers messages + calls + deals into one context block."""
    workspace_id = uuid.uuid4()
    contact = _fake_contact()

    msg = MagicMock()
    msg.subject = "Re: Q3 Proposal"

    call = MagicMock()
    call.title = "Discovery Call"
    call.summary = "We discussed pricing and rollout timing."

    deal = MagicMock()
    deal.title = "Acme Platform Rollout"
    deal.stage = "proposal"
    deal.value = 50000.0
    deal.ml_win_probability = 65

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _make_scalars_result([msg]),
        _make_scalars_result([call]),
        _make_scalars_result([deal]),
    ])

    result = await assemble_contact_context(db, workspace_id, contact.id, contact)

    assert result.has_data is True
    # Contact header
    assert "Alice Smith (alice@example.com), VP Sales at Acme" in result.text
    assert "Status: lead" in result.text
    # Messages / calls / deals all present
    assert "Recent emails:" in result.text
    assert "Re: Q3 Proposal" in result.text
    assert "Recent calls:" in result.text
    assert "Discovery Call: We discussed pricing and rollout timing." in result.text
    assert "Active deals:" in result.text
    assert "Acme Platform Rollout | Stage: proposal | Value: $50,000 | Win prob: 65%" in result.text
    # All three queries were issued
    assert db.execute.await_count == 3


@pytest.mark.asyncio
async def test_assembles_context_with_no_history():
    """With no messages/calls/deals, only the contact header is emitted."""
    workspace_id = uuid.uuid4()
    contact = _fake_contact()

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _make_scalars_result([]),
        _make_scalars_result([]),
        _make_scalars_result([]),
    ])

    result = await assemble_contact_context(db, workspace_id, contact.id, contact)

    assert result.has_data is False
    assert "Alice Smith" in result.text
    assert "Recent emails:" not in result.text
    assert "Recent calls:" not in result.text
    assert "Active deals:" not in result.text


@pytest.mark.asyncio
async def test_assembles_context_handles_missing_subject_and_summary():
    """Null subject/summary degrade to placeholders rather than crashing."""
    workspace_id = uuid.uuid4()
    contact = _fake_contact()

    msg = MagicMock()
    msg.subject = None

    call = MagicMock()
    call.title = "Intro Call"
    call.summary = None

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _make_scalars_result([msg]),
        _make_scalars_result([call]),
        _make_scalars_result([]),
    ])

    result = await assemble_contact_context(db, workspace_id, contact.id, contact)

    assert "Subject: (none)" in result.text
    assert "Intro Call: (no summary)" in result.text


# ---------------------------------------------------------------------------
# Fact-grounding guard
# ---------------------------------------------------------------------------


_CONTEXT = (
    "Contact: Alice Smith (alice@example.com), VP Sales at Acme\n"
    "Status: lead\n"
    "Recent emails:\n"
    "  - Subject: Re: Q3 Proposal\n"
    "Active deals:\n"
    "  - Acme Platform Rollout | Stage: proposal | Value: $50,000 | Win prob: 65%"
)


def test_guard_passes_grounded_draft():
    """A draft citing only facts present in the context is grounded."""
    subject = "Following up on the Q3 Proposal"
    body = (
        "Hi Alice,\n\nThanks for the note. I wanted to follow up on the Acme Platform "
        "Rollout and the Q3 Proposal we discussed.\n\nBest regards"
    )
    assert find_unsupported_claims(subject, body, _CONTEXT) == []
    assert draft_is_grounded(subject, body, _CONTEXT) is True


def test_guard_flags_unsupported_named_company():
    """A fabricated multi-word company name is flagged."""
    subject = "Congrats on the news"
    body = "Hi Alice,\n\nI saw your partnership with Globex Industries.\n\nBest regards"

    unsupported = find_unsupported_claims(subject, body, _CONTEXT)

    assert "Globex Industries" in unsupported
    assert draft_is_grounded(subject, body, _CONTEXT) is False


def test_guard_flags_unsupported_named_person():
    """A fabricated mutual contact is flagged."""
    subject = "Intro"
    body = "Hi Alice,\n\nJohn Doe suggested I reach out.\n\nBest regards"

    unsupported = find_unsupported_claims(subject, body, _CONTEXT)

    assert "John Doe" in unsupported


def test_guard_flags_unsupported_money_and_percentage():
    """Invented figures — the classic hallucinated first-party fact — are flagged."""
    subject = "Congrats"
    body = "Hi Alice,\n\nCongrats on the $5M raise and 40% growth this year.\n\nBest regards"

    unsupported = find_unsupported_claims(subject, body, _CONTEXT)

    assert any("5M" in u for u in unsupported)
    assert any("40%" in u for u in unsupported)


def test_guard_allows_figures_present_in_context():
    """Figures that DO appear in the context are not flagged."""
    subject = "Re: Q3 Proposal"
    body = "Hi Alice,\n\nOn the $50,000 rollout at 65% win probability — shall we talk?\n\nBest regards"

    assert find_unsupported_claims(subject, body, _CONTEXT) == []


def test_guard_does_not_flag_greetings_or_signoffs():
    """Greeting/sign-off capitalization must not masquerade as a named entity."""
    subject = "Hello Alice"
    body = "Hi Alice,\n\nHope you are well. Looking forward to hearing from you.\n\nBest Regards"

    assert find_unsupported_claims(subject, body, _CONTEXT) == []


def test_guard_known_limitation_single_token_name_passes():
    """Documented blind spot: a single-token invented proper noun is NOT caught.

    This test pins the guard's honest limitation so it is visible rather than
    assumed away — tighten it only alongside a false-positive strategy.
    """
    subject = "Hello"
    body = "Hi Alice,\n\nI saw the Globex news.\n\nBest regards"

    assert find_unsupported_claims(subject, body, _CONTEXT) == []


# ---------------------------------------------------------------------------
# safe_generic_draft
# ---------------------------------------------------------------------------


def test_safe_generic_draft_is_itself_grounded():
    """The fallback must never introduce a claim the guard would reject."""
    subject, body = safe_generic_draft("Alice Smith", "Acme")

    assert "Alice" in body
    assert "Acme" in body
    assert find_unsupported_claims(subject, body, _CONTEXT) == []


def test_safe_generic_draft_handles_unknown_fields():
    """Missing name/company degrade gracefully."""
    subject, body = safe_generic_draft(None, "Unknown")

    assert subject
    assert "Hi there," in body
    assert "Unknown" not in body
