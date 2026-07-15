"""
Contact enrichment provider abstraction (the "socket").

A small ordered-waterfall over pluggable providers. Today Hunter.io is the only
rung; future data sources (account-based LinkedIn fetch, bought job-change /
funding feeds) implement the same ``EnrichmentProvider`` interface and slot in
without touching call sites. Each provider is key-gated: if it is not configured
it reports itself unavailable and is skipped, so the waterfall degrades cleanly.

The waterfall fills each field from the first provider that returns a value for
it; it never overwrites a field a higher-priority provider already filled.
"""
from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Fields a provider may contribute. Keep this the shared vocabulary so callers
# and the merge logic in enrich_contact stay in sync.
ENRICHMENT_FIELDS = ("email", "role")


@runtime_checkable
class EnrichmentProvider(Protocol):
    """A source that can fill in missing contact fields."""

    name: str

    def available(self) -> bool:
        """True when the provider is configured and safe to call."""
        ...

    async def lookup(
        self, *, email: str | None, name: str | None, company: str | None
    ) -> dict[str, str | None]:
        """Return any of ENRICHMENT_FIELDS this provider can resolve.

        Must never raise: on error, log and return ``{}`` so the waterfall
        continues to the next rung.
        """
        ...


class HunterProvider:
    """Hunter.io email finder + verifier. Gated on ``HUNTER_API_KEY``."""

    name = "hunter"

    def available(self) -> bool:
        return bool(settings.HUNTER_API_KEY)

    async def lookup(
        self, *, email: str | None, name: str | None, company: str | None
    ) -> dict[str, str | None]:
        if not self.available():
            return {}

        result: dict[str, str | None] = {}
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                if not email and name and company:
                    # Email finder
                    parts = (name or "").split()
                    first = parts[0] if parts else ""
                    last = parts[-1] if len(parts) > 1 else ""
                    resp = await client.get(
                        "https://api.hunter.io/v2/email-finder",
                        params={
                            "domain": company,
                            "first_name": first,
                            "last_name": last,
                            "api_key": settings.HUNTER_API_KEY,
                        },
                    )
                    found = resp.json().get("data", {})
                    if found.get("email"):
                        result["email"] = found["email"]
                        result["role"] = found.get("position")
                elif email:
                    # Email verifier + enrichment
                    resp = await client.get(
                        "https://api.hunter.io/v2/email-verifier",
                        params={"email": email, "api_key": settings.HUNTER_API_KEY},
                    )
                    found = resp.json().get("data", {})
                    result["role"] = found.get("position") or None
        except Exception as exc:  # noqa: BLE001
            logger.warning("enrichment hunter lookup_failed email=%s exc=%s", email, exc)

        return result


def default_providers() -> list[EnrichmentProvider]:
    """The ordered waterfall. Highest-priority provider first.

    New sources (e.g. an account-based LinkedIn fetch or a bought contact-data
    feed) are appended here once implemented; ordering is priority.
    """
    return [HunterProvider()]


async def enrich_contact_fields(
    *,
    email: str | None,
    name: str | None,
    company: str | None,
    providers: list[EnrichmentProvider] | None = None,
) -> dict[str, str | None]:
    """Run the enrichment waterfall and return the merged fields.

    Each field is taken from the first available provider that resolves it;
    later providers only fill fields still missing. Unavailable providers are
    skipped. Never raises.
    """
    if providers is None:
        providers = default_providers()

    merged: dict[str, str | None] = {}
    for provider in providers:
        if not provider.available():
            continue
        # Stop early once every field is filled.
        if all(merged.get(f) for f in ENRICHMENT_FIELDS):
            break
        try:
            found = await provider.lookup(email=email, name=name, company=company)
        except Exception as exc:  # noqa: BLE001 — defensive; providers shouldn't raise
            logger.warning("enrichment provider=%s raised exc=%s", provider.name, exc)
            continue
        for field, value in found.items():
            if value and not merged.get(field):
                merged[field] = value
    return merged
