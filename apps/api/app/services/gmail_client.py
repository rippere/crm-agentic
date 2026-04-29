"""
GmailClient — thin httpx wrapper around the Gmail REST API.
Handles decryption of stored tokens, 401-triggered refresh, and re-encryption.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connector import Connector
from app.services.crypto import decrypt_token, encrypt_token

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


class GmailClient:
    def __init__(self, connector: Connector, db: AsyncSession, google_client_id: str, google_client_secret: str):
        self._connector = connector
        self._db = db
        self._client_id = google_client_id
        self._client_secret = google_client_secret
        self._access_token: str | None = None

    # ──────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────

    def _decrypt_access_token(self) -> str:
        return decrypt_token(self._connector.encrypted_token)

    async def _refresh_access_token(self) -> str:
        """Exchange the stored refresh token for a new access token and persist."""
        if not self._connector.refresh_token:
            raise ValueError("No refresh token available for connector")

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
        """Make an authenticated request; on 401 refresh and retry once."""
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

    # ──────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────

    async def list_messages(self, max_results: int = 100, page_token: str | None = None) -> dict[str, Any]:
        """List message stubs from the inbox."""
        params: dict[str, Any] = {"maxResults": max_results}
        if page_token:
            params["pageToken"] = page_token
        resp = await self._request("GET", "/users/me/messages", params=params)
        return resp.json()

    async def get_message(self, message_id: str, format: str = "full") -> dict[str, Any]:
        """Fetch a full message by its Gmail ID."""
        resp = await self._request("GET", f"/users/me/messages/{message_id}", params={"format": format})
        return resp.json()

    async def get_profile(self) -> dict[str, Any]:
        """Return the authenticated Gmail user profile."""
        resp = await self._request("GET", "/users/me/profile")
        return resp.json()

    async def send_message(self, to: str, subject: str, body: str) -> dict[str, Any]:
        """Send an email via Gmail API using stored OAuth token."""
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
