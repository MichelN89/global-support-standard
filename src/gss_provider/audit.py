from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from gss_provider.contracts import ShopRuntimeAdapter


def log_action(
    store: ShopRuntimeAdapter,
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
    store.append_event(
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


def get_customer_audit(store: ShopRuntimeAdapter, customer_id: str) -> list[dict[str, Any]]:
    return store.list_customer_events(customer_id)
