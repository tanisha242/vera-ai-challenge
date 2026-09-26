"""
Typed data models matching magicpin AI Challenge specifications and schemas.
All models use ConfigDict(extra="allow") to gracefully support unexpected or Phase 3 adaptive context fields.
"""

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict


# =============================================================================
# CONTEXT SCOPES & HTTP PAYLOAD SCHEMAS
# =============================================================================

ContextScope = Literal["category", "merchant", "customer", "trigger"]


class ContextPush(BaseModel):
    model_config = ConfigDict(extra="allow")

    scope: str
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: str


class ContextPushAck(BaseModel):
    accepted: bool = True
    ack_id: str
    stored_at: str


class ContextPushReject(BaseModel):
    accepted: bool = False
    reason: str
    current_version: int | None = None
    details: str | None = None


class HealthCheckResponse(BaseModel):
    status: str = "ok"
    uptime_seconds: int
    contexts_loaded: dict[str, int]


class TeardownResponse(BaseModel):
    status: str = "ok"
    cleared: bool = True



class MetadataResponse(BaseModel):
    team_name: str
    team_members: list[str]
    model: str
    approach: str
    contact_email: str
    version: str
    submitted_at: str


class TickRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    now: str
    available_triggers: list[str] = Field(default_factory=list)


class Action(BaseModel):
    model_config = ConfigDict(extra="allow")

    conversation_id: str
    merchant_id: str
    customer_id: str | None = None
    send_as: Literal["vera", "merchant_on_behalf"]
    trigger_id: str
    template_name: str
    template_params: list[str] = Field(default_factory=list)
    body: str
    cta: str
    suppression_key: str
    rationale: str


class TickResponse(BaseModel):
    actions: list[Action] = Field(default_factory=list)


class ReplyRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    conversation_id: str
    merchant_id: str | None = None
    customer_id: str | None = None
    from_role: str  # "merchant" or "customer"
    message: str
    received_at: str
    turn_number: int


class ReplyResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    action: Literal["send", "wait", "end"]
    body: str | None = None
    cta: str | None = None
    wait_seconds: int | None = None
    rationale: str


# =============================================================================
# DOMAIN DATA STRUCTURE MODELS (for internal usage & validation)
# =============================================================================

class CategoryContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    slug: str
    voice: dict[str, Any] = Field(default_factory=dict)
    offer_catalog: list[dict[str, Any]] = Field(default_factory=list)
    peer_stats: dict[str, Any] = Field(default_factory=dict)
    digest: list[dict[str, Any]] = Field(default_factory=list)
    patient_content_library: list[dict[str, Any]] = Field(default_factory=list)
    seasonal_beats: list[dict[str, Any]] = Field(default_factory=list)
    trend_signals: list[dict[str, Any]] = Field(default_factory=list)


class MerchantContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    merchant_id: str
    category_slug: str
    identity: dict[str, Any] = Field(default_factory=dict)
    subscription: dict[str, Any] = Field(default_factory=dict)
    performance: dict[str, Any] = Field(default_factory=dict)
    offers: list[dict[str, Any]] = Field(default_factory=list)
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)
    customer_aggregate: dict[str, Any] = Field(default_factory=dict)
    signals: list[str] = Field(default_factory=list)
    review_themes: list[dict[str, Any]] = Field(default_factory=list)


class CustomerContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    customer_id: str
    merchant_id: str
    identity: dict[str, Any] = Field(default_factory=dict)
    relationship: dict[str, Any] = Field(default_factory=dict)
    state: str = "active"  # new, active, lapsed_soft, lapsed_hard, churned
    preferences: dict[str, Any] = Field(default_factory=dict)
    consent: dict[str, Any] = Field(default_factory=dict)


class TriggerContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    scope: Literal["merchant", "customer"]
    kind: str
    source: Literal["external", "internal"]
    merchant_id: str
    customer_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    urgency: int = 1
    suppression_key: str = ""
    expires_at: str | None = None
