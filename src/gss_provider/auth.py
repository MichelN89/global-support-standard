from __future__ import annotations

import uuid

from gss_core.errors import err
from gss_core.models import ConsumerType
from gss_provider.contracts import AuthContext, ShopRuntimeAdapter


def detect_auth_state(
    *,
    authorization: str | None,
    gss_agent_key: str | None,
) -> str:
    if gss_agent_key:
        return "agent"
    if not authorization or not authorization.startswith("Bearer "):
        return "none"
    token = authorization.replace("Bearer ", "", 1).strip()
    if token.startswith("agt-"):
        return "agent"
    if token.startswith("tok-"):
        return "customer"
    return "customer"


def parse_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise err("UNAUTHORIZED", "Missing or invalid Authorization header", status_code=401)
    token = authorization.replace("Bearer ", "", 1).strip()
    if not token:
        raise err("UNAUTHORIZED", "Missing bearer token", status_code=401)
    return token


def validate_headers(
    *,
    adapter: ShopRuntimeAdapter,
    authorization: str | None,
    consumer_id: str | None,
    consumer_type: str | None,
    gss_version: str | None,
    request_id: str | None,
    gss_agent_key: str | None = None,
) -> AuthContext:
    auth_state = detect_auth_state(authorization=authorization, gss_agent_key=gss_agent_key)
    if auth_state != "customer":
        raise err("UNAUTHORIZED", "Customer authentication is required for this endpoint", status_code=401)
    token = parse_token(authorization)
    customer_id = adapter.resolve_customer(token)
    if not customer_id:
        raise err("UNAUTHORIZED", "Unknown or expired token", status_code=401)
    if not consumer_id or not consumer_type or not gss_version:
        raise err(
            "MISSING_HEADERS",
            "Required GSS headers are missing",
            status_code=400,
            details={
                "required": ["GSS-Consumer-Id", "GSS-Consumer-Type", "GSS-Version"],
            },
        )
    try:
        c_type = ConsumerType(consumer_type)
    except ValueError as exc:
        raise err("INVALID_CONSUMER_TYPE", "Unsupported GSS-Consumer-Type", status_code=400) from exc
    rid = request_id or f"req-{uuid.uuid4().hex}"
    return AuthContext(
        customer_id=customer_id,
        token=token,
        consumer_id=consumer_id,
        consumer_type=c_type,
        request_id=rid,
    )


def redact_token(token: str | None) -> str | None:
    if not token:
        return None
    if len(token) <= 8:
        return "***"
    return f"{token[:4]}...{token[-4:]}"
