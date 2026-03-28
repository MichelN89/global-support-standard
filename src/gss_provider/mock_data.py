from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

ORDERS: list[dict[str, Any]] = [
    {
        "id": "ORD-1001",
        "customer_id": "CUST-001",
        "status": "delivered",
        "created_at": "2026-03-20T10:00:00Z",
        "expected_delivery": "2026-03-24T12:00:00Z",
        "items": [
            {"id": "ITEM-1", "name": "Wireless Headphones", "quantity": 1, "price": 79.99},
            {"id": "ITEM-2", "name": "USB-C Cable", "quantity": 2, "price": 9.99},
        ],
        "shipping": {
            "carrier": "PostNL",
            "tracking_number": "TRK-POSTNL-1001",
            "last_event": "delivered",
        },
    },
    {
        "id": "ORD-1002",
        "customer_id": "CUST-001",
        "status": "shipped",
        "created_at": "2026-03-25T10:00:00Z",
        "expected_delivery": "2026-03-29T12:00:00Z",
        "items": [
            {"id": "ITEM-3", "name": "Mechanical Keyboard", "quantity": 1, "price": 129.99},
        ],
        "shipping": {
            "carrier": "DHL",
            "tracking_number": "TRK-DHL-1002",
            "last_event": "in_transit",
        },
    },
    {
        "id": "ORD-2001",
        "customer_id": "CUST-002",
        "status": "delivered",
        "created_at": "2026-03-10T10:00:00Z",
        "expected_delivery": "2026-03-15T12:00:00Z",
        "items": [
            {"id": "ITEM-X", "name": "Smart Lamp", "quantity": 1, "price": 49.99},
        ],
        "shipping": {
            "carrier": "UPS",
            "tracking_number": "TRK-UPS-2001",
            "last_event": "delivered",
        },
    },
]


def list_orders(customer_id: str, status: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    rows = [deepcopy(o) for o in ORDERS if o["customer_id"] == customer_id]
    if status:
        rows = [r for r in rows if r["status"] == status]
    return rows[: max(1, min(limit, 100))]


def get_order(order_id: str) -> dict[str, Any] | None:
    for order in ORDERS:
        if order["id"] == order_id:
            return deepcopy(order)
    return None


def owns_order(customer_id: str, order_id: str) -> bool:
    order = get_order(order_id)
    return bool(order and order["customer_id"] == customer_id)


def return_eligibility(order_id: str, item_id: str) -> dict[str, Any]:
    order = get_order(order_id)
    if not order:
        return {"eligible": False, "reason": "ORDER_NOT_FOUND"}
    item = next((i for i in order["items"] if i["id"] == item_id), None)
    if not item:
        return {"eligible": False, "reason": "ITEM_NOT_FOUND"}
    if order["status"] != "delivered":
        return {"eligible": False, "reason": "ORDER_NOT_DELIVERED"}
    return {"eligible": True, "window_days": 30, "refund_method": "original_payment_method"}


def enriched_context(order_id: str | None) -> dict[str, Any]:
    if not order_id:
        return {}
    order = get_order(order_id)
    if not order:
        return {}
    expected = datetime.fromisoformat(order["expected_delivery"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    days_since_expected = max(0, int((now - expected).total_seconds() // 86400))
    return {
        "order_id": order["id"],
        "order_status": order["status"],
        "order_value": round(sum(i["price"] * i["quantity"] for i in order["items"]), 2),
        "carrier": order["shipping"]["carrier"],
        "last_tracking_event": order["shipping"]["last_event"],
        "days_since_expected": days_since_expected,
    }
