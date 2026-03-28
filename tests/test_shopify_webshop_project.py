from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from gss_webshop_shopify.app import create_shopify_app
from gss_webshop_shopify.settings import ShopifyProviderSettings
from gss_webshop_shopify.shopify_client import ShopifyAdminClient


class FakeShopifyClient(ShopifyAdminClient):
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
                "customer": {
                    "id": 1234,
                    "email": "c@example.com",
                    "phone": "+31611112222",
                    "default_address": {"phone": "+31611112222"},
                },
                "shipping_address": {"phone": "+31611112222"},
            }
        ]

    def get_order(self, *, order_id: str):  # type: ignore[override]
        if order_id == "404":
            return None
        return {
            "id": int(order_id),
            "name": f"#{order_id}",
            "created_at": "2026-03-28T10:00:00Z",
            "financial_status": "paid",
            "fulfillment_status": "fulfilled",
            "total_price": "79.99",
            "currency": "EUR",
            "line_items": [{"id": 1, "title": "Headphones", "quantity": 1, "price": "79.99", "sku": "SKU-1"}],
            "customer": {
                "id": 1234,
                "email": "c@example.com",
                "phone": "+31611112222",
                "default_address": {"phone": "+31611112222"},
            },
            "shipping_address": {"phone": "+31611112222"},
            "fulfillments": [{"tracking_company": "PostNL", "tracking_number": "TRK-1", "tracking_url": "https://t"}],
        }


class UnauthorizedShopifyClient(ShopifyAdminClient):
    def __init__(self) -> None:
        super().__init__(shop_domain="example.myshopify.com", admin_token="token", api_version="2024-10")

    def list_orders(self, *, limit: int = 20, status: str | None = None):  # type: ignore[override]
        request = httpx.Request("GET", "https://example.myshopify.com/admin/api/2024-10/orders.json")
        response = httpx.Response(401, request=request)
        raise httpx.HTTPStatusError("Unauthorized", request=request, response=response)


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "GSS-Consumer-Id": "support-squad-ai",
        "GSS-Consumer-Type": "ai_agent",
        "GSS-Version": "1.0",
    }


def test_shopify_describe_has_compliance() -> None:
    app = create_shopify_app()
    client = TestClient(app)
    res = client.get("/v1/describe")
    assert res.status_code == 200
    payload = res.json()["data"]
    assert "authorization" in payload
    assert "orders:read" in payload["authorization"]["gss_scopes_supported"]
    assert "compliance" in payload
    assert "certified" in payload["compliance"]


def test_shopify_orders_list_and_not_supported_actions() -> None:
    settings = ShopifyProviderSettings(
        endpoint="http://127.0.0.1:8010/v1",
        host="127.0.0.1",
        port=8010,
        debug=False,
        shop_name="Test Store",
        shop_domain="example.myshopify.com",
        admin_token="token",
        api_version="2024-10",
        token_ttl_seconds=3600,
        compliance_level="basic",
        certified=False,
        test_suite_version="unverified",
    )
    app = create_shopify_app(settings=settings, client=FakeShopifyClient())
    client = TestClient(app)
    token = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "c@example.com"}).json()["data"]["access_token"]

    orders = client.get("/v1/orders", headers=_headers(token))
    assert orders.status_code == 200
    assert len(orders.json()["data"]) == 1

    account = client.get("/v1/account/get")
    assert account.status_code == 501
    assert account.json()["error"]["code"] == "ACTION_NOT_SUPPORTED"


def test_shopify_upstream_unauthorized_is_mapped() -> None:
    settings = ShopifyProviderSettings(
        endpoint="http://127.0.0.1:8010/v1",
        host="127.0.0.1",
        port=8010,
        debug=False,
        shop_name="Test Store",
        shop_domain="example.myshopify.com",
        admin_token="token",
        api_version="2024-10",
        token_ttl_seconds=3600,
        compliance_level="basic",
        certified=False,
        test_suite_version="unverified",
    )
    app = create_shopify_app(settings=settings, client=UnauthorizedShopifyClient())
    client = TestClient(app)
    token = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "c@example.com"}).json()["data"]["access_token"]
    res = client.get("/v1/orders", headers=_headers(token))
    assert res.status_code == 502
    assert res.json()["error"]["code"] == "UPSTREAM_AUTH_ERROR"


