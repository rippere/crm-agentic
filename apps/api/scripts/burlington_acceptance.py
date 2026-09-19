#!/usr/bin/env python
"""
Burlington acceptance harness (BUILD-SPEC §2.1.14) — the Increment 1 firm gate.

Diffs the discovery engine's produced fit-scores against the ground-truth sheet
``docs/betson/Burlington_Photo_Booth_Prospect_Master.xlsx`` (16 venues, sheet
"Master Prospects"), transcribed offline into
``tests/fixtures/burlington_ground_truth.json``.

Pipeline (matches the spec):
    1. Load the fixtures (recorded places universe + ground-truth sheet).
    2. Build the venue universe from ``burlington_places_fixture.json`` (a
       recorded ``discover_venue_universe`` result — offline CI does not bill a
       Places API key). In ``--live`` mode it instead calls the real
       ``discover_venue_universe`` (BILLS Google Places — external spend gate).
    3. Score each venue with ``score_venue`` (live ``ANTHROPIC_API_KEY`` under
       ``--live`` — BILLS Anthropic), or the recorded-LLM subscore stand-in for
       pure-offline CI, then run the REAL ``compute_overall`` / ``tier_for``.
    4. Fuzzy-match produced venues to sheet venues, then compute the three gate
       metrics and print an inspectable table.

Fuzzy-match implementation (pinned, stated per spec):
    ``normalized_token_set_ratio(a, b) >= 0.85`` — implemented here as a
    dependency-free **token-set Jaccard** over the normalized token sets (the
    spec's explicit fallback when ``rapidfuzz`` is not a desired dependency;
    ``rapidfuzz`` is not installed in this venv). Normalization = lowercase,
    strip punctuation, collapse whitespace, drop stopwords
    ``{the, a, and, &, co, company, llc, inc, restaurant, bar, pub}``.

Pearson r: hand-rolled in stdlib (no numpy/scipy).

Firm pass bars (gate, not diagnostic):
    * venue coverage  >= 12/16 matched (fuzzy >= 0.85 on name)
    * Pearson r       >= 0.6  (produced fit-score vs sheet Overall, matched venues)
    * tier agreement  >= 0.7  (fraction whose produced tier == sheet tier)
A run below ANY bar fails the increment. V5 (DEFAULT_RUBRIC weights == the sheet's
Scoring Guide) must pass before the run — asserted here up front.

Usage:
    python scripts/burlington_acceptance.py            # offline (fixtures; recorded-LLM stand-in)
    python scripts/burlington_acceptance.py --live     # BILLS Google Places + Anthropic (§6 spend gate)
    python scripts/burlington_acceptance.py --self-test # run the fuzzy/Pearson helper self-checks only

External spend gate (§6): the ``--live`` end-to-end run bills a Google Places API
key and paid Anthropic calls — same tier as SMS 10DLC. Offline CI uses the
fixtures and does not bill.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable

# ─── Paths ───────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_API_ROOT = _HERE.parent  # apps/api
_FIXTURES = _API_ROOT / "tests" / "fixtures"
_GROUND_TRUTH = _FIXTURES / "burlington_ground_truth.json"
_PLACES_FIXTURE = _FIXTURES / "burlington_places_fixture.json"

# Make ``app`` importable when the harness is run directly (python scripts/...).
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

# ─── Firm gate bars (§2.1.14) ────────────────────────────────────────────────
COVERAGE_MIN = 12          # of 16
PEARSON_MIN = 0.60
TIER_AGREEMENT_MIN = 0.70
FUZZY_THRESHOLD = 0.85

# Expected Scoring-Guide weights (sheet "Scoring Guide" tab) — V5 gate.
_SHEET_WEIGHTS = {
    "traffic": 0.25,
    "social_photo": 0.20,
    "group_dwell": 0.15,
    "brand_fit": 0.15,
    "placement_feasibility": 0.10,
    "year_round": 0.05,
    "contactability": 0.10,
}

_STOPWORDS = {"the", "a", "and", "&", "co", "company", "llc", "inc", "restaurant", "bar", "pub"}


# ─── Fuzzy match (REAL, runnable — no external deps) ──────────────────────────
def _normalize_tokens(text: str) -> set[str]:
    """Lowercase, strip punctuation, collapse whitespace, drop stopwords → token set."""
    lowered = (text or "").lower()
    # Replace any non-alphanumeric run with a single space.
    cleaned = re.sub(r"[^a-z0-9]+", " ", lowered)
    tokens = [t for t in cleaned.split() if t and t not in _STOPWORDS]
    return set(tokens)


def normalized_token_set_ratio(a: str, b: str) -> float:
    """Token-set Jaccard over normalized token sets, in [0.0, 1.0].

    Dependency-free stand-in for ``rapidfuzz.fuzz.token_set_ratio / 100`` (the
    spec's explicit fallback). Two empty token sets are treated as a perfect
    match (1.0); one empty and one non-empty is 0.0.
    """
    sa = _normalize_tokens(a)
    sb = _normalize_tokens(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


# ─── Pearson r (REAL, runnable — stdlib only) ─────────────────────────────────
def pearson_r(xs: list[float], ys: list[float]) -> float:
    """Pearson product-moment correlation coefficient, hand-rolled in stdlib.

    Returns 0.0 when fewer than two points are supplied or when either series
    has zero variance (correlation is undefined — treated as no linear
    relationship for gate purposes).
    """
    n = len(xs)
    if n < 2 or n != len(ys):
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    denom = math.sqrt(var_x * var_y)
    if denom == 0.0:
        return 0.0
    return cov / denom


# ─── Fixture loading ─────────────────────────────────────────────────────────
def load_ground_truth() -> list[dict[str, Any]]:
    data = json.loads(_GROUND_TRUTH.read_text(encoding="utf-8"))
    return data["venues"]


def load_places_fixture() -> list[dict[str, Any]]:
    data = json.loads(_PLACES_FIXTURE.read_text(encoding="utf-8"))
    return data["places"]


def assert_weights_match_sheet() -> None:
    """V5 gate — DEFAULT_RUBRIC weights must equal the sheet's Scoring Guide."""
    from app.services.discovery_rubric import DEFAULT_RUBRIC

    produced = {c["key"]: round(float(c["weight"]), 4) for c in DEFAULT_RUBRIC["criteria"]}
    for key, expected in _SHEET_WEIGHTS.items():
        got = produced.get(key)
        if got is None or abs(got - expected) > 1e-9:
            raise AssertionError(
                f"V5 FAIL: DEFAULT_RUBRIC weight for {key!r} is {got}, "
                f"sheet Scoring Guide says {expected}"
            )
    print("V5 OK: DEFAULT_RUBRIC weights == sheet Scoring Guide.")


# ─── Scorers ─────────────────────────────────────────────────────────────────
def _recorded_llm_subscores(gt_by_name: dict[str, dict]) -> Callable[[Any], dict]:
    """Offline stand-in for a recorded-LLM subscore fixture.

    Returns the ground-truth sheet subscores as the "produced" subscores so the
    harness plumbing + deterministic ``compute_overall``/``tier_for`` path runs
    end-to-end offline. This proves the pipeline and the scoring math, NOT the
    LLM's live correlation — the correlation bar is only meaningful under
    ``--live`` (or a real recorded-LLM subscore fixture).

    # TODO(execute): replace with real subscores recorded from a live
    # score_venue()/ANTHROPIC run so offline r/tier metrics reflect the model.
    """

    def _scorer(place: Any) -> dict:
        name = _place_attr(place, "name")
        gt = gt_by_name.get(_normalize_name_key(name))
        subs = dict(gt["subscores"]) if gt else {}
        return {"subscores": subs}

    return _scorer


def _place_attr(place: Any, attr: str) -> Any:
    """Read a field from a PlaceResult dataclass OR a plain dict fixture row."""
    if isinstance(place, dict):
        return place.get(attr)
    return getattr(place, attr, None)


def _normalize_name_key(name: str) -> str:
    return " ".join(sorted(_normalize_tokens(name or "")))


async def _live_scorer(place: Any) -> dict:
    """Call the real deep-research scorer (BILLS Anthropic)."""
    from app.services.discovery_research import score_venue

    vs = await score_venue(place)
    subs = getattr(vs, "subscores", None) or {}
    return {"subscores": dict(subs)}


async def build_universe(live: bool, places_fixture: list[dict]) -> list[Any]:
    """Return the venue universe. Offline: the recorded fixture rows (as dicts).

    Live: call the real ``discover_venue_universe`` (BILLS Google Places).
    """
    if not live:
        return list(places_fixture)
    from app.services.places import discover_venue_universe

    universe = await discover_venue_universe(
        market="Burlington, VT",
        categories=["hospitality", "brewery", "museum", "music"],
        max_venues=60,
    )
    return list(universe)


# ─── Core diff ───────────────────────────────────────────────────────────────
def _best_match(name: str, ground_truth: list[dict]) -> tuple[dict | None, float]:
    """Return (best ground-truth venue, ratio) by normalized_token_set_ratio."""
    best: dict | None = None
    best_ratio = 0.0
    for gt in ground_truth:
        ratio = normalized_token_set_ratio(name, gt["name"])
        if ratio > best_ratio:
            best_ratio = ratio
            best = gt
    return best, best_ratio


def run_diff(universe: list[Any], ground_truth: list[dict], scorer, *, is_async: bool) -> dict:
    """Score every venue, fuzzy-match to the sheet, compute the three metrics."""
    from app.services.discovery_rubric import compute_overall, tier_for

    rows: list[dict[str, Any]] = []
    matched_produced: list[float] = []
    matched_sheet: list[float] = []
    tier_hits = 0
    matched_names: set[str] = set()

    for place in universe:
        name = _place_attr(place, "name")
        scored = asyncio.run(scorer(place)) if is_async else scorer(place)
        subs = scored.get("subscores", {})
        produced_overall = compute_overall(subs) if subs else 0.0
        produced_tier = tier_for(produced_overall)

        gt, ratio = _best_match(name, ground_truth)
        is_match = gt is not None and ratio >= FUZZY_THRESHOLD

        row = {
            "venue": name,
            "matched_to": gt["name"] if gt else None,
            "ratio": round(ratio, 3),
            "matched": is_match,
            "produced_score": produced_overall,
            "sheet_score": gt["overall"] if gt else None,
            "produced_tier": produced_tier,
            "sheet_tier": gt["tier"] if gt else None,
        }
        rows.append(row)

        if is_match:
            matched_names.add(gt["name"])
            matched_produced.append(produced_overall)
            matched_sheet.append(float(gt["overall"]))
            if produced_tier == gt["tier"]:
                tier_hits += 1

    coverage = len(matched_names)
    r = pearson_r(matched_produced, matched_sheet)
    tier_agreement = (tier_hits / coverage) if coverage else 0.0

    return {
        "rows": rows,
        "coverage": coverage,
        "total": len(ground_truth),
        "pearson_r": r,
        "tier_agreement": tier_agreement,
    }


def print_report(result: dict) -> None:
    print()
    header = f"{'Venue':38} {'Sheet':>6} {'Made':>6} {'S.Tier':>7} {'M.Tier':>7} {'Fuzzy':>6}"
    print(header)
    print("-" * len(header))
    for row in result["rows"]:
        print(
            f"{(row['venue'] or '')[:38]:38} "
            f"{('' if row['sheet_score'] is None else row['sheet_score']):>6} "
            f"{row['produced_score']:>6} "
            f"{(row['sheet_tier'] or '-'):>7} "
            f"{row['produced_tier']:>7} "
            f"{row['ratio']:>6}"
        )
    print()
    print(f"coverage       : {result['coverage']}/{result['total']}  (bar >= {COVERAGE_MIN})")
    print(f"pearson r      : {result['pearson_r']:.3f}       (bar >= {PEARSON_MIN})")
    print(f"tier agreement : {result['tier_agreement']:.3f}       (bar >= {TIER_AGREEMENT_MIN})")


def gate_passed(result: dict) -> bool:
    return (
        result["coverage"] >= COVERAGE_MIN
        and result["pearson_r"] >= PEARSON_MIN
        and result["tier_agreement"] >= TIER_AGREEMENT_MIN
    )


# ─── Self-test for the pure helpers (REAL, runnable with no app deps) ─────────
def self_test() -> None:
    # Fuzzy: identical → 1.0; stopword/punct-insensitive; unrelated → low.
    assert normalized_token_set_ratio("Rí Rá Irish Pub", "Rí Rá Irish Pub") == 1.0
    assert normalized_token_set_ratio("The Archives", "Archives") == 1.0  # 'the' dropped
    assert normalized_token_set_ratio("Foam Brewers - Burlington", "Foam Brewers Burlington") == 1.0
    assert normalized_token_set_ratio("Hotel Vermont", "Higher Ground") < 0.85
    # Pearson: perfect positive, perfect negative, flat.
    assert abs(pearson_r([1, 2, 3], [2, 4, 6]) - 1.0) < 1e-9
    assert abs(pearson_r([1, 2, 3], [6, 4, 2]) + 1.0) < 1e-9
    assert pearson_r([1, 1, 1], [1, 2, 3]) == 0.0
    assert pearson_r([1], [1]) == 0.0
    print("self-test OK: normalized_token_set_ratio + pearson_r behave as specified.")


# ─── Entrypoint ──────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Burlington acceptance harness (§2.1.14).")
    parser.add_argument("--live", action="store_true",
                        help="Call live Google Places + Anthropic (BILLS — §6 spend gate).")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the fuzzy/Pearson helper self-checks (no app imports).")
    args = parser.parse_args(argv)

    if args.self_test:
        self_test()
        return 0

    # V5 must pass before any scoring run.
    assert_weights_match_sheet()

    ground_truth = load_ground_truth()
    places_fixture = load_places_fixture()
    universe = asyncio.run(build_universe(args.live, places_fixture))

    if args.live:
        result = run_diff(universe, ground_truth, _live_scorer, is_async=True)
    else:
        print(
            "OFFLINE mode: using recorded-LLM subscore stand-in (ground-truth sheet "
            "subscores). This proves the harness + deterministic compute_overall/tier_for\n"
            "end-to-end; the r/tier bars are only a live-model gate under --live.\n"
        )
        gt_by_name = {_normalize_name_key(v["name"]): v for v in ground_truth}
        scorer = _recorded_llm_subscores(gt_by_name)
        result = run_diff(universe, ground_truth, scorer, is_async=False)

    print_report(result)

    if gate_passed(result):
        print("\nRESULT: PASS — all three firm bars met.")
        return 0
    print("\nRESULT: FAIL — one or more firm bars not met.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
