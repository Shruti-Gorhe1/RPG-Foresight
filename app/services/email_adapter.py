"""Email notification adapter — sends tender signals to configured recipients.

Resend configuration:

    EMAIL_PROVIDER=resend
    RESEND_API_KEY=<API key or Key Vault URI>
    RESEND_FROM=RPG Foresight <alerts@verified-domain.example>

SMTP remains available for providers that accept the configured SMTP
authentication method.
"""
from __future__ import annotations

import smtplib
import ssl
from html import escape
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import make_msgid
from typing import Any

import httpx
import truststore

from services.notification import NotificationAdapter, NotificationResult, register_adapter
from shared.config import get_settings
from shared.logger import get_logger
from observability.tracing import traced_span

log = get_logger("services.email_adapter")
_SSL_CONTEXT = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


class EmailAdapter(NotificationAdapter):
    """Delivers notifications via SMTP email."""

    def __init__(self, channel: str = "email"):
        super().__init__(channel)
        settings = get_settings()
        self.smtp_host = settings.smtp_host
        self.smtp_port = settings.smtp_port
        self.smtp_username = settings.smtp_username
        self.smtp_password = settings.smtp_password
        self.smtp_from = settings.smtp_from
        self.smtp_use_tls = settings.smtp_use_tls
        self.smtp_timeout = settings.smtp_timeout_seconds
        self.email_provider = settings.email_provider.strip().lower()
        self.resend_api_key = settings.resend_api_key
        self.resend_from = settings.resend_from

    def _is_configured(self) -> bool:
        if self.email_provider == "resend":
            return bool(self.resend_api_key and self.resend_from)
        if self.email_provider != "smtp":
            return False
        return bool(self.smtp_host and self.smtp_port and self.smtp_from)

    def _build_content(self, fields: dict[str, Any]) -> tuple[str, str, str]:
        subject = f"New Tender Signal — {fields.get('tender_ref', fields.get('project_name', 'Tender'))}"

        lines = [
            f"{key.replace('_', ' ').title()}: {value}"
            for key, value in fields.items()
            if value is not None
        ]
        text_body = "\n".join(lines) if lines else "No approved fields to display."
        text_body += "\n\n— RPG Foresight Tender Signal"

        rows = "".join(
            f"<tr><td style='padding:4px 12px;border:1px solid #ccc;'>{escape(key.replace('_', ' ').title())}</td>"
            f"<td style='padding:4px 12px;border:1px solid #ccc;'>{escape(str(value))}</td></tr>"
            for key, value in fields.items()
            if value is not None
        )
        html_body = f"""
<html><body style="font-family:Arial,sans-serif;">
  <h2 style="color:#0E6E55;">New Tender Signal</h2>
  <table style="border-collapse:collapse;">{rows}</table>
  <p style="color:#829087;font-size:12px;">RPG Foresight Tender Signal</p>
</body></html>
"""
        return subject, text_body, html_body

    def _build_message(
        self,
        recipient_email: str,
        fields: dict[str, Any],
    ) -> MIMEMultipart:
        subject, text_body, html_body = self._build_content(fields)
        msg = MIMEMultipart("alternative")
        msg["From"] = self.smtp_from
        msg["To"] = recipient_email
        msg["Message-ID"] = make_msgid()
        msg["Subject"] = subject

        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))
        return msg

    async def _send_resend(
        self,
        recipient_email: str,
        fields: dict[str, Any],
    ) -> NotificationResult:
        subject, text_body, html_body = self._build_content(fields)
        try:
            async with httpx.AsyncClient(
                timeout=self.smtp_timeout,
                verify=_SSL_CONTEXT,
            ) as client:
                response = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {self.resend_api_key}"},
                    json={
                        "from": self.resend_from,
                        "to": [recipient_email],
                        "subject": subject,
                        "text": text_body,
                        "html": html_body,
                    },
                )
                response.raise_for_status()
                response_data = response.json()
        except httpx.HTTPStatusError as exc:
            try:
                response_details = exc.response.json()
            except ValueError:
                response_details = {}
            detail = response_details.get("message") or response_details.get("name")
            log.error(
                "resend_email_rejected",
                status_code=exc.response.status_code,
                recipient=recipient_email,
            )
            return NotificationResult(
                recipient_user_id=recipient_email,
                channel=self.channel,
                status="failed",
                error=(
                    f"Resend rejected the email request (HTTP {exc.response.status_code}): {detail}"
                    if detail
                    else f"Resend rejected the email request (HTTP {exc.response.status_code})."
                ),
            )
        except httpx.RequestError as exc:
            log.exception("resend_email_request_failed", recipient=recipient_email)
            return NotificationResult(
                recipient_user_id=recipient_email,
                channel=self.channel,
                status="failed",
                error=f"Resend request failed: {type(exc).__name__}",
            )

        message_id = response_data.get("id")
        if not message_id:
            log.error("resend_email_id_missing", recipient=recipient_email)
            return NotificationResult(
                recipient_user_id=recipient_email,
                channel=self.channel,
                status="failed",
                error="Resend response did not contain an email ID.",
            )

        return NotificationResult(
            recipient_user_id=recipient_email,
            channel=self.channel,
            status="sent",
            message_id=message_id,
        )

    @traced_span("rpg_foresight.email.send")
    async def send(
        self,
        recipient_user_id: str,
        payload: dict[str, Any],
        approved_fields: list[str] | None = None,
    ) -> NotificationResult:
        if not self._is_configured():
            if self.email_provider == "resend":
                error = "Resend is selected but RESEND_API_KEY or RESEND_FROM is missing."
            elif self.email_provider == "smtp":
                error = "SMTP not configured in .env (SMTP_HOST/SMTP_PORT/SMTP_FROM)"
            else:
                error = f"Unsupported EMAIL_PROVIDER: {self.email_provider}"
            return NotificationResult(
                recipient_user_id=recipient_user_id,
                channel=self.channel,
                status="failed",
                error=error,
            )

        # Keep the optional field filter for callers that explicitly request it.
        fields: dict[str, Any] = payload or {}
        if approved_fields:
            fields = {k: v for k, v in fields.items() if k in approved_fields}

        # The recipient_user_id doubles as the email address in this adapter.
        recipient_email = recipient_user_id
        if "@" not in recipient_email:
            return NotificationResult(
                recipient_user_id=recipient_user_id,
                channel=self.channel,
                status="failed",
                error=f"recipient_user_id is not a valid email address: {recipient_user_id}",
            )

        if self.email_provider == "resend":
            return await self._send_resend(recipient_email, fields)

        msg = self._build_message(recipient_email, fields)

        try:
            import asyncio

            def _send_sync():
                if self.smtp_use_tls and self.smtp_port == 465:
                    with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=self.smtp_timeout) as server:
                        if self.smtp_username and self.smtp_password:
                            server.login(self.smtp_username, self.smtp_password)
                        server.send_message(msg)
                elif self.smtp_use_tls:
                    with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=self.smtp_timeout) as server:
                        server.ehlo()
                        server.starttls(context=ssl.create_default_context())
                        server.ehlo()
                        if self.smtp_username and self.smtp_password:
                            server.login(self.smtp_username, self.smtp_password)
                        server.send_message(msg)
                else:
                    with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=self.smtp_timeout) as server:
                        if self.smtp_username and self.smtp_password:
                            server.login(self.smtp_username, self.smtp_password)
                        server.send_message(msg)
            await asyncio.to_thread(_send_sync)
        except Exception as exc:  # noqa: BLE001
            log.exception("email_send_failed", recipient=recipient_email, error=str(exc))
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
            message_id=msg.get("Message-ID"),
        )


# Auto-register for the "email" channel so routing_service can look it up.
register_adapter("email", EmailAdapter("email"))