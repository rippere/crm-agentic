"""
OutlookClient — thin httpx wrapper around the Microsoft Graph mail API.

The Outlook / Microsoft 365 counterpart of GmailClient: decrypts stored tokens,
refreshes on 401 (persisting the ROTATED refresh token Microsoft returns), and
re-encrypts. Covers work/school (Microsoft 365) and personal (Outlook.com)
accounts via the multi-tenant ``common`` authority.
"""
from __future__ import annotations

from datetime import datetime
from email.utils import formataddr
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connector import Connector
from app.services.crypto import decrypt_token, encrypt_token

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
MS_AUTHORITY = "https://login.microsoftonline.com/common/oauth2/v2.0"
MS_AUTH_URL = f"{MS_AUTHORITY}/authorize"
MS_TOKEN_URL = f"{MS_AUTHORITY}/token"

# Delegated scopes. offline_access is what makes Microsoft issue a refresh token;
# Mail.Read covers Inbox + Sent Items, Mail.Send covers /me/sendMail.
OUTLOOK_SCOPES = ["offline_access", "openid", "email", "User.Read", "Mail.Read", "Mail.Send"]

# The Graph equivalent of GMAIL_DEFAULT_QUERY's "(category:primary OR in:sent)":
# the Inbox plus your own sent mail. Listing the two well-known folders (rather
# than /me/messages across every folder) keeps Junk, Deleted Items, Drafts and
# archive folders out of ingest. Sent mail is load-bearing for the same reason
# as in Gmail — reciprocity and reply latency are uncomputable from inbound only.
OUTLOOK_INGEST_FOLDERS = ("inbox", "sentitems")

# Fields ingest needs; everything else is left on the server.
_MESSAGE_SELECT = ",".join([
    "id",
    "conversationId",
    "internetMessageId",
    "internetMessageHeaders",
    "subject",
    "from",
    "toRecipients",
    "ccRecipients",
    "receivedDateTime",
    "sentDateTime",
    "bodyPreview",
    "body",
])

# Plain-text bodies (ingest stores body_plain) and immutable ids, so a message's
# id — our messages.external_id dedupe key — survives moves between folders.
_PREFER = 'outlook.body-content-type="text", IdType="ImmutableId"'

# Token-endpoint error codes that mean the user must reconnect: the refresh token
# expired/was revoked (invalid_grant), or a tenant policy / revoked consent now
# requires an interactive sign-in (interaction_required, consent_required).
_REAUTH_ERRORS = {"invalid_grant", "interaction_required", "consent_required"}


class OutlookReauthRequired(Exception):
    """The Outlook connector's refresh token is missing, expired, or revoked.

    Mirrors GmailReauthRequired: a user-actionable reconnect condition, not a
    transient failure. ``code`` carries the specific cause for logging/triage.
    """

    def __init__(self, message: str, code: str = "reauth_required"):
        super().__init__(message)
        self.code = code


def graph_address(recipient: dict[str, Any] | None) -> str:
    """Render a Graph recipient ``{"emailAddress": {"name", "address"}}`` as an
    RFC 5322 ``"Name" <addr>`` string — the shape Gmail's From/To headers have,
    so the shared ingest helpers (_link_contact, _parse_addresses,
    _is_automated_sender) treat both providers identically."""
    email_address = (recipient or {}).get("emailAddress") or {}
    address = (email_address.get("address") or "").strip()
    if not address:
        return ""
    return formataddr(((email_address.get("name") or "").strip(), address))


def graph_address_list(recipients: list[dict[str, Any]] | None) -> str:
    return ", ".join(a for a in (graph_address(r) for r in recipients or []) if a)


