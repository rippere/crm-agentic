"""
Deal health scoring service.

Health starts at 100 and decays based on:
  - Stage staleness: days in current stage beyond the per-stage threshold
  - Engagement gap: days since last message from the linked contact
"""
from __future__ import annotations

from datetime import datetime, timezone

# How many days a deal can stay in a stage before health starts decaying
_STAGE_THRESHOLD_DAYS: dict[str, int] = {
    "discovery":   7,
    "qualified":   14,
    "proposal":    10,
    "negotiation": 7,
    "closed_won":  999,
    "closed_lost": 999,
}

_DECAY_PER_DAY = 3          # health points lost per day past threshold
_ENGAGEMENT_FLOOR_DAYS = 14  # no activity beyond this → penalty
_ENGAGEMENT_CUT_DAYS   = 30  # no activity beyond this → bigger penalty


def compute_health(
    stage: str,
    stage_changed_at: datetime,
    last_message_at: datetime | None,
    now: datetime | None = None,
) -> tuple[int, list[str]]:
    """
    Returns (health_score: 0–100, signals: list[str]).
    *signals* are human-readable strings explaining the score.
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)

    # Ensure timezone-aware
    if stage_changed_at.tzinfo is None:
        stage_changed_at = stage_changed_at.replace(tzinfo=timezone.utc)

    score = 100
    signals: list[str] = []

    # ── Stage staleness ────────────────────────────────────────────
    threshold = _STAGE_THRESHOLD_DAYS.get(stage, 14)
    days_in_stage = (now - stage_changed_at).days

    if stage not in ("closed_won", "closed_lost") and days_in_stage > threshold:
        overdue = days_in_stage - threshold
        penalty = overdue * _DECAY_PER_DAY
        score -= penalty
        signals.append(f"Stale in {stage.replace('_', ' ')} for {days_in_stage}d (−{penalty} pts)")

    # ── Engagement gap ─────────────────────────────────────────────
    if stage not in ("closed_won", "closed_lost"):
        if last_message_at is None:
            score -= 20
            signals.append("No messages linked (−20 pts)")
        else:
            if last_message_at.tzinfo is None:
                last_message_at = last_message_at.replace(tzinfo=timezone.utc)
            days_since = (now - last_message_at).days
            if days_since > _ENGAGEMENT_CUT_DAYS:
                score -= 30
                signals.append(f"No contact in {days_since}d (−30 pts)")
            elif days_since > _ENGAGEMENT_FLOOR_DAYS:
                score -= 20
                signals.append(f"Low engagement: {days_since}d since last message (−20 pts)")

    final_score = max(0, min(100, score))
    if not signals:
        signals.append("Healthy — on track")
    return final_score, signals
