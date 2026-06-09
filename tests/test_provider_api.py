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


def test_auth_verify_customer_unknown_order_fails_closed() -> None:
    client = TestClient(app)
    verify = client.post(
        "/v1/auth/verify-customer",
        json={"order_id": "ORD-9999", "email": "cust@example.com"},
    )
    assert verify.status_code == 400
    assert verify.json()["error"]["code"] == "VERIFICATION_FAILED"


def test_auth_agent_success_and_failure() -> None:
    client = TestClient(app)
    bad = client.post("/v1/auth/agent", json={"key": "wrong"})
    assert bad.status_code == 401
    good = client.post("/v1/auth/agent", json={"key": "agent-dev-key"})
    assert good.status_code == 200
    assert good.json()["data"]["access_token"].startswith("agt-")


def test_auth_agent_disabled_returns_clear_error() -> None:
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
            enable_legacy_login=True,
            enable_agent_auth=False,
        ),
        adapter=InMemoryShopAdapter(),
    )
    client = TestClient(test_app)
    disabled = client.post("/v1/auth/agent", json={"key": "agent-dev-key"})
    assert disabled.status_code == 404
    assert disabled.json()["error"]["code"] == "AGENT_AUTH_DISABLED"


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


def test_orders_request_actions_return_expected_statuses() -> None:
    client = TestClient(app)
    auth = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "CUST-001"}).json()
    token = auth["data"]["access_token"]
    headers = _auth_headers(token)

    cancel = client.post("/v1/orders/cancel", headers=headers, json={"id": "ORD-1001", "reason": "customer_request"})
    assert cancel.status_code == 200
    assert cancel.json()["data"]["status"] == "cancel_requested"

    modify = client.post("/v1/orders/modify", headers=headers, json={"id": "ORD-1001", "changes": {"gift_wrap": True}})
    assert modify.status_code == 200
    assert modify.json()["data"]["status"] == "modification_requested"

    reorder = client.post("/v1/orders/reorder", headers=headers, json={"id": "ORD-1001"})
    assert reorder.status_code == 200
    assert reorder.json()["data"]["status"] == "created"


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
            enable_legacy_login=True,
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
            enable_legacy_login=True,
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


def test_legacy_login_can_be_disabled() -> None:
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
            enable_legacy_login=False,
            enable_agent_auth=False,
        ),
        adapter=InMemoryShopAdapter(),
    )
    client = TestClient(test_app)
    res = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "CUST-001"})
    assert res.status_code == 410
    assert res.json()["error"]["code"] == "LEGACY_AUTH_DISABLED"


def test_scope_enforcement_blocks_missing_scope() -> None:
    class ScopedAdapter(InMemoryShopAdapter):
        def issue_token(self, *, customer_id: str, method: str, ttl_seconds: int) -> IssuedToken:
            issued = super().issue_token(customer_id=customer_id, method=method, ttl_seconds=ttl_seconds)
            row = self._tokens[issued.access_token]
            self._tokens[issued.access_token] = (row[0], row[1], ["orders:read"])
            return issued

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
            enable_legacy_login=True,
            enable_agent_auth=False,
        ),
        adapter=ScopedAdapter(),
    )
    client = TestClient(test_app)
    token = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "CUST-001"}).json()["data"]["access_token"]
    res = client.post(
        "/v1/account/update",
        headers=_auth_headers(token),
        json={"changes": {"phone": "+31600000000"}},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"


def test_rate_limiting_applies_when_enabled() -> None:
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
            rate_limit_enabled=True,
            rate_limit_window_seconds=60,
            rate_limit_data_max_requests=1,
            rate_limit_auth_max_requests=10,
        ),
        adapter=InMemoryShopAdapter(),
    )
    client = TestClient(test_app)
    assert client.get("/v1/describe").status_code == 200
    limited = client.get("/v1/describe")
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"


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
            enable_legacy_login=True,
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


def test_domain_describe_carries_affordance_semantics() -> None:
    client = TestClient(app)
    response = client.get("/v1/returns/describe")
    assert response.status_code == 200
    data = response.json()["data"]
    # Legacy flat command surface is preserved.
    assert isinstance(data["command_strings"], list)
    assert "returns initiate --order-id --item-id --reason [--option]" in data["command_strings"]
    # Enriched objects carry intent/ordering/scope/risk.
    initiate = next(c for c in data["commands"] if c["name"] == "returns initiate")
    assert initiate["purpose"]
    assert initiate["risk"] == "request"
    assert initiate["requires_confirmation"] is True
    assert initiate["scope"] == "returns:request"
    assert "returns.check-eligibility" in initiate["prerequisites"]
    assert "returns.confirm" in initiate["next"]


def test_describe_shop_includes_intent_for_agent() -> None:
    client = TestClient(app)
    payload = client.get("/v1/describe", headers={"GSS-Agent-Key": "agent-dev-key"}).json()["data"]
    intent = payload["intent"]
    assert intent["summary"]
    assert any("return" in s.lower() for s in intent["in_scope"])
    assert any("shop" in s.lower() or "brows" in s.lower() for s in intent["out_of_scope"])
    blocked = intent["consumer_constraints"]["ai_agent_blocked_actions"]
    assert "account.change-email" in blocked
    # Domains are generated from the registry: products gone, support present.
    assert "products" not in payload["domains"]
    assert "support" in payload["domains"]


def test_products_domain_removed() -> None:
    client = TestClient(app)
    # describe surfaces the canonical "domain not supported" 404.
    assert client.get("/v1/products/describe").status_code == 404
    token = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "CUST-001"}).json()["data"]["access_token"]
    # The data route no longer exists and is no longer reachable (no products scope is granted).
    assert client.get("/v1/products/PRD-100", headers=_auth_headers(token)).status_code in (403, 404)


def test_support_escalate_creates_handoff() -> None:
    client = TestClient(app)
    token = client.post("/v1/auth/login", json={"method": "api_key", "customer_id": "CUST-001"}).json()["data"]["access_token"]
    res = client.post(
        "/v1/support/escalate",
        headers=_auth_headers(token),
        json={"reason": "refund not received after 30 days", "context": {"order_id": "ORD-1001"}},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["status"] == "handoff_created"
    assert data["handoff_id"].startswith("handoff-")

    missing = client.post("/v1/support/escalate", headers=_auth_headers(token), json={})
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "VALIDATION_ERROR"
