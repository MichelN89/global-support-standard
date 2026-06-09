"""Central GSS action registry — the single source of truth for the standard.

Every GSS action is defined exactly once here, carrying both the *routing*
binding (HTTP method + path template + scope) and the *semantic/affordance*
metadata (purpose, risk level, confirmation style, prerequisites, next steps,
consumer restrictions). The provider's ``describe`` output, scope enforcement,
and the MCP reference client are all driven from this one table so they can
never drift apart.

This module lives in ``gss_core`` and has no FastAPI/web dependency, so any GSS
implementation (the reference provider, the managed backend, future clients)
can import it as the shared contract.
"""

from __future__ import annotations

from dataclasses import dataclass

from gss_core.models import ActionLevel

# Confirmation idioms used across the standard.
#   "two_step_endpoint": first call returns a confirmation_token; a *separate*
#                        endpoint (e.g. returns confirm) consumes it.
#   "inline_token":      re-invoke the *same* endpoint with a confirm_token.
ConfirmationStyle = str  # "two_step_endpoint" | "inline_token" | None


@dataclass(frozen=True)
class ActionDef:
    domain: str
    action: str
    command: str
    purpose: str
    risk: ActionLevel
    http_method: str
    path_template: str
    requires_confirmation: bool = False
    confirmation_style: ConfirmationStyle | None = None
    consumer_block: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    next: tuple[str, ...] = ()
    scope_override: str | None = None
    enabled_setting: str | None = None  # settings bool that must be true to expose this action

    @property
    def key(self) -> str:
        return f"{self.domain}.{self.action}"

    @property
    def scoped(self) -> bool:
        """Auth actions bypass scope enforcement (they *issue* the token)."""
        return not self.path_template.startswith("/v1/auth/")


def scope_for(action: ActionDef) -> str | None:
    """Required token scope for an action.

    Mirrors the historical derivation exactly: read-level -> ``domain:read``,
    request/critical -> ``domain:request`` (the *risk* level, not the scope,
    gates any extra out-of-band verification for critical actions).
    """
    if not action.scoped:
        return None
    if action.scope_override is not None:
        return action.scope_override
    if action.risk == ActionLevel.READ:
        return f"{action.domain}:read"
    return f"{action.domain}:request"


