"""Keystone test (V4/V5) — the rubric reproducibility proof, NO LLM, deterministic.

Feeds the 16 ground-truth subscore vectors (transcribed from the sheet
"Master Prospects" into tests/fixtures/burlington_ground_truth.json) through
``compute_overall``/``tier_for`` and asserts each reproduces the sheet's Overall
(±0.1) and Tier exactly, and that ``DEFAULT_RUBRIC`` weights equal the sheet's
"Scoring Guide" tab values (blocks scoring if drifted).

This is the reproducibility keystone: because the overall (0..100) and tier are
computed in Python from the seven 1..5 subscores, score correlation is testable
without depending on LLM determinism (BUILD-SPEC §2.1.2, V4/V5).

Zero DB, zero Celery, zero network — pure functions only.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_GROUND_TRUTH = _FIXTURES / "burlington_ground_truth.json"

# The sheet's "Scoring Guide" tab, weight column (V5 gate).
_SHEET_WEIGHTS = {
    "traffic": 0.25,
    "social_photo": 0.20,
    "group_dwell": 0.15,
    "brand_fit": 0.15,
    "placement_feasibility": 0.10,
    "year_round": 0.05,
    "contactability": 0.10,
}


def _load_ground_truth() -> list[dict]:
    data = json.loads(_GROUND_TRUTH.read_text(encoding="utf-8"))
    return data["venues"]


_GT = _load_ground_truth()


# ---------------------------------------------------------------------------
# V5 — DEFAULT_RUBRIC weights match the sheet Scoring Guide (must pass first)
# ---------------------------------------------------------------------------


def test_default_rubric_weights_match_sheet_scoring_guide():
    from app.services.discovery_rubric import DEFAULT_RUBRIC

    produced = {c["key"]: float(c["weight"]) for c in DEFAULT_RUBRIC["criteria"]}
    assert produced == pytest.approx(_SHEET_WEIGHTS, abs=1e-9)


def test_default_rubric_weights_sum_to_one():
    from app.services.discovery_rubric import DEFAULT_RUBRIC

    total = sum(float(c["weight"]) for c in DEFAULT_RUBRIC["criteria"])
    assert total == pytest.approx(1.0, abs=1e-3)


def test_default_rubric_scale_max_and_tiers():
    from app.services.discovery_rubric import DEFAULT_RUBRIC

    assert DEFAULT_RUBRIC["scale_max"] == 5
    tiers = {t["tier"]: t["min"] for t in DEFAULT_RUBRIC["tiers"]}
    assert tiers == {"A+": 95, "A": 90, "A-": 85, "B+": 80, "B": 0}


def test_ground_truth_fixture_has_sixteen_venues():
    assert len(_GT) == 16


# ---------------------------------------------------------------------------
# V4 — compute_overall reproduces every sheet Overall (±0.1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("venue", _GT, ids=[v["name"] for v in _GT])
def test_compute_overall_reproduces_sheet(venue):
    from app.services.discovery_rubric import compute_overall

    produced = compute_overall(venue["subscores"])
    assert produced == pytest.approx(venue["overall"], abs=0.1), (
        f"{venue['name']}: produced {produced}, sheet {venue['overall']}"
    )


@pytest.mark.parametrize("venue", _GT, ids=[v["name"] for v in _GT])
def test_tier_for_reproduces_sheet_tier(venue):
    from app.services.discovery_rubric import compute_overall, tier_for

    produced_tier = tier_for(compute_overall(venue["subscores"]))
    assert produced_tier == venue["tier"], (
        f"{venue['name']}: produced tier {produced_tier}, sheet {venue['tier']}"
    )


def test_ri_ra_is_ninety_seven_point_five():
    """The load-bearing hand-verified anchor (BUILD-SPEC §2.1.2)."""
    from app.services.discovery_rubric import compute_overall, tier_for

    ri_ra = next(v for v in _GT if v["name"].startswith("Rí Rá"))
    overall = compute_overall(ri_ra["subscores"])
    assert overall == pytest.approx(97.5, abs=0.1)
    assert tier_for(overall) == "A+"


def test_echo_is_ninety_five():
    """The second hand-verified anchor (BUILD-SPEC §2.1.2)."""
    from app.services.discovery_rubric import compute_overall, tier_for

    echo = next(v for v in _GT if v["name"].startswith("ECHO"))
    overall = compute_overall(echo["subscores"])
    assert overall == pytest.approx(95.0, abs=0.1)
    assert tier_for(overall) == "A+"


def test_every_produced_tier_bucket_is_consistent_with_overall():
    """Independent cross-check: tier_for(overall) obeys the A+/A/A-/B+/B bands."""
    from app.services.discovery_rubric import compute_overall, tier_for

    for venue in _GT:
        overall = compute_overall(venue["subscores"])
        tier = tier_for(overall)
        if overall >= 95:
            assert tier == "A+"
        elif overall >= 90:
            assert tier == "A"
        elif overall >= 85:
            assert tier == "A-"
        elif overall >= 80:
            assert tier == "B+"
        else:
            assert tier == "B"


# ---------------------------------------------------------------------------
# compute_overall / tier_for edge behavior
# ---------------------------------------------------------------------------


def test_compute_overall_missing_subscore_contributes_zero():
    from app.services.discovery_rubric import compute_overall

    # Only traffic (weight .25) present at max → 5 * .25 * 20 = 25.0
    assert compute_overall({"traffic": 5}) == pytest.approx(25.0, abs=0.1)


def test_compute_overall_empty_is_zero():
    from app.services.discovery_rubric import compute_overall

    assert compute_overall({}) == pytest.approx(0.0, abs=0.1)


def test_compute_overall_all_fives_is_one_hundred():
    from app.services.discovery_rubric import compute_overall, DEFAULT_RUBRIC

    perfect = {c["key"]: 5 for c in DEFAULT_RUBRIC["criteria"]}
    assert compute_overall(perfect) == pytest.approx(100.0, abs=0.1)


def test_tier_for_boundaries():
    from app.services.discovery_rubric import tier_for

    assert tier_for(95.0) == "A+"
    assert tier_for(94.9) == "A"
    assert tier_for(90.0) == "A"
    assert tier_for(89.9) == "A-"
    assert tier_for(85.0) == "A-"
    assert tier_for(84.9) == "B+"
    assert tier_for(80.0) == "B+"
    assert tier_for(79.9) == "B"
    assert tier_for(0.0) == "B"


# ---------------------------------------------------------------------------
# validate_rubric — the 422 gate the router relies on
# ---------------------------------------------------------------------------


def test_validate_rubric_accepts_default():
    from app.services.discovery_rubric import DEFAULT_RUBRIC, validate_rubric

    validate_rubric(DEFAULT_RUBRIC)  # must not raise


def test_validate_rubric_rejects_bad_weight_sum():
    from app.services.discovery_rubric import validate_rubric

    bad = {
        "scale_max": 5,
        "criteria": [
            {"key": "a", "weight": 0.5},
            {"key": "b", "weight": 0.2},  # sums to 0.7
        ],
        "tiers": [{"tier": "B", "min": 0}],
    }
    with pytest.raises(ValueError):
        validate_rubric(bad)


def test_validate_rubric_rejects_duplicate_keys():
    from app.services.discovery_rubric import validate_rubric

    bad = {
        "scale_max": 5,
        "criteria": [
            {"key": "dup", "weight": 0.5},
            {"key": "dup", "weight": 0.5},
        ],
        "tiers": [{"tier": "B", "min": 0}],
    }
    with pytest.raises(ValueError):
        validate_rubric(bad)


def test_validate_rubric_rejects_nonpositive_scale_max():
    from app.services.discovery_rubric import validate_rubric

    bad = {
        "scale_max": 0,
        "criteria": [{"key": "a", "weight": 1.0}],
        "tiers": [{"tier": "B", "min": 0}],
    }
    with pytest.raises(ValueError):
        validate_rubric(bad)
