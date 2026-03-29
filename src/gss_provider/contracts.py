from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from gss_core.models import ConsumerType


@dataclass
class AuthContext:
    customer_id: str
    token: str
    consumer_id: str
    consumer_type: ConsumerType
    request_id: str


@dataclass
class IssuedToken:
    access_token: str
    token_type: str
    expires_in_seconds: int
    customer_id: str
    method: str


@dataclass
class VerificationRecord:
    verification_id: str
    customer_id: str
    expires_at: datetime
    accepted_fields: list[str]
    channel: str | None = None
    customer_hint: str | None = None


@dataclass
class ConfirmationRecord:
    token: str
    customer_id: str
    payload: dict[str, Any]
    expires_at: datetime


class AuthStore(Protocol):
    def issue_token(self, *, customer_id: str, method: str, ttl_seconds: int) -> IssuedToken: ...

    def resolve_customer(self, token: str) -> str | None: ...

    def authenticate_agent_key(self, key: str) -> dict[str, Any] | None: ...

    def issue_agent_token(self, *, agent_id: str, ttl_seconds: int, scopes: list[str]) -> IssuedToken: ...

    def resolve_agent(self, token: str) -> str | None: ...

    def create_customer_verification(self, *, payload: dict[str, Any], ttl_seconds: int) -> VerificationRecord: ...

    def consume_customer_verification(self, *, verification_id: str) -> VerificationRecord | None: ...


class ConfirmationStore(Protocol):
    def create_confirmation(
        self,
        *,
        customer_id: str,
        payload: dict[str, Any],
        ttl_seconds: int,
    ) -> ConfirmationRecord: ...

    def consume_confirmation(self, *, token: str, customer_id: str) -> ConfirmationRecord | None: ...


class AuditStore(Protocol):
    def append_event(self, event: dict[str, Any]) -> None: ...

    def list_customer_events(self, customer_id: str) -> list[dict[str, Any]]: ...


class ShopRuntimeAdapter(AuthStore, ConfirmationStore, AuditStore, Protocol):
    """Combined adapter contract for shop-owned runtime state."""
