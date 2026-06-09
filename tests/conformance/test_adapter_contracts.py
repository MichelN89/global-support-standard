from __future__ import annotations

from datetime import datetime, timezone

from gss_provider.mock_adapter import InMemoryShopAdapter
from gss_webshop_shopify.runtime import ShopOwnedRuntimeAdapter


def test_adapter_token_issue_and_resolve() -> None:
    adapter = InMemoryShopAdapter()
    issued = adapter.issue_token(customer_id="CUST-001", method="api_key", ttl_seconds=300)
    assert issued.customer_id == "CUST-001"
    assert adapter.resolve_customer(issued.access_token) == "CUST-001"


def test_adapter_confirmation_single_use() -> None:
    adapter = InMemoryShopAdapter()
    record = adapter.create_confirmation(
        customer_id="CUST-001",
        payload={"order_id": "ORD-1"},
        ttl_seconds=300,
    )
    first = adapter.consume_confirmation(token=record.token, customer_id="CUST-001")
    second = adapter.consume_confirmation(token=record.token, customer_id="CUST-001")
    assert first is not None
    assert second is None


def test_adapter_confirmation_expiry() -> None:
    adapter = InMemoryShopAdapter()
    record = adapter.create_confirmation(
        customer_id="CUST-001",
        payload={"order_id": "ORD-1"},
        ttl_seconds=0,
    )
    assert record.expires_at <= datetime.now(timezone.utc)
    assert adapter.consume_confirmation(token=record.token, customer_id="CUST-001") is None


def test_adapter_audit_append_and_list() -> None:
    adapter = InMemoryShopAdapter()
    adapter.append_event({"customer_id": "CUST-001", "action": "returns initiate"})
    adapter.append_event({"customer_id": "CUST-002", "action": "orders get"})
    rows = adapter.list_customer_events("CUST-001")
    assert len(rows) == 1
    assert rows[0]["action"] == "returns initiate"


def test_adapter_exposes_agent_and_scope_capabilities() -> None:
    adapter = InMemoryShopAdapter()
    agent = adapter.authenticate_agent_key("agent-dev-key")
    assert agent is not None
    issued = adapter.issue_agent_token(agent_id=str(agent["agent_id"]), ttl_seconds=300, scopes=["orders:read"])
    assert adapter.resolve_agent(issued.access_token) == str(agent["agent_id"])
    assert "orders:read" in adapter.resolve_scopes(issued.access_token)


def test_adapter_verification_contract_consumes_single_use() -> None:
    adapter = InMemoryShopAdapter()
    record = adapter.create_customer_verification(payload={"order_id": "ORD-1001", "email": "cust@example.com"}, ttl_seconds=300)
    assert record.verification_id
    first = adapter.consume_customer_verification(verification_id=record.verification_id)
    second = adapter.consume_customer_verification(verification_id=record.verification_id)
    assert first is not None
    assert second is None


def test_shopify_runtime_implements_split_capabilities() -> None:
    runtime = ShopOwnedRuntimeAdapter()
    token = runtime.issue_token(customer_id="cust@example.com", method="api_key", ttl_seconds=60)
    assert runtime.resolve_customer(token.access_token) == "cust@example.com"
    assert runtime.resolve_scopes(token.access_token)
    assert runtime.authenticate_agent_key("missing") is None
