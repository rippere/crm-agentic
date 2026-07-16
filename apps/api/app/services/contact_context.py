"""
Shared contact-context assembly + a fact-grounding guard for LLM drafts.

Two responsibilities, both first introduced to de-duplicate and harden the
outreach/brief LLM calls in ``app/routers/contacts.py``:

1. ``assemble_contact_context`` — gathers the *rich* first-party context for a
   contact (recent messages, call summaries, active deals) and formats it into a
   single text block. ``pre_meeting_brief`` and ``compose_email`` both call this
   so the two endpoints stay in sync instead of drifting apart. The output
   format is byte-for-byte what ``pre_meeting_brief`` used to build inline, so
   the brief is behaviour-preserving.

2. ``find_unsupported_claims`` — a lightweight, LLM-free post-generation check
   that flags specific factual claims in a generated draft that do NOT trace
   back to the supplied context, so the composer can fall back to a safe generic
   draft rather than send a hallucinated first-party fact to a prospect.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.models.call_summary import CallSummary
from app.models.deal import Deal


@dataclass
class ContactContext:
    """Assembled context for a contact.

    ``text`` is the formatted block handed to the LLM; ``has_data`` is True when
    at least one message/call/deal was found (callers can use it to decide
    whether the rich context is worth using over a shallow fallback).
    """

    text: str
    has_data: bool


async def assemble_contact_context(
    db: AsyncSession,
    workspace_id,
    contact_id,
    contact,
) -> ContactContext:
    """Gather recent messages (3), call summaries (2), and active deals (3) for a
    contact and format them into a single context block.

    ``contact`` is the already-loaded ORM row (both callers fetch it first for
    the 404 check), so we don't re-query it. Mirrors the exact gather + format
    that ``pre_meeting_brief`` performed inline, so brief output is unchanged.
    """
    # Recent messages (subjects only — bodies are deliberately not surfaced).
    # graph_only rows are excluded: they exist for the relationship graph, carry
    # no body, and must never become grounding facts for a generated draft.
    msg_result = await db.execute(
        select(Message)
        .where(
            Message.workspace_id == workspace_id,
            Message.contact_id == contact_id,
            Message.graph_only.is_(False),
        )
        .order_by(Message.received_at.desc())
        .limit(3)
    )
    messages = msg_result.scalars().all()

    call_result = await db.execute(
        select(CallSummary)
        .where(
            CallSummary.workspace_id == workspace_id,
            CallSummary.contact_id == contact_id,
        )
        .order_by(CallSummary.call_date.desc())
        .limit(2)
    )
    calls = call_result.scalars().all()

    deal_result = await db.execute(
        select(Deal)
        .where(
            Deal.workspace_id == workspace_id,
            Deal.contact_id == contact_id,
            Deal.stage.not_in(["closed_lost"]),
        )
        .limit(3)
    )
    deals = deal_result.scalars().all()

    context_parts = [
        f"Contact: {contact.name} ({contact.email}), {contact.role} at {contact.company}",
        f"Status: {contact.status}",
    ]
    if messages:
        context_parts.append("Recent emails:")
        for m in messages:
            context_parts.append(f"  - Subject: {m.subject or '(none)'}")
    if calls:
        context_parts.append("Recent calls:")
        for c in calls:
            context_parts.append(f"  - {c.title}: {c.summary[:300] if c.summary else '(no summary)'}")
    if deals:
        context_parts.append("Active deals:")
        for d in deals:
            context_parts.append(
                f"  - {d.title} | Stage: {d.stage} | Value: ${d.value:,.0f} | Win prob: {d.ml_win_probability}%"
            )

    return ContactContext(
        text="\n".join(context_parts),
        has_data=bool(messages or calls or deals),
    )


# ---------------------------------------------------------------------------
# Fact-grounding guard
# ---------------------------------------------------------------------------
#
# Goal: stop a generated draft from asserting a *specific first-party fact*
# (a named person/company, a dollar figure, a percentage) that is NOT present in
# the context we supplied — the classic hallucination that reaches a prospect and
# destroys trust ("congrats on your $5M raise" when there was no raise).
#
# Design is deliberately simple and LLM-free: it extracts a small set of
# high-signal claim tokens from the draft and checks each one is substring-present
# (case-insensitive) in the supplied context. A miss = an ungrounded claim.
#
# HONEST LIMITATIONS (do not oversell this guard):
#   * It only catches claims that surface as (a) a multi-word Proper Noun phrase
#     e.g. "Acme Robotics", (b) a $ amount, or (c) an X% figure. A *single-token*
#     fabricated proper noun ("TechCorp") or a fabricated fact phrased in plain
#     lowercase prose ("your recent expansion into Europe") will pass through.
#   * It is purely lexical: a paraphrase of a real fact may be flagged (false
#     positive) and a fabrication that happens to reuse context words will pass
#     (false negative).
#   * Common greeting/sign-off/pronoun words are allow-listed to keep the
#     false-positive rate low, which necessarily widens the blind spot above.
# It is a cheap safety net, not a guarantee. When it fires, the composer falls
# back to a generic name+company-only draft rather than trusting the model.

# Capitalized words that routinely open sentences / greetings / sign-offs and are
# NOT proper-noun claims. Kept lowercase for case-insensitive comparison.
_COMMON_WORDS = {
    "hi", "hello", "hey", "dear", "greetings",
    "thanks", "thank", "best", "regards", "sincerely", "cheers", "warmly",
    "i", "i'm", "i'd", "i've", "i'll", "we", "we're", "we'd", "we've", "we'll",
    "you", "you're", "you'd", "you've", "you'll", "your", "yours", "our", "ours",
    "my", "me", "us", "they", "he", "she", "it", "it's", "this", "that", "these",
    "those", "the", "a", "an", "as", "and", "but", "or", "if", "so", "then",
    "when", "while", "here", "there", "let", "let's", "looking", "hope", "hoping",
    "would", "could", "should", "will", "can", "just", "also", "please", "wanted",
    "reaching", "reach", "following", "quick", "connecting", "connect", "re",
    "via", "with", "for", "to", "from", "at", "on", "in", "of", "about", "over",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
}

# Claims are extracted per *segment*: the draft is split on sentence/line
# punctuation first so a phrase can never be glued together across a sentence or
# line boundary (e.g. a subject ending "…Q3 Proposal" followed by a body opening
# "Hi Alice" must not read as the single entity "Proposal Hi Alice").
_SEGMENT_SPLIT = re.compile(r"[.!?,;:\n\r()\[\]\"'`]+")
# Within a segment, a run of 2+ capitalized words = candidate proper-noun phrase
# (e.g. person or company). Separator is spaces/tabs only — never newlines.
_PROPER_NOUN_PHRASE = re.compile(r"\b([A-Z][\w&\-]*(?:[ \t]+[A-Z][\w&\-]*)+)\b")
# Money amounts, e.g. $5M, $1,200, $3.4 billion (we capture the numeric core).
_MONEY = re.compile(r"\$\s?[\d,]+(?:\.\d+)?\s*(?:[KMB]|thousand|million|billion)?", re.IGNORECASE)
# Percentages, e.g. 40%, 12.5 %.
_PERCENT = re.compile(r"\b\d+(?:\.\d+)?\s?%")


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def find_unsupported_claims(subject: str, body: str, context: str) -> list[str]:
    """Return the list of specific claims in the draft not found in ``context``.

    Empty list == every checkable claim is grounded. See the module-level notes
    for exactly what is (and is not) checked.
    """
    draft = f"{subject}\n{body}"
    haystack = _normalize(context)
    unsupported: list[str] = []

    for segment in _SEGMENT_SPLIT.split(draft):
        for match in _PROPER_NOUN_PHRASE.finditer(segment):
            phrase = match.group(1)
            # Drop leading/trailing allow-listed words (e.g. "Hello Alice" ->
            # "Alice", "Best Regards" -> nothing) so greetings and sign-offs
            # don't masquerade as named entities.
            words = phrase.split()
            while words and words[0].lower() in _COMMON_WORDS:
                words.pop(0)
            while words and words[-1].lower() in _COMMON_WORDS:
                words.pop()
            # Only a *remaining* multi-word proper-noun phrase is a claim.
            if len(words) < 2:
                continue
            candidate = " ".join(words)
            if _normalize(candidate) not in haystack:
                unsupported.append(candidate)

    for pattern in (_MONEY, _PERCENT):
        for match in pattern.finditer(draft):
            token = match.group(0)
            if _normalize(token) not in haystack:
                unsupported.append(token.strip())

    return unsupported


def draft_is_grounded(subject: str, body: str, context: str) -> bool:
    """True when the draft asserts no specific claim absent from ``context``."""
    return not find_unsupported_claims(subject, body, context)


def safe_generic_draft(contact_name: str | None, contact_company: str | None) -> tuple[str, str]:
    """A neutral fallback draft built only from known first-party fields (name +
    company). Contains no specific claims, so it cannot leak a hallucinated fact.
    """
    first = (contact_name or "there").split()[0] if contact_name else "there"
    company_bit = ""
    if contact_company and contact_company not in ("Unknown", "", "None"):
        company_bit = f" at {contact_company}"
    subject = "Reaching out"
    body = (
        f"Hi {first},\n\n"
        f"I wanted to introduce myself and learn more about the work you're doing"
        f"{company_bit}. Would you be open to a brief conversation in the coming weeks?\n\n"
        f"Best regards"
    )
    return subject, body


# ---------------------------------------------------------------------------
# Humanizer pass
# ---------------------------------------------------------------------------
#
# A lightweight second Claude call that runs a grounded, already-generated draft
# through the top AI-writing tells documented in the global humanizer skill
# (~/.claude/skills/humanizer/SKILL.md, github.com/blader/humanizer, based on
# Wikipedia's "Signs of AI writing" guide) before it reaches Ben for review: em
# dashes, curly quotes, AI-vocabulary words, filler phrases, rule-of-three padding,
# inflated-significance language, and collaborative-communication artifacts
# ("I hope this helps!"). It must never be allowed to make the draft worse or
# less safe than the input, so it fails soft: any API error, malformed response,
# or empty output leaves the original subject/body untouched, and the caller is
# expected to re-run the fact-grounding guard on the result before trusting it
# (a rewrite could in principle introduce a claim that isn't in the corpus).

_HUMANIZER_SYSTEM_PROMPT = (
    "You are a lightweight editing pass that removes common AI-writing tells from an "
    "already-drafted outreach email (see ~/.claude/skills/humanizer/SKILL.md for the full "
    "pattern reference, based on Wikipedia's 'Signs of AI writing' guide). Rewrite the "
    "subject and body to fix, when present: em dashes or en dashes (replace with a "
    "period, comma, or colon instead), curly quotation marks (use straight quotes), "
    "overused AI vocabulary (e.g. delve, crucial, boasts, testament, underscores, "
    "tapestry, vibrant, showcase), filler phrases ('in order to', 'due to the fact "
    "that'), rule-of-three padding, inflated-significance language, and collaborative-"
    "communication artifacts ('I hope this helps!', 'Let me know if you have any "
    "questions!'). Preserve every fact, name, figure, and the overall meaning, tone, and "
    "length -- do not add any claim that is not already present in the input, and do not "
    "shorten or pad the email. If the draft already reads naturally, return it unchanged. "
    'Return JSON only: {"subject": "<subject>", "body": "<body>"}'
)


def _strip_code_fence(raw: str) -> str:
    """Strip a leading/trailing ``` fence if the model wrapped its JSON in one."""
    stripped = raw.strip()
    if not stripped.startswith("```"):
        return raw
    lines = stripped.splitlines()
    return "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])


def humanize_draft(client, subject: str, body: str) -> tuple[str, str]:
    """Run a grounded draft through the humanizer pattern-cleanup pass.

    Returns the (possibly rewritten) ``(subject, body)``. On any failure -- API
    error, non-JSON response, missing fields -- returns the original ``subject``/
    ``body`` unchanged so a humanizer hiccup never blocks a draft from reaching
    Ben. Callers should re-run ``find_unsupported_claims`` on the result against
    the same grounding corpus used for the original draft before accepting it.
    """
    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=_HUMANIZER_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": f"Subject: {subject}\n\nBody:\n{body}"}
            ],
        )
        raw = message.content[0].text if message.content else "{}"
        data = json.loads(_strip_code_fence(raw))
        new_subject = data.get("subject") or subject
        new_body = data.get("body") or body
        return new_subject, new_body
    except Exception:
        return subject, body
