from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from ingestion.connectors.zoho import ZohoConnector


def _settings(**overrides):
    values = {
        "zoho_connector_enabled": True,
        "zoho_client_id": "client-id",
        "zoho_client_secret": "client-secret",
        "zoho_refresh_token": "refresh-token",
        "zoho_accounts_domain": "accounts.zoho.in",
        "zoho_api_domain": "www.zohoapis.in",
        "zoho_module": "Tenders",
        "zoho_tenant_id": "KEC-001",
        "zoho_sender_entity_id": "KEC-ENTITY",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_connector_enables_when_all_oauth_credentials_exist(monkeypatch) -> None:
    monkeypatch.setattr("ingestion.connectors.zoho.get_settings", lambda: _settings())
    assert ZohoConnector().is_enabled is True

    monkeypatch.setattr(
        "ingestion.connectors.zoho.get_settings",
        lambda: _settings(zoho_refresh_token=""),
    )
    assert ZohoConnector().is_enabled is False


@pytest.mark.asyncio
async def test_zoho_records_request_uses_crm_module_endpoint(monkeypatch) -> None:
    requests = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            requests.append((url, kwargs))
            return httpx.Response(200)

    monkeypatch.setattr("ingestion.connectors.zoho.get_settings", lambda: _settings())
    monkeypatch.setattr(
        "ingestion.connectors.zoho.httpx.AsyncClient",
        lambda **kwargs: FakeClient(),
    )
    connector = ZohoConnector()

    await connector._get("Tenders", "access-token", page=2)

    assert requests[0][0] == "https://www.zohoapis.in/crm/v2/Tenders"
    assert requests[0][1]["params"] == {"per_page": 200, "page": 2}
    assert connector._token_url() == "https://accounts.zoho.in/oauth/v2/token"


@pytest.mark.asyncio
async def test_zoho_normalizer_uses_configured_tenant_defaults(monkeypatch) -> None:
    monkeypatch.setattr("ingestion.connectors.zoho.get_settings", lambda: _settings())
    connector = ZohoConnector()

    normalized = await connector.normalize(
        {
            "id": "zoho-record-1",
            "Tender_Ref": "T-2026-1",
            "Project_Name": "Transmission upgrade",
            "Stage": "Bid Submitted",
            "Materials": ["Power cables", "Cable accessories"],
            "Modified_Time": "2026-10-21T10:00:00+05:30",
            "Win_Probability": "82.5",
            "Estimated_Tender_Value": "1250000",
            "Currency": "INR",
            "Submission_Deadline": "2026-12-30T17:00:00+05:30",
            "Historical_Outcome_Snapshots": [{
                "source_event_id": "closed-tender-1",
                "snapshot_key": "qualification",
                "stage": "Qualification",
                "material_categories": ["Power cables"],
                "region": "West",
                "tender_value": 1_000_000,
                "currency": "INR",
                "outcome": "won",
            }],
        }
    )

    assert normalized is not None
    assert normalized["tenant_id"] == "KEC-001"
    assert normalized["sender_entity_id"] == "KEC-ENTITY"
    assert normalized["event_id"] == "zoho-record-1"
    assert normalized["material_categories"] == ["Power cables", "Cable accessories"]
    assert normalized["existing_win_probability_percent"] is None
    assert normalized["tender_value"] == 1_250_000
    assert normalized["currency"] == "INR"
    assert normalized["closing_at"] == "2026-12-30T17:00:00+05:30"
    assert normalized["historical_outcomes"][0]["outcome"] == "won"


@pytest.mark.asyncio
async def test_oauth_invalid_client_is_reported_as_configuration_error(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            request = httpx.Request("POST", "https://accounts.zoho.com/oauth/v2/token")
            return httpx.Response(200, json={"error": "invalid_client"}, request=request)

    monkeypatch.setattr("ingestion.connectors.zoho.get_settings", lambda: _settings())
    monkeypatch.setattr("ingestion.connectors.zoho.httpx.AsyncClient", FakeClient)
    connector = ZohoConnector()

    result = await connector.fetch()

    assert result.errors
    assert "invalid_client" in result.errors[0]
    assert "ZOHO_ACCOUNTS_DOMAIN" in result.errors[0]
    assert "client-secret" not in result.errors[0]


@pytest.mark.asyncio
async def test_oauth_invalid_code_points_to_refresh_token_setup(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            request = httpx.Request("POST", "https://accounts.zoho.in/oauth/v2/token")
            return httpx.Response(200, json={"error": "invalid_code"}, request=request)

    monkeypatch.setattr("ingestion.connectors.zoho.get_settings", lambda: _settings())
    monkeypatch.setattr("ingestion.connectors.zoho.httpx.AsyncClient", FakeClient)
    connector = ZohoConnector()

    result = await connector.fetch()

    assert result.errors
    assert "refresh-token grant (invalid_code)" in result.errors[0]
    assert "fresh grant code" in result.errors[0]
    assert "client-secret" not in result.errors[0]
