from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from gss_provider.app import app, create_app
from gss_provider.contracts import ConfirmationRecord, IssuedToken
from gss_provider.mock_adapter import InMemoryShopAdapter
from gss_provider.settings import ProviderSettings


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
    assert payload["data"]["auth_state"] == "none"
    assert "domains" not in payload["data"]


def test_describe_shop_with_agent_header_returns_full_metadata() -> None:
    client = TestClient(app)
    response = client.get("/v1/describe", headers={"GSS-Agent-Key": "agent-dev-key"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["auth_state"] == "agent"
    assert "orders" in payload["data"]["domains"]
    assert "channels" in payload["data"]
    assert "consumer_policies" in payload["data"]


def test_orders_for_authenticated_customer() -> None:
    client = TestClient(app)
    auth = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "CUST-001"}).json()
    token = auth["data"]["access_token"]
    response = client.get("/v1/orders", headers=_auth_headers(token))
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert len(payload["data"]) >= 1


def test_auth_verify_then_issue_token() -> None:
    client = TestClient(app)
    verify = client.post(
        "/v1/auth/verify-customer",
        json={"order_id": "ORD-1001", "email": "cust@example.com", "channel": "web"},
    )
    assert verify.status_code == 200
    verification_id = verify.json()["data"]["verification_id"]
    assert verify.json()["meta"]["channel"] == "web"

    issue = client.post("/v1/auth/issue-token", json={"verification_id": verification_id, "method": "api_key"})
    assert issue.status_code == 200
    payload = issue.json()["data"]
    assert payload["access_token"].startswith("tok-")
    assert payload["customer_id"] == "CUST-001"


def test_auth_agent_success_and_failure() -> None:
    client = TestClient(app)
    bad = client.post("/v1/auth/agent", json={"key": "wrong"})
    assert bad.status_code == 401
    good = client.post("/v1/auth/agent", json={"key": "agent-dev-key"})
    assert good.status_code == 200
    assert good.json()["data"]["access_token"].startswith("agt-")


def test_forbidden_cross_customer_order_access() -> None:
    client = TestClient(app)
    auth = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "CUST-001"}).json()
    token = auth["data"]["access_token"]
    response = client.get("/v1/orders/ORD-2001", headers=_auth_headers(token))
    assert response.status_code == 403
    payload = response.json()
    assert payload["error"]["code"] == "FORBIDDEN"


def test_invalid_order_id_rejected_for_get_and_tracking() -> None:
    client = TestClient(app)
    auth = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "CUST-001"}).json()
    token = auth["data"]["access_token"]
    headers = _auth_headers(token)

    bad_get = client.get("/v1/orders/ORD.1001", headers=headers)
    assert bad_get.status_code == 400
    assert bad_get.json()["error"]["code"] == "VALIDATION_ERROR"

    bad_track = client.get("/v1/shipping/track/ORD$1001", headers=headers)
    assert bad_track.status_code == 400
    assert bad_track.json()["error"]["code"] == "VALIDATION_ERROR"


def test_channel_routing_and_wrong_channel_behavior() -> None:
    client = TestClient(app)
    auth = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "CUST-001"}).json()
    token = auth["data"]["access_token"]
    headers = _auth_headers(token)
    headers["GSS-Channel"] = "email"
    ok_track = client.get("/v1/shipping/track/ORD-1002", headers=headers)
    assert ok_track.status_code == 200
    assert ok_track.json()["meta"]["channel"] == "email"
    wrong_channel = client.get("/v1/orders/ORD-1001", headers=headers)
    assert wrong_channel.status_code == 404


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


def test_confirmation_token_single_use() -> None:
    client = TestClient(app)
    token = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "CUST-001"}).json()["data"]["access_token"]
    headers = _auth_headers(token)

    initiate = client.post(
        "/v1/returns/initiate",
        headers=headers,
        json={"order_id": "ORD-1001", "item_id": "ITEM-1", "reason": "defective"},
    )
    confirmation_token = initiate.json()["data"]["confirmation_token"]

    first_confirm = client.post("/v1/returns/confirm", headers=headers, json={"token": confirmation_token})
    assert first_confirm.status_code == 200

    second_confirm = client.post("/v1/returns/confirm", headers=headers, json={"token": confirmation_token})
    assert second_confirm.status_code == 400
    assert second_confirm.json()["error"]["code"] == "INVALID_CONFIRMATION_TOKEN"


