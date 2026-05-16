"""Tests for worker-layer pure functions — zero DB, zero Celery, zero API calls."""

from __future__ import annotations

import base64
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# score_contact._compute_score — heuristic lead scorer
# ---------------------------------------------------------------------------


def _fake_contact(**kwargs) -> MagicMock:
    c = MagicMock()
    c.status = kwargs.get("status", "lead")
    c.revenue = kwargs.get("revenue", 0)
    c.deal_count = kwargs.get("deal_count", 0)
    return c


def test_compute_score_base_lead_is_50_warm():
    from app.workers.score_contact import _compute_score

    result = _compute_score(_fake_contact(status="lead", revenue=0, deal_count=0))
    assert result["value"] == 50
    assert result["label"] == "warm"
    assert result["trend"] == "stable"
    assert result["signals"] == []


def test_compute_score_customer_bonus():
    from app.workers.score_contact import _compute_score

    result = _compute_score(_fake_contact(status="customer", revenue=0, deal_count=0))
    assert result["value"] == 60
    assert any("customer" in s.lower() for s in result["signals"])


def test_compute_score_prospect_bonus():
    from app.workers.score_contact import _compute_score

    result = _compute_score(_fake_contact(status="prospect", revenue=0, deal_count=0))
    assert result["value"] == 55
    assert any("Prospect" in s for s in result["signals"])


def test_compute_score_churned_penalty():
    from app.workers.score_contact import _compute_score

    result = _compute_score(_fake_contact(status="churned", revenue=0, deal_count=0))
    assert result["value"] == 40
    assert any("Churned" in s for s in result["signals"])


def test_compute_score_deal_count_bonus():
    from app.workers.score_contact import _compute_score

    result = _compute_score(_fake_contact(status="lead", revenue=0, deal_count=3))
    assert result["value"] == 60  # 50 + 10
    assert any("deal" in s.lower() for s in result["signals"])


def test_compute_score_revenue_above_50k():
    from app.workers.score_contact import _compute_score

    result = _compute_score(_fake_contact(status="lead", revenue=75000, deal_count=0))
    assert result["value"] == 55  # 50 + 5
    assert any("+5" in s for s in result["signals"])


def test_compute_score_revenue_10k_to_50k():
    from app.workers.score_contact import _compute_score

    result = _compute_score(_fake_contact(status="lead", revenue=25000, deal_count=0))
    assert result["value"] == 60  # 50 + 10
    assert any("+10" in s for s in result["signals"])


def test_compute_score_hot_label_at_70_plus():
    from app.workers.score_contact import _compute_score

    # customer(+10) + deals(+10) + 25k revenue(+10) = 80
    result = _compute_score(_fake_contact(status="customer", revenue=25000, deal_count=2))
    assert result["value"] == 80
    assert result["label"] == "hot"


def test_compute_score_all_bonuses_clamped_at_100():
    from app.workers.score_contact import _compute_score

    # 50 + 10 + 10 + 10 = 80 (all bonuses, capped at 100 still returns 80)
    result = _compute_score(_fake_contact(status="customer", revenue=25000, deal_count=5))
    assert result["value"] <= 100


def test_compute_score_zero_revenue_no_revenue_signal():
    from app.workers.score_contact import _compute_score

    result = _compute_score(_fake_contact(status="lead", revenue=0, deal_count=0))
    assert not any("revenue" in s.lower() for s in result["signals"])


# ---------------------------------------------------------------------------
# ingest._decode_body — recursive Gmail payload decoder
# ---------------------------------------------------------------------------


def _b64(text: str) -> str:
    """URL-safe base64 WITHOUT padding (Gmail API format)."""
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def test_decode_body_plain_text():
    from app.workers.ingest import _decode_body

    payload = {"mimeType": "text/plain", "body": {"data": _b64("Hello world")}}
    assert _decode_body(payload) == "Hello world"


def test_decode_body_html_mime_returns_empty():
    from app.workers.ingest import _decode_body

    payload = {"mimeType": "text/html", "body": {"data": _b64("<p>Hello</p>")}}
    assert _decode_body(payload) == ""


def test_decode_body_no_data_field_returns_empty():
    from app.workers.ingest import _decode_body

    payload = {"mimeType": "text/plain", "body": {}}
    assert _decode_body(payload) == ""


def test_decode_body_empty_payload_returns_empty():
    from app.workers.ingest import _decode_body

    assert _decode_body({}) == ""


def test_decode_body_multipart_finds_first_plain():
    from app.workers.ingest import _decode_body

    payload = {
        "mimeType": "multipart/alternative",
        "body": {},
        "parts": [
            {"mimeType": "text/html", "body": {"data": _b64("<p>HTML</p>")}},
            {"mimeType": "text/plain", "body": {"data": _b64("Plain text body")}},
        ],
    }
    assert _decode_body(payload) == "Plain text body"


def test_decode_body_nested_multipart():
    from app.workers.ingest import _decode_body

    payload = {
        "mimeType": "multipart/mixed",
        "body": {},
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "body": {},
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": _b64("Nested plain text")}}
                ],
            }
        ],
    }
    assert _decode_body(payload) == "Nested plain text"


def test_decode_body_unicode_content():
    from app.workers.ingest import _decode_body

    payload = {"mimeType": "text/plain", "body": {"data": _b64("Héllo wörld — Ünïcode")}}
    result = _decode_body(payload)
    assert "Héllo" in result
