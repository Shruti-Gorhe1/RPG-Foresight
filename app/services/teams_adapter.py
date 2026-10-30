"""Microsoft Teams notification adapter — posts to an incoming webhook.

Configure in ``agent-registry/.env``:

    TEAMS_WEBHOOK_URL=<Incoming webhook URL from Teams connector>

The adapter builds an adaptive MessageCard from the tender
fields and POSTs it to the Teams webhook. Read-only delivery — it never writes
to Teams beyond posting the message.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from services.notification import NotificationAdapter, NotificationResult, register_adapter
from shared.config import get_settings
from shared.logger import get_logger

log = get_logger("services.teams_adapter")


class TeamsAdapter(NotificationAdapter):
    """Delivers notifications to Microsoft Teams via an incoming webhook."""

    def __init__(self, channel: str = "teams"):
        super().__init__(channel)
        settings = get_settings()
        self.webhook_url = settings.teams_webhook_url

    async def send(
        self,
        recipient_user_id: str,
        payload: dict[str, Any],
        approved_fields: list[str] | None = None,
    ) -> NotificationResult:
        if not self.webhook_url:
            return NotificationResult(
                recipient_user_id=recipient_user_id,
                channel=self.channel,
                status="failed",
                error="TEAMS_WEBHOOK_URL not configured in .env",
            )

        # Filter payload to approved fields only.
        fields: dict[str, Any] = payload or {}
        if approved_fields:
            fields = {k: v for k, v in fields.items() if k in approved_fields}

        lines = []
        for k, v in fields.items():
            if v is not None:
                lines.append(f"• **{k.replace('_', ' ').title()}:** {v}")

        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": "0078D4",
            "summary": (
                f"New tender signal: "
                f"{fields.get('tender_ref', fields.get('project_name', 'Tender'))}"
            ),
            "title": "📋 New Tender Signal — RPG Foresight",
            "text": "\n".join(lines) if lines else "No approved fields to display.",
            "sections": [
                {
                    "activityTitle": "Recipient",
                    "activitySubtitle": recipient_user_id,
                },
                {
                    "activityTitle": "Channel",
                    "activitySubtitle": self.channel,
                },
                {
                    "activityTitle": "Source",
                    "activitySubtitle": fields.get("data_provenance", "Zoho CRM"),
                },
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(self.webhook_url, json=card)
                resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            log.exception("teams_send_failed", error=str(exc))
            return NotificationResult(
                recipient_user_id=recipient_user_id,
                channel=self.channel,
                status="failed",
                error=str(exc),
            )

        return NotificationResult(
            recipient_user_id=recipient_user_id,
            channel=self.channel,
            status="sent",
            message_id=f"teams-{recipient_user_id}-{datetime.utcnow().timestamp()}",
        )


# Auto-register for the "teams" channel so routing_service can look it up.
register_adapter("teams", TeamsAdapter("teams"))
