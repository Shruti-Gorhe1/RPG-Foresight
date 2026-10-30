from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from services.email_adapter import EmailAdapter


@pytest.mark.asyncio
async def test_email_adapter_sends_selected_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = EmailAdapter()
    adapter.smtp_host = "smtp.example.test"
    adapter.smtp_port = 587
    adapter.smtp_username = "alerts@example.test"
    adapter.smtp_password = "test-password"
    adapter.smtp_from = "alerts@example.test"
    adapter.smtp_use_tls = True
    adapter.email_provider = "smtp"

    smtp = MagicMock()
    smtp_context = MagicMock()
    smtp_context.__enter__.return_value = smtp
    monkeypatch.setattr("services.email_adapter.smtplib.SMTP", MagicMock(return_value=smtp_context))

    result = await adapter.send(
        "recipient@example.test",
        {
            "tender_ref": "T-123",
            "project_name": "<Tender>",
            "private_field": "not selected",
        },
        ["tender_ref", "project_name"],
    )

    assert result.status == "sent"
    assert result.message_id
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("alerts@example.test", "test-password")
    sent_message = smtp.send_message.call_args.args[0]
    assert sent_message["To"] == "recipient@example.test"
    assert "&lt;Tender&gt;" in sent_message.get_payload()[1].get_payload()
    assert "private_field" not in sent_message.get_payload()[0].get_payload()


@pytest.mark.asyncio
async def test_email_adapter_reports_missing_configuration() -> None:
    adapter = EmailAdapter()
    adapter.email_provider = "smtp"
    adapter.smtp_host = ""
    adapter.smtp_from = ""

    result = await adapter.send("recipient@example.test", {"tender_ref": "T-123"})

    assert result.status == "failed"
    assert "SMTP not configured" in (result.error or "")


@pytest.mark.asyncio
async def test_email_adapter_rejects_non_email_recipient(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = EmailAdapter()
    adapter.email_provider = "smtp"
    adapter.smtp_host = "smtp.example.test"
    adapter.smtp_port = 587
    adapter.smtp_from = "alerts@example.test"
    monkeypatch.setattr("services.email_adapter.smtplib.SMTP", MagicMock())

    result = await adapter.send("recipient-id", {"tender_ref": "T-123"})

    assert result.status == "failed"
    assert "not a valid email address" in (result.error or "")


@pytest.mark.asyncio
async def test_email_adapter_sends_selected_fields_with_resend(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = EmailAdapter()
    adapter.email_provider = "resend"
    adapter.resend_api_key = "re_test_key"
    adapter.resend_from = "RPG Foresight <alerts@example.test>"
    requests = []
    client_options = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            requests.append((url, kwargs))
            return httpx.Response(
                200,
                json={"id": "resend-message-123"},
                request=httpx.Request("POST", url),
            )

    def fake_async_client(**kwargs):
        client_options.append(kwargs)
        return FakeClient()

    monkeypatch.setattr("services.email_adapter.httpx.AsyncClient", fake_async_client)

    result = await adapter.send(
        "buyer@example.test",
        {
            "tender_ref": "T-123",
            "project_name": "<Tender>",
            "private_field": "not selected",
        },
        ["tender_ref", "project_name"],
    )

    assert result.status == "sent"
    assert result.message_id == "resend-message-123"
    assert client_options[0]["verify"] is not True
    url, request = requests[0]
    assert url == "https://api.resend.com/emails"
    assert request["headers"]["Authorization"] == "Bearer re_test_key"
    assert request["json"]["to"] == ["buyer@example.test"]
    assert request["json"]["from"] == "RPG Foresight <alerts@example.test>"
    assert "&lt;Tender&gt;" in request["json"]["html"]
    assert "private_field" not in request["json"]["text"]


@pytest.mark.asyncio
async def test_resend_requires_api_key_and_verified_sender_configuration() -> None:
    adapter = EmailAdapter()
    adapter.email_provider = "resend"
    adapter.resend_api_key = ""
    adapter.resend_from = ""

    result = await adapter.send("buyer@example.test", {"tender_ref": "T-123"})

    assert result.status == "failed"
    assert "RESEND_API_KEY or RESEND_FROM is missing" in (result.error or "")
