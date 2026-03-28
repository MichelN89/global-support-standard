from __future__ import annotations

from fastapi.testclient import TestClient

from gss_provider.app import app


def _auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "GSS-Consumer-Id": "support-squad-ai",
        "GSS-Consumer-Type": "ai_agent",
        "GSS-Version": "1.0",
        "GSS-Request-Id": "req-test",
    }


def test_describe_shop() -> None:
    client = TestClient(app)
    response = client.get("/v1/describe")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "orders" in payload["data"]["domains"]


def test_orders_for_authenticated_customer() -> None:
    client = TestClient(app)
    auth = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "CUST-001"}).json()
    token = auth["data"]["access_token"]
    response = client.get("/v1/orders", headers=_auth_headers(token))
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert len(payload["data"]) >= 1


def test_forbidden_cross_customer_order_access() -> None:
    client = TestClient(app)
    auth = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "CUST-001"}).json()
    token = auth["data"]["access_token"]
    response = client.get("/v1/orders/ORD-2001", headers=_auth_headers(token))
    assert response.status_code == 403
    payload = response.json()
    assert payload["error"]["code"] == "FORBIDDEN"


def test_returns_initiate_then_confirm() -> None:
    client = TestClient(app)
    auth = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "CUST-001"}).json()
    token = auth["data"]["access_token"]
    headers = _auth_headers(token)

    initiate = client.post(
        "/v1/returns/initiate",
        headers=headers,
        json={"order_id": "ORD-1001", "item_id": "ITEM-1", "reason": "defective"},
    )
    assert initiate.status_code == 200
    init_payload = initiate.json()["data"]
    assert init_payload["status"] == "pending_confirmation"
    confirmation_token = init_payload["confirmation_token"]

    confirm = client.post("/v1/returns/confirm", headers=headers, json={"token": confirmation_token})
    assert confirm.status_code == 200
    assert confirm.json()["data"]["status"] == "submitted"


def test_protocol_get_with_context_enrichment() -> None:
    client = TestClient(app)
    auth = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "CUST-001"}).json()
    token = auth["data"]["access_token"]
    response = client.post(
        "/v1/protocols/get",
        headers=_auth_headers(token),
        json={
            "trigger": "delivery-not-received",
            "context": {"order_id": "ORD-1002", "days_since_expected": 1},
        },
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["context_received"]["order_id"] == "ORD-1002"
    assert "carrier" in payload["context_enriched"]


def test_missing_headers_rejected() -> None:
    client = TestClient(app)
    auth = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "CUST-001"}).json()
    token = auth["data"]["access_token"]
    response = client.get("/v1/orders", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MISSING_HEADERS"
