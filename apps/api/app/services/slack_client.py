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

    async def post_message(self, channel: str, text: str, blocks: list[dict] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"channel": channel, "text": text}
        if blocks:
            payload["blocks"] = blocks
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{SLACK_API_BASE}/chat.postMessage",
                headers={**self._headers(), "Content-Type": "application/json"},
                json=payload,
            )
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack post error: {data.get('error', 'unknown')}")
        return data

    async def post_hitl_block(
        self,
        channel: str,
        deal_title: str,
        company: str,
        subject: str,
        body_preview: str,
        approve_value: str,
        dismiss_value: str,
    ) -> dict[str, Any]:
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"Follow-up needed: {deal_title}", "emoji": True},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Company:* {company}\n*Subject:* {subject}\n\n_{body_preview}_"},
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✓ Approve & Send", "emoji": True},
                        "style": "primary",
                        "action_id": "hitl_approve",
                        "value": approve_value,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✗ Dismiss", "emoji": True},
                        "style": "danger",
                        "action_id": "hitl_dismiss",
                        "value": dismiss_value,
                    },
                ],
            },
        ]
        return await self.post_message(channel=channel, text=f"Follow-up needed: {deal_title}", blocks=blocks)
