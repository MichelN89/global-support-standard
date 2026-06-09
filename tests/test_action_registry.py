from __future__ import annotations

from gss_core.actions import (
    ActionLevel,
    action_by_path,
    ai_agent_blocked_actions,
    all_actions,
    domains,
    scope_for,
)


def test_every_action_has_purpose_and_valid_risk() -> None:
    for action in all_actions():
        assert action.purpose.strip(), f"{action.key} has no purpose"
        assert isinstance(action.risk, ActionLevel)


def test_prerequisites_and_next_reference_real_actions() -> None:
    keys = {a.key for a in all_actions()}
    for action in all_actions():
        for ref in (*action.prerequisites, *action.next):
            assert ref in keys, f"{action.key} references unknown action '{ref}'"


def test_scope_derivation_matches_levels() -> None:
    # read -> domain:read, request/critical -> domain:request, auth -> None.
    cases = {
        "orders.get": "orders:read",
        "orders.cancel": "orders:request",
        "returns.check-eligibility": "returns:read",  # read-level despite POST
        "account.change-email": "account:request",  # critical risk, request-namespace scope
        "support.escalate": "support:request",
        "auth.issue-token": None,  # auth actions are never scope-enforced
    }
    by_key = {a.key: a for a in all_actions()}
    for key, expected in cases.items():
        assert scope_for(by_key[key]) == expected, key


def test_action_by_path_prefers_literal_over_placeholder() -> None:
    assert action_by_path("POST", "/v1/orders/cancel").key == "orders.cancel"
    assert action_by_path("GET", "/v1/orders/ORD-1001").key == "orders.get"
    assert action_by_path("POST", "/v1/subscriptions/SUB-1/pause").key == "subscriptions.pause"
    assert action_by_path("DELETE", "/v1/account/addresses/ADDR-1").key == "account.addresses-delete"
    assert action_by_path("GET", "/v1/unknown/thing") is None


def test_products_domain_is_gone_and_support_exists() -> None:
    assert "products" not in domains()
    assert "support" in domains()


def test_ai_agent_blocked_includes_critical_account_actions() -> None:
    blocked = ai_agent_blocked_actions()
    assert "account.change-email" in blocked
    assert "account.delete-request" in blocked
    # A normal read action must never be blocked.
    assert "orders.get" not in blocked
