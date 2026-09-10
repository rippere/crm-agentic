"""
Discovery scoring rubric — rubric-as-config (R4/C5).

The Autonomous Lead Engine's discovery spine scores each venue against a fixed,
weighted rubric. Per the resolved-collisions ledger (R4/C5) the rubric is a
**Python config module only** for this build — there is no ``scoring_rubrics``
DB table. ``DEFAULT_RUBRIC`` is the seed; a run may supply an override via
``DiscoveryRunRequest.rubric`` (validated with :func:`validate_rubric` → 422),
and the effective rubric is snapshotted into ``discovery_runs.rubric`` for
reproducibility.

Load-bearing determinism (drives the acceptance test, §2.1.2): the LLM produces
only the seven 1–5 subscores plus qualitative context; the overall (0–100) score
and the tier are computed **here, in Python**, by :func:`compute_overall` and
:func:`tier_for`. This makes score correlation testable without depending on LLM
determinism. The overall is the weighted mean of the seven subscores scaled by
``100 / scale_max`` (i.e. ×20 for a 1–5 scale) — verified by hand against the
Burlington ground-truth sheet (Rí Rá → 97.5, ECHO → 95.0).

The seven weights (Traffic 0.25, Social/Photo 0.20, Group/Dwell 0.15, Brand Fit
0.15, Placement 0.10, Year-Round 0.05, Contactability 0.10) sum to 1.00 and
mirror the sheet's "Scoring Guide" tab. Tiers: A+ ≥95, A ≥90, A- ≥85, B+ ≥80,
B ≥0.
"""
from __future__ import annotations

# ─── Rubric config ───────────────────────────────────────────────────────────
# Weights sum to 1.00; the criterion order matches the ground-truth sheet's
# Scoring Guide (traffic, social/photo, group/dwell, brand fit, placement,
# year-round, contactability). Changing a weight here changes every produced
# fit score — V5 of the acceptance plan asserts these values match the sheet
# before any scoring run is allowed to proceed.
DEFAULT_RUBRIC: dict = {
    "scale_max": 5,
    "criteria": [
        {
            "key": "traffic",
            "label": "Traffic Potential",
            "weight": 0.25,
            "what_5_means": (
                "High, sustained foot traffic — a busy, high-dwell venue that "
                "puts a photo booth in front of a large volume of guests."
            ),
            "why_it_matters": (
                "Volume of eyeballs is the single largest driver of booth "
                "usage and per-location revenue."
            ),
        },
        {
            "key": "social_photo",
            "label": "Social / Photo Behavior",
            "weight": 0.20,
            "what_5_means": (
                "Guests already photograph themselves and post — visible "
                "check-ins, tagged photos, an active social presence, "
                "photo-friendly decor."
            ),
            "why_it_matters": (
                "A crowd that already wants to capture and share the moment "
                "converts far better than one that does not."
            ),
        },
        {
            "key": "group_dwell",
            "label": "Group / Dwell Time",
            "weight": 0.15,
            "what_5_means": (
                "Groups linger — large parties, celebrations, long table "
                "turns — giving natural, unhurried moments to use the booth."
            ),
            "why_it_matters": (
                "Longer group dwell time creates the relaxed, celebratory "
                "windows in which a booth actually gets used."
            ),
        },
        {
            "key": "brand_fit",
            "label": "Brand Fit",
            "weight": 0.15,
            "what_5_means": (
                "The venue's identity and aesthetic align naturally with a "
                "premium photo-booth experience; the placement reads as "
                "on-brand, not bolted on."
            ),
            "why_it_matters": (
                "A booth that fits the venue's brand is welcomed and promoted "
                "rather than tolerated."
            ),
        },
        {
            "key": "placement_feasibility",
            "label": "Placement Feasibility",
            "weight": 0.10,
            "what_5_means": (
                "There is an obvious, accessible spot with power and space and "
                "no operational conflict — installation is low-friction."
            ),
            "why_it_matters": (
                "Even a perfect audience is worthless if there is nowhere "
                "practical to site the booth."
            ),
        },
        {
            "key": "year_round",
            "label": "Year-Round Strength",
            "weight": 0.05,
            "what_5_means": (
                "The venue draws consistent traffic across all seasons rather "
                "than a short peak — dependable year-round revenue."
            ),
            "why_it_matters": (
                "Seasonal-only venues cap the annualized return on a placed "
                "booth."
            ),
        },
        {
            "key": "contactability",
            "label": "Contactability",
            "weight": 0.10,
            "what_5_means": (
                "A clear, reachable decision-maker with public contact "
                "details — an easy, direct path to a conversation."
            ),
            "why_it_matters": (
                "A great fit that cannot be reached never becomes a deal; "
                "reachability gates the whole funnel."
            ),
        },
    ],
    "tiers": [
        {"tier": "A+", "min": 95},
        {"tier": "A", "min": 90},
        {"tier": "A-", "min": 85},
        {"tier": "B+", "min": 80},
        {"tier": "B", "min": 0},
    ],
}


