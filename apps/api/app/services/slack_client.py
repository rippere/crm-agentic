"""
SlackClient — thin httpx wrapper around the Slack Web API.
Slack user tokens (xoxp-) don't expire unless revoked, so no refresh logic needed.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.models.connector import Connector
from app.services.crypto import decrypt_token

SLACK_API_BASE = "https://slack.com/api"


class SlackClient:
    def __init__(self, connector: Connector):
        self._token = decrypt_token(connector.encrypted_token)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def _get(self, method: str, **params: Any) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{SLACK_API_BASE}/{method}",
                headers=self._headers(),
                params={k: v for k, v in params.items() if v is not None},
            )
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack API error [{method}]: {data.get('error', 'unknown')}")
        return data

    async def list_conversations(
        self,
        types: str = "im,mpim,public_channel",
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        return await self._get(
            "conversations.list",
            types=types,
            limit=limit,
            exclude_archived=True,
            cursor=cursor,
        )

    async def get_history(
        self,
        channel: str,
        limit: int = 200,
        oldest: str | None = None,
    ) -> dict[str, Any]:
        return await self._get(
            "conversations.history",
            channel=channel,
            limit=limit,
            oldest=oldest,
        )

    async def get_user_info(self, user_id: str) -> dict[str, Any]:
        return await self._get("users.info", user=user_id)
