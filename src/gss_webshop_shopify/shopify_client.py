from __future__ import annotations

from typing import Any

import httpx


class ShopifyAdminClient:
    def __init__(self, *, shop_domain: str, admin_token: str, api_version: str) -> None:
        self.shop_domain = shop_domain
        self.admin_token = admin_token
        self.api_version = api_version

    @property
    def configured(self) -> bool:
        return bool(self.shop_domain and self.admin_token)

    @property
    def _base_url(self) -> str:
        return f"https://{self.shop_domain}/admin/api/{self.api_version}"

    def _headers(self) -> dict[str, str]:
        return {
            "X-Shopify-Access-Token": self.admin_token,
            "Content-Type": "application/json",
        }

    def list_orders(self, *, limit: int = 20, status: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "status": "any",
            "limit": max(1, min(limit, 50)),
            "fields": (
                "id,name,created_at,financial_status,fulfillment_status,total_price,currency,"
                "line_items,customer,shipping_address"
            ),
        }
        if status:
            params["fulfillment_status"] = status
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(f"{self._base_url}/orders.json", headers=self._headers(), params=params)
        resp.raise_for_status()
        return resp.json().get("orders", [])

    def get_order(self, *, order_id: str) -> dict[str, Any] | None:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(
                f"{self._base_url}/orders/{order_id}.json",
                headers=self._headers(),
                params={
                    "fields": (
                        "id,name,created_at,financial_status,fulfillment_status,total_price,currency,"
                        "line_items,customer,shipping_address,fulfillments"
                    )
                },
            )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json().get("order")


def map_shopify_order(order: dict[str, Any]) -> dict[str, Any]:
    fulfillment = order.get("fulfillment_status") or "pending"
    status_map = {
        "fulfilled": "delivered",
        "partial": "shipped",
        "restocked": "returned",
        "pending": "processing",
        "open": "processing",
        "unfulfilled": "processing",
    }
    items = [
        {
            "id": str(item.get("id")),
            "name": item.get("title"),
            "quantity": item.get("quantity", 1),
            "price": float(item.get("price", 0)),
            "sku": item.get("sku"),
        }
        for item in order.get("line_items", [])
    ]
    customer = order.get("customer") or {}
    default_address = customer.get("default_address") or {}
    shipping_address = order.get("shipping_address") or {}
    customer_phone = customer.get("phone") or default_address.get("phone") or shipping_address.get("phone")

    return {
        "id": str(order.get("id")),
        "name": order.get("name"),
        "status": status_map.get(fulfillment, "processing"),
        "created_at": order.get("created_at"),
        "currency": order.get("currency"),
        "total_price": float(order.get("total_price", 0)),
        "items": items,
        "customer_id": str(customer.get("id")) if customer.get("id") else None,
        "customer_email": customer.get("email"),
        "customer_phone": customer_phone,
    }
