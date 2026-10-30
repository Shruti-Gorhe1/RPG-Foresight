"""Schemas for data ingestion endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class CSVUploadResponse(BaseModel):
    """Response for CSV upload."""
    records_processed: int = Field(..., description="Number of records processed")
    records_created: int = Field(..., description="Number of new tender events created")
    errors: List[str] = Field(default_factory=list, description="List of error messages")


class ExcelUploadResponse(BaseModel):
    """Response for Excel upload."""
    records_processed: int = Field(..., description="Number of records processed")
    records_created: int = Field(..., description="Number of new tender events created")
    errors: List[str] = Field(default_factory=list, description="List of error messages")


class ManualTenderEntry(BaseModel):
    """Schema for manual tender entry."""
    source_type: str = Field(..., description="Source type: manual")
    source_event_id: str = Field(..., description="Stable identifier from the source")
    source_revision: str = Field(..., description="Version of the source record")
    tender_id: str = Field(..., description="Tender reference")
    stage: str = Field(..., description="Current source-reported stage")
    source_win_probability: Optional[float] = Field(
        None, description="Source-maintained probability, if genuinely available"
    )
    material_requirements: str = Field(..., description="Known material needs, as a string")
    source_updated_at: datetime = Field(..., description="Timestamp reported by the source")
    data_provenance: str = Field(..., description="Origin, reference, and whether the information is public, synthetic, or internally authorized")
    # Additional fields required by the TenderEvent model
    tenant_id: str = Field(..., description="Tenant ID")
    project_name: str = Field(..., description="Project name")
    sender_entity_id: str = Field(..., description="Sender entity ID")
    # Optional fields with defaults
    prior_stage: Optional[str] = Field(None, description="Previous stage")
    expected_need_window: Optional[str] = Field(None, description="Expected need window")
    # We don't have probability_updated_at in the manual entry, so we'll leave it as None in the model


class ManualEntryResponse(BaseModel):
    """Response for manual entry."""
    event_id: str = Field(..., description="ID of the created tender event")
    message: str = Field(default="Tender event created successfully")