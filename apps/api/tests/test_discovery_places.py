"""Tests for the places provider waterfall (app.services.places).

Mirrors the enrichment-waterfall test style (fake providers implementing the
Protocol) but asserts discovery's *distinct* semantics (BUILD-SPEC R3/§2.1.4):
enrichment fills-first-wins; discovery **unions across providers and dedupes**
into a complete venue universe. Also covers the key-gate degradation (no provider
configured → ``[]``, never a 500) and the never-raise contract.

Zero network: fake providers plus one mocked-httpx GooglePlacesProvider case.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_PLACES_FIXTURE = _FIXTURES / "burlington_places_fixture.json"


def _pr(name, locality="Burlington, VT", provider="fake", place_id=None, **kw):
    """Build a PlaceResult using the real dataclass (fields per §2.1.4)."""
    from app.services.places import PlaceResult

    return PlaceResult(
        provider=provider,
        place_id=place_id or f"{provider}:{name}",
        name=name,
        category=kw.get("category"),
        address=kw.get("address"),
        locality=locality,
        lat=kw.get("lat"),
        lng=kw.get("lng"),
        phone=kw.get("phone"),
        website=kw.get("website"),
        source_url=kw.get("source_url"),
    )


class _FakeProvider:
    """Test double implementing the PlacesProvider interface."""

    def __init__(self, name, results, available=True, raises=False):
        self.name = name
        self._results = results
        self._available = available
        self._raises = raises

    def available(self):
        return self._available

    async def search(self, *, market, categories, radius_m, max_results):
        if self._raises:
            raise RuntimeError("provider boom")
        return list(self._results)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_fake_provider_satisfies_protocol():
    from app.services.places import PlacesProvider

    assert isinstance(_FakeProvider("x", []), PlacesProvider)


# ---------------------------------------------------------------------------
# discover_venue_universe — union across providers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_union_across_providers():
    from app.services.places import discover_venue_universe

    p1 = _FakeProvider("a", [_pr("Rí Rá Irish Pub", provider="a")])
    p2 = _FakeProvider("b", [_pr("Foam Brewers", provider="b")])
    universe = await discover_venue_universe(market="Burlington, VT", providers=[p1, p2])
    names = {p.name for p in universe}
    assert names == {"Rí Rá Irish Pub", "Foam Brewers"}


@pytest.mark.asyncio
async def test_dedupe_same_venue_across_providers():
    """Same name + locality from two providers collapses to one row (R3 dedupe)."""
    from app.services.places import discover_venue_universe

    p1 = _FakeProvider("a", [_pr("Hotel Vermont", provider="a", place_id="a:1")])
    p2 = _FakeProvider("b", [_pr("Hotel Vermont", provider="b", place_id="b:2")])
    universe = await discover_venue_universe(market="Burlington, VT", providers=[p1, p2])
    assert len([p for p in universe if p.name == "Hotel Vermont"]) == 1


@pytest.mark.asyncio
async def test_distinct_localities_are_not_deduped():
    from app.services.places import discover_venue_universe

    p1 = _FakeProvider("a", [_pr("Common Name", locality="Burlington, VT")])
    p2 = _FakeProvider("b", [_pr("Common Name", locality="Essex, VT")])
    universe = await discover_venue_universe(market="VT", providers=[p1, p2])
    assert len(universe) == 2


# ---------------------------------------------------------------------------
# key-gate + degradation (no 500)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unavailable_provider_skipped():
    from app.services.places import discover_venue_universe

    off = _FakeProvider("off", [_pr("Should Not Appear")], available=False)
    on = _FakeProvider("on", [_pr("Appears")])
    universe = await discover_venue_universe(market="Burlington, VT", providers=[off, on])
    assert {p.name for p in universe} == {"Appears"}


@pytest.mark.asyncio
async def test_no_available_providers_returns_empty_not_error():
    from app.services.places import discover_venue_universe

    off = _FakeProvider("off", [_pr("x")], available=False)
    universe = await discover_venue_universe(market="Burlington, VT", providers=[off])
    assert universe == []


@pytest.mark.asyncio
async def test_provider_exception_is_swallowed_never_raises():
    from app.services.places import discover_venue_universe

    bad = _FakeProvider("bad", [], raises=True)
    good = _FakeProvider("good", [_pr("Survivor")])
    universe = await discover_venue_universe(market="Burlington, VT", providers=[bad, good])
    assert {p.name for p in universe} == {"Survivor"}


@pytest.mark.asyncio
async def test_max_venues_cap_enforced():
    from app.services.places import discover_venue_universe

    many = _FakeProvider("many", [_pr(f"Venue {i}") for i in range(50)])
    universe = await discover_venue_universe(
        market="Burlington, VT", providers=[many], max_venues=10
    )
    assert len(universe) <= 10


# ---------------------------------------------------------------------------
# _dedupe_key contract
# ---------------------------------------------------------------------------


def test_dedupe_key_same_for_same_name_and_locality():
    from app.services.places import _dedupe_key

    a = _pr("The Archives", locality="Burlington, VT", provider="a", place_id="a:1")
    b = _pr("the archives", locality="burlington, vt", provider="b", place_id="b:2")
    assert _dedupe_key(a) == _dedupe_key(b)


def test_dedupe_key_differs_for_different_venues():
    from app.services.places import _dedupe_key

    a = _pr("The Archives", locality="Burlington, VT")
    b = _pr("Foam Brewers", locality="Burlington, VT")
    assert _dedupe_key(a) != _dedupe_key(b)


# ---------------------------------------------------------------------------
# GooglePlacesProvider — key gate + never-raise (mocked httpx)
# ---------------------------------------------------------------------------


def test_google_provider_unavailable_without_key(monkeypatch):
    from app.services import places

    monkeypatch.setattr(places.settings, "GOOGLE_PLACES_API_KEY", "", raising=False)
    provider = places.GooglePlacesProvider()
    assert provider.name == "google_places"
    assert provider.available() is False


def test_google_provider_available_with_key(monkeypatch):
    from app.services import places

    monkeypatch.setattr(places.settings, "GOOGLE_PLACES_API_KEY", "test-key", raising=False)
    assert places.GooglePlacesProvider().available() is True


@pytest.mark.asyncio
async def test_google_provider_search_never_raises_on_http_error(monkeypatch):
    """A transport error must degrade to [] (never-raise contract)."""
    from app.services import places

    monkeypatch.setattr(places.settings, "GOOGLE_PLACES_API_KEY", "test-key", raising=False)

    # httpx.AsyncClient(...) used as an async context manager whose .get raises.
    failing_client = MagicMock()
    failing_client.__aenter__ = AsyncMock(return_value=failing_client)
    failing_client.__aexit__ = AsyncMock(return_value=False)
    failing_client.get = AsyncMock(side_effect=RuntimeError("network down"))

    with patch.object(places.httpx, "AsyncClient", return_value=failing_client):
        out = await places.GooglePlacesProvider().search(
            market="Burlington, VT", categories=None, radius_m=None, max_results=10
        )
    assert out == []


# ---------------------------------------------------------------------------
# Recorded fixture sanity — the offline CI universe has no dupe keys
# ---------------------------------------------------------------------------


def test_recorded_fixture_has_no_duplicate_dedupe_keys():
    from app.services.places import _dedupe_key

    rows = json.loads(_PLACES_FIXTURE.read_text(encoding="utf-8"))["places"]
    places_objs = [_pr(**{k: r[k] for k in ("name",)},
                       locality=r["locality"], provider=r["provider"],
                       place_id=r["place_id"]) for r in rows]
    keys = [_dedupe_key(p) for p in places_objs]
    assert len(keys) == len(set(keys)), "recorded places fixture contains a dedupe collision"


def test_default_providers_returns_list():
    from app.services.places import default_providers

    provs = default_providers()
    assert isinstance(provs, list)
    # every entry conforms to the interface
    for p in provs:
        assert hasattr(p, "available") and hasattr(p, "search") and hasattr(p, "name")
