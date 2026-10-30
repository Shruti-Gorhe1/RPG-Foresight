"""Base interface for all data source connectors.

Any CRM, tender portal, or data source must implement this interface to be
plugged into the agentic ingestion pipeline. New connectors are discovered
automatically through the registry.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from observability.tracing import traced_span
from shared.logger import get_logger

log = get_logger("ingestion.connectors.base")


class ConnectorResult:
    """Result of a connector fetch operation."""

    def __init__(
        self,
        connector_id: str,
        source_name: str,
        records: list[dict[str, Any]] | None = None,
        errors: list[str] | None = None,
    ):
        self.connector_id = connector_id
        self.source_name = source_name
        self.records = records or []
        self.errors = errors or []
        self.fetched_at = datetime.now(timezone.utc)


class BaseConnector(ABC):
    """Abstract base class for all data source connectors.

    Subclasses must define:
        source_type  — 'crm', 'public_portal', 'csv', 'manual'
        source_name  — human-readable source name, e.g. 'iTrack', 'CPPP'
    """

    source_type: str = "crm"
    source_name: str = "base"
    name: str = "base"
    description: str | None = None
    is_active: bool = True
    is_enabled: bool = False
    last_sync_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None

    def __init__(self, connector_id: str, config: dict[str, Any] | None = None):
        self.connector_id = connector_id
        self.config = config or {}

    @abstractmethod
    async def fetch(self) -> ConnectorResult:
        """Fetch raw records from the source.

        Returns a ConnectorResult with raw records and any errors.
        Must not write to the database.
        """
        ...

    @abstractmethod
    async def normalize(self, raw_record: dict[str, Any]) -> dict[str, Any] | None:
        """Map a raw source record to the normalized TenderEvent schema.

        Returns None if the record should be skipped.
        """
        ...

    async def deduplicate(
        self, normalized: list[dict[str, Any]], existing_event_ids: set[tuple[str, str]]
    ) -> list[dict[str, Any]]:
        """Remove records that already exist by (source_event_id, source_revision)."""
        deduped = []
        for record in normalized:
            key = (record.get("event_id", ""), record.get("source_revision", ""))
            if key not in existing_event_ids:
                deduped.append(record)
                existing_event_ids.add(key)
        return deduped

    @traced_span("rpg_foresight.connector.run")
    async def run(self, existing_event_ids: set[tuple[str, str]]) -> ConnectorResult:
        """Execute the full connector lifecycle: fetch → normalize → deduplicate."""
        result = await self.fetch()
        if result.errors:
            log.warning(
                "connector_fetch_errors",
                connector_id=self.connector_id,
                errors=result.errors,
            )

        normalized: list[dict[str, Any]] = []
        for raw in result.records:
            try:
                mapped = await self.normalize(raw)
                if mapped:
                    normalized.append(mapped)
            except Exception as exc:  # noqa: BLE001
                log.exception(
                    "connector_normalize_error",
                    connector_id=self.connector_id,
                    error=str(exc),
                )
                result.errors.append(f"normalize_error: {str(exc)}")

        deduped = await self.deduplicate(normalized, existing_event_ids)
        result.records = deduped
        return result