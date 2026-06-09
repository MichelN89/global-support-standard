"""Shared shop-intent definition.

The ``intent`` block tells a consumer (especially an AI agent) what GSS is — and
is not — for, how to start, and which actions are off-limits to agents. It lives
in ``gss_core`` so every GSS implementation (the reference provider and the
managed backend) surfaces the *same* intent from one source of truth.
"""

from __future__ import annotations

from gss_core.actions import ai_agent_blocked_actions

DEFAULT_SUMMARY = (
    "GSS handles post-purchase customer support self-service on behalf of an "
    "authenticated customer."
)

DEFAULT_IN_SCOPE: tuple[str, ...] = (
    "order status and history",
    "returns, refunds and exchanges",
    "shipping and delivery issues",
    "account, subscription and loyalty management",
    "warranty claims on existing orders",
    "reading the shop's resolution protocols",
    "escalating to a human when self-service cannot resolve the request",
)

DEFAULT_OUT_OF_SCOPE: tuple[str, ...] = (
    "browsing, search or product recommendations",
    "placing new orders or shopping",
    "payments not tied to an existing order",
    "actions requiring human-only identity proof",
)

DEFAULT_FIRST_STEPS: tuple[str, ...] = (
    "GET /v1/describe to discover capabilities and this intent",
    "auth verify-customer -> auth issue-token to obtain a customer token",
    "then call domain actions; consult protocols get for the right workflow",
    "support escalate when self-service cannot resolve the request",
)


def default_shop_intent(
    *,
    summary: str | None = None,
    in_scope: tuple[str, ...] | list[str] | None = None,
    out_of_scope: tuple[str, ...] | list[str] | None = None,
    first_steps: tuple[str, ...] | list[str] | None = None,
) -> dict[str, object]:
    """Build the intent block, allowing a shop to override the human-readable parts.

    ``ai_agent_blocked_actions`` is always derived from the shared action
    registry so it can never drift from the actual action contract.
    """
    return {
        "summary": summary or DEFAULT_SUMMARY,
        "in_scope": list(in_scope if in_scope is not None else DEFAULT_IN_SCOPE),
        "out_of_scope": list(out_of_scope if out_of_scope is not None else DEFAULT_OUT_OF_SCOPE),
        "first_steps": list(first_steps if first_steps is not None else DEFAULT_FIRST_STEPS),
        "consumer_constraints": {
            "requires_customer_auth_for_data": True,
            "ai_agent_blocked_actions": ai_agent_blocked_actions(),
        },
    }
