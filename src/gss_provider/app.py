from __future__ import annotations

import os
from pathlib import Path
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
    OrdersListQuery,
    ProtocolGetRequest,
    ReturnsCheckEligibilityRequest,
    ReturnsConfirmRequest,
    ReturnsInitiateRequest,
)
from gss_provider.audit import get_customer_audit, log_action
from gss_provider.auth import endpoint_from_env, issue_token, validate_headers
from gss_provider.mock_data import get_order, list_orders, owns_order, return_eligibility
from gss_provider.protocol_engine import ProtocolEngine

app = FastAPI(title="GSS Provider MVP", version="0.1.0")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_ENGINE = ProtocolEngine(Path(os.getenv("GSS_PROTOCOL_DIR", str(PROJECT_ROOT / "protocols"))))
PENDING_CONFIRMATIONS: dict[str, dict[str, Any]] = {}


@app.exception_handler(GssError)
async def gss_error_handler(request: Request, exc: GssError) -> JSONResponse:
    request_id = request.headers.get("GSS-Request-Id") or f"req-{uuid4().hex}"
    return JSONResponse(
        status_code=exc.status_code,
        content=fail(exc.code, exc.message, request_id, exc.details),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = request.headers.get("GSS-Request-Id") or f"req-{uuid4().hex}"
    return JSONResponse(
        status_code=422,
        content=fail("VALIDATION_ERROR", "Request validation failed", request_id, {"errors": exc.errors()}),
    )


@app.get("/v1/describe")
def describe_shop(request: Request) -> dict[str, Any]:
    request_id = request.headers.get("GSS-Request-Id", f"req-{uuid4().hex}")
    return ok(
        {
            "shop": "mockshop.local",
            "name": "Mock Shop",
            "gss_version": "1.0",
            "domains": ["orders", "shipping", "returns", "protocols", "account", "auth"],
            "auth_methods": ["oauth2", "api_key"],
            "endpoint": endpoint_from_env(),
        },
        request_id,
    )


@app.get("/v1/{domain}/describe")
def describe_domain(domain: str, request: Request) -> dict[str, Any]:
    request_id = request.headers.get("GSS-Request-Id", f"req-{uuid4().hex}")
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
    request_id = request.headers.get("GSS-Request-Id", f"req-{uuid4().hex}")
    token = issue_token(payload.customer_id)
    return ok(
        {
            "access_token": token,
            "token_type": "bearer",
            "expires_in_seconds": 3600,
            "customer_id": payload.customer_id,
            "method": payload.method,
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

    token = f"conf-{uuid4().hex[:12]}"
    order = get_order(payload.order_id)
    item = next(i for i in (order or {}).get("items", []) if i["id"] == payload.item_id)
    PENDING_CONFIRMATIONS[token] = {
        "customer_id": auth.customer_id,
        "order_id": payload.order_id,
        "item_id": payload.item_id,
        "reason": payload.reason,
    }
    log_action(
        customer_id=auth.customer_id,
        consumer_id=auth.consumer_id,
        consumer_type=auth.consumer_type.value,
        consumer_ip=request.client.host if request.client else "unknown",
        action="returns initiate",
        action_level="request",
        parameters=payload.model_dump(),
        result="pending_confirmation",
        confirmation_token=token,
    )
    return ok(
        {
            "status": "pending_confirmation",
            "confirmation_token": token,
            "summary": (
                f"Return {payload.item_id} ({item['name']}, {item['price']}). "
                "Refund to original payment method."
            ),
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
    pending = PENDING_CONFIRMATIONS.get(payload.token)
    if not pending or pending["customer_id"] != auth.customer_id:
        raise err("INVALID_CONFIRMATION_TOKEN", "Invalid or expired confirmation token", status_code=400)

    return_id = f"RET-{uuid4().hex[:8].upper()}"
    log_action(
        customer_id=auth.customer_id,
        consumer_id=auth.consumer_id,
        consumer_type=auth.consumer_type.value,
        consumer_ip=request.client.host if request.client else "unknown",
        action="returns confirm",
        action_level="request",
        parameters={"token": payload.token},
        result="ok",
        confirmation_token=payload.token,
    )
    del PENDING_CONFIRMATIONS[payload.token]
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
    data = PROTOCOL_ENGINE.get(payload.trigger, payload.context)
    log_action(
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
    return ok(get_customer_audit(auth.customer_id), auth.request_id)


def run() -> None:
    uvicorn.run("gss_provider.app:app", host="127.0.0.1", port=8000, reload=False)
