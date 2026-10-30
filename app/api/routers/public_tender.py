"""Router for triggering public tender portal adapters."""
from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ingestion.adapters import run_all_adapters
from db.base import get_db_session
from shared.logger import get_logger

router = APIRouter()
log = get_logger("api.public_tender")


@router.post("/trigger-adapters", response_model=Dict[str, int])
async def trigger_adapters(
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, int]:
    """
    Trigger all public tender portal adapters and store the results.
    Returns a dictionary with the adapter name and the number of records created.
    """
    try:
        results = await run_all_adapters(db)
        return results
    except Exception as e:
        log.error("adapter_trigger_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger adapters: {str(e)}",
        )