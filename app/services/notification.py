"""Notification delivery adapter interfaces and channel registry."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from shared.logger import get_logger

log = get_logger("services.notification")


class NotificationResult:
    def __init__(
        self,
        recipient_user_id: str,
        channel: str,
        status: str,
        message_id: str | None = None,
        error: str | None = None,
    ):
        self.recipient_user_id = recipient_user_id
        self.channel = channel
        self.status = status  # pending, sent, delivered, failed, suppressed
        self.message_id = message_id
        self.error = error
        self.sent_at = datetime.now(timezone.utc) if status == "sent" else None


class NotificationAdapter:
    """Base notification delivery adapter."""

    def __init__(self, channel: str):
        self.channel = channel

    async def send(
        self,
        recipient_user_id: str,
        payload: dict[str, Any],
        approved_fields: list[str] | None = None,
    ) -> NotificationResult:
        """Fail closed unless a channel adapter implements real delivery."""
        raise NotImplementedError(
            f"No real notification implementation for channel '{self.channel}'"
        )


# Registry of available notification channels
_notification_adapters: dict[str, NotificationAdapter] = {}


def register_adapter(channel: str, adapter: NotificationAdapter) -> None:
    _notification_adapters[channel] = adapter
    log.info("notification_adapter_registered", channel=channel)


def get_adapter(channel: str) -> NotificationAdapter | None:
    return _notification_adapters.get(channel)

