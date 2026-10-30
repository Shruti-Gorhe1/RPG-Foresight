"""Output schemas for rules, recipients, signal history, and delivery status."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator


class SubsidiaryRouteOut(BaseModel):
    id: int
    rule_id: str
    subsidiary_entity_id: str
    material_categories: List[str] = Field(default_factory=list)


class RoutingRuleOut(BaseModel):
    id: int
    rule_id: str
    tenant_id: str
    name: str
    description: Optional[str] = None
    enabled: bool
    trigger_stages: List[str] = Field(default_factory=list)
    min_win_probability_percent: Optional[float] = Field(default=None, ge=0, le=100)
    purpose: str
    channel: str
    selected_recipient_email: Optional[str] = None
    selected_recipient_emails: List[str] = Field(default_factory=list)
    regions: List[str] = Field(default_factory=list)
    tender_currency: Optional[str] = None
    minimum_tender_value: Optional[float] = None
    maximum_tender_value: Optional[float] = None
    minimum_days_to_close: Optional[int] = None
    maximum_days_to_close: Optional[int] = None
    max_event_age_seconds: int
    max_probability_age_seconds: int
    version: int
    created_at: Optional[datetime] = None
    previewed_at: Optional[datetime] = None
    routes: List[SubsidiaryRouteOut] = Field(default_factory=list)


class RecipientDecisionOut(BaseModel):
    id: int
    event_id: str
    tenant_id: str
    subsidiary_entity_id: str
    recipient_user_id: str
    disposition: str
    reason: str
    payload: dict[str, Any] = Field(default_factory=dict)
    decided_at: Optional[datetime] = None


class NotificationDeliveryOut(BaseModel):
    id: int
    event_id: str
    recipient_user_id: str
    channel: str
    status: str
    message_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int
    created_at: Optional[datetime] = None


class DeliveryStatsOut(BaseModel):
    total: int
    pending: int
    sent: int
    delivered: int
    failed: int
    suppressed: int


class SubsidiaryRouteIn(BaseModel):
    subsidiary_entity_id: str = ""
    material_categories: List[str] = Field(default_factory=list)


class RoutingRuleIn(BaseModel):
    rule_id: str
    name: str
    description: Optional[str] = None
    enabled: bool = True
    trigger_stages: List[str]
    min_win_probability_percent: Optional[float] = None
    purpose: str
    channel: str
    selected_recipient_email: Optional[str] = Field(default=None, min_length=3, max_length=254)
    selected_recipient_emails: List[str] = Field(default_factory=list)
    regions: List[str] = Field(default_factory=list)
    tender_currency: Optional[str] = Field(default=None, min_length=3, max_length=8)
    minimum_tender_value: Optional[float] = Field(default=None, ge=0)
    maximum_tender_value: Optional[float] = Field(default=None, ge=0)
    minimum_days_to_close: Optional[int] = Field(default=None, ge=0)
    maximum_days_to_close: Optional[int] = Field(default=None, ge=0)
    max_event_age_seconds: int = 86400
    max_probability_age_seconds: int = 604800
    routes: List[SubsidiaryRouteIn] = Field(default_factory=list)

    @field_validator("selected_recipient_email")
    @classmethod
    def validate_selected_recipient_email(cls, value: str | None) -> str | None:
        if value is not None and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value) is None:
            raise ValueError("selected_recipient_email must be a valid email address")
        return value

    @field_validator("selected_recipient_emails")
    @classmethod
    def validate_selected_recipient_emails(cls, values: List[str]) -> List[str]:
        for value in values:
            if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value) is None:
                raise ValueError("Every selected_recipient_emails entry must be a valid email address")
        return list(dict.fromkeys(values))


class RecipientAddressOut(BaseModel):
    id: int
    email: str
    display_name: Optional[str] = None
    created_at: Optional[datetime] = None
