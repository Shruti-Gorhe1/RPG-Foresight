"""Mock CRM connector for iTrack-style tender tracking systems.

This is a reference implementation that simulates connecting to an organization's
CRM (e.g., KEC's iTrack). In production, replace the mock fetch() with real API
calls, database reads, or webhook handling.

Read-only: this connector never writes to the source system.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import re
from typing import Any

from ingestion.connectors.base import BaseConnector, ConnectorResult
from shared.logger import get_logger

log = get_logger("ingestion.connectors.itrack")


class ITrackConnector(BaseConnector):
    """Mock connector simulating iTrack tender tracking system."""

    source_type = "crm"
    source_name = "iTrack"
    name = "iTrack Tender Tracking"
    description = "Mock CRM connector simulating KEC iTrack tender tracking system"
    is_enabled = True

    def __init__(self, connector_id: str = "itrack", config: dict[str, Any] | None = None):
        super().__init__(connector_id, config)
        self._mock_data = self._seed_mock_data()

    def _seed_mock_data(self) -> list[dict[str, Any]]:
        """Seed mock iTrack records. In production, this would be replaced
        with actual API calls to iTrack."""
        now = datetime.now(timezone.utc).replace(microsecond=0)
        revision = "demo-v1"
        historical_outcomes = self._seed_mock_outcomes(now)
        return [
            {
                "itrack_tender_id": "IT-2026-1001",
                "revision": revision,
                "project_name": "Western transmission corridor EPC",
                "current_stage": "Bid Submitted",
                "prior_stage": "Technical evaluation",
                "materials": "Power cables · Cable accessories",
                "expected_need_window": "2026-Q4",
                "tender_value": 1_250_000_000,
                "currency": "INR",
                "opening_at": (now - timedelta(days=14)).isoformat(),
                "closing_at": (now + timedelta(days=30)).isoformat(),
                "last_updated": (now - timedelta(minutes=20)).isoformat(),
                "sender_entity": "KEC-ENTITY",
                "tenant_id": "KEC-001",
                "historical_outcomes": historical_outcomes,
            },
            {
                "itrack_tender_id": "IT-2026-1002",
                "revision": revision,
                "project_name": "Regional distribution upgrade",
                "current_stage": "Technical evaluation",
                "prior_stage": "Bid prepared",
                "materials": "Substation equipment",
                "expected_need_window": "2026-Q1",
                "tender_value": 480_000_000,
                "currency": "INR",
                "opening_at": (now - timedelta(days=7)).isoformat(),
                "closing_at": (now + timedelta(days=18)).isoformat(),
                "last_updated": (now - timedelta(minutes=35)).isoformat(),
                "sender_entity": "KEC-ENTITY",
                "tenant_id": "KEC-001",
            },
            {
                "itrack_tender_id": "IT-2026-1003",
                "revision": revision,
                "project_name": "National highway EPC package",
                "current_stage": "Preferred bidder",
                "prior_stage": "Bid Submitted",
                "materials": "Project-specific materials",
                "expected_need_window": "2026-Q2",
                "tender_value": 2_100_000_000,
                "currency": "INR",
                "opening_at": (now - timedelta(days=21)).isoformat(),
                "closing_at": (now + timedelta(days=45)).isoformat(),
                "last_updated": (now - timedelta(hours=1)).isoformat(),
                "sender_entity": "KEC-ENTITY",
                "tenant_id": "KEC-001",
            },
            {
                "itrack_tender_id": "IT-2026-1004",
                "revision": revision,
                "project_name": "Transmission network expansion package",
                "current_stage": "Bid Submitted",
                "prior_stage": "Technical evaluation",
                "materials": "Power cables · Cable accessories",
                "expected_need_window": "2026-Q4",
                "tender_value": 1_250_000_000,
                "currency": "INR",
                "opening_at": (now - timedelta(days=10)).isoformat(),
                "closing_at": (now + timedelta(days=35)).isoformat(),
                "last_updated": (now - timedelta(minutes=10)).isoformat(),
                "sender_entity": "KEC-ENTITY",
                "tenant_id": "KEC-001",
            },
        ]

    @staticmethod
    def _seed_mock_outcomes(now: datetime) -> list[dict[str, Any]]:
        """Create stable, explicitly synthetic stage snapshots for demo training."""
        materials = ("Power cables", "Substation equipment", "Highway EPC", "Renewables")
        regions = ("West", "South", "North", "East")
        values = (180_000_000, 480_000_000, 1_250_000_000, 2_100_000_000)
        stages = (
            "Market assessment",
            "Technical evaluation",
            "Bid prepared",
            "Bid submitted",
            "Preferred bidder",
        )
        snapshots = []
        for tender_index in range(40):
            tender_id = f"IT-DEMO-HISTORY-{tender_index + 1:03d}"
            material = materials[tender_index % len(materials)]
            region = regions[(tender_index // 2) % len(regions)]
            tender_value = values[(tender_index // 3) % len(values)]
            outcome = "won" if (tender_index * 7 + tender_index // 4) % 10 < 4 else "lost"
            stages_reached = (
                len(stages)
                if outcome == "won"
                else 1 + (tender_index * 3) % len(stages)
            )
            for stage_index, stage in enumerate(stages[:stages_reached]):
                snapshot_stage = re.sub(r"[^a-z0-9]+", "-", stage.casefold()).strip("-")
                snapshots.append({
                    "tenant_id": "KEC-001",
                    "source_event_id": tender_id,
                    "snapshot_key": snapshot_stage,
                    "stage": stage,
                    "material_categories": [material],
                    "region": region,
                    "tender_value": tender_value,
                    "currency": "INR",
                    "outcome": outcome,
                    "observed_at": (
                        now - timedelta(days=(40 - tender_index) * 90 - stage_index * 14)
                    ).isoformat(),
                })
        return snapshots

    async def fetch(self) -> ConnectorResult:
        """Simulate fetching records from iTrack API."""
        # Simulate network delay
        await asyncio.sleep(0.1)

        # In production, this would be:
        # response = await http_client.get(f"{self.config['api_base']}/tenders",
        #                                  headers={"Authorization": f"Bearer {self.config['api_key']}"})
        # raw_records = response.json()["data"]

        log.info("itrack_fetch_complete", records=len(self._mock_data))
        return ConnectorResult(
            connector_id=self.connector_id,
            source_name=self.source_name,
            records=self._mock_data,
        )

    async def normalize(self, raw_record: dict[str, Any]) -> dict[str, Any] | None:
        """Map iTrack fields to the normalized TenderEvent schema."""
        try:
            materials_raw = raw_record.get("materials", "")
            categories = [c.strip() for c in materials_raw.replace("·", ",").split(",") if c.strip()]

            return {
                "tenant_id": raw_record.get("tenant_id", ""),
                "event_id": raw_record.get("itrack_tender_id", ""),
                "sender_entity_id": raw_record.get("sender_entity", ""),
                "tender_ref": raw_record.get("itrack_tender_id", ""),
                "project_name": raw_record.get("project_name", ""),
                "source_revision": raw_record.get("revision", ""),
                "prior_stage": raw_record.get("prior_stage") or None,
                "stage": raw_record.get("current_stage", ""),
                "occurred_at": raw_record.get("last_updated", datetime.now(timezone.utc).isoformat()),
                "material_categories": categories,
                "expected_need_window": raw_record.get("expected_need_window") or None,
                "existing_win_probability_percent": None,
                "probability_updated_at": None,
                "tender_value": raw_record.get("tender_value"),
                "currency": raw_record.get("currency"),
                "opening_at": raw_record.get("opening_at"),
                "closing_at": raw_record.get("closing_at"),
                "source_type": self.source_type,
                "data_provenance": f"Demo data: synthetic {self.source_name} records",
                "ingested_at": datetime.now(timezone.utc).isoformat(),
                "material_requirements_raw": materials_raw,
                "historical_outcomes": raw_record.get("historical_outcomes", []),
            }
        except Exception as exc:  # noqa: BLE001
            log.exception("itrack_normalize_error", error=str(exc))
            return None