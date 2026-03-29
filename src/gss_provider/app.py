from __future__ import annotations

import json
import logging
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from gss_core.envelope import fail, ok
from gss_core.errors import GssError, err
from gss_core.models import (
    AgentAuthResponse,
    AuthIssueTokenRequest,
    AuthLoginRequest,
    AuthorizationMetadata,
    ComplianceMetadata,
    CustomerVerificationRequest,
    CustomerVerificationResponse,
    OrdersListQuery,
    ProtocolGetRequest,
    ReturnsCheckEligibilityRequest,
    ReturnsConfirmRequest,
    ReturnsInitiateRequest,
)
from gss_core.security import validate_resource_id
from gss_provider.audit import get_customer_audit, log_action
from gss_provider.auth import detect_auth_state, redact_token, validate_headers
from gss_provider.contracts import ShopRuntimeAdapter
from gss_provider.mock_adapter import InMemoryShopAdapter
from gss_provider.mock_data import get_order, list_channels, list_orders, owns_order, return_eligibility
from gss_provider.protocol_engine import ProtocolEngine
from gss_provider.settings import ProviderSettings, load_settings

LOGGER = logging.getLogger("gss_provider")
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO)


def create_app(
    *,
    settings: ProviderSettings | None = None,
    adapter: ShopRuntimeAdapter | None = None,
) -> FastAPI:
    runtime_settings = settings or load_settings()
    runtime_adapter = adapter or InMemoryShopAdapter()
    protocol_engine = ProtocolEngine(runtime_settings.protocol_dir)

    app = FastAPI(title="GSS Provider", version="0.2.2")
    return_records: dict[str, dict[str, Any]] = {}
    refund_records: dict[str, dict[str, Any]] = {}
    payment_disputes: list[dict[str, Any]] = []
    account_profiles: dict[str, dict[str, Any]] = {}
    account_addresses: dict[str, list[dict[str, Any]]] = {}
    payment_methods: dict[str, list[dict[str, Any]]] = {}
    subscriptions: dict[str, list[dict[str, Any]]] = {}
    loyalty_ledgers: dict[str, list[dict[str, Any]]] = {}
    product_catalog: list[dict[str, Any]] = [
        {"id": "PRD-100", "name": "Wireless Headphones", "category": "audio", "stock": 8, "warranty_months": 24},
        {"id": "PRD-101", "name": "Mechanical Keyboard", "category": "peripherals", "stock": 5, "warranty_months": 24},
        {"id": "PRD-102", "name": "USB-C Cable", "category": "accessories", "stock": 42, "warranty_months": 12},
        {"id": "PRD-103", "name": "Smart Lamp", "category": "home", "stock": 0, "warranty_months": 12},
    ]

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("GSS-Request-Id", f"req-{uuid4().hex}")
        request.state.request_id = request_id
        LOGGER.info("request start %s %s request_id=%s", request.method, request.url.path, request_id)
        response = await call_next(request)
        response.headers["GSS-Request-Id"] = request_id
        LOGGER.info("request end %s request_id=%s", response.status_code, request_id)
        return response

    @app.exception_handler(GssError)
    async def gss_error_handler(request: Request, exc: GssError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", request.headers.get("GSS-Request-Id") or f"req-{uuid4().hex}")
        return JSONResponse(
            status_code=exc.status_code,
            content=fail(exc.code, exc.message, request_id, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", request.headers.get("GSS-Request-Id") or f"req-{uuid4().hex}")
        return JSONResponse(
            status_code=422,
            content=fail("VALIDATION_ERROR", "Request validation failed", request_id, {"errors": exc.errors()}),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", request.headers.get("GSS-Request-Id") or f"req-{uuid4().hex}")
        LOGGER.exception("unhandled exception request_id=%s", request_id, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=fail("SERVICE_UNAVAILABLE", "Unexpected server error", request_id),
        )

    @app.get("/v1/describe")
    def describe_shop(request: Request) -> dict[str, Any]:
        request_id = getattr(request.state, "request_id", request.headers.get("GSS-Request-Id", f"req-{uuid4().hex}"))
        auth_state = detect_auth_state(
            authorization=request.headers.get("Authorization"),
            gss_agent_key=request.headers.get("GSS-Agent-Key"),
        )
        public_describe = False
        authorization = AuthorizationMetadata(
            gss_scopes_supported=[
                "orders:read",
                "shipping:read",
                "returns:read",
                "returns:request",
                "protocols:read",
                "account:read",
            ],
            scope_policy={
                "deny_by_default": True,
                "least_privilege_required": True,
                "action_level_enforced": True,
            },
            scope_mapping_hints=[
                {
                    "gss_scope": "orders:read",
                    "adapter_scope": "adapter:orders:read",
                    "note": "Reference adapter-local permission identifier",
                },
                {
                    "gss_scope": "returns:request",
                    "adapter_scope": "adapter:returns:request",
                    "note": "Reference adapter-local permission identifier",
                },
            ],
            custom_scopes=[],
        )
        compliance = ComplianceMetadata(
            level=runtime_settings.compliance_level,
            certified=runtime_settings.certified,
            test_suite_version=runtime_settings.test_suite_version,
            responsibility_boundary=(
                "GSS defines protocol contracts and validation. "
                "Shop implementations own token issuance, persistence, and audit infrastructure."
            ),
        )
        minimum_payload = {
            "shop": "mockshop.local",
            "name": "Mock Shop",
            "gss_version": "1.0",
            "auth_methods": ["agent_key", "customer_verify", "oauth2", "api_key"],
            "endpoint": runtime_settings.endpoint,
            "public_describe": public_describe,
            "auth_state": auth_state,
        }
        if auth_state == "none" and not public_describe:
            return ok(minimum_payload, request_id)
        return ok(
            {
                **minimum_payload,
                "domains": [
                    "orders",
                    "shipping",
                    "returns",
                    "refunds",
                    "products",
                    "account",
                    "payments",
                    "subscriptions",
                    "loyalty",
                    "protocols",
                    "auth",
                ],
                "channels": list_channels(),
                "auth_methods_menu": {
                    "agent_key": {"recommended": True, "deprecated": False},
                    "customer_verify": {
                        "recommended": True,
                        "fields_supported": ["order_id", "email", "phone", "postal_code", "last_name"],
                    },
                    "oauth2": {"recommended": True, "deprecated": False},
                    "api_key": {"recommended": True, "deprecated": False},
                    "login": {"recommended": False, "deprecated": True},
                },
                "consumer_policies": {
                    "requires_customer_auth_for_data": True,
                    "minimum_token_ttl_seconds": 300,
                    "recommend_channel_hint": True,
                },
                "authorization": authorization.model_dump(),
                "compliance": compliance.model_dump(),
            },
            request_id,
        )

    @app.get("/v1/{domain}/describe")
    def describe_domain(domain: str, request: Request) -> dict[str, Any]:
        request_id = getattr(request.state, "request_id", request.headers.get("GSS-Request-Id", f"req-{uuid4().hex}"))
        catalog = {
            "orders": [
                "orders get --id",
                "orders list [--status] [--since] [--limit]",
                "orders cancel --id [--reason]",
                "orders modify --id --changes",
                "orders reorder --id",
            ],
            "returns": [
                "returns check-eligibility --order-id --item-id",
                "returns initiate --order-id --item-id --reason [--option]",
                "returns status --return-id",
                "returns list [--status] [--since]",
                "returns cancel --return-id",
                "returns dispute --return-id --reason",
                "returns request-return-back --return-id",
                "returns accept-partial --return-id --option",
            ],
            "refunds": [
                "refunds status --refund-id",
                "refunds list [--since]",
            ],
            "shipping": [
                "shipping track --order-id",
                "shipping report-issue --order-id --issue",
                "shipping change-address --order-id --address",
                "shipping request-redelivery --order-id [--date]",
                "shipping delivery-preferences --set",
            ],
            "products": [
                "products get --id",
                "products search --query [--category] [--limit]",
                "products check-availability --id [--postal-code]",
                "products warranty-status --id --purchase-date",
                "products notify-restock --id --email",
                "products compare --ids",
            ],
            "account": [
                "account get",
                "account update --changes",
                "account addresses list",
                "account addresses add --address",
                "account addresses update --id --changes",
                "account addresses delete --id",
                "account change-email --new-email",
                "account change-email-recover --new-email",
                "account payment-methods list",
                "account payment-methods add --method",
                "account payment-methods delete --id",
                "account delete-request",
                "account export-data",
                "account audit-log [--since] [--limit]",
            ],
            "payments": [
                "payments get --order-id",
                "payments invoice --order-id",
                "payments dispute --order-id --reason",
                "payments retry --order-id",
                "payments list [--since] [--status]",
            ],
            "subscriptions": [
                "subscriptions list",
                "subscriptions get --id",
                "subscriptions pause --id [--until]",
                "subscriptions resume --id",
                "subscriptions cancel --id [--reason]",
                "subscriptions modify --id --changes",
                "subscriptions skip-next --id",
                "subscriptions change-frequency --id --cycle",
            ],
            "loyalty": [
                "loyalty balance",
                "loyalty history [--since] [--limit]",
                "loyalty redeem --points --order-id",
                "loyalty rewards list",
                "loyalty rewards redeem --reward-id",
                "loyalty tier-benefits",
            ],
            "protocols": ["protocols get --trigger --context"],
            "auth": ["auth agent --key", "auth verify-customer [...fields]", "auth issue-token --verification-id", "auth login (deprecated)"],
        }
        if domain not in catalog:
            raise err("DOMAIN_NOT_SUPPORTED", f"Domain '{domain}' is not supported", status_code=404)
        return ok({"domain": domain, "commands": catalog[domain]}, request_id)

    @app.post("/v1/auth/login")
    def auth_login(payload: AuthLoginRequest, request: Request) -> dict[str, Any]:
        request_id = getattr(request.state, "request_id", request.headers.get("GSS-Request-Id", f"req-{uuid4().hex}"))
        issued = runtime_adapter.issue_token(
            customer_id=payload.customer_id,
            method=payload.method,
            ttl_seconds=runtime_settings.token_ttl_seconds,
        )
        return ok(
            {
                "access_token": issued.access_token,
                "token_type": issued.token_type,
                "expires_in_seconds": issued.expires_in_seconds,
                "customer_id": issued.customer_id,
                "method": issued.method,
                "deprecated": True,
            },
            request_id,
        )

    @app.post("/v1/auth/agent")
    def auth_agent(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        request_id = getattr(request.state, "request_id", request.headers.get("GSS-Request-Id", f"req-{uuid4().hex}"))
        key = str(payload.get("key", "")).strip()
        if not key:
            raise err("VALIDATION_ERROR", "Missing agent key", status_code=400, details={"field": "key"})
        agent_info = runtime_adapter.authenticate_agent_key(key)
        if not agent_info:
            raise err("UNAUTHORIZED", "Invalid agent key", status_code=401)
        scopes = list(agent_info.get("scopes", []))
        token = runtime_adapter.issue_agent_token(
            agent_id=str(agent_info.get("agent_id", "agent")),
            ttl_seconds=runtime_settings.token_ttl_seconds,
            scopes=scopes,
        )
        response = AgentAuthResponse(
            access_token=token.access_token,
            token_type=token.token_type,
            expires_in_seconds=token.expires_in_seconds,
            scopes=scopes,
        )
        return ok(response.model_dump(), request_id)

    @app.post("/v1/auth/verify-customer")
    def auth_verify_customer(payload: CustomerVerificationRequest, request: Request) -> dict[str, Any]:
        request_id = getattr(request.state, "request_id", request.headers.get("GSS-Request-Id", f"req-{uuid4().hex}"))
        body = payload.model_dump(exclude_none=True)
        if not body:
            raise err("VALIDATION_ERROR", "Provide at least one verification field", status_code=400)
        record = runtime_adapter.create_customer_verification(
            payload=body,
            ttl_seconds=runtime_settings.confirmation_ttl_seconds,
        )
        response = CustomerVerificationResponse(
            verification_id=record.verification_id,
            accepted_fields=record.accepted_fields,
            expires_in_seconds=runtime_settings.confirmation_ttl_seconds,
            channel=record.channel,
            customer_hint=record.customer_hint,
        )
        return ok(response.model_dump(), request_id, channel=record.channel)

    @app.post("/v1/auth/issue-token")
    def auth_issue_token(payload: AuthIssueTokenRequest, request: Request) -> dict[str, Any]:
        request_id = getattr(request.state, "request_id", request.headers.get("GSS-Request-Id", f"req-{uuid4().hex}"))
        verification = runtime_adapter.consume_customer_verification(verification_id=payload.verification_id)
        if not verification:
            raise err("INVALID_VERIFICATION", "Invalid or expired verification id", status_code=400)
        issued = runtime_adapter.issue_token(
            customer_id=verification.customer_id,
            method=payload.method,
            ttl_seconds=runtime_settings.token_ttl_seconds,
        )
        return ok(
            {
                "access_token": issued.access_token,
                "token_type": issued.token_type,
                "expires_in_seconds": issued.expires_in_seconds,
                "customer_id": issued.customer_id,
                "method": issued.method,
                "verification_fields": verification.accepted_fields,
            },
            request_id,
            channel=verification.channel,
        )

    def _ctx(
        *,
        authorization: str | None,
        consumer_id: str | None,
        consumer_type: str | None,
        version: str | None,
        request_id: str | None,
        gss_agent_key: str | None = None,
    ):
        return validate_headers(
            adapter=runtime_adapter,
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            gss_version=version,
            request_id=request_id,
            gss_agent_key=gss_agent_key,
        )

    def _resolve_channel(request: Request, payload: dict[str, Any] | None = None) -> str | None:
        candidate = request.query_params.get("channel")
        if not candidate:
            candidate = request.headers.get("GSS-Channel")
        if not candidate and payload:
            value = payload.get("channel")
            if isinstance(value, str) and value:
                candidate = value
        if not candidate:
            return None
        valid_channels = {row["id"] for row in list_channels()}
        if candidate not in valid_channels:
            raise err(
                "CHANNEL_NOT_SUPPORTED",
                f"Channel '{candidate}' is not supported",
                status_code=400,
                details={"supported_channels": sorted(valid_channels)},
            )
        return candidate

    def _ok(data: Any, request_id: str, request: Request, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return ok(data, request_id, channel=_resolve_channel(request, payload))

    def _json_dict(raw: str | None, *, field_name: str) -> dict[str, Any]:
        if raw is None:
            raise err("VALIDATION_ERROR", f"Missing {field_name}", status_code=400, details={"field": field_name})
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise err("VALIDATION_ERROR", f"Invalid JSON in {field_name}", status_code=400) from exc
        if not isinstance(parsed, dict):
            raise err("VALIDATION_ERROR", f"{field_name} must be a JSON object", status_code=400)
        return parsed

    def _order_or_forbidden(customer_id: str, order_id: str) -> dict[str, Any]:
        validate_resource_id(field_name="order_id", value=order_id)
        order = get_order(order_id)
        if not order or order["customer_id"] != customer_id:
            raise err("FORBIDDEN", "Order does not belong to authenticated customer", status_code=403)
        return order

    def _profile(customer_id: str) -> dict[str, Any]:
        return account_profiles.setdefault(
            customer_id,
            {
                "customer_id": customer_id,
                "email": f"{customer_id.lower()}@example.com",
                "phone": "+31000000000",
                "language": "nl-NL",
                "marketing_opt_in": False,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )

    def _addresses(customer_id: str) -> list[dict[str, Any]]:
        return account_addresses.setdefault(
            customer_id,
            [
                {
                    "id": "ADDR-1",
                    "label": "home",
                    "line1": "Example Street 1",
                    "postal_code": "1000AA",
                    "city": "Amsterdam",
                    "country": "NL",
                }
            ],
        )

    def _payment_methods(customer_id: str) -> list[dict[str, Any]]:
        return payment_methods.setdefault(
            customer_id,
            [{"id": "PM-1", "type": "card", "masked": "**** **** **** 4242", "default": True}],
        )

    def _subscriptions(customer_id: str) -> list[dict[str, Any]]:
        return subscriptions.setdefault(
            customer_id,
            [
                {
                    "id": "SUB-1",
                    "status": "active",
                    "cycle": "monthly",
                    "next_billing_date": (datetime.now(UTC) + timedelta(days=20)).date().isoformat(),
                }
            ],
        )

    def _loyalty_history(customer_id: str) -> list[dict[str, Any]]:
        return loyalty_ledgers.setdefault(
            customer_id,
            [
                {"id": "LOY-1", "type": "earn", "points": 50, "created_at": datetime.now(UTC).isoformat()},
                {"id": "LOY-2", "type": "redeem", "points": -10, "created_at": datetime.now(UTC).isoformat()},
            ],
        )

    @app.get("/v1/orders")
    def orders_list(
        request: Request,
        status: str | None = None,
        since: str | None = None,
        limit: int = 20,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        query = OrdersListQuery(status=status, since=since, limit=limit)
        channel = _resolve_channel(request)
        data = list_orders(auth.customer_id, status=query.status, limit=query.limit, channel=channel)
        return _ok(data, auth.request_id, request)


    @app.get("/v1/orders/{order_id}")
    def orders_get(
        order_id: str,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        validate_resource_id(field_name="order_id", value=order_id)
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        order = get_order(order_id)
        if not order or order["customer_id"] != auth.customer_id:
            raise err("FORBIDDEN", "Order does not belong to authenticated customer", status_code=403)
        channel = _resolve_channel(request)
        if channel and order.get("channel") != channel:
            raise err("NOT_FOUND", "Order not found for provided channel", status_code=404)
        return _ok(order, auth.request_id, request, payload=order)

    @app.post("/v1/orders/cancel")
    def orders_cancel(
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        order_id = str(payload.get("id", ""))
        reason = str(payload.get("reason", "not_specified"))
        order = _order_or_forbidden(auth.customer_id, order_id)
        return ok({"order_id": order_id, "status": "cancel_requested", "reason": reason, "previous_status": order["status"]}, auth.request_id)

    @app.post("/v1/orders/modify")
    def orders_modify(
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        order_id = str(payload.get("id", ""))
        changes_raw = payload.get("changes")
        changes = changes_raw if isinstance(changes_raw, dict) else _json_dict(str(changes_raw), field_name="changes")
        _order_or_forbidden(auth.customer_id, order_id)
        return ok({"order_id": order_id, "status": "modification_requested", "changes": changes}, auth.request_id)

    @app.post("/v1/orders/reorder")
    def orders_reorder(
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        order_id = str(payload.get("id", ""))
        order = _order_or_forbidden(auth.customer_id, order_id)
        new_order_id = f"ORD-R-{uuid4().hex[:8].upper()}"
        return ok(
            {
                "source_order_id": order_id,
                "new_order_id": new_order_id,
                "status": "created",
                "item_count": len(order.get("items", [])),
            },
            auth.request_id,
        )


    @app.get("/v1/shipping/track/{order_id}")
    def shipping_track(
        order_id: str,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        validate_resource_id(field_name="order_id", value=order_id)
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        order = get_order(order_id)
        if not order or order["customer_id"] != auth.customer_id:
            raise err("FORBIDDEN", "Order does not belong to authenticated customer", status_code=403)
        channel = _resolve_channel(request)
        if channel and order.get("channel") != channel:
            raise err("NOT_FOUND", "Order not found for provided channel", status_code=404)
        return ok(
            {
                "order_id": order_id,
                "carrier": order["shipping"]["carrier"],
                "tracking_number": order["shipping"]["tracking_number"],
                "last_event": order["shipping"]["last_event"],
                "status": order["status"],
                "channel": order.get("channel"),
            },
            auth.request_id,
            channel=channel or order.get("channel"),
        )

    @app.post("/v1/shipping/report-issue")
    def shipping_report_issue(
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        order_id = str(payload.get("order_id", ""))
        issue = str(payload.get("issue", "unknown"))
        _order_or_forbidden(auth.customer_id, order_id)
        case_id = f"SHP-{uuid4().hex[:8].upper()}"
        return ok({"order_id": order_id, "issue": issue, "case_id": case_id, "status": "reported"}, auth.request_id)

    @app.post("/v1/shipping/change-address")
    def shipping_change_address(
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        order_id = str(payload.get("order_id", ""))
        _order_or_forbidden(auth.customer_id, order_id)
        return ok({"order_id": order_id, "status": "address_change_requested", "address": payload.get("address")}, auth.request_id)

    @app.post("/v1/shipping/request-redelivery")
    def shipping_request_redelivery(
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        order_id = str(payload.get("order_id", ""))
        _order_or_forbidden(auth.customer_id, order_id)
        return ok(
            {"order_id": order_id, "status": "redelivery_requested", "preferred_date": payload.get("date")},
            auth.request_id,
        )

    @app.post("/v1/shipping/delivery-preferences")
    def shipping_delivery_preferences(
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        return ok({"status": "preferences_saved", "preferences": payload.get("set")}, auth.request_id)


    @app.post("/v1/returns/check-eligibility")
    def returns_check_eligibility(
        payload: ReturnsCheckEligibilityRequest,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        if not owns_order(auth.customer_id, payload.order_id):
            raise err("FORBIDDEN", "Order does not belong to authenticated customer", status_code=403)
        channel = _resolve_channel(request, payload.model_dump(exclude_none=True))
        order = get_order(payload.order_id)
        if channel and order and order.get("channel") != channel:
            raise err("NOT_FOUND", "Order not found for provided channel", status_code=404)
        return ok(return_eligibility(payload.order_id, payload.item_id), auth.request_id, channel=channel or (order or {}).get("channel"))


    @app.post("/v1/returns/initiate")
    def returns_initiate(
        payload: ReturnsInitiateRequest,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        if not owns_order(auth.customer_id, payload.order_id):
            raise err("FORBIDDEN", "Order does not belong to authenticated customer", status_code=403)
        channel = _resolve_channel(request, payload.model_dump(exclude_none=True))

        if auth.consumer_type.value == "ai_agent" and payload.reason == "change-email":
            raise err("CONSUMER_TYPE_BLOCKED", "Action blocked for ai_agent", status_code=403)

        eligibility = return_eligibility(payload.order_id, payload.item_id)
        if not eligibility["eligible"]:
            raise err("NOT_ELIGIBLE", "Return request is not eligible", status_code=400, details=eligibility)

        order = get_order(payload.order_id)
        if channel and order and order.get("channel") != channel:
            raise err("NOT_FOUND", "Order not found for provided channel", status_code=404)
        item = next(i for i in (order or {}).get("items", []) if i["id"] == payload.item_id)
        confirmation = runtime_adapter.create_confirmation(
            customer_id=auth.customer_id,
            payload={
                "order_id": payload.order_id,
                "item_id": payload.item_id,
                "reason": payload.reason,
            },
            ttl_seconds=runtime_settings.confirmation_ttl_seconds,
        )
        log_action(
            runtime_adapter,
            customer_id=auth.customer_id,
            consumer_id=auth.consumer_id,
            consumer_type=auth.consumer_type.value,
            consumer_ip=request.client.host if request.client else "unknown",
            action="returns initiate",
            action_level="request",
            parameters=payload.model_dump(),
            result="pending_confirmation",
            confirmation_token=redact_token(confirmation.token),
        )
        return ok(
            {
                "status": "pending_confirmation",
                "confirmation_token": confirmation.token,
                "summary": (
                    f"Return {payload.item_id} ({item['name']}, {item['price']}). "
                    "Refund to original payment method."
                ),
                "expires_at": confirmation.expires_at.isoformat(),
            },
            auth.request_id,
            channel=channel or (order or {}).get("channel"),
        )


    @app.post("/v1/returns/confirm")
    def returns_confirm(
        payload: ReturnsConfirmRequest,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        pending = runtime_adapter.consume_confirmation(token=payload.token, customer_id=auth.customer_id)
        if not pending:
            raise err("INVALID_CONFIRMATION_TOKEN", "Invalid or expired confirmation token", status_code=400)

        return_id = f"RET-{uuid4().hex[:8].upper()}"
        return_records[return_id] = {
            "return_id": return_id,
            "customer_id": auth.customer_id,
            "order_id": pending.payload.get("order_id"),
            "item_id": pending.payload.get("item_id"),
            "reason": pending.payload.get("reason"),
            "status": "submitted",
            "created_at": datetime.now(UTC).isoformat(),
        }
        refund_id = f"RFD-{uuid4().hex[:8].upper()}"
        refund_records[refund_id] = {
            "refund_id": refund_id,
            "return_id": return_id,
            "customer_id": auth.customer_id,
            "status": "pending",
            "amount": 0,
            "created_at": datetime.now(UTC).isoformat(),
        }
        log_action(
            runtime_adapter,
            customer_id=auth.customer_id,
            consumer_id=auth.consumer_id,
            consumer_type=auth.consumer_type.value,
            consumer_ip=request.client.host if request.client else "unknown",
            action="returns confirm",
            action_level="request",
            parameters={"token": redact_token(payload.token)},
            result="ok",
            confirmation_token=redact_token(payload.token),
        )
        return ok({"return_id": return_id, "refund_id": refund_id, "status": "submitted"}, auth.request_id)

    @app.get("/v1/returns")
    def returns_list(
        request: Request,
        status: str | None = None,
        since: str | None = None,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        rows = [deepcopy(v) for v in return_records.values() if v["customer_id"] == auth.customer_id]
        if status:
            rows = [r for r in rows if r.get("status") == status]
        if since:
            rows = [r for r in rows if r.get("created_at", "") >= since]
        return ok(rows, auth.request_id)

    @app.get("/v1/returns/{return_id}")
    def returns_status(
        return_id: str,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        validate_resource_id(field_name="return_id", value=return_id)
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        record = return_records.get(return_id)
        if not record or record["customer_id"] != auth.customer_id:
            raise err("FORBIDDEN", "Return does not belong to authenticated customer", status_code=403)
        return ok(deepcopy(record), auth.request_id)

    @app.post("/v1/returns/cancel")
    def returns_cancel(
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        return_id = str(payload.get("return_id", ""))
        record = return_records.get(return_id)
        if not record or record["customer_id"] != auth.customer_id:
            raise err("FORBIDDEN", "Return does not belong to authenticated customer", status_code=403)
        record["status"] = "cancel_requested"
        return ok({"return_id": return_id, "status": record["status"]}, auth.request_id)

    @app.post("/v1/returns/dispute")
    def returns_dispute(
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        return_id = str(payload.get("return_id", ""))
        record = return_records.get(return_id)
        if not record or record["customer_id"] != auth.customer_id:
            raise err("FORBIDDEN", "Return does not belong to authenticated customer", status_code=403)
        case_id = f"DSP-{uuid4().hex[:8].upper()}"
        return ok({"return_id": return_id, "case_id": case_id, "reason": payload.get("reason"), "status": "in_review"}, auth.request_id)

    @app.post("/v1/returns/request-return-back")
    def returns_request_return_back(
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        return_id = str(payload.get("return_id", ""))
        record = return_records.get(return_id)
        if not record or record["customer_id"] != auth.customer_id:
            raise err("FORBIDDEN", "Return does not belong to authenticated customer", status_code=403)
        return ok({"return_id": return_id, "status": "return_back_requested"}, auth.request_id)

    @app.post("/v1/returns/accept-partial")
    def returns_accept_partial(
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        return_id = str(payload.get("return_id", ""))
        record = return_records.get(return_id)
        if not record or record["customer_id"] != auth.customer_id:
            raise err("FORBIDDEN", "Return does not belong to authenticated customer", status_code=403)
        return ok({"return_id": return_id, "status": "partial_accepted", "option": payload.get("option")}, auth.request_id)

    @app.get("/v1/refunds")
    def refunds_list(
        request: Request,
        since: str | None = None,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        rows = [deepcopy(v) for v in refund_records.values() if v["customer_id"] == auth.customer_id]
        if since:
            rows = [r for r in rows if r.get("created_at", "") >= since]
        return ok(rows, auth.request_id)

    @app.get("/v1/refunds/{refund_id}")
    def refunds_status(
        refund_id: str,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        validate_resource_id(field_name="refund_id", value=refund_id)
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        row = refund_records.get(refund_id)
        if not row or row["customer_id"] != auth.customer_id:
            raise err("FORBIDDEN", "Refund does not belong to authenticated customer", status_code=403)
        return ok(deepcopy(row), auth.request_id)


    @app.post("/v1/protocols/get")
    def protocols_get(
        payload: ProtocolGetRequest,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        requested_channel = _resolve_channel(request, payload.context)
        data = protocol_engine.get(payload.trigger, payload.context)
        log_action(
            runtime_adapter,
            customer_id=auth.customer_id,
            consumer_id=auth.consumer_id,
            consumer_type=auth.consumer_type.value,
            consumer_ip=request.client.host if request.client else "unknown",
            action="protocols get",
            action_level="read",
            parameters=payload.model_dump(),
            result="ok",
            protocol_used=data["protocol_used"],
        )
        return ok(data, auth.request_id, channel=requested_channel)

    @app.get("/v1/products/{product_id}")
    def products_get(
        product_id: str,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        validate_resource_id(field_name="product_id", value=product_id)
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        product = next((p for p in product_catalog if p["id"] == product_id), None)
        if not product:
            raise err("NOT_FOUND", "Product not found", status_code=404)
        return ok(deepcopy(product), auth.request_id)

    @app.get("/v1/products/search")
    def products_search(
        request: Request,
        query: str,
        category: str | None = None,
        limit: int = 20,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        rows = [p for p in product_catalog if query.lower() in p["name"].lower()]
        if category:
            rows = [p for p in rows if p["category"] == category]
        rows = rows[: max(1, min(limit, 100))]
        return ok(deepcopy(rows), auth.request_id)

    @app.get("/v1/products/check-availability/{product_id}")
    def products_check_availability(
        product_id: str,
        request: Request,
        postal_code: str | None = None,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        validate_resource_id(field_name="product_id", value=product_id)
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        product = next((p for p in product_catalog if p["id"] == product_id), None)
        if not product:
            raise err("NOT_FOUND", "Product not found", status_code=404)
        return ok(
            {
                "product_id": product_id,
                "available": product["stock"] > 0,
                "stock": product["stock"],
                "postal_code": postal_code,
            },
            auth.request_id,
        )

    @app.get("/v1/products/warranty-status/{product_id}")
    def products_warranty_status(
        product_id: str,
        request: Request,
        purchase_date: str,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        validate_resource_id(field_name="product_id", value=product_id)
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        product = next((p for p in product_catalog if p["id"] == product_id), None)
        if not product:
            raise err("NOT_FOUND", "Product not found", status_code=404)
        return ok(
            {
                "product_id": product_id,
                "purchase_date": purchase_date,
                "warranty_months": product["warranty_months"],
                "status": "active",
            },
            auth.request_id,
        )

    @app.post("/v1/products/notify-restock")
    def products_notify_restock(
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        product_id = str(payload.get("id", ""))
        validate_resource_id(field_name="id", value=product_id)
        return ok({"product_id": product_id, "email": payload.get("email"), "status": "subscription_created"}, auth.request_id)

    @app.get("/v1/products/compare")
    def products_compare(
        request: Request,
        ids: str,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        requested = [x.strip() for x in ids.split(",") if x.strip()]
        return ok({"ids": requested, "items": [p for p in product_catalog if p["id"] in requested]}, auth.request_id)

    @app.get("/v1/account")
    def account_get(
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        return ok(deepcopy(_profile(auth.customer_id)), auth.request_id)

    @app.post("/v1/account/update")
    def account_update(
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        changes_raw = payload.get("changes")
        changes = changes_raw if isinstance(changes_raw, dict) else _json_dict(str(changes_raw), field_name="changes")
        profile = _profile(auth.customer_id)
        profile.update(changes)
        return ok({"status": "updated", "profile": deepcopy(profile)}, auth.request_id)

    @app.get("/v1/account/addresses")
    def account_addresses_list(
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        return ok(deepcopy(_addresses(auth.customer_id)), auth.request_id)

    @app.post("/v1/account/addresses")
    def account_addresses_add(
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        address_raw = payload.get("address")
        address = address_raw if isinstance(address_raw, dict) else _json_dict(str(address_raw), field_name="address")
        addresses = _addresses(auth.customer_id)
        new_address = {"id": f"ADDR-{uuid4().hex[:6].upper()}", **address}
        addresses.append(new_address)
        return ok({"status": "added", "address": new_address}, auth.request_id)

    @app.post("/v1/account/addresses/{address_id}")
    def account_addresses_update(
        address_id: str,
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        validate_resource_id(field_name="address_id", value=address_id)
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        changes_raw = payload.get("changes")
        changes = changes_raw if isinstance(changes_raw, dict) else _json_dict(str(changes_raw), field_name="changes")
        addresses = _addresses(auth.customer_id)
        for row in addresses:
            if row["id"] == address_id:
                row.update(changes)
                return ok({"status": "updated", "address": deepcopy(row)}, auth.request_id)
        raise err("NOT_FOUND", "Address not found", status_code=404)

    @app.delete("/v1/account/addresses/{address_id}")
    def account_addresses_delete(
        address_id: str,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        validate_resource_id(field_name="address_id", value=address_id)
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        rows = _addresses(auth.customer_id)
        updated = [row for row in rows if row["id"] != address_id]
        if len(updated) == len(rows):
            raise err("NOT_FOUND", "Address not found", status_code=404)
        account_addresses[auth.customer_id] = updated
        return ok({"status": "deleted", "id": address_id}, auth.request_id)

    @app.post("/v1/account/change-email")
    def account_change_email(
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        new_email = str(payload.get("new_email", ""))
        if "@" not in new_email:
            raise err("VALIDATION_ERROR", "Invalid new_email", status_code=400)
        return ok(
            {
                "status": "verification_required",
                "channel": "email",
                "masked_destination": f"***@{new_email.split('@')[-1]}",
            },
            auth.request_id,
        )

    @app.post("/v1/account/change-email-recover")
    def account_change_email_recover(
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        new_email = str(payload.get("new_email", ""))
        if "@" not in new_email:
            raise err("VALIDATION_ERROR", "Invalid new_email", status_code=400)
        return ok({"status": "manual_recovery_started", "new_email": new_email}, auth.request_id)

    @app.get("/v1/account/payment-methods")
    def account_payment_methods_list(
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        return ok(deepcopy(_payment_methods(auth.customer_id)), auth.request_id)

    @app.post("/v1/account/payment-methods")
    def account_payment_methods_add(
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        method_raw = payload.get("method")
        method = method_raw if isinstance(method_raw, dict) else _json_dict(str(method_raw), field_name="method")
        rows = _payment_methods(auth.customer_id)
        new_row = {"id": f"PM-{uuid4().hex[:6].upper()}", "default": False, **method}
        rows.append(new_row)
        return ok({"status": "verification_required", "payment_method": new_row}, auth.request_id)

    @app.delete("/v1/account/payment-methods/{method_id}")
    def account_payment_methods_delete(
        method_id: str,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        validate_resource_id(field_name="method_id", value=method_id)
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        rows = _payment_methods(auth.customer_id)
        new_rows = [row for row in rows if row["id"] != method_id]
        if len(rows) == len(new_rows):
            raise err("NOT_FOUND", "Payment method not found", status_code=404)
        payment_methods[auth.customer_id] = new_rows
        return ok({"status": "deleted", "id": method_id}, auth.request_id)

    @app.post("/v1/account/delete-request")
    def account_delete_request(
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        return ok({"status": "delete_request_created", "estimated_completion_days": 30}, auth.request_id)

    @app.get("/v1/account/export-data")
    def account_export_data(
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        export_id = f"EXP-{uuid4().hex[:8].upper()}"
        return ok({"export_id": export_id, "status": "queued", "format": "json"}, auth.request_id)

    @app.get("/v1/payments")
    def payments_list(
        request: Request,
        since: str | None = None,
        status: str | None = None,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        rows = []
        for order in list_orders(auth.customer_id, limit=100):
            row = {
                "order_id": order["id"],
                "status": "paid",
                "amount": round(sum(i["price"] * i["quantity"] for i in order["items"]), 2),
                "created_at": order["created_at"],
            }
            rows.append(row)
        if status:
            rows = [row for row in rows if row["status"] == status]
        if since:
            rows = [row for row in rows if row["created_at"] >= since]
        return ok(rows, auth.request_id)

    @app.get("/v1/payments/{order_id}")
    def payments_get(
        order_id: str,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        order = _order_or_forbidden(auth.customer_id, order_id)
        amount = round(sum(i["price"] * i["quantity"] for i in order["items"]), 2)
        return ok({"order_id": order_id, "status": "paid", "amount": amount, "currency": "EUR"}, auth.request_id)

    @app.get("/v1/payments/{order_id}/invoice")
    def payments_invoice(
        order_id: str,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        _order_or_forbidden(auth.customer_id, order_id)
        return ok(
            {"order_id": order_id, "invoice_url": f"https://example.test/invoices/{order_id}.pdf", "status": "available"},
            auth.request_id,
        )

    @app.post("/v1/payments/dispute")
    def payments_dispute(
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        order_id = str(payload.get("order_id", ""))
        _order_or_forbidden(auth.customer_id, order_id)
        dispute_id = f"PMD-{uuid4().hex[:8].upper()}"
        payment_disputes.append(
            {"dispute_id": dispute_id, "order_id": order_id, "customer_id": auth.customer_id, "reason": payload.get("reason")}
        )
        return ok({"dispute_id": dispute_id, "status": "submitted"}, auth.request_id)

    @app.post("/v1/payments/retry")
    def payments_retry(
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        order_id = str(payload.get("order_id", ""))
        _order_or_forbidden(auth.customer_id, order_id)
        return ok({"order_id": order_id, "status": "retry_scheduled"}, auth.request_id)

    @app.get("/v1/subscriptions")
    def subscriptions_list(
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        return ok(deepcopy(_subscriptions(auth.customer_id)), auth.request_id)

    @app.get("/v1/subscriptions/{subscription_id}")
    def subscriptions_get(
        subscription_id: str,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        validate_resource_id(field_name="subscription_id", value=subscription_id)
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        sub = next((row for row in _subscriptions(auth.customer_id) if row["id"] == subscription_id), None)
        if not sub:
            raise err("NOT_FOUND", "Subscription not found", status_code=404)
        return ok(deepcopy(sub), auth.request_id)

    @app.post("/v1/subscriptions/{subscription_id}/pause")
    def subscriptions_pause(
        subscription_id: str,
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        validate_resource_id(field_name="subscription_id", value=subscription_id)
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        sub = next((row for row in _subscriptions(auth.customer_id) if row["id"] == subscription_id), None)
        if not sub:
            raise err("NOT_FOUND", "Subscription not found", status_code=404)
        sub["status"] = "paused"
        sub["paused_until"] = payload.get("until")
        return ok({"id": subscription_id, "status": sub["status"], "until": sub.get("paused_until")}, auth.request_id)

    @app.post("/v1/subscriptions/{subscription_id}/resume")
    def subscriptions_resume(
        subscription_id: str,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        validate_resource_id(field_name="subscription_id", value=subscription_id)
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        sub = next((row for row in _subscriptions(auth.customer_id) if row["id"] == subscription_id), None)
        if not sub:
            raise err("NOT_FOUND", "Subscription not found", status_code=404)
        sub["status"] = "active"
        sub.pop("paused_until", None)
        return ok({"id": subscription_id, "status": sub["status"]}, auth.request_id)

    @app.post("/v1/subscriptions/{subscription_id}/cancel")
    def subscriptions_cancel(
        subscription_id: str,
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        validate_resource_id(field_name="subscription_id", value=subscription_id)
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        sub = next((row for row in _subscriptions(auth.customer_id) if row["id"] == subscription_id), None)
        if not sub:
            raise err("NOT_FOUND", "Subscription not found", status_code=404)
        sub["status"] = "cancel_requested"
        sub["cancel_reason"] = payload.get("reason")
        return ok({"id": subscription_id, "status": sub["status"], "reason": sub["cancel_reason"]}, auth.request_id)

    @app.post("/v1/subscriptions/{subscription_id}/modify")
    def subscriptions_modify(
        subscription_id: str,
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        validate_resource_id(field_name="subscription_id", value=subscription_id)
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        sub = next((row for row in _subscriptions(auth.customer_id) if row["id"] == subscription_id), None)
        if not sub:
            raise err("NOT_FOUND", "Subscription not found", status_code=404)
        changes_raw = payload.get("changes")
        changes = changes_raw if isinstance(changes_raw, dict) else _json_dict(str(changes_raw), field_name="changes")
        sub.update(changes)
        return ok({"id": subscription_id, "status": "modify_requested", "changes": changes}, auth.request_id)

    @app.post("/v1/subscriptions/{subscription_id}/skip-next")
    def subscriptions_skip_next(
        subscription_id: str,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        validate_resource_id(field_name="subscription_id", value=subscription_id)
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        sub = next((row for row in _subscriptions(auth.customer_id) if row["id"] == subscription_id), None)
        if not sub:
            raise err("NOT_FOUND", "Subscription not found", status_code=404)
        return ok({"id": subscription_id, "status": "next_cycle_skipped"}, auth.request_id)

    @app.post("/v1/subscriptions/{subscription_id}/change-frequency")
    def subscriptions_change_frequency(
        subscription_id: str,
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        validate_resource_id(field_name="subscription_id", value=subscription_id)
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        sub = next((row for row in _subscriptions(auth.customer_id) if row["id"] == subscription_id), None)
        if not sub:
            raise err("NOT_FOUND", "Subscription not found", status_code=404)
        sub["cycle"] = payload.get("cycle", sub["cycle"])
        return ok({"id": subscription_id, "status": "frequency_change_requested", "cycle": sub["cycle"]}, auth.request_id)

    @app.get("/v1/loyalty/balance")
    def loyalty_balance(
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        points = sum(row["points"] for row in _loyalty_history(auth.customer_id))
        return ok({"points": points}, auth.request_id)

    @app.get("/v1/loyalty/history")
    def loyalty_history(
        request: Request,
        since: str | None = None,
        limit: int = 20,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        rows = deepcopy(_loyalty_history(auth.customer_id))
        if since:
            rows = [row for row in rows if row["created_at"] >= since]
        return ok(rows[: max(1, min(limit, 200))], auth.request_id)

    @app.post("/v1/loyalty/redeem")
    def loyalty_redeem(
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        points = int(payload.get("points", 0))
        order_id = str(payload.get("order_id", ""))
        _order_or_forbidden(auth.customer_id, order_id)
        _loyalty_history(auth.customer_id).append(
            {"id": f"LOY-{uuid4().hex[:6].upper()}", "type": "redeem", "points": -abs(points), "created_at": datetime.now(UTC).isoformat()}
        )
        return ok({"status": "redeemed", "points": abs(points), "order_id": order_id}, auth.request_id)

    @app.get("/v1/loyalty/rewards")
    def loyalty_rewards_list(
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        rewards = [
            {"reward_id": "RWD-5", "points_required": 500, "description": "EUR 5 voucher"},
            {"reward_id": "RWD-10", "points_required": 1000, "description": "EUR 10 voucher"},
        ]
        return ok(rewards, auth.request_id)

    @app.post("/v1/loyalty/rewards/redeem")
    def loyalty_rewards_redeem(
        payload: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        reward_id = str(payload.get("reward_id", ""))
        validate_resource_id(field_name="reward_id", value=reward_id)
        return ok({"reward_id": reward_id, "status": "redeemed"}, auth.request_id)

    @app.get("/v1/loyalty/tier-benefits")
    def loyalty_tier_benefits(
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        points = sum(row["points"] for row in _loyalty_history(auth.customer_id))
        tier = "silver" if points >= 500 else "bronze"
        benefits = ["priority_support"] if tier == "silver" else ["standard_support"]
        return ok({"tier": tier, "benefits": benefits}, auth.request_id)


    @app.get("/v1/account/audit-log")
    def account_audit_log(
        request: Request,
        since: str | None = None,
        limit: int = 100,
        authorization: str | None = Header(default=None, alias="Authorization"),
        consumer_id: str | None = Header(default=None, alias="GSS-Consumer-Id"),
        consumer_type: str | None = Header(default=None, alias="GSS-Consumer-Type"),
        gss_version: str | None = Header(default=None, alias="GSS-Version"),
        gss_request_id: str | None = Header(default=None, alias="GSS-Request-Id"),
    ) -> dict[str, Any]:
        auth = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        rows = get_customer_audit(runtime_adapter, auth.customer_id)
        if since:
            rows = [row for row in rows if row.get("timestamp", "") >= since]
        rows = rows[: max(1, min(limit, 500))]
        return ok(rows, auth.request_id)

    return app


app = create_app()


def run() -> None:
    settings = load_settings()
    uvicorn.run("gss_provider.app:app", host=settings.host, port=settings.port, reload=settings.debug)
