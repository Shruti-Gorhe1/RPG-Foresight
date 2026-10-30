"""Connector registry — discovers and manages all available connectors."""
from __future__ import annotations

import asyncio

from ingestion.connectors.base import BaseConnector, ConnectorResult

log = __import__("shared.logger", fromlist=["get_logger"]).get_logger("ingestion.connectors.registry")


class ConnectorRegistry:
    """Registry that holds connector instances by connector_id.

    Connectors are registered explicitly. To add a new CRM (e.g. iTrack),
    instantiate its connector class and register it here.
    """

    def __init__(self) -> None:
        self._connectors: dict[str, BaseConnector] = {}

    def register(self, connector: BaseConnector) -> None:
        """Register a connector instance."""
        self._connectors[connector.connector_id] = connector
        log.info("connector_registered", connector_id=connector.connector_id, source=connector.source_name)

    def get(self, connector_id: str) -> BaseConnector | None:
        return self._connectors.get(connector_id)

    def list(self) -> list[BaseConnector]:
        return list(self._connectors.values())

    def enabled(self) -> list[BaseConnector]:
        """Return connectors that are active and enabled."""
        return [c for c in self._connectors.values() if c.is_active and c.is_enabled]

    async def run_all(self, existing_event_ids: set[tuple[str, str]]) -> dict[str, ConnectorResult]:
        """Run enabled connectors concurrently and retain per-connector errors."""
        async def run_connector(connector: BaseConnector) -> tuple[str, ConnectorResult]:
            try:
                result = await connector.run(existing_event_ids)
                return connector.connector_id, result
            except Exception as exc:  # noqa: BLE001
                log.exception(
                    "connector_run_failed",
                    connector_id=connector.connector_id,
                    error=str(exc),
                )
                return (
                    connector.connector_id,
                    ConnectorResult(
                        connector_id=connector.connector_id,
                        source_name=connector.source_name,
                        errors=[str(exc)],
                    ),
                )
        return dict(await asyncio.gather(*(run_connector(c) for c in self.enabled())))


# Global registry instance
registry = ConnectorRegistry()