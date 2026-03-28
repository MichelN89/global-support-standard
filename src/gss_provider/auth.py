from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

from gss_core.errors import err
from gss_core.models import ConsumerType


@dataclass
class AuthContext:
    customer_id: str
    token: str
    consumer_id: str
    consumer_type: ConsumerType
    request_id: str


TOKENS: dict[str, str] = {}


def issue_token(customer_id: str) -> str:
    token = f"tok-{customer_id}-{uuid.uuid4().hex[:10]}"
    TOKENS[token] = customer_id
    return token


def parse_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise err("UNAUTHORIZED", "Missing or invalid Authorization header", status_code=401)
    token = authorization.replace("Bearer ", "", 1).strip()
    if token not in TOKENS:
        raise err("UNAUTHORIZED", "Unknown or expired token", status_code=401)
    return token


def validate_headers(
    *,
    authorization: str | None,
    consumer_id: str | None,
    consumer_type: str | None,
    gss_version: str | None,
    request_id: str | None,
) -> AuthContext:
    token = parse_token(authorization)
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
        customer_id=TOKENS[token],
        token=token,
        consumer_id=consumer_id,
        consumer_type=c_type,
        request_id=rid,
    )


def endpoint_from_env() -> str:
    return os.getenv("GSS_PROVIDER_ENDPOINT", "http://127.0.0.1:8000/v1")
