"""Zoho CRM connector — fetches tender records from Zoho CRM via OAuth2.

Configure in ``app/.env``:

    ZOHO_CLIENT_ID=<from Zoho API console>
    ZOHO_CLIENT_SECRET=<from Zoho API console>
    ZOHO_REFRESH_TOKEN=<obtained via the OAuth2 refresh-token flow>
    ZOHO_MODULE=Tenders            # CRM module to read (default: Tenders)
    ZOHO_API_DOMAIN=www.zohoapis.com
    ZOHO_ACCOUNTS_DOMAIN=accounts.zoho.com

The connector auto-refreshes the access token using the refresh token. It never
writes to Zoho — read-only ingestion only.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import ssl
from typing import Any

import httpx
import truststore

from ingestion.connectors.base import BaseConnector, ConnectorResult
from shared.config import get_settings
from shared.logger import get_logger

log = get_logger("ingestion.connectors.zoho")

_SSL_CONTEXT = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


class ZohoConnector(BaseConnector):
    """Zoho CRM connector using OAuth2 access tokens."""

    source_type = "crm"
    source_name = "Zoho CRM"
    name = "Zoho CRM Tender Tracking"
    description = "Fetches tender records from Zoho CRM via OAuth2 REST API"
    is_active = True
    is_enabled = False

    def __init__(self, connector_id: str = "zoho", config: dict[str, Any] | None = None):
        super().__init__(connector_id, config)
        settings = get_settings()
        self.is_enabled = bool(
            settings.zoho_connector_enabled
            and settings.zoho_client_id
            and settings.zoho_client_secret
            and settings.zoho_refresh_token
        )
        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None
        self._auth_error: str | None = None

    def _api_base(self) -> str:
        settings = get_settings()
        domain = (settings.zoho_api_domain or "www.zohoapis.com").strip().rstrip("/")
        domain = domain.removeprefix("https://").removeprefix("http://")
        return f"https://{domain}"

    def _token_url(self) -> str:
        settings = get_settings()
        domain = (settings.zoho_accounts_domain or "accounts.zoho.com").strip().rstrip("/")
        domain = domain.removeprefix("https://").removeprefix("http://")
        return f"https://{domain}/oauth/v2/token"

    async def _get_access_token(self) -> str | None:
        """Obtain (or refresh) a Zoho OAuth2 access token."""
        self._auth_error = None
        settings = get_settings()
        client_id = settings.zoho_client_id
        client_secret = settings.zoho_client_secret
        refresh_token = settings.zoho_refresh_token

        if not client_id or not client_secret or not refresh_token:
            log.warning("zoho_credentials_missing")
            self._auth_error = (
                "Zoho OAuth credentials are missing. Configure "
                "ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET and ZOHO_REFRESH_TOKEN in app/.env."
            )
            return None

        # Return cached token if still valid (60s skew).
        if self._access_token and self._token_expires_at:
            if datetime.now(timezone.utc) < self._token_expires_at - timedelta(seconds=60):
                return self._access_token

        try:
            async with httpx.AsyncClient(timeout=30, verify=_SSL_CONTEXT) as client:
                resp = await client.post(
                    self._token_url(),
                    data={
                        "refresh_token": refresh_token,
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "grant_type": "refresh_token",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            if data.get("error"):
                error_code = str(data["error"])
                if error_code == "invalid_client":
                    self._auth_error = (
                        "Zoho OAuth rejected the client credentials (invalid_client). "
                        "Verify the client ID/secret pair and that ZOHO_ACCOUNTS_DOMAIN "
                        "matches the Zoho account data center."
                    )
                elif error_code in {"invalid_code", "invalid_grant"}:
                    self._auth_error = (
                        f"Zoho OAuth rejected the refresh-token grant ({error_code}). "
                        "Generate a fresh grant code and exchange it for a refresh token "
                        "using this same client ID, client secret, and Zoho data center. "
                        "Do not use the short-lived grant code as ZOHO_REFRESH_TOKEN."
                    )
                else:
                    self._auth_error = f"Zoho OAuth rejected the token request ({error_code})."
                log.error("zoho_oauth_rejected", error_code=error_code)
                return None
            self._access_token = data.get("access_token")
            if not self._access_token:
                self._auth_error = "Zoho OAuth response did not contain an access token."
                log.error("zoho_oauth_access_token_missing")
                return None
            expires_in = int(data.get("expires_in", 3600))
            self._token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            log.info("zoho_token_refreshed")
            return self._access_token
        except Exception as exc:  # noqa: BLE001
            self._auth_error = (
                f"Zoho token request failed ({type(exc).__name__}). "
                "Check network access, TLS trust, and the configured Zoho data center."
            )
            log.exception("zoho_token_refresh_failed", error=str(exc))
            return None

    async def fetch(self) -> ConnectorResult:
        """Fetch tender records from Zoho CRM."""
        token = await self._get_access_token()
        if not token:
            return ConnectorResult(
                connector_id=self.connector_id,
                source_name=self.source_name,
                errors=[self._auth_error or "Zoho token request failed without an error detail."],
            )

        settings = get_settings()
        module = (settings.zoho_module or "Tenders").strip()
        raw_records: list[dict[str, Any]] = []
        page = 1
        page_token: str | None = None

        try:
            while True:
                resp = await self._get(module, token, page, page_token)
                if resp.status_code == 401:
                    self._access_token = None
                    self._token_expires_at = None
                    token = await self._get_access_token()
                    if not token:
                        return ConnectorResult(
                            connector_id=self.connector_id,
                            source_name=self.source_name,
                            errors=[self._auth_error or "Zoho token refresh failed."],
                        )
                    resp = await self._get(module, token, page, page_token)
                resp.raise_for_status()
                data = resp.json()
                raw_records.extend(data.get("data", []))
                info = data.get("info") or {}
                if not info.get("more_records"):
                    break
                page_token = info.get("next_page_token")
                if not page_token:
                    page += 1
                    if page > 10:
                        return ConnectorResult(
                            connector_id=self.connector_id,
                            source_name=self.source_name,
                            records=raw_records,
                            errors=[
                                "Zoho has more than 2,000 records but did not return "
                                "a next_page_token; use a supported page-token API."
                            ],
                        )
        except Exception as exc:  # noqa: BLE001
            log.exception("zoho_fetch_failed", error=str(exc))
            return ConnectorResult(
                connector_id=self.connector_id,
                source_name=self.source_name,
                errors=[str(exc)],
            )

        raw_records = data.get("data", [])
        log.info("zoho_fetch_complete", records=len(raw_records))
        return ConnectorResult(
            connector_id=self.connector_id,
            source_name=self.source_name,
            records=raw_records,
        )

    async def _get(
        self,
        module: str,
        token: str,
        page: int = 1,
        page_token: str | None = None,
    ) -> httpx.Response:
        params: dict[str, Any] = {"per_page": 200}
        if page_token:
            params["page_token"] = page_token
        else:
            params["page"] = page
        async with httpx.AsyncClient(timeout=30, verify=_SSL_CONTEXT) as client:
            return await client.get(
                f"{self._api_base()}/crm/v2/{module}",
                headers={"Authorization": f"Zoho-oauthtoken {token}"},
                params=params,
            )

    async def normalize(self, raw_record: dict[str, Any]) -> dict[str, Any] | None:
        """Map Zoho CRM fields to the normalized TenderEvent schema."""
        try:
            settings = get_settings()

            def pick(*names, default=None):
                for n in names:
                    if n in raw_record and raw_record[n] is not None:
                        return raw_record[n]
                return default

            materials = pick("Materials", "Material_Categories", "materials", default="")
            if isinstance(materials, list):
                categories = [str(item).strip() for item in materials if str(item).strip()]
                materials_raw = ", ".join(categories)
            else:
                materials_raw = str(materials or "")
                categories = [c.strip() for c in materials_raw.replace("·", ",").split(",") if c.strip()]

            event_id = str(pick("Tender_Id", "id", "TenderID", default="") or "")
            tender_ref = str(pick("Tender_Ref", "TenderRef", default="") or event_id)
            project_name = pick("Project_Name", "ProjectName", "Name", default="")
            stage = pick("Stage", "Current_Stage", default="")
            if not event_id or not tender_ref or not project_name or not stage or not categories:
                log.warning(
                    "zoho_record_missing_required_fields",
                    event_id=event_id or None,
                    has_tender_ref=bool(tender_ref),
                    has_project_name=bool(project_name),
                    has_stage=bool(stage),
                    has_material_categories=bool(categories),
                )
                return None

            tender_value = pick(
                "Estimated_Tender_Value",
                "Tender_Value",
                "Estimated_Value",
                "Contract_Value",
                "tender_value",
                default=None,
            )
            tender_value = float(tender_value) if tender_value not in (None, "") else None
            historical_outcomes = pick(
                "Historical_Outcome_Snapshots",
                "historical_outcomes",
                default=[],
            )
            if not isinstance(historical_outcomes, list):
                raise ValueError("Historical outcome snapshots must be a list")

            return {
                "tenant_id": pick("Tenant_Id", "tenant_id", default=None) or settings.zoho_tenant_id,
                "event_id": event_id,
                "sender_entity_id": pick("Sender_Entity", "sender_entity", default=None)
                or settings.zoho_sender_entity_id,
                "tender_ref": tender_ref,
                "project_name": project_name,
                "source_revision": str(pick("Revision", "revision", "Modified_Time", default="rev1")),
                "prior_stage": pick("Prior_Stage", "PriorStage", default=None),
                "stage": stage,
                "occurred_at": pick(
                    "Last_Updated",
                    "modified_time",
                    "Modified_Time",
                    "LastUpdated",
                    default=datetime.now(timezone.utc).isoformat(),
                ),
                "material_categories": categories,
                "expected_need_window": pick("Expected_Need_Window", "expected_need_window", default=None),
                "existing_win_probability_percent": None,
                "probability_updated_at": None,
                "tender_value": tender_value,
                "currency": pick("Currency", "Tender_Currency", "currency", default=None),
                "closing_at": pick(
                    "Closing_Date",
                    "Tender_Closing_Date",
                    "Submission_Deadline",
                    "closing_at",
                    default=None,
                ),
                "opening_at": pick(
                    "Opening_Date",
                    "Tender_Opening_Date",
                    "opening_at",
                    default=None,
                ),
                "historical_outcomes": historical_outcomes,
                "source_type": self.source_type,
                "data_provenance": f"CRM: {self.source_name} - Zoho CRM",
                "ingested_at": datetime.now(timezone.utc).isoformat(),
                "material_requirements_raw": materials_raw,
            }
        except Exception as exc:  # noqa: BLE001
            log.exception("zoho_normalize_error", error=str(exc))
            return None
