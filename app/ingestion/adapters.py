"""Adapters for public tender portals."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import List, Dict, Any

import httpx

from db.models import TenderEvent
from shared.logger import get_logger

log = get_logger("ingestion.adapters")


async def fetch_cppp_notices() -> List[Dict[str, Any]]:
    """
    Fetch notices from the CPPP (Central Public Procurement Portal) - India.
    Note: This is a placeholder implementation. The actual implementation would
    use the CPPP API or scrape the website, respecting the terms of use.
    """
    # Placeholder: return empty list
    log.info("cppp_adapter_called")
    return []


async def fetch_government_etenders_notices() -> List[Dict[str, Any]]:
    """
    Fetch notices from Government eTenders platform.
    Note: This is a placeholder implementation.
    """
    log.info("government_etenders_adapter_called")
    return []


async def fetch_kec_disclosures_notices() -> List[Dict[str, Any]]:
    """
    Fetch notices from KEC disclosures.
    Note: This is a placeholder implementation.
    """
    log.info("kec_disclosures_adapter_called")
    return []


async def convert_and_store_notices(
    notices: List[Dict[str, Any]],
    source_type: str,
    db_session,
) -> int:
    """
    Convert a list of notice dictionaries to TenderEvent records and store them in the database.
    Returns the number of records created.
    """
    # This is a placeholder for the conversion logic.
    # In a real implementation, we would map the notice fields to the TenderEvent fields.
    # For now, we'll return 0.
    # We'll just return 0 without doing anything.
    return 0


async def run_all_adapters(db_session) -> Dict[str, int]:
    """
    Run all public tender portal adapters and store the results.
    Returns a dictionary with the adapter name and the number of records created.
    """
    # We'll run the adapters concurrently
    cppp_task = asyncio.create_task(fetch_cppp_notices())
    government_etenders_task = asyncio.create_task(fetch_government_etenders_notices())
    kec_disclosures_task = asyncio.create_task(fetch_kec_disclosures_notices())

    cppp_notices = await cppp_task
    government_etenders_notices = await government_etenders_task
    kec_disclosures_notices = await kec_disclosures_task

    results = {}

    # Process CPPP notices
    cppp_count = await convert_and_store_notices(
        cppp_notices, "public_portal", db_session
    )
    results["cppp"] = cppp_count

    # Process Government eTenders notices
    government_etenders_count = await convert_and_store_notices(
        government_etenders_notices, "public_portal", db_session
    )
    results["government_etenders"] = government_etenders_count

    # Process KEC disclosures notices
    kec_disclosures_count = await convert_and_store_notices(
        kec_disclosures_notices, "public_portal", db_session
    )
    results["kec_disclosures"] = kec_disclosures_count

    return results