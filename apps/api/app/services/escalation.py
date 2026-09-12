"""Escalation decision service — the pure, DB-free heart of the control graph.

Autonomous Lead Engine, Increment 2 (§2.2.2). Two layers, no I/O:

1. **PROPOSE** — ``propose_action`` reads the signals (reply sentiment, engagement
   score, per-stage thresholds) and returns the action the engine *wants* to take
   (``send`` / ``escalate`` / ``stop`` / ``hold``). This is signal-driven and knows
   nothing about the operator's autonomy settings.
2. **CLAMP** — ``clamp_action`` narrows the proposed action by the per-stage
   operator cap (``auto`` / ``ask`` / ``off``) via the ``_CLAMP`` table: ``ask``
   downgrades an outward ``send`` to ``park`` (surface for human approval), ``off``
   downgrades to ``hold`` (kill switch — and suppresses even an escalation), and a
   ``stop`` (an unsubscribe) is always honored regardless of mode.

``decide_action`` composes the two and returns an :class:`EscalationDecision`
value object the caller (``sequence_sender._run_tick`` / the call-outcome path)
persists as an ``escalation_decisions`` row. This module has **no DB and no LLM**
— it is exhaustively unit-testable as a decision truth table.

The per-stage cap is resolved by ``app.services.authority.resolve_authority``
(the ONE shared resolver, R11) reading ``stage_controls`` + ``workspace_autonomy``;
this module only consumes the resolved ``mode`` string. ``DEFAULT_STAGE_MODE`` is
``'ask'`` for every stage (R12 fail-closed).

The ``decide_action_model`` seam (``decided_by='model'``) is a documented design
placeholder — NOT built here. When it lands it will read
``settings.ANTHROPIC_MODEL_SMART`` via the shared client (R7).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Vocabularies (mirror the 025 CHECK constraints) ────────────────────────────
STAGE_MODES: tuple[str, ...] = ("auto", "ask", "off")
PROPOSED_ACTIONS: tuple[str, ...] = ("send", "escalate", "stop", "hold")
FINAL_ACTIONS: tuple[str, ...] = ("send", "park", "escalate", "stop", "hold")
SENTIMENTS: tuple[str, ...] = (
    "positive", "neutral", "negative", "objection", "booking", "unsubscribe",
)  # R8 vocab
DECIDERS: tuple[str, ...] = ("threshold", "model", "human")

# The six lead stages (mirror leads.stage CHECK). Every stage fail-closes to 'ask'.
_STAGES: tuple[str, ...] = ("new", "contacted", "engaged", "qualified", "converted", "lost")
DEFAULT_STAGE_MODE: dict[str, str] = {stage: "ask" for stage in _STAGES}  # R12

DEFAULT_THRESHOLDS: dict[str, int] = {"book_score": 70, "send_floor": 0}

# ── The clamp table: _CLAMP[proposed][mode] -> final ───────────────────────────
# ask  → downgrade an outward send to 'park' (human-approve); escalation still
#        surfaces; stop is always honored.
# off  → kill switch: send/escalate collapse to 'hold'; stop still honored.
# auto → pass the proposed action through unchanged.
_CLAMP: dict[str, dict[str, str]] = {
    "send":     {"auto": "send",     "ask": "park",     "off": "hold"},
    "escalate": {"auto": "escalate", "ask": "escalate", "off": "hold"},
    "stop":     {"auto": "stop",     "ask": "stop",     "off": "stop"},
    "hold":     {"auto": "hold",     "ask": "hold",     "off": "hold"},
}


@dataclass
class EscalationDecision:
    """The value object ``decide_action`` returns (NOT the ORM row).

    ``sequence_sender._run_tick`` maps these fields onto a
    ``models.escalation_decision.EscalationDecision`` row for the append-only
    audit trail. Pure data — no DB identity.
    """

    stage: str
    proposed_action: str
    final_action: str
    mode: str
    score: int | None = None
    sentiment: str | None = None
    reason: str | None = None
    decided_by: str = "threshold"
    metadata: dict[str, Any] = field(default_factory=dict)


def propose_action(
    *,
    sentiment: str | None,
    score: int | None,
    thresholds: dict[str, Any] | None = None,
) -> str:
    """Return the signal-driven proposed action (pre-clamp).

    Precedence (most decisive signal first):
      - ``unsubscribe``            -> ``stop``   (halt the drip; opt-out is terminal)
      - ``negative`` / ``objection`` -> ``escalate`` (needs human judgment)
      - ``booking``                -> ``escalate`` (hot: a human should close)
      - engagement ``score`` below ``send_floor`` -> ``hold`` (too cold to send)
      - otherwise (``positive`` / ``neutral`` / no reply yet) -> ``send``

    Note a fresh cold lead has ``sentiment=None`` and ``score=0``; with the default
    ``send_floor=0`` that yields ``send`` — the ordinary cold-outreach drip. The
    engagement-score-driven branches only bite once real engagement events exist
    (a zero-engagement lead never trips ``hold`` under the default floor).
    """
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    send_floor = int(th.get("send_floor", 0))

    if sentiment == "unsubscribe":
        return "stop"
    if sentiment in ("negative", "objection"):
        return "escalate"
    if sentiment == "booking":
        return "escalate"
    if score is not None and score < send_floor:
        return "hold"
    return "send"


def clamp_action(proposed: str, mode: str) -> str:
    """Narrow a proposed action by the per-stage operator cap. Never widens.

    Unknown ``proposed`` collapses to ``hold`` (fail-closed); unknown ``mode`` is
    treated as ``ask`` (fail-closed).
    """
    row = _CLAMP.get(proposed, _CLAMP["hold"])
    return row.get(mode, row.get("ask", "hold"))


def decide_action(
    *,
    stage: str,
    mode: str,
    sentiment: str | None = None,
    score: int | None = None,
    thresholds: dict[str, Any] | None = None,
) -> EscalationDecision:
    """Compose PROPOSE + CLAMP into a decision value object.

    The reason string records the two-layer path so the audit row is self-
    explanatory (``"propose=send clamp(ask)=park"``).
    """
    proposed = propose_action(sentiment=sentiment, score=score, thresholds=thresholds)
    final = clamp_action(proposed, mode)
    reason = f"propose={proposed} clamp({mode})={final}"
    if sentiment:
        reason += f" sentiment={sentiment}"
    return EscalationDecision(
        stage=stage,
        proposed_action=proposed,
        final_action=final,
        mode=mode,
        score=score,
        sentiment=sentiment,
        reason=reason,
        decided_by="threshold",
    )


async def decide_action_model(*args: Any, **kwargs: Any) -> EscalationDecision:
    """FUTURE model-governed decision seam (``decided_by='model'``) — NOT built.

    Design placeholder per §2.2.2/R7: when implemented this will consult
    ``settings.ANTHROPIC_MODEL_SMART`` through ``app.services.llm`` to make a
    judgment call the threshold table cannot. It is intentionally unwired today so
    no code path depends on it; the threshold decider (:func:`decide_action`) is
    the sole live decider in Inc 2.
    """
    raise NotImplementedError(
        "decide_action_model is a design placeholder (Inc 2); the live decider is decide_action"
    )
