"""
Places provider abstraction (the discovery "socket") — R3.

Mirrors :mod:`app.services.enrichment`'s shape verbatim: a ``Protocol`` +
``available()`` key-gate + an ordered ``default_providers()`` waterfall, where
every provider **never raises** (on error it logs and returns ``[]``).

**Deliberate semantic difference from enrichment (documented per R3):**
``enrichment`` fills each *missing field* from the first provider that resolves
it (first-provider-wins merge). Discovery instead **unions venues across all
available providers and dedupes** them into a single complete "venue universe"
for a locality — every provider contributes rows, and
:func:`discover_venue_universe` collapses duplicates by :func:`_dedupe_key`.

``GooglePlacesProvider`` is the first concrete rung (Google Places Text Search +
Place Details over ``httpx``). ``YelpProvider`` / ``FoursquareProvider`` are
key-gated stubs behind the same interface — which places API is primary is an
open question (§6); the abstraction lets a different provider slot in later
without touching call sites.

Key-gate degradation: with no provider configured the waterfall returns ``[]``
and the run completes ``partial`` with ``stats.found == 0`` — never a 500.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Shared HTTP timeout for provider calls (matches enrichment.py's conservative
# per-call budget; discovery runs are async/off-request so a slightly larger
# ceiling is acceptable).
_HTTP_TIMEOUT = 10.0

# Google Places (legacy) endpoints. The abstraction is provider-agnostic; if the
# primary provider changes (§6 open question) only this class changes.
_GOOGLE_TEXTSEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
_GOOGLE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

# Tokens dropped when normalizing a venue name for dedup — generic legal/venue
# suffixes that add no identifying signal.
_DEDUPE_STOPWORDS = {
    "the", "a", "and", "&", "co", "company", "llc", "inc",
    "restaurant", "bar", "pub",
}


@dataclass(frozen=True)
class PlaceResult:
    """One discovered venue, provider-normalized.

    The immutable unit the waterfall unions and dedupes. ``provider`` +
    ``place_id`` together form the durable cross-run dedup key that rides the
    shipped partial-unique index ``idx_leads_ws_extid`` via
    ``leads.external_id = f"{provider}:{place_id}"``.
    """

    provider: str
    place_id: str
    name: str
    category: str | None
    address: str | None
    locality: str | None
    lat: float | None
    lng: float | None
    phone: str | None
    website: str | None
    source_url: str | None


@runtime_checkable
class PlacesProvider(Protocol):
    """A source that enumerates venues in a locality.

    Every implementation must be key-gated (``available()``) and must **never
    raise** from ``search()``: on any error it logs and returns ``[]`` so the
    union waterfall degrades cleanly.
    """

    name: str

    def available(self) -> bool:
        """True when the provider is configured (API key present) and callable."""
        ...

    async def search(
        self,
        *,
        market: str,
        categories: list[str] | None,
        radius_m: int | None,
        max_results: int,
    ) -> list[PlaceResult]:
        """Return venues for ``market``. Must never raise — log and return ``[]``."""
        ...


class GooglePlacesProvider:
    """Google Places provider (legacy Text Search + Place Details).

    Gated on ``settings.GOOGLE_PLACES_API_KEY``. For each requested category it
    issues a Text Search (``"{category} in {market}"``), paginates via
    ``next_page_token`` up to ``max_results``, and best-effort enriches each hit
    with phone/website via a Place Details call. Never raises.
    """

    name = "google_places"

    def available(self) -> bool:
        return bool(settings.GOOGLE_PLACES_API_KEY)

    async def search(
        self,
        *,
        market: str,
        categories: list[str] | None,
        radius_m: int | None,
        max_results: int,
    ) -> list[PlaceResult]:
        if not self.available():
            return []

        # With no categories, run a single generic locality query.
        queries = [f"{c} in {market}" for c in categories] if categories else [market]

        results: list[PlaceResult] = []
        seen_place_ids: set[str] = set()
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                for query in queries:
                    if len(results) >= max_results:
                        break
                    raw_hits = await self._text_search(
                        client, query=query, market=market, radius_m=radius_m,
                        remaining=max_results - len(results),
                    )
                    for hit in raw_hits:
                        place_id = hit.get("place_id")
                        if not place_id or place_id in seen_place_ids:
                            continue
                        seen_place_ids.add(place_id)
                        place = await self._to_place_result(client, hit)
                        if place is not None:
                            results.append(place)
                        if len(results) >= max_results:
                            break
        except Exception as exc:  # noqa: BLE001 — never-raise contract
            logger.warning("places google search_failed market=%s exc=%s", market, exc)

        return results[:max_results]

    async def _text_search(
        self,
        client: httpx.AsyncClient,
        *,
        query: str,
        market: str,
        radius_m: int | None,
        remaining: int,
    ) -> list[dict]:
        """Run a paginated Text Search, returning raw result dicts (never raises)."""
        hits: list[dict] = []
        params: dict[str, str] = {
            "query": query,
            "key": settings.GOOGLE_PLACES_API_KEY,
        }
        # TODO(execute): legacy Text Search ignores `radius` without a `location`
        # anchor; verify against the live API whether a geocoded center + radius
        # (or the new Places API v1 `searchText` with a locationBias) is needed
        # for tight-locality discovery, and whether legacy is still enabled on
        # the billing project.
        if radius_m:
            params["radius"] = str(radius_m)

        page_token: str | None = None
        for _ in range(3):  # legacy API caps at 3 pages (~60 results) per query
            if len(hits) >= remaining:
                break
            call_params = dict(params)
            if page_token:
                call_params["pagetoken"] = page_token
            try:
                resp = await client.get(_GOOGLE_TEXTSEARCH_URL, params=call_params)
                payload = resp.json()
            except Exception as exc:  # noqa: BLE001
                logger.warning("places google textsearch_failed query=%s exc=%s", query, exc)
                break

            status = payload.get("status")
            if status not in ("OK", "ZERO_RESULTS"):
                logger.warning("places google textsearch_status=%s query=%s", status, query)
                break
            hits.extend(payload.get("results", []) or [])

            page_token = payload.get("next_page_token")
            if not page_token:
                break
            # TODO(execute): Google requires a short delay before a next_page_token
            # becomes valid; a live run must add a bounded async sleep/retry here
            # or the second page returns INVALID_REQUEST. Left out to keep the
            # scaffold side-effect-free for offline tests.

        return hits

    async def _to_place_result(
        self, client: httpx.AsyncClient, hit: dict
    ) -> PlaceResult | None:
        """Map one Text Search hit to a :class:`PlaceResult`, enriching contact
        fields via Place Details. Returns ``None`` if the hit lacks an id/name."""
        place_id = hit.get("place_id")
        name = hit.get("name")
        if not place_id or not name:
            return None

        geometry = (hit.get("geometry") or {}).get("location") or {}
        types = hit.get("types") or []
        # TODO(execute): Google `types` are machine categories (e.g. "bar",
        # "restaurant", "point_of_interest"); confirm the mapping we want to
        # surface as `category` (first non-generic type vs. the requested query
        # category) against real responses.
        category = next(
            (t for t in types if t not in ("point_of_interest", "establishment")),
            types[0] if types else None,
        )

        phone, website = await self._fetch_details(client, place_id)

        return PlaceResult(
            provider=self.name,
            place_id=place_id,
            name=name,
            category=category,
            address=hit.get("formatted_address"),
            locality=None,  # legacy Text Search does not split out locality
            lat=geometry.get("lat"),
            lng=geometry.get("lng"),
            phone=phone,
            website=website,
            source_url=f"https://www.google.com/maps/place/?q=place_id:{place_id}",
        )

    async def _fetch_details(
        self, client: httpx.AsyncClient, place_id: str
    ) -> tuple[str | None, str | None]:
        """Best-effort Place Details fetch for phone + website. Never raises."""
        try:
            resp = await client.get(
                _GOOGLE_DETAILS_URL,
                params={
                    "place_id": place_id,
                    "fields": "formatted_phone_number,website",
                    "key": settings.GOOGLE_PLACES_API_KEY,
                },
            )
            data = (resp.json() or {}).get("result", {}) or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("places google details_failed place_id=%s exc=%s", place_id, exc)
            return None, None
        return data.get("formatted_phone_number"), data.get("website")


class YelpProvider:
    """Yelp Fusion provider — key-gated stub. Gated on ``settings.YELP_API_KEY``.

    Slots behind :class:`PlacesProvider`; a live implementation would call the
    Yelp Fusion ``/businesses/search`` endpoint with an ``Authorization: Bearer``
    header. Returns ``[]`` until implemented (never raises).
    """

    name = "yelp"

    def available(self) -> bool:
        return bool(settings.YELP_API_KEY)

    async def search(
        self,
        *,
        market: str,
        categories: list[str] | None,
        radius_m: int | None,
        max_results: int,
    ) -> list[PlaceResult]:
        if not self.available():
            return []
        # TODO(execute): implement Yelp Fusion /businesses/search (Bearer auth,
        # `location`=market, `categories`, `radius`, `limit`) and map each
        # business to PlaceResult(provider="yelp", place_id=business["id"], ...).
        logger.info("places yelp provider not yet implemented; returning []")
        return []


class FoursquareProvider:
    """Foursquare Places provider — key-gated stub. Gated on
    ``settings.FOURSQUARE_API_KEY``.

    Slots behind :class:`PlacesProvider`; a live implementation would call the
    Foursquare Places ``/v3/places/search`` endpoint. Returns ``[]`` until
    implemented (never raises).
    """

    name = "foursquare"

    def available(self) -> bool:
        return bool(settings.FOURSQUARE_API_KEY)

    async def search(
        self,
        *,
        market: str,
        categories: list[str] | None,
        radius_m: int | None,
        max_results: int,
    ) -> list[PlaceResult]:
        if not self.available():
            return []
        # TODO(execute): implement Foursquare /v3/places/search (Authorization
        # header, `near`=market, `categories`, `radius`, `limit`) and map each
        # place to PlaceResult(provider="foursquare", place_id=place["fsq_id"], ...).
        logger.info("places foursquare provider not yet implemented; returning []")
        return []


def default_providers() -> list[PlacesProvider]:
    """The ordered discovery waterfall, highest-priority provider first.

    Google Places is the first concrete rung; Yelp and Foursquare are key-gated
    stubs (§6 open question on which is primary). All are returned regardless of
    configuration — :func:`discover_venue_universe` checks ``available()`` and
    skips unconfigured ones. Ordering is dedup priority (an earlier provider's
    row wins when two collide on :func:`_dedupe_key`).
    """
    return [GooglePlacesProvider(), YelpProvider(), FoursquareProvider()]


def _dedupe_key(p: PlaceResult) -> str:
    """Stable dedup key for a venue.

    Prefers a normalized ``name + locality`` (lowercased, punctuation stripped,
    whitespace collapsed, generic venue/legal stopwords dropped) so the *same*
    venue found by two different providers collapses to one row. Falls back to
    ``f"{provider}:{place_id}"`` when the name normalizes to nothing.
    """
    tokens = _normalize_tokens(p.name)
    if p.locality:
        tokens = tokens + _normalize_tokens(p.locality)
    if tokens:
        return " ".join(tokens)
    return f"{p.provider}:{p.place_id}"


def _normalize_tokens(text: str | None) -> list[str]:
    """Lowercase, strip punctuation, collapse whitespace, drop stopwords."""
    if not text:
        return []
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return [tok for tok in cleaned.split() if tok and tok not in _DEDUPE_STOPWORDS]


async def discover_venue_universe(
    *,
    market: str,
    categories: list[str] | None = None,
    radius_m: int | None = None,
    max_venues: int = 60,
    providers: list[PlacesProvider] | None = None,
) -> list[PlaceResult]:
    """Build the deduped venue universe for a locality.

    Unions results across every **available** provider (in
    :func:`default_providers` priority order), dedupes by :func:`_dedupe_key`
    (first-seen wins, so higher-priority providers keep their row), and caps the
    result at ``max_venues``.

    Never raises: a provider that errors is logged and skipped. With no provider
    configured this returns ``[]`` (the caller reports the run ``partial`` with
    ``found == 0`` rather than a 500).
    """
    if providers is None:
        providers = default_providers()

    universe: list[PlaceResult] = []
    seen: set[str] = set()

    for provider in providers:
        if len(universe) >= max_venues:
            break
        try:
            if not provider.available():
                continue
            found = await provider.search(
                market=market,
                categories=categories,
                radius_m=radius_m,
                max_results=max_venues,
            )
        except Exception as exc:  # noqa: BLE001 — defensive; providers shouldn't raise
            logger.warning(
                "places provider=%s raised during discovery market=%s exc=%s",
                getattr(provider, "name", "?"), market, exc,
            )
            continue

        for place in found:
            key = _dedupe_key(place)
            if key in seen:
                continue
            seen.add(key)
            universe.append(place)
            if len(universe) >= max_venues:
                break

    return universe[:max_venues]
