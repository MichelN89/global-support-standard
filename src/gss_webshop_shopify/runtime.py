from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from gss_provider.contracts import ConfirmationRecord, IssuedToken, ShopRuntimeAdapter, VerificationRecord


class ShopOwnedRuntimeAdapter(ShopRuntimeAdapter):
    """
    Shop-owned runtime state adapter for the Shopify project.

    Replace with production-grade persistence (Redis/DB/KMS-backed) in the webshop
    deployment. This in-memory adapter is intentionally local-dev oriented.
    """

    def __init__(self) -> None:
        self._tokens: dict[str, tuple[str, datetime, list[str]]] = {}
        self._agent_tokens: dict[str, tuple[str, datetime, list[str]]] = {}
        self._agent_keys: dict[str, dict[str, Any]] = {}
        self._verifications: dict[str, dict[str, Any]] = {}
        self._confirmations: dict[str, ConfirmationRecord] = {}
        self._audit_events: list[dict[str, Any]] = []

    def issue_token(self, *, customer_id: str, method: str, ttl_seconds: int) -> IssuedToken:
        token = f"shop-{customer_id}-{uuid4().hex[:16]}"
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        scopes = [
            "orders:read",
            "shipping:read",
            "returns:read",
            "returns:request",
            "protocols:read",
            "account:read",
            "payments:read",
            "subscriptions:read",
            "loyalty:read",
            "orders:request",
            "shipping:request",
            "account:request",
            "payments:request",
            "subscriptions:request",
            "loyalty:request",
            "support:request",
        ]
        self._tokens[token] = (customer_id, expires_at, scopes)
        return IssuedToken(
            access_token=token,
            token_type="bearer",
            expires_in_seconds=ttl_seconds,
            customer_id=customer_id,
            method=method,
            scopes=scopes,
        )

    def resolve_customer(self, token: str) -> str | None:
        row = self._tokens.get(token)
        if not row:
            return None
        customer_id, expires_at, _ = row
        if expires_at <= datetime.now(timezone.utc):
            del self._tokens[token]
            return None
        return customer_id

    def resolve_scopes(self, token: str) -> list[str]:
        row = self._tokens.get(token)
        if row:
            _, expires_at, scopes = row
            if expires_at <= datetime.now(timezone.utc):
                self._tokens.pop(token, None)
                return []
            return list(scopes)
        agent = self._agent_tokens.get(token)
        if not agent:
            return []
        _, expires_at, scopes = agent
        if expires_at <= datetime.now(timezone.utc):
            self._agent_tokens.pop(token, None)
            return []
        return list(scopes)

    def authenticate_agent_key(self, key: str) -> dict[str, Any] | None:
        return self._agent_keys.get(key)

    def issue_agent_token(self, *, agent_id: str, ttl_seconds: int, scopes: list[str]) -> IssuedToken:
        token = f"agt-{agent_id}-{uuid4().hex[:16]}"
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        self._agent_tokens[token] = (agent_id, expires_at, list(scopes))
        return IssuedToken(
            access_token=token,
            token_type="bearer",
            expires_in_seconds=ttl_seconds,
            customer_id=agent_id,
            method="agent_key",
            scopes=list(scopes),
        )

    def resolve_agent(self, token: str) -> str | None:
        row = self._agent_tokens.get(token)
        if not row:
            return None
        agent_id, expires_at, _ = row
        if expires_at <= datetime.now(timezone.utc):
            self._agent_tokens.pop(token, None)
            return None
        return agent_id

    def create_customer_verification(self, *, payload: dict[str, Any], ttl_seconds: int) -> VerificationRecord:
        verification_id = f"ver-{uuid4().hex[:16]}"
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        record = {
            "verification_id": verification_id,
            "customer_id": str(payload.get("customer_id") or payload.get("email") or "unknown"),
            "expires_at": expires_at,
            "accepted_fields": [k for k in ("order_id", "email", "phone", "postal_code", "last_name") if payload.get(k)],
            "channel": payload.get("channel"),
            "customer_hint": None,
        }
        self._verifications[verification_id] = record
        return VerificationRecord(**record)

    def consume_customer_verification(self, *, verification_id: str) -> VerificationRecord | None:
        row = self._verifications.pop(verification_id, None)
        if not row:
            return None
        if row["expires_at"] <= datetime.now(timezone.utc):
            return None
        return VerificationRecord(**row)

    def create_confirmation(
        self,
        *,
        customer_id: str,
        payload: dict[str, Any],
        ttl_seconds: int,
    ) -> ConfirmationRecord:
        token = f"shop-conf-{uuid4().hex[:16]}"
        record = ConfirmationRecord(
            token=token,
            customer_id=customer_id,
            payload=payload,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
        )
        self._confirmations[token] = record
        return record

    def consume_confirmation(self, *, token: str, customer_id: str) -> ConfirmationRecord | None:
        record = self._confirmations.get(token)
        if not record:
            return None
        if record.customer_id != customer_id or record.expires_at <= datetime.now(timezone.utc):
            self._confirmations.pop(token, None)
            return None
        self._confirmations.pop(token, None)
        return record

    def append_event(self, event: dict[str, Any]) -> None:
        self._audit_events.append(dict(event))

    def list_customer_events(self, customer_id: str) -> list[dict[str, Any]]:
        return [e for e in self._audit_events if e.get("customer_id") == customer_id]
