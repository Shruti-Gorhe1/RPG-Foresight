"""Synthetic iTrack-style tender connector for RPG subsidiary dashboard demos."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ingestion.connectors.base import BaseConnector, ConnectorResult
from shared.subsidiaries import SUBSIDIARIES


class SubsidiaryDemoConnector(BaseConnector):
    """Generate clearly labeled sample tender records for each RPG subsidiary."""

    source_type = "crm"
    source_name = "Subsidiary CRM demo"
    name = "RPG Subsidiary CRM Demo"
    description = "Synthetic iTrack-style records for KEC, CEAT, and RayChem"
    is_enabled = True

    async def fetch(self) -> ConnectorResult:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        records: list[dict[str, Any]] = []
        samples = (
            ("Won", "Transmission line package", 1_250_000_000, -150, -120),
            ("Lost", "Regional grid upgrade", 480_000_000, -110, -80),
            ("In Progress", "Substation expansion", 720_000_000, 20, 45),
        )
        for subsidiary_id, subsidiary in SUBSIDIARIES.items():
            for index, (stage, project, value, opening_days, closing_days) in enumerate(samples, 1):
                tender_id = f"DEMO-{subsidiary_id.upper()}-{index:03d}"
                records.append({
                    "event_id": tender_id,
                    "tender_ref": tender_id,
                    "revision": "demo-v1",
                    "project_name": f"{subsidiary['name']} {project}",
                    "stage": stage,
                    "materials": "Power systems, EPC",
                    "tender_value": value,
                    "currency": "INR",
                    "opening_at": (now + timedelta(days=opening_days)).isoformat(),
                    "closing_at": (now + timedelta(days=closing_days)).isoformat(),
                    "occurred_at": now.isoformat(),
                    "tenant_id": subsidiary["tenant_id"],
                    "sender_entity_id": subsidiary["sender_entity_id"],
                })
        return ConnectorResult(
            connector_id=self.connector_id,
            source_name=self.source_name,
            records=records,
        )

    async def normalize(self, raw_record: dict[str, Any]) -> dict[str, Any] | None:
        materials_raw = str(raw_record["materials"])
        categories = [item.strip() for item in materials_raw.split(",") if item.strip()]
        return {
            "tenant_id": raw_record["tenant_id"],
            "event_id": raw_record["event_id"],
            "sender_entity_id": raw_record["sender_entity_id"],
            "tender_ref": raw_record["tender_ref"],
            "project_name": raw_record["project_name"],
            "source_revision": raw_record["revision"],
            "prior_stage": None,
            "stage": raw_record["stage"],
            "occurred_at": raw_record["occurred_at"],
            "material_categories": categories,
            "expected_need_window": None,
            "existing_win_probability_percent": None,
            "probability_updated_at": None,
            "tender_value": raw_record["tender_value"],
            "currency": raw_record["currency"],
            "opening_at": raw_record["opening_at"],
            "closing_at": raw_record["closing_at"],
            "source_type": self.source_type,
            "data_provenance": "Demo data: synthetic subsidiary CRM records",
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "material_requirements_raw": materials_raw,
            "historical_outcomes": [],
        }
