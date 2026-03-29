from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from gss_provider.contracts import ConfirmationRecord, IssuedToken, ShopRuntimeAdapter, VerificationRecord
from gss_provider.mock_data import get_order


class InMemoryShopAdapter(ShopRuntimeAdapter):
    """
    Test/local-only adapter.

    Production deployments should provide their own adapter implementing
    ShopRuntimeAdapter with shop-owned persistence and security controls.
    """

    def __init__(self) -> None:
        self._tokens: dict[str, tuple[str, datetime]] = {}
        self._agent_tokens: dict[str, tuple[str, datetime]] = {}
        self._agent_keys: dict[str, dict[str, Any]] = {
            "agent-dev-key": {"agent_id": "agent-dev", "scopes": ["orders:read", "shipping:read", "returns:request"]}
        }
        self._verifications: dict[str, VerificationRecord] = {}
        self._confirmations: dict[str, ConfirmationRecord] = {}
        self._audit: list[dict[str, Any]] = []

    def issue_token(self, *, customer_id: str, method: str, ttl_seconds: int) -> IssuedToken:
        token = f"tok-{customer_id}-{uuid4().hex[:16]}"
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        self._tokens[token] = (customer_id, expires_at)
        return IssuedToken(
            access_token=token,
            token_type="bearer",
            expires_in_seconds=ttl_seconds,
            customer_id=customer_id,
            method=method,
        )

    def resolve_customer(self, token: str) -> str | None:
        row = self._tokens.get(token)
        if not row:
            return None
        customer_id, expires_at = row
        if expires_at <= datetime.now(timezone.utc):
            del self._tokens[token]
            return None
        return customer_id

    def authenticate_agent_key(self, key: str) -> dict[str, Any] | None:
        return self._agent_keys.get(key)

    def issue_agent_token(self, *, agent_id: str, ttl_seconds: int, scopes: list[str]) -> IssuedToken:
        token = f"agt-{agent_id}-{uuid4().hex[:16]}"
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        self._agent_tokens[token] = (agent_id, expires_at)
        return IssuedToken(
            access_token=token,
            token_type="bearer",
            expires_in_seconds=ttl_seconds,
            customer_id=agent_id,
            method="agent_key",
        )

    def resolve_agent(self, token: str) -> str | None:
        row = self._agent_tokens.get(token)
        if not row:
            return None
        agent_id, expires_at = row
        if expires_at <= datetime.now(timezone.utc):
            del self._agent_tokens[token]
            return None
        return agent_id

    def create_customer_verification(self, *, payload: dict[str, Any], ttl_seconds: int) -> VerificationRecord:
        order_id = payload.get("order_id")
        email = payload.get("email")
        phone = payload.get("phone")
        order = get_order(str(order_id)) if order_id else None
        if not order:
            # fallback for compatibility with existing mock flow
            customer_id = "CUST-001"
        else:
            customer_id = order["customer_id"]
        verification_id = f"ver-{uuid4().hex[:16]}"
        accepted_fields = [name for name in ("order_id", "email", "phone", "postal_code", "last_name") if payload.get(name)]
        hint = str(email or phone or customer_id)
        record = VerificationRecord(
            verification_id=verification_id,
            customer_id=customer_id,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
            accepted_fields=accepted_fields,
            channel=payload.get("channel"),
            customer_hint=hint[:4] + "***" if len(hint) > 4 else hint,
        )
        self._verifications[verification_id] = record
        return record

    def consume_customer_verification(self, *, verification_id: str) -> VerificationRecord | None:
        record = self._verifications.get(verification_id)
        if not record:
            return None
        del self._verifications[verification_id]
        if record.expires_at <= datetime.now(timezone.utc):
            return None
        return record

    def create_confirmation(
        self,
        *,
        customer_id: str,
        payload: dict[str, Any],
        ttl_seconds: int,
    ) -> ConfirmationRecord:
        token = f"conf-{uuid4().hex[:16]}"
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
            del self._confirmations[token]
            return None
        # single-use token by contract
        del self._confirmations[token]
        return record

    def append_event(self, event: dict[str, Any]) -> None:
        self._audit.append(dict(event))

    def list_customer_events(self, customer_id: str) -> list[dict[str, Any]]:
        return [row for row in self._audit if row.get("customer_id") == customer_id]