def test_expired_token_rejected_with_short_ttl() -> None:
    test_app = create_app(
        settings=ProviderSettings(
            protocol_dir=Path.cwd() / "protocols",
            endpoint="http://127.0.0.1:8000/v1",
            host="127.0.0.1",
            port=8000,
            debug=False,
            token_ttl_seconds=0,
            confirmation_ttl_seconds=900,
            compliance_level="basic",
            certified=False,
            test_suite_version="unverified",
        ),
        adapter=InMemoryShopAdapter(),
    )
    client = TestClient(test_app)
    token = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "CUST-001"}).json()["data"]["access_token"]
    response = client.get("/v1/orders", headers=_auth_headers(token))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_expired_confirmation_rejected_with_short_ttl() -> None:
    test_app = create_app(
        settings=ProviderSettings(
            protocol_dir=Path.cwd() / "protocols",
            endpoint="http://127.0.0.1:8000/v1",
            host="127.0.0.1",
            port=8000,
            debug=False,
            token_ttl_seconds=3600,
            confirmation_ttl_seconds=0,
            compliance_level="basic",
            certified=False,
            test_suite_version="unverified",
        ),
        adapter=InMemoryShopAdapter(),
    )
    client = TestClient(test_app)
    token = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "CUST-001"}).json()["data"]["access_token"]
    headers = _auth_headers(token)
    initiate = client.post(
        "/v1/returns/initiate",
        headers=headers,
        json={"order_id": "ORD-1001", "item_id": "ITEM-1", "reason": "defective"},
    )
    confirmation_token = initiate.json()["data"]["confirmation_token"]
    confirm = client.post("/v1/returns/confirm", headers=headers, json={"token": confirmation_token})
    assert confirm.status_code == 400
    assert confirm.json()["error"]["code"] == "INVALID_CONFIRMATION_TOKEN"


def test_protocol_trigger_path_traversal_rejected() -> None:
    client = TestClient(app)
    token = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "CUST-001"}).json()["data"]["access_token"]
    response = client.post(
        "/v1/protocols/get",
        headers=_auth_headers(token),
        json={"trigger": "../secrets", "context": {"order_id": "ORD-1001"}},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_provider_uses_injected_shop_adapter_contracts() -> None:
    class RecordingAdapter(InMemoryShopAdapter):
        def __init__(self) -> None:
            super().__init__()
            self.issued = 0
            self.created_conf = 0
            self.consumed_conf = 0
            self.appended_audit = 0

        def issue_token(self, *, customer_id: str, method: str, ttl_seconds: int) -> IssuedToken:
            self.issued += 1
            return super().issue_token(customer_id=customer_id, method=method, ttl_seconds=ttl_seconds)

        def create_confirmation(
            self,
            *,
            customer_id: str,
            payload: dict,
            ttl_seconds: int,
        ) -> ConfirmationRecord:
            self.created_conf += 1
            return super().create_confirmation(customer_id=customer_id, payload=payload, ttl_seconds=ttl_seconds)

        def consume_confirmation(self, *, token: str, customer_id: str) -> ConfirmationRecord | None:
            self.consumed_conf += 1
            return super().consume_confirmation(token=token, customer_id=customer_id)

        def append_event(self, event: dict) -> None:
            self.appended_audit += 1
            super().append_event(event)

    adapter = RecordingAdapter()
    test_app = create_app(
        settings=ProviderSettings(
            protocol_dir=Path.cwd() / "protocols",
            endpoint="http://127.0.0.1:8000/v1",
            host="127.0.0.1",
            port=8000,
            debug=False,
            token_ttl_seconds=3600,
            confirmation_ttl_seconds=900,
            compliance_level="basic",
            certified=False,
            test_suite_version="unverified",
        ),
        adapter=adapter,
    )
    client = TestClient(test_app)

    auth = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "CUST-001"})
    token = auth.json()["data"]["access_token"]
    headers = _auth_headers(token)
    start = client.post(
        "/v1/returns/initiate",
        headers=headers,
        json={"order_id": "ORD-1001", "item_id": "ITEM-1", "reason": "defective"},
    ).json()
    client.post("/v1/returns/confirm", headers=headers, json={"token": start["data"]["confirmation_token"]})

    assert adapter.issued >= 1
    assert adapter.created_conf >= 1
    assert adapter.consumed_conf >= 1
    assert adapter.appended_audit >= 2