def test_shopify_rejects_unscoped_customer_identity() -> None:
    app = create_shopify_app(client=FakeShopifyClient())
    client = TestClient(app)
    res = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "CUST-1"})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "INVALID_CUSTOMER_ID"


def test_shopify_forbids_cross_customer_order_and_tracking_access() -> None:
    settings = ShopifyProviderSettings(
        endpoint="http://127.0.0.1:8010/v1",
        host="127.0.0.1",
        port=8010,
        debug=False,
        shop_name="Test Store",
        shop_domain="example.myshopify.com",
        admin_token="token",
        api_version="2024-10",
        token_ttl_seconds=3600,
        compliance_level="basic",
        certified=False,
        test_suite_version="unverified",
    )
    app = create_shopify_app(settings=settings, client=FakeShopifyClient())
    client = TestClient(app)
    # FakeShopifyClient orders belong to c@example.com
    token = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "other@example.com"}).json()["data"]["access_token"]

    order = client.get("/v1/orders/1001", headers=_headers(token))
    assert order.status_code == 403
    assert order.json()["error"]["code"] == "FORBIDDEN"

    tracking = client.get("/v1/shipping/track/1001", headers=_headers(token))
    assert tracking.status_code == 403
    assert tracking.json()["error"]["code"] == "FORBIDDEN"


def test_shopify_rejects_invalid_order_id_for_get_and_tracking() -> None:
    app = create_shopify_app(client=FakeShopifyClient())
    client = TestClient(app)
    token = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "c@example.com"}).json()["data"]["access_token"]

    bad_get = client.get("/v1/orders/ORD.1001", headers=_headers(token))
    assert bad_get.status_code == 400
    assert bad_get.json()["error"]["code"] == "VALIDATION_ERROR"

    bad_tracking = client.get("/v1/shipping/track/ORD$1001", headers=_headers(token))
    assert bad_tracking.status_code == 400
    assert bad_tracking.json()["error"]["code"] == "VALIDATION_ERROR"


def test_shopify_verify_customer_then_issue_token_flow() -> None:
    app = create_shopify_app(client=FakeShopifyClient())
    client = TestClient(app)

    verify = client.post(
        "/v1/auth/verify-customer",
        json={"order_id": "1001", "email": "c@example.com"},
    )
    assert verify.status_code == 200
    data = verify.json()["data"]
    assert data["status"] == "verified"
    verification_id = data["verification_id"]

    issue = client.post(
        "/v1/auth/issue-token",
        json={"verification_id": verification_id, "method": "api_key"},
    )
    assert issue.status_code == 200
    token = issue.json()["data"]["access_token"]
    assert issue.json()["data"]["issued_via"] == "verify_customer"

    orders = client.get("/v1/orders", headers=_headers(token))
    assert orders.status_code == 200
    assert len(orders.json()["data"]) == 1


def test_shopify_verify_customer_recovery_phone_path() -> None:
    app = create_shopify_app(client=FakeShopifyClient())
    client = TestClient(app)
    verify = client.post(
        "/v1/auth/verify-customer",
        json={"phone": "+31 6 1111 2222"},
    )
    assert verify.status_code == 200
    assert verify.json()["data"]["status"] == "verified_via_phone_recovery"


def test_shopify_issue_token_rejects_reused_verification_id() -> None:
    app = create_shopify_app(client=FakeShopifyClient())
    client = TestClient(app)
    verify = client.post(
        "/v1/auth/verify-customer",
        json={"order_id": "1001", "email": "c@example.com"},
    ).json()
    verification_id = verify["data"]["verification_id"]

    first = client.post("/v1/auth/issue-token", json={"verification_id": verification_id, "method": "api_key"})
    assert first.status_code == 200
    second = client.post("/v1/auth/issue-token", json={"verification_id": verification_id, "method": "api_key"})
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "INVALID_VERIFICATION_ID"
