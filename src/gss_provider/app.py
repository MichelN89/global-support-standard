from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from gss_core.envelope import fail, ok
from gss_core.errors import GssError, err
from gss_core.models import (
    AuthLoginRequest,
    AuthorizationMetadata,
    ComplianceMetadata,
    OrdersListQuery,
    ProtocolGetRequest,
    ReturnsCheckEligibilityRequest,
    ReturnsConfirmRequest,
    ReturnsInitiateRequest,
)
from gss_core.security import validate_resource_id
from gss_provider.audit import get_customer_audit, log_action
from gss_provider.auth import redact_token, validate_headers
from gss_provider.contracts import ShopRuntimeAdapter
from gss_provider.mock_adapter import InMemoryShopAdapter
from gss_provider.mock_data import get_order, list_orders, owns_order, return_eligibility
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

    app = FastAPI(title="GSS Provider MVP", version="0.1.0")

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
        return ok(
            {
                "shop": "mockshop.local",
                "name": "Mock Shop",
                "gss_version": "1.0",
                "domains": ["orders", "shipping", "returns", "protocols", "account", "auth"],
                "auth_methods": ["oauth2", "api_key"],
                "endpoint": runtime_settings.endpoint,
                "authorization": authorization.model_dump(),
                "compliance": compliance.model_dump(),
            },
            request_id,
        )

    @app.get("/v1/{domain}/describe")
    def describe_domain(domain: str, request: Request) -> dict[str, Any]:
        request_id = getattr(request.state, "request_id", request.headers.get("GSS-Request-Id", f"req-{uuid4().hex}"))
        catalog = {
            "orders": ["orders list", "orders get"],
            "shipping": ["shipping track"],
            "returns": ["returns check-eligibility", "returns initiate", "returns confirm"],
            "protocols": ["protocols get"],
            "account": ["account audit-log"],
            "auth": ["auth login"],
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
            },
            request_id,
        )

    def _ctx(
        *,
        authorization: str | None,
        consumer_id: str | None,
        consumer_type: str | None,
        version: str | None,
        request_id: str | None,
    ):
        return validate_headers(
            adapter=runtime_adapter,
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            gss_version=version,
            request_id=request_id,
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
        data = list_orders(auth.customer_id, status=query.status, limit=query.limit)
        return ok(data, auth.request_id)


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
        return ok(order, auth.request_id)


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
        return ok(
            {
                "order_id": order_id,
                "carrier": order["shipping"]["carrier"],
                "tracking_number": order["shipping"]["tracking_number"],
                "last_event": order["shipping"]["last_event"],
                "status": order["status"],
            },
            auth.request_id,
        )


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
        return ok(return_eligibility(payload.order_id, payload.item_id), auth.request_id)


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

        if auth.consumer_type.value == "ai_agent" and payload.reason == "change-email":
            raise err("CONSUMER_TYPE_BLOCKED", "Action blocked for ai_agent", status_code=403)

        eligibility = return_eligibility(payload.order_id, payload.item_id)
        if not eligibility["eligible"]:
            raise err("NOT_ELIGIBLE", "Return request is not eligible", status_code=400, details=eligibility)

        order = get_order(payload.order_id)
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
        return ok({"return_id": return_id, "status": "submitted"}, auth.request_id)


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
        return ok(data, auth.request_id)


    @app.get("/v1/account/audit-log")
    def account_audit_log(
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
        return ok(get_customer_audit(runtime_adapter, auth.customer_id), auth.request_id)

    return app


app = create_app()


def run() -> None:
    settings = load_settings()
    uvicorn.run("gss_provider.app:app", host=settings.host, port=settings.port, reload=settings.debug)