def validate_rubric(rubric: dict) -> None:
    """Validate a rubric config, raising :class:`ValueError` on any defect.

    Enforced invariants (per §2.1.3):

    * ``scale_max`` is present and > 0.
    * ``criteria`` is a non-empty list, each with a ``key`` and a numeric
      ``weight``.
    * criterion keys are unique.
    * the weights sum to ~1.0 within an absolute tolerance of ``1e-3``.

    Router callers surface the raised ``ValueError`` as an HTTP 422. This is a
    pure, side-effect-free validator; it returns ``None`` on success.
    """
    if not isinstance(rubric, dict):
        raise ValueError("rubric must be a dict")

    scale_max = rubric.get("scale_max")
    if not isinstance(scale_max, (int, float)) or isinstance(scale_max, bool) or scale_max <= 0:
        raise ValueError(f"rubric scale_max must be a positive number, got {scale_max!r}")

    criteria = rubric.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        raise ValueError("rubric criteria must be a non-empty list")

    keys: list[str] = []
    total_weight = 0.0
    for i, criterion in enumerate(criteria):
        if not isinstance(criterion, dict):
            raise ValueError(f"rubric criterion[{i}] must be a dict")
        key = criterion.get("key")
        if not key or not isinstance(key, str):
            raise ValueError(f"rubric criterion[{i}] is missing a string 'key'")
        weight = criterion.get("weight")
        if not isinstance(weight, (int, float)) or isinstance(weight, bool):
            raise ValueError(f"rubric criterion {key!r} has a non-numeric weight {weight!r}")
        keys.append(key)
        total_weight += float(weight)

    if len(keys) != len(set(keys)):
        raise ValueError("rubric criterion keys must be unique")

    if abs(total_weight - 1.0) > 1e-3:
        raise ValueError(
            f"rubric weights must sum to 1.0 (±1e-3), got {total_weight:.6f}"
        )


def compute_overall(subscores: dict[str, float], rubric: dict = DEFAULT_RUBRIC) -> float:
    """Compute the deterministic overall fit score (0–100) from subscores.

    The overall is the weighted mean of the per-criterion subscores scaled by
    ``100 / scale_max`` (×20 on the default 1–5 scale), rounded to one decimal
    place::

        overall = sum(subscore[k] * weight_k) * (100 / scale_max)

    A criterion whose subscore is missing (or ``None``/non-numeric) contributes
    ``0`` for that criterion — i.e. an incomplete LLM result degrades the score
    rather than raising. Extra keys in ``subscores`` that are not rubric
    criteria are ignored.

    This function is the keystone of the acceptance test (V4): fed the 16
    ground-truth subscore vectors it must reproduce each sheet Overall within
    ±0.1.
    """
    scale_max = rubric.get("scale_max", 5)
    weighted_sum = 0.0
    for criterion in rubric.get("criteria", []):
        key = criterion.get("key")
        weight = float(criterion.get("weight", 0.0))
        raw = subscores.get(key) if isinstance(subscores, dict) else None
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            value = 0.0
        else:
            value = float(raw)
        weighted_sum += value * weight

    overall = weighted_sum * (100.0 / float(scale_max))
    return round(overall, 1)


def tier_for(overall: float, rubric: dict = DEFAULT_RUBRIC) -> str:
    """Return the tier label for an overall score.

    Walks the rubric's tiers by descending ``min`` and returns the first whose
    ``min`` threshold is ``<= overall`` (so 97.5 → "A+", 82.0 → "B+", 40.0 →
    "B"). Falls back to ``"B"`` if the rubric defines no catch-all tier.
    """
    tiers = sorted(
        rubric.get("tiers", []),
        key=lambda t: t.get("min", 0),
        reverse=True,
    )
    for tier in tiers:
        if overall >= tier.get("min", 0):
            return tier.get("tier", "B")
    return "B"
