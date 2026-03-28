from __future__ import annotations

from fastapi.testclient import TestClient

from gss_provider.app import create_app
from gss_webshop_shopify.app import create_shopify_app
from gss_webshop_shopify.shopify_client import ShopifyAdminClient


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "GSS-Consumer-Id": "support-squad-ai",
        "GSS-Consumer-Type": "ai_agent",
        "GSS-Version": "1.0",
    }


class _FakeShopifyClient(ShopifyAdminClient):
    def __init__(self) -> None:
        super().__init__(shop_domain="example.myshopify.com", admin_token="token", api_version="2024-10")

    def list_orders(self, *, limit: int = 20, status: str | None = None):  # type: ignore[override]
        return [
            {
                "id": 1001,
                "name": "#1001",
                "created_at": "2026-03-28T10:00:00Z",
                "financial_status": "paid",
                "fulfillment_status": "fulfilled",
                "total_price": "79.99",
                "currency": "EUR",
                "line_items": [{"id": 1, "title": "Headphones", "quantity": 1, "price": "79.99", "sku": "SKU-1"}],
                "customer": {"id": 1234, "email": "c@example.com", "phone": "+31611112222"},
                "shipping_address": {"phone": "+31611112222"},
            }
        ]

    def get_order(self, *, order_id: str):  # type: ignore[override]
        return {
            "id": int(order_id),
            "name": f"#{order_id}",
            "created_at": "2026-03-28T10:00:00Z",
            "financial_status": "paid",
            "fulfillment_status": "fulfilled",
            "total_price": "79.99",
            "currency": "EUR",
            "line_items": [{"id": 1, "title": "Headphones", "quantity": 1, "price": "79.99", "sku": "SKU-1"}],
            "customer": {"id": 1234, "email": "c@example.com", "phone": "+31611112222"},
            "shipping_address": {"phone": "+31611112222"},
            "fulfillments": [{"tracking_company": "PostNL", "tracking_number": "TRK-1", "tracking_url": "https://t"}],
        }


def test_core_provider_requires_auth_context_for_data_calls() -> None:
    client = TestClient(create_app())
    response = client.get("/v1/orders")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_core_provider_validates_resource_identifiers() -> None:
    client = TestClient(create_app())
    token = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "CUST-001"}).json()["data"]["access_token"]
    headers = _headers(token)
    bad_order = client.get("/v1/orders/ORD.1001", headers=headers)
    bad_tracking = client.get("/v1/shipping/track/ORD$1001", headers=headers)
    assert bad_order.status_code == 400
    assert bad_order.json()["error"]["code"] == "VALIDATION_ERROR"
    assert bad_tracking.status_code == 400
    assert bad_tracking.json()["error"]["code"] == "VALIDATION_ERROR"


def test_shopify_provider_enforces_customer_ownership() -> None:
    client = TestClient(create_shopify_app(client=_FakeShopifyClient()))
    token = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "other@example.com"}).json()["data"]["access_token"]
    headers = _headers(token)
    order = client.get("/v1/orders/1001", headers=headers)
    tracking = client.get("/v1/shipping/track/1001", headers=headers)
    assert order.status_code == 403
    assert order.json()["error"]["code"] == "FORBIDDEN"
    assert tracking.status_code == 403
    assert tracking.json()["error"]["code"] == "FORBIDDEN"
