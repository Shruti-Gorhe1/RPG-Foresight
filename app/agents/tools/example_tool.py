"""Read-only, tenant-scoped tools available to the conversational agent."""
from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool
from sqlalchemy import or_, select

from db.base import AsyncSessionLocal
from db.models import RoutingRule, TenderEvent
from ingestion.connectors.registry import registry
from observability.tracing import traced_span


@traced_span("rpg_foresight.tool.search_tenders")
async def search_tenders(
    query: str,
    tenant_id: str,
) -> list[dict[str, Any]]:
    """Search this organization's tender records by name, reference, or stage."""
    if not tenant_id:
        raise ValueError("An authenticated tenant is required to search tenders.")
    search_term = query.strip()
    if not search_term:
        raise ValueError("Provide a search term for tender lookup.")
    term = f"%{search_term}%"
    async with AsyncSessionLocal() as db:
        rows = await db.scalars(
            select(TenderEvent)
            .where(
                TenderEvent.tenant_id == tenant_id,
                or_(
                    TenderEvent.project_name.ilike(term),
                    TenderEvent.tender_ref.ilike(term),
                    TenderEvent.stage.ilike(term),
                ),
            )
            .order_by(TenderEvent.occurred_at.desc())
            .limit(10)
        )
        return [
            {
                "tender_ref": row.tender_ref,
                "project_name": row.project_name,
                "stage": row.stage,
                "region": row.region,
                "material_categories": row.material_categories,
                "closing_at": row.closing_at.isoformat() if row.closing_at else None,
            }
            for row in rows
        ]


@traced_span("rpg_foresight.tool.list_enabled_connectors")
async def list_enabled_connectors() -> list[dict[str, str]]:
    """List active, enabled data connectors without exposing their credentials."""
    return [
        {
            "connector_id": connector.connector_id,
            "name": connector.name,
            "source_type": connector.source_type,
            "source_name": connector.source_name,
        }
        for connector in registry.enabled()
    ]


@traced_span("rpg_foresight.tool.list_routing_rules")
async def list_routing_rules(
    tenant_id: str,
) -> list[dict[str, Any]]:
    """Summarize this organization's enabled routing rules, excluding recipients."""
    if not tenant_id:
        raise ValueError("An authenticated tenant is required to list routing rules.")
    async with AsyncSessionLocal() as db:
        rows = await db.scalars(
            select(RoutingRule)
            .where(RoutingRule.tenant_id == tenant_id, RoutingRule.enabled.is_(True))
            .order_by(RoutingRule.name)
        )
        return [
            {
                "name": row.name,
                "purpose": row.purpose,
                "channel": row.channel,
                "trigger_stages": row.trigger_stages,
                "minimum_win_probability_percent": row.min_win_probability_percent,
            }
            for row in rows
        ]


def create_agent_tools(tenant_id: str) -> list[StructuredTool]:
    """Create tools closed over the authenticated tenant, never model arguments."""
    async def scoped_search_tenders(query: str) -> list[dict[str, Any]]:
        return await search_tenders(query, tenant_id)

    async def scoped_list_routing_rules() -> list[dict[str, Any]]:
        return await list_routing_rules(tenant_id)

    return [
        StructuredTool.from_function(
            coroutine=scoped_search_tenders,
            name="search_tenders",
            description="Search this organization's tender records by name, reference, or stage.",
        ),
        StructuredTool.from_function(
            coroutine=list_enabled_connectors,
            name="list_enabled_connectors",
            description="List active, enabled data connectors without exposing their credentials.",
        ),
        StructuredTool.from_function(
            coroutine=scoped_list_routing_rules,
            name="list_routing_rules",
            description="Summarize this organization's enabled routing rules, excluding recipients.",
        ),
    ]
