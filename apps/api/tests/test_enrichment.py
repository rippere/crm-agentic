"""Tests for the enrichment provider waterfall (app.services.enrichment)."""
import pytest

from app.services.enrichment import (
    ENRICHMENT_FIELDS,
    EnrichmentProvider,
    enrich_contact_fields,
)


class _FakeProvider:
    """Test double implementing the EnrichmentProvider interface."""

    def __init__(self, name, fields, available=True, raises=False):
        self.name = name
        self._fields = fields
        self._available = available
        self._raises = raises

    def available(self):
        return self._available

    async def lookup(self, *, email, name, company):
        if self._raises:
            raise RuntimeError("boom")
        return dict(self._fields)


def test_fake_provider_satisfies_protocol():
    assert isinstance(_FakeProvider("x", {}), EnrichmentProvider)


@pytest.mark.asyncio
async def test_empty_when_no_providers_available():
    providers = [_FakeProvider("off", {"email": "a@b.com"}, available=False)]
    result = await enrich_contact_fields(
        email=None, name="A B", company="b.com", providers=providers
    )
    assert result == {}


@pytest.mark.asyncio
async def test_first_available_provider_fills_field():
    providers = [
        _FakeProvider("primary", {"email": "found@b.com", "role": "VP"}),
        _FakeProvider("secondary", {"email": "other@b.com", "role": "CEO"}),
    ]
    result = await enrich_contact_fields(
        email=None, name="A B", company="b.com", providers=providers
    )
    # Higher-priority provider wins; secondary never overwrites.
    assert result["email"] == "found@b.com"
    assert result["role"] == "VP"


@pytest.mark.asyncio
async def test_waterfall_fills_missing_field_from_later_provider():
    providers = [
        _FakeProvider("primary", {"email": "found@b.com"}),  # no role
        _FakeProvider("secondary", {"role": "Director"}),
    ]
    result = await enrich_contact_fields(
        email=None, name="A B", company="b.com", providers=providers
    )
    assert result["email"] == "found@b.com"
    assert result["role"] == "Director"


@pytest.mark.asyncio
async def test_provider_exception_is_swallowed_and_waterfall_continues():
    providers = [
        _FakeProvider("bad", {}, raises=True),
        _FakeProvider("good", {"email": "found@b.com"}),
    ]
    result = await enrich_contact_fields(
        email=None, name="A B", company="b.com", providers=providers
    )
    assert result == {"email": "found@b.com"}


@pytest.mark.asyncio
async def test_hunter_provider_unavailable_without_key(monkeypatch):
    from app.services import enrichment

    monkeypatch.setattr(enrichment.settings, "HUNTER_API_KEY", "", raising=False)
    provider = enrichment.HunterProvider()
    assert provider.available() is False
    assert await provider.lookup(email="x@y.com", name=None, company=None) == {}


def test_enrichment_fields_vocabulary():
    assert set(ENRICHMENT_FIELDS) == {"email", "role"}
