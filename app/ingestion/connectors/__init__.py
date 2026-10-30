"""Connectors package."""
from ingestion.connectors.base import BaseConnector, ConnectorResult
from ingestion.connectors.registry import registry
from ingestion.connectors.itrack import ITrackConnector
from ingestion.connectors.subsidiary_demo import SubsidiaryDemoConnector
from ingestion.connectors.zoho import ZohoConnector

# Auto-register connectors
registry.register(ITrackConnector())
registry.register(SubsidiaryDemoConnector("subsidiary-demo"))
registry.register(ZohoConnector())

__all__ = [
    "BaseConnector",
    "ConnectorResult",
    "registry",
    "ITrackConnector",
    "SubsidiaryDemoConnector",
    "ZohoConnector",
]