"""Truth table + edge cases for the safe ``when`` evaluator (§7)."""

from __future__ import annotations

import pytest

from orchestrator.whenexpr import WhenSyntaxError, evaluate

ARTIFACTS = {
    "plan": {"touches": ["backend", "frontend"], "risk": "high"},
    "review": {"status": "pass"},
}


@pytest.mark.parametrize(
    "expr,expected",
    [
        ("always", True),
        ("never", False),
        (None, True),
        ("", True),
        ("backend in plan.touches", True),
        ("frontend in plan.touches", True),
        ("infra in plan.touches", False),
        ("plan.risk == high", True),
        ("plan.risk == low", False),
        ("plan.risk != low", True),
        ("plan.risk != high", False),
        ("review.status == pass", True),
        ('review.status == "pass"', True),
        # Unknown artifact / field => False.
        ("backend in missing.touches", False),
        ("missing.field == x", False),
        ("plan.missing == x", False),
        ("x in plan.missing", False),
    ],
)
def test_truth_table(expr, expected):
    result, _reason = evaluate(expr, ARTIFACTS)
    assert result is expected


def test_unknown_artifact_reports_reason():
    result, reason = evaluate("backend in missing.touches", ARTIFACTS)
    assert result is False
    assert "missing" in reason


def test_syntax_error_raises():
    with pytest.raises(WhenSyntaxError):
        evaluate("plan.touches and review.status", ARTIFACTS)
    with pytest.raises(WhenSyntaxError):
        evaluate("foo == bar == baz extra", {"foo": {"x": 1}})


def test_in_requires_artifact_field_ref():
    with pytest.raises(WhenSyntaxError):
        evaluate("backend in plan", ARTIFACTS)
