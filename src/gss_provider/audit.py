from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


AUDIT_LOG: list[dict[str, Any]] = []


def log_action(
    *,
    customer_id: str,
    consumer_id: str,
    consumer_type: str,
    consumer_ip: str,
    action: str,
    action_level: str,
    parameters: dict[str, Any],
    result: str,
    protocol_used: str | None = None,
    confirmation_token: str | None = None,
) -> None:
    AUDIT_LOG.append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "customer_id": customer_id,
            "consumer_id": consumer_id,
            "consumer_type": consumer_type,
            "consumer_ip": consumer_ip,
            "action": action,
            "action_level": action_level,
            "parameters": parameters,
            "confirmation_token": confirmation_token,
            "result": result,
            "protocol_used": protocol_used,
        }
    )


def get_customer_audit(customer_id: str) -> list[dict[str, Any]]:
    return [row for row in AUDIT_LOG if row["customer_id"] == customer_id]