def _a(**kwargs: object) -> ActionDef:
    return ActionDef(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The registry. Risk levels follow spec/overview.md §3.9 (Action Level
# Classification). Command strings are lifted verbatim from the historical
# describe catalog so the flat command surface is unchanged.
# ---------------------------------------------------------------------------
_AUTH_PRE = ("auth.verify-customer", "auth.issue-token")

ACTIONS: list[ActionDef] = [
    # --- auth (token issuance; never scope-enforced) -----------------------
    _a(domain="auth", action="verify-customer", command="auth verify-customer [...fields]",
       purpose="Verify a customer's identity from order/contact fields to obtain a verification id.",
       risk=ActionLevel.READ, http_method="POST", path_template="/v1/auth/verify-customer"),
    _a(domain="auth", action="issue-token", command="auth issue-token --verification-id",
       purpose="Exchange a verification id for a short-lived customer access token.",
       risk=ActionLevel.READ, http_method="POST", path_template="/v1/auth/issue-token",
       prerequisites=("auth.verify-customer",)),
    _a(domain="auth", action="agent", command="auth agent --key",
       purpose="Authenticate a trusted agent via an agent key (when enabled by the shop).",
       risk=ActionLevel.READ, http_method="POST", path_template="/v1/auth/agent",
       enabled_setting="enable_agent_auth"),
    _a(domain="auth", action="login", command="auth login (deprecated)",
       purpose="Deprecated direct login; disabled by default on secure deployments.",
       risk=ActionLevel.READ, http_method="POST", path_template="/v1/auth/login",
       enabled_setting="enable_legacy_login"),

    # --- orders ------------------------------------------------------------
    _a(domain="orders", action="list", command="orders list [--status] [--since] [--limit]",
       purpose="List the authenticated customer's orders.",
       risk=ActionLevel.READ, http_method="GET", path_template="/v1/orders",
       prerequisites=_AUTH_PRE),
    _a(domain="orders", action="get", command="orders get --id",
       purpose="Get a single order the customer owns.",
       risk=ActionLevel.READ, http_method="GET", path_template="/v1/orders/{order_id}",
       prerequisites=_AUTH_PRE, next=("returns.check-eligibility", "shipping.track", "payments.get")),
    _a(domain="orders", action="cancel", command="orders cancel --id [--reason]",
       purpose="Request cancellation of an order.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/orders/cancel",
       requires_confirmation=True, confirmation_style="inline_token", prerequisites=("orders.get",)),
    _a(domain="orders", action="modify", command="orders modify --id --changes",
       purpose="Request a modification to an order (e.g. gift wrap, address).",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/orders/modify",
       requires_confirmation=True, confirmation_style="inline_token", prerequisites=("orders.get",)),
    _a(domain="orders", action="reorder", command="orders reorder --id",
       purpose="Create a new order replicating a previous one.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/orders/reorder",
       prerequisites=("orders.get",)),

    # --- shipping ----------------------------------------------------------
    _a(domain="shipping", action="track", command="shipping track --order-id",
       purpose="Get live tracking status for an order's shipment.",
       risk=ActionLevel.READ, http_method="GET", path_template="/v1/shipping/track/{order_id}",
       prerequisites=_AUTH_PRE),
    _a(domain="shipping", action="report-issue", command="shipping report-issue --order-id --issue",
       purpose="Report a delivery problem for an order.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/shipping/report-issue",
       prerequisites=("shipping.track",), next=("support.escalate",)),
    _a(domain="shipping", action="change-address", command="shipping change-address --order-id --address",
       purpose="Request a delivery address change for an in-flight order.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/shipping/change-address",
       prerequisites=_AUTH_PRE),
    _a(domain="shipping", action="request-redelivery", command="shipping request-redelivery --order-id [--date]",
       purpose="Request redelivery of a failed delivery.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/shipping/request-redelivery",
       prerequisites=("shipping.track",)),
    _a(domain="shipping", action="delivery-preferences", command="shipping delivery-preferences --set",
       purpose="Set delivery preferences for future shipments.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/shipping/delivery-preferences",
       prerequisites=_AUTH_PRE),

    # --- returns -----------------------------------------------------------
    _a(domain="returns", action="check-eligibility", command="returns check-eligibility --order-id --item-id",
       purpose="Check whether an item is eligible for return before starting one.",
       risk=ActionLevel.READ, http_method="POST", path_template="/v1/returns/check-eligibility",
       prerequisites=("orders.get",), next=("returns.initiate",)),
    _a(domain="returns", action="initiate", command="returns initiate --order-id --item-id --reason [--option]",
       purpose="Start a return for an item and obtain a shipping option summary.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/returns/initiate",
       requires_confirmation=True, confirmation_style="two_step_endpoint",
       prerequisites=("returns.check-eligibility",), next=("returns.confirm", "returns.status")),
    _a(domain="returns", action="confirm", command="returns confirm --token",
       purpose="Confirm a previously initiated return using its confirmation token.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/returns/confirm",
       prerequisites=("returns.initiate",), next=("returns.status",)),
    _a(domain="returns", action="status", command="returns status --return-id",
       purpose="Get the status of an existing return.",
       risk=ActionLevel.READ, http_method="GET", path_template="/v1/returns/{return_id}",
       prerequisites=_AUTH_PRE),
    _a(domain="returns", action="list", command="returns list [--status] [--since]",
       purpose="List the customer's returns.",
       risk=ActionLevel.READ, http_method="GET", path_template="/v1/returns",
       prerequisites=_AUTH_PRE),
    _a(domain="returns", action="cancel", command="returns cancel --return-id",
       purpose="Cancel an in-progress return.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/returns/cancel",
       prerequisites=("returns.status",)),
    _a(domain="returns", action="dispute", command="returns dispute --return-id --reason",
       purpose="Dispute the handling or outcome of a return.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/returns/dispute",
       prerequisites=("returns.status",), next=("support.escalate",)),
    _a(domain="returns", action="request-return-back", command="returns request-return-back --return-id",
       purpose="Request the returned item be shipped back to the customer.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/returns/request-return-back",
       prerequisites=("returns.status",)),
    _a(domain="returns", action="accept-partial", command="returns accept-partial --return-id --option",
       purpose="Accept a partial-refund or partial-return resolution.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/returns/accept-partial",
       requires_confirmation=True, confirmation_style="inline_token", prerequisites=("returns.status",)),

    # --- refunds -----------------------------------------------------------
    _a(domain="refunds", action="list", command="refunds list [--since]",
       purpose="List refunds issued to the customer.",
       risk=ActionLevel.READ, http_method="GET", path_template="/v1/refunds",
       prerequisites=_AUTH_PRE),
    _a(domain="refunds", action="status", command="refunds status --refund-id",
       purpose="Get the status of a specific refund.",
       risk=ActionLevel.READ, http_method="GET", path_template="/v1/refunds/{refund_id}",
       prerequisites=_AUTH_PRE),

    # --- protocols ---------------------------------------------------------
    _a(domain="protocols", action="get", command="protocols get --trigger --context",
       purpose="Resolve the shop's machine-readable support protocol for a situation (the workflow to follow).",
       risk=ActionLevel.READ, http_method="POST", path_template="/v1/protocols/get"),

    # --- account -----------------------------------------------------------
    _a(domain="account", action="get", command="account get",
       purpose="Get the customer's account profile.",
       risk=ActionLevel.READ, http_method="GET", path_template="/v1/account",
       prerequisites=_AUTH_PRE),
    _a(domain="account", action="update", command="account update --changes",
       purpose="Update account fields (name, phone, preferences). Cannot change email.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/account/update",
       prerequisites=_AUTH_PRE),
    _a(domain="account", action="addresses-list", command="account addresses list",
       purpose="List the customer's saved addresses.",
       risk=ActionLevel.READ, http_method="GET", path_template="/v1/account/addresses",
       prerequisites=_AUTH_PRE),
    _a(domain="account", action="addresses-add", command="account addresses add --address",
       purpose="Add a new saved address.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/account/addresses",
       prerequisites=_AUTH_PRE),
    _a(domain="account", action="addresses-update", command="account addresses update --id --changes",
       purpose="Update an existing saved address.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/account/addresses/{address_id}",
       prerequisites=("account.addresses-list",)),
    _a(domain="account", action="addresses-delete", command="account addresses delete --id",
       purpose="Delete a saved address.",
       risk=ActionLevel.REQUEST, http_method="DELETE", path_template="/v1/account/addresses/{address_id}",
       prerequisites=("account.addresses-list",)),
    _a(domain="account", action="change-email", command="account change-email --new-email",
       purpose="Start the standard dual-OTP email change flow.",
       risk=ActionLevel.CRITICAL, http_method="POST", path_template="/v1/account/change-email",
       consumer_block=("ai_agent",), prerequisites=_AUTH_PRE, next=("support.escalate",)),
    _a(domain="account", action="change-email-recover", command="account change-email-recover --new-email",
       purpose="Start the email-change recovery flow (phone + identity + new-email OTP).",
       risk=ActionLevel.CRITICAL, http_method="POST", path_template="/v1/account/change-email-recover",
       consumer_block=("ai_agent",), prerequisites=_AUTH_PRE, next=("support.escalate",)),
    _a(domain="account", action="payment-methods-list", command="account payment-methods list",
       purpose="List saved payment methods.",
       risk=ActionLevel.READ, http_method="GET", path_template="/v1/account/payment-methods",
       prerequisites=_AUTH_PRE),
    _a(domain="account", action="payment-methods-add", command="account payment-methods add --method",
       purpose="Add a payment method (out-of-band OTP required).",
       risk=ActionLevel.CRITICAL, http_method="POST", path_template="/v1/account/payment-methods",
       consumer_block=("ai_agent",), prerequisites=_AUTH_PRE),
    _a(domain="account", action="payment-methods-delete", command="account payment-methods delete --id",
       purpose="Delete a payment method (out-of-band OTP required).",
       risk=ActionLevel.CRITICAL, http_method="DELETE", path_template="/v1/account/payment-methods/{method_id}",
       consumer_block=("ai_agent",), prerequisites=("account.payment-methods-list",)),
    _a(domain="account", action="delete-request", command="account delete-request",
       purpose="Request account deletion (out-of-band OTP required).",
       risk=ActionLevel.CRITICAL, http_method="POST", path_template="/v1/account/delete-request",
       consumer_block=("ai_agent",), prerequisites=_AUTH_PRE, next=("support.escalate",)),
    _a(domain="account", action="export-data", command="account export-data",
       purpose="Export the customer's account data (GDPR portability).",
       risk=ActionLevel.READ, http_method="GET", path_template="/v1/account/export-data",
       prerequisites=_AUTH_PRE),
    _a(domain="account", action="audit-log", command="account audit-log [--since] [--limit]",
       purpose="View the audit log of actions taken on the customer's account.",
       risk=ActionLevel.READ, http_method="GET", path_template="/v1/account/audit-log",
       prerequisites=_AUTH_PRE),

    # --- payments ----------------------------------------------------------
    _a(domain="payments", action="list", command="payments list [--since] [--status]",
       purpose="List payments tied to the customer's orders.",
       risk=ActionLevel.READ, http_method="GET", path_template="/v1/payments",
       prerequisites=_AUTH_PRE),
    _a(domain="payments", action="get", command="payments get --order-id",
       purpose="Get payment details for an order.",
       risk=ActionLevel.READ, http_method="GET", path_template="/v1/payments/{order_id}",
       prerequisites=("orders.get",)),
    _a(domain="payments", action="invoice", command="payments invoice --order-id",
       purpose="Get the invoice for an order's payment.",
       risk=ActionLevel.READ, http_method="GET", path_template="/v1/payments/{order_id}/invoice",
       prerequisites=("orders.get",)),
    _a(domain="payments", action="dispute", command="payments dispute --order-id --reason",
       purpose="Dispute a payment on an order.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/payments/dispute",
       prerequisites=("payments.get",), next=("support.escalate",)),
    _a(domain="payments", action="retry", command="payments retry --order-id",
       purpose="Retry a failed payment on an order.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/payments/retry",
       prerequisites=("payments.get",)),

    # --- subscriptions -----------------------------------------------------
    _a(domain="subscriptions", action="list", command="subscriptions list",
       purpose="List the customer's subscriptions.",
       risk=ActionLevel.READ, http_method="GET", path_template="/v1/subscriptions",
       prerequisites=_AUTH_PRE),
    _a(domain="subscriptions", action="get", command="subscriptions get --id",
       purpose="Get a single subscription.",
       risk=ActionLevel.READ, http_method="GET", path_template="/v1/subscriptions/{subscription_id}",
       prerequisites=_AUTH_PRE),
    _a(domain="subscriptions", action="pause", command="subscriptions pause --id [--until]",
       purpose="Pause a subscription.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/subscriptions/{subscription_id}/pause",
       prerequisites=("subscriptions.get",)),
    _a(domain="subscriptions", action="resume", command="subscriptions resume --id",
       purpose="Resume a paused subscription.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/subscriptions/{subscription_id}/resume",
       prerequisites=("subscriptions.get",)),
    _a(domain="subscriptions", action="cancel", command="subscriptions cancel --id [--reason]",
       purpose="Cancel a subscription.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/subscriptions/{subscription_id}/cancel",
       prerequisites=("subscriptions.get",), next=("support.escalate",)),
    _a(domain="subscriptions", action="modify", command="subscriptions modify --id --changes",
       purpose="Modify a subscription's items or settings.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/subscriptions/{subscription_id}/modify",
       prerequisites=("subscriptions.get",)),
    _a(domain="subscriptions", action="skip-next", command="subscriptions skip-next --id",
       purpose="Skip the next delivery of a subscription.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/subscriptions/{subscription_id}/skip-next",
       prerequisites=("subscriptions.get",)),
    _a(domain="subscriptions", action="change-frequency", command="subscriptions change-frequency --id --cycle",
       purpose="Change a subscription's delivery frequency.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/subscriptions/{subscription_id}/change-frequency",
       prerequisites=("subscriptions.get",)),

    # --- loyalty -----------------------------------------------------------
    _a(domain="loyalty", action="balance", command="loyalty balance",
       purpose="Get the customer's loyalty point balance.",
       risk=ActionLevel.READ, http_method="GET", path_template="/v1/loyalty/balance",
       prerequisites=_AUTH_PRE),
    _a(domain="loyalty", action="history", command="loyalty history [--since] [--limit]",
       purpose="Get loyalty point history.",
       risk=ActionLevel.READ, http_method="GET", path_template="/v1/loyalty/history",
       prerequisites=_AUTH_PRE),
    _a(domain="loyalty", action="redeem", command="loyalty redeem --points --order-id",
       purpose="Redeem loyalty points against an order.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/loyalty/redeem",
       requires_confirmation=True, confirmation_style="inline_token", prerequisites=("loyalty.balance",)),
    _a(domain="loyalty", action="rewards-list", command="loyalty rewards list",
       purpose="List available loyalty rewards.",
       risk=ActionLevel.READ, http_method="GET", path_template="/v1/loyalty/rewards",
       prerequisites=_AUTH_PRE),
    _a(domain="loyalty", action="rewards-redeem", command="loyalty rewards redeem --reward-id",
       purpose="Redeem a loyalty reward.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/loyalty/rewards/redeem",
       requires_confirmation=True, confirmation_style="inline_token", prerequisites=("loyalty.rewards-list",)),
    _a(domain="loyalty", action="tier-benefits", command="loyalty tier-benefits",
       purpose="Get the benefits of the customer's loyalty tier.",
       risk=ActionLevel.READ, http_method="GET", path_template="/v1/loyalty/tier-benefits",
       prerequisites=_AUTH_PRE),

    # --- support (escalation / human handoff) ------------------------------
    _a(domain="support", action="escalate", command="support escalate --reason [--context]",
       purpose="Hand off to human support with context when self-service cannot resolve the request.",
       risk=ActionLevel.REQUEST, http_method="POST", path_template="/v1/support/escalate",
       prerequisites=_AUTH_PRE),
]


_BY_KEY: dict[str, ActionDef] = {a.key: a for a in ACTIONS}


def all_actions() -> list[ActionDef]:
    return list(ACTIONS)


def action_by_key(key: str) -> ActionDef | None:
    return _BY_KEY.get(key)


def domains() -> list[str]:
    """Domains in stable declaration order (unique)."""
    seen: list[str] = []
    for a in ACTIONS:
        if a.domain not in seen:
            seen.append(a.domain)
    return seen


def actions_for_domain(domain: str) -> list[ActionDef]:
    return [a for a in ACTIONS if a.domain == domain]


def _segments(path: str) -> list[str]:
    return [s for s in path.strip("/").split("/") if s != ""]


def _template_matches(template: str, path: str) -> bool:
    t = _segments(template)
    p = _segments(path)
    if len(t) != len(p):
        return False
    for ts, ps in zip(t, p):
        if ts.startswith("{") and ts.endswith("}"):
            continue
        if ts != ps:
            return False
    return True


def action_by_path(method: str, path: str) -> ActionDef | None:
    """Resolve a concrete request (method + path) to its action.

    Exact literal matches win over placeholder matches so that, e.g.,
    ``POST /v1/orders/cancel`` resolves to ``orders.cancel`` rather than being
    mistaken for ``orders.get`` (``/v1/orders/{order_id}``).
    """
    method = method.upper()
    for a in ACTIONS:
        if a.http_method == method and a.path_template == path:
            return a
    for a in ACTIONS:
        if a.http_method == method and _template_matches(a.path_template, path):
            return a
    return None


def ai_agent_blocked_actions() -> list[str]:
    return [a.key for a in ACTIONS if "ai_agent" in a.consumer_block]
