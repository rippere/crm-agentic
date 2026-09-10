"""
Deep-research / venue-scoring service for the Autonomous Lead Engine (Inc 1).

The LLM pass of the hybrid discovery spine (spec §2.1.5, resolutions R3/R7).
Given one structured ``PlaceResult`` from the places waterfall (§2.1.4) plus the
active scoring rubric (§2.1.3), it asks Claude for the seven 1..5 subscores and
the qualitative closing context, then computes the deterministic 0..100 overall
and tier **in Python** (the load-bearing finding §2.1.2 — the overall is a pure
weighted mean, so score correlation is testable without LLM determinism).

Design contract (mirrors ``sequence_sender._draft_body``): this is a guarded,
patchable async boundary that **never raises**. Any LLM/parse failure degrades to
a hard-facts-only ``VenueScore`` (subscores empty, overall 0, tier 'B',
research_confidence 'Low') so the worker can still upsert the venue as a lead.

LLM client + model id come from the shared singleton (R7): the client is
``app.services.llm.get_async_anthropic_client()`` and the model id is
``settings.ANTHROPIC_MODEL_SMART`` — never an inline ``AsyncAnthropic()`` and
never a model literal in logic.

The qualitative keys are exactly the four R6 shared-contract fields
(``fit_summary``, ``why_it_works``, ``best_outreach_angle``, ``key_risks``) plus
the contact fields — no ``potential_placement`` divergence. ``market_context`` is
the seam the psychology spine (Inc 3) later fills; it ships empty so discovery
stands alone.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.services.discovery_rubric import DEFAULT_RUBRIC, compute_overall, tier_for
from app.services.llm import get_async_anthropic_client
from app.services.places import PlaceResult

logger = logging.getLogger(__name__)

# Max tokens for the single research call. Enough for seven subscores + four
# qualitative paragraphs + contact fields as compact JSON.
_RESEARCH_MAX_TOKENS = 1024

# The only accepted values for research_confidence; anything else -> "Low".
_RESEARCH_CONFIDENCE_VALUES = ("High", "Medium", "Low")


@dataclass
class VenueScore:
    """One venue's score: LLM subscores/context + Python-computed overall/tier.

    ``subscores`` are the clamped 1..scale_max per-criterion values the LLM
    returned (empty when the LLM pass produced nothing usable). ``overall`` and
    ``tier`` are always derived in Python via ``compute_overall`` / ``tier_for``.
    The four qualitative fields (``fit_summary`` … ``key_risks``) are the R6
    shared contract the psychology distiller + drafting later read. ``raw`` keeps
    the parsed LLM payload for debugging/provenance.
    """

    subscores: dict[str, float]          # criterion.key -> 1..scale_max
    overall: float                       # from compute_overall (0..100)
    tier: str                            # from tier_for
    fit_summary: str | None
    why_it_works: str | None
    best_outreach_angle: str | None
    key_risks: str | None
    best_contact: str | None
    contact_role: str | None
    contact_email: str | None
    contact_phone: str | None
    research_confidence: str             # "High" | "Medium" | "Low"
    best_scouting_window: str | None
    raw: dict


def _criteria_block(rubric: dict) -> str:
    """Render the rubric criteria as a human-readable scoring guide for the prompt."""
    lines: list[str] = []
    for crit in rubric.get("criteria", []):
        key = crit.get("key")
        if not key:
            continue
        label = crit.get("label", key)
        what_5 = crit.get("what_5_means") or crit.get("what_5") or ""
        why = crit.get("why_it_matters") or ""
        frag = f'- "{key}" ({label})'
        if what_5:
            frag += f" — 5 means: {what_5}"
        if why:
            frag += f" (why it matters: {why})"
        lines.append(frag)
    return "\n".join(lines)


def _extract_text(message: Any) -> str:
    """Concatenate the text blocks of an Anthropic ``messages.create`` result."""
    parts: list[str] = []
    for block in getattr(message, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)


def _parse_strict_json(text: str) -> dict:
    """Best-effort strict-JSON parse of the model reply. Returns ``{}`` on failure.

    Tolerates a ```` ```json … ``` ```` code fence and leading/trailing prose by
    slicing to the outermost braces before parsing. Never raises.
    """
    if not text:
        return {}
    candidate = text.strip()
    if candidate.startswith("```"):
        # Strip an opening fence (``` or ```json) and the trailing fence.
        inner = candidate[3:]
        if inner[:4].lower() == "json":
            inner = inner[4:]
        end_fence = inner.rfind("```")
        candidate = (inner[:end_fence] if end_fence != -1 else inner).strip()
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:  # noqa: BLE001 — fall through to brace-slice recovery
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(candidate[start : end + 1])
                return parsed if isinstance(parsed, dict) else {}
            except Exception:  # noqa: BLE001
                return {}
        return {}


async def _research_venue(
    place: PlaceResult,
    rubric: dict,
    market_context: str,
    *,
    client: Any = None,
) -> dict:
    """Run the single deep-research LLM call for one venue and return parsed JSON.

    Issues exactly one ``messages.create(model=settings.ANTHROPIC_MODEL_SMART, ...)``
    asking for STRICT JSON with the shape::

        {"subscores": {<criterion.key>: 1..scale_max for each rubric criterion},
         "fit_summary", "why_it_works", "best_outreach_angle", "key_risks",
         "best_contact", "contact_role", "contact_email", "contact_phone",
         "research_confidence", "best_scouting_window"}

    Parses the reply; on ANY failure (no client, SDK error, unparseable reply)
    returns ``{}``. Never raises. Patchable seam for tests — inject ``client`` or
    monkeypatch this function directly.
    """
    if client is None:
        client = get_async_anthropic_client()

    criteria_keys = [c.get("key") for c in rubric.get("criteria", []) if c.get("key")]
    scale_max = rubric.get("scale_max", 5)

    facts = {
        "name": place.name,
        "category": place.category,
        "address": place.address,
        "locality": place.locality,
        "phone": place.phone,
        "website": place.website,
        "source_url": place.source_url,
    }
    keys_spec = ", ".join(f'"{k}": <number 1..{scale_max}>' for k in criteria_keys)
    market_block = f"MARKET CONTEXT:\n{market_context}\n\n" if market_context else ""

    # TODO(execute): tune this instruction wording against the live model + the
    # Burlington ground-truth sheet until produced subscores clear the §2.1.14
    # acceptance bar (Pearson r >= 0.6, tier agreement >= 0.7). The JSON output
    # contract below is FIXED (worker + rubric depend on it); only the guidance
    # prose is best-effort and may be iterated against real API responses.
    prompt = (
        "You are a field-marketing analyst scoring a venue as a prospect for an "
        "experiential photo-booth placement. Research the venue from the facts "
        "below plus your general knowledge of it, then score it on every rubric "
        f"criterion on a 1..{scale_max} scale (halves allowed).\n\n"
        f"VENUE FACTS (JSON):\n{json.dumps(facts, indent=2)}\n\n"
        f"{market_block}"
        "RUBRIC CRITERIA (score each key):\n"
        f"{_criteria_block(rubric)}\n\n"
        "Also write concise closing context: fit_summary (one sentence), "
        "why_it_works, best_outreach_angle, key_risks, and — if discoverable — a "
        "best_contact name, their contact_role, contact_email, contact_phone, and "
        "a best_scouting_window (when to visit). Set research_confidence to one of "
        '"High" | "Medium" | "Low" reflecting how much you actually know.\n\n'
        "Return ONLY a single strict-JSON object, no prose, no code fence, with "
        "EXACTLY these keys:\n"
        f'{{"subscores": {{{keys_spec}}}, '
        '"fit_summary": <string>, "why_it_works": <string>, '
        '"best_outreach_angle": <string>, "key_risks": <string>, '
        '"best_contact": <string|null>, "contact_role": <string|null>, '
        '"contact_email": <string|null>, "contact_phone": <string|null>, '
        '"research_confidence": <"High"|"Medium"|"Low">, '
        '"best_scouting_window": <string|null>}'
    )

    try:
        message = await client.messages.create(
            model=settings.ANTHROPIC_MODEL_SMART,
            max_tokens=_RESEARCH_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_strict_json(_extract_text(message))
    except Exception as exc:  # noqa: BLE001 — guard: never raise, degrade to {}
        logger.warning(
            "discovery_research research_failed venue=%s provider=%s exc=%s",
            getattr(place, "name", None), getattr(place, "provider", None), exc,
        )
        return {}


def _clamp_subscores(raw_subscores: Any, rubric: dict) -> dict[str, float]:
    """Coerce + clamp LLM subscores to ``[1, scale_max]`` for known keys only.

    Unknown criterion keys and non-numeric values are dropped. A subscore missing
    from the LLM output is simply absent here — ``compute_overall`` treats a
    missing criterion as 0 for that criterion (per §2.1.3).
    """
    scale_max = float(rubric.get("scale_max", 5) or 5)
    valid_keys = {c.get("key") for c in rubric.get("criteria", []) if c.get("key")}
    out: dict[str, float] = {}
    if not isinstance(raw_subscores, dict):
        return out
    for key, value in raw_subscores.items():
        if key not in valid_keys:
            continue
        try:
            num = float(value)
        except (TypeError, ValueError):
            continue
        out[key] = max(1.0, min(scale_max, num))
    return out


async def score_venue(
    place: PlaceResult,
    *,
    rubric: dict = DEFAULT_RUBRIC,
    market_context: str = "",
    client: Any = None,
) -> VenueScore:
    """Score one venue: LLM subscores/context + Python-computed overall/tier.

    ``client`` defaults to the shared ``get_async_anthropic_client()`` singleton;
    when ``settings.ANTHROPIC_API_KEY`` is empty the guarded call short-circuits
    (no request) and the venue degrades to a hard-facts-only result. Calls
    :func:`_research_venue`, clamps the returned subscores to ``[1, scale_max]``,
    then computes ``overall = compute_overall`` and ``tier = tier_for``. On an
    empty LLM result the venue still yields a VenueScore (``subscores={}``,
    ``overall=0``, ``tier='B'``, ``research_confidence='Low'``) carrying only the
    hard facts. Never raises.
    """
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "") or ""
    research: dict = {}
    if api_key:
        research = await _research_venue(place, rubric, market_context, client=client)
    if not isinstance(research, dict):
        research = {}

    subscores = _clamp_subscores(research.get("subscores"), rubric)

    if subscores:
        overall = compute_overall(subscores, rubric)
    else:
        # Empty LLM result -> hard-facts-only; overall 0, tier the min-0 band
        # (tier_for(0.0) == 'B' for DEFAULT_RUBRIC, per §2.1.5).
        overall = 0.0
    tier = tier_for(overall, rubric)

    confidence = research.get("research_confidence")
    if confidence not in _RESEARCH_CONFIDENCE_VALUES:
        confidence = "Low"

    return VenueScore(
        subscores=subscores,
        overall=overall,
        tier=tier,
        fit_summary=research.get("fit_summary"),
        why_it_works=research.get("why_it_works"),
        best_outreach_angle=research.get("best_outreach_angle"),
        key_risks=research.get("key_risks"),
        best_contact=research.get("best_contact"),
        contact_role=research.get("contact_role"),
        contact_email=research.get("contact_email"),
        contact_phone=research.get("contact_phone"),
        research_confidence=confidence,
        best_scouting_window=research.get("best_scouting_window"),
        raw=research,
    )