class OutlookClient:
    def __init__(
        self,
        connector: Connector,
        db: AsyncSession,
        microsoft_client_id: str,
        microsoft_client_secret: str,
    ):
        self._connector = connector
        self._db = db
        self._client_id = microsoft_client_id
        self._client_secret = microsoft_client_secret
        self._access_token: str | None = None

    def _decrypt_access_token(self) -> str:
        return decrypt_token(self._connector.encrypted_token)

    async def _refresh_access_token(self) -> str:
        if not self._connector.refresh_token:
            raise OutlookReauthRequired(
                "No refresh token stored for this Outlook connector", code="no_refresh_token"
            )

        refresh_plain = decrypt_token(self._connector.refresh_token)

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                MS_TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": refresh_plain,
                    "grant_type": "refresh_token",
                    "scope": " ".join(OUTLOOK_SCOPES),
                },
            )

        if resp.status_code >= 400:
            error_code = ""
            try:
                error_code = str(resp.json().get("error", ""))
            except Exception:  # noqa: BLE001 — body may not be JSON
                pass
            # Only reauth-class errors are user-fixable by reconnecting. Others —
            # invalid_client (bad/expired MICROSOFT_CLIENT_SECRET), unauthorized_client
            # — are server-side config bugs; surface them via raise_for_status().
            if error_code in _REAUTH_ERRORS:
                raise OutlookReauthRequired(
                    "Outlook refresh token expired or revoked", code=error_code
                )
            resp.raise_for_status()

        data = resp.json()

        new_access_token: str = data["access_token"]
        self._connector.encrypted_token = encrypt_token(new_access_token)
        # Microsoft rotates refresh tokens: each refresh returns a new one and the
        # old one eventually stops working. Persist it or the connector silently
        # dies once the original refresh token ages out.
        new_refresh_token = data.get("refresh_token")
        if new_refresh_token:
            self._connector.refresh_token = encrypt_token(new_refresh_token)
        self._db.add(self._connector)
        await self._db.commit()
        await self._db.refresh(self._connector)
        self._access_token = new_access_token
        return new_access_token

    async def _get_valid_access_token(self) -> str:
        if self._access_token:
            return self._access_token
        return self._decrypt_access_token()

    async def _request(self, method: str, path_or_url: str, **kwargs: Any) -> httpx.Response:
        # @odata.nextLink values are absolute URLs; everything else is a path.
        url = path_or_url if path_or_url.startswith("https://") else f"{GRAPH_API_BASE}{path_or_url}"
        extra_headers: dict[str, str] = kwargs.pop("headers", {}) or {}

        token = await self._get_valid_access_token()
        async with httpx.AsyncClient() as client:
            resp = await client.request(
                method, url, headers={"Authorization": f"Bearer {token}", **extra_headers}, **kwargs
            )

        if resp.status_code == 401:
            token = await self._refresh_access_token()
            async with httpx.AsyncClient() as client:
                resp = await client.request(
                    method, url, headers={"Authorization": f"Bearer {token}", **extra_headers}, **kwargs
                )

        resp.raise_for_status()
        return resp

    async def list_messages(
        self,
        folder: str = "inbox",
        top: int = 100,
        since: datetime | None = None,
        next_link: str | None = None,
    ) -> dict[str, Any]:
        """One page of a mail folder, newest first.

        Pass the previous page's ``@odata.nextLink`` as ``next_link`` to continue;
        it already encodes the folder, filter, ordering and page size.
        """
        headers = {"Prefer": _PREFER}
        if next_link:
            resp = await self._request("GET", next_link, headers=headers)
            return resp.json()

        params: dict[str, Any] = {
            "$top": top,
            "$select": _MESSAGE_SELECT,
            "$orderby": "receivedDateTime desc",
        }
        if since is not None:
            # Graph requires an $orderby property to also lead the $filter.
            params["$filter"] = f"receivedDateTime ge {since.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        resp = await self._request(
            "GET", f"/me/mailFolders/{folder}/messages", params=params, headers=headers
        )
        return resp.json()

    async def get_profile(self) -> dict[str, Any]:
        resp = await self._request("GET", "/me", params={"$select": "mail,userPrincipalName,displayName"})
        return resp.json()

    async def send_message(self, to: str, subject: str, body: str) -> dict[str, Any]:
        """Send a plain-text email from the connected mailbox via /me/sendMail.

        Graph answers 202 Accepted with an EMPTY body — unlike Gmail there is no
        message id or thread id to return (getting one would need Mail.ReadWrite
        to create a draft first). The sent copy is saved to Sent Items, so the
        next Outlook sync ingests it as an outbound message.
        """
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": to}}],
            },
            "saveToSentItems": True,
        }
        await self._request("POST", "/me/sendMail", json=payload)
        return {"id": None, "threadId": None, "status": "accepted"}
