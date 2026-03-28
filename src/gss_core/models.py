from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ActionLevel(str, Enum):
    READ = "read"
    REQUEST = "request"
    CRITICAL = "critical"


class ErrorPayload(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ResponseEnvelope(BaseModel):
    status: str
    data: Any | None = None
    error: ErrorPayload | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class ConsumerType(str, Enum):
    AI_AGENT = "ai_agent"
    APP = "app"
    BROWSER_EXTENSION = "browser_extension"
    DEVICE = "device"


class DescribeResponse(BaseModel):
    shop: str
    name: str
    gss_version: str
    domains: list[str]
    auth_methods: list[str]
    endpoint: str


class AuthLoginRequest(BaseModel):
    method: str = Field(pattern=r"^(oauth2|api_key)$")
    customer_id: str = "CUST-001"


class OrdersListQuery(BaseModel):
    status: str | None = None
    since: str | None = None
    limit: int = 20


class ReturnsCheckEligibilityRequest(BaseModel):
    order_id: str
    item_id: str


class ReturnsInitiateRequest(BaseModel):
    order_id: str
    item_id: str
    reason: str


class ReturnsConfirmRequest(BaseModel):
    token: str


class ProtocolGetRequest(BaseModel):
    trigger: str
    context: dict[str, Any] = Field(default_factory=dict)
