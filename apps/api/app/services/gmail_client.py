"""
GmailClient — thin httpx wrapper around the Gmail REST API.
Handles decryption of stored tokens, 401-triggered refresh, and re-encryption.
"""
from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connector import Connector
from app.services.crypto import decrypt_token, encrypt_token

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


class GmailReauthRequired(Exception):
    """The Gmail connector's refresh token is missing, expired, or revoked.

    Google returns HTTP 400 ``{"error": "invalid_grant"}`` when a refresh token
    is no longer valid (e.g. the 7-day expiry that applies while the OAuth app is
    in Testing mode). This is a user-actionable reauth condition, not a transient
    failure, so callers should surface a "reconnect Gmail" path rather than a
    generic 502. ``code`` carries the specific cause for logging/triage.
    """

    def __init__(self, message: str, code: str = "reauth_required"):
        super().__init__(message)
        self.code = code


# Default query: Primary inbox + your own sent mail, skipping automated senders.
#
# `in:sent` is load-bearing, not a nicety. Reciprocity (do they write back?) and
# reply latency are the two strongest terms in any relationship-strength score,
# and both are uncomputable from inbound mail alone — under `category:primary`
# the workspace has no record that it ever sent anything. Sent mail carries no
# Gmail category, so it takes an explicit OR rather than a looser category
# filter. Costs no new OAuth scope: gmail.readonly already covers SENT.
GMAIL_DEFAULT_QUERY = (
    "(category:primary OR in:sent) "
    "-from:noreply -from:no-reply -from:no_reply -from:donotreply "
    "-from:notifications -from:newsletter -from:mailer-daemon -from:bounce"
)


class GmailClient:
    def __init__(self, connector: Connector, db: AsyncSession, google_client_id: str, google_client_secret: str):
        self._connector = connector
        self._db = db
        self._client_id = google_client_id
        self._client_secret = google_client_secret
        self._access_token: str | None = None

    def _decrypt_access_token(self) -> str:
        return decrypt_token(self._connector.encrypted_token)

    async def _refresh_access_token(self) -> str:
        if not self._connector.refresh_token:
            raise GmailReauthRequired(
                "No refresh token stored for this Gmail connector", code="no_refresh_token"
            )

        refresh_plain = decrypt_token(self._connector.refresh_token)

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": refresh_plain,
                    "grant_type": "refresh_token",
                },
            )

        if resp.status_code >= 400:
            error_code = ""
            try:
                error_code = str(resp.json().get("error", ""))
            except Exception:  # noqa: BLE001 — body may not be JSON
                pass
            # Only invalid_grant (refresh token expired/revoked) is user-fixable by
            # reconnecting. Other errors — invalid_client (bad GOOGLE_CLIENT_SECRET),
            # invalid_request, etc. — are server-side config bugs; let them surface
            # via raise_for_status() so they're logged, not hidden behind a pointless
            # "Reconnect Gmail" loop.
            if error_code == "invalid_grant":
                raise GmailReauthRequired(
                    "Gmail refresh token expired or revoked", code="invalid_grant"
                )
            resp.raise_for_status()

        data = resp.json()

        new_access_token: str = data["access_token"]
        self._connector.encrypted_token = encrypt_token(new_access_token)
        self._db.add(self._connector)
        await self._db.commit()
        await self._db.refresh(self._connector)
        return new_access_token

    async def _get_valid_access_token(self) -> str:
        if self._access_token:
            return self._access_token
        return self._decrypt_access_token()

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        token = await self._get_valid_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient() as client:
            resp = await client.request(method, f"{GMAIL_API_BASE}{path}", headers=headers, **kwargs)

        if resp.status_code == 401:
            token = await self._refresh_access_token()
            headers = {"Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient() as client:
                resp = await client.request(method, f"{GMAIL_API_BASE}{path}", headers=headers, **kwargs)

        resp.raise_for_status()
        return resp

    async def list_messages(
        self,
        max_results: int = 100,
        page_token: str | None = None,
        q: str = GMAIL_DEFAULT_QUERY,
    ) -> dict[str, Any]:
        """List message stubs filtered to Primary inbox by default."""
        params: dict[str, Any] = {"maxResults": max_results, "q": q}
        if page_token:
            params["pageToken"] = page_token
        resp = await self._request("GET", "/users/me/messages", params=params)
        return resp.json()

    async def get_message(self, message_id: str, format: str = "full") -> dict[str, Any]:
        resp = await self._request("GET", f"/users/me/messages/{message_id}", params={"format": format})
        return resp.json()

    async def get_profile(self) -> dict[str, Any]:
        resp = await self._request("GET", "/users/me/profile")
        return resp.json()

    async def send_message(self, to: str, subject: str, body: str) -> dict[str, Any]:
        import base64
        import email.mime.text

        profile = await self.get_profile()
        sender = profile.get("emailAddress", "me")

        msg = email.mime.text.MIMEText(body, "plain")
        msg["To"] = to
        msg["From"] = sender
        msg["Subject"] = subject

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        resp = await self._request("POST", "/users/me/messages/send", json={"raw": raw})
        return resp.json()
