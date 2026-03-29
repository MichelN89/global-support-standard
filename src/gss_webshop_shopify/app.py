from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import httpx
import uvicorn
from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from gss_core.envelope import fail, ok
from gss_core.errors import GssError, err
from gss_core.models import (
    AuthIssueTokenRequest,
    AuthLoginRequest,
    AuthorizationMetadata,
    AuthVerifyCustomerRequest,
    ComplianceMetadata,
    OrdersListQuery,
)
from gss_core.security import matches_customer_identity, validate_resource_id
from gss_provider.auth import validate_headers
from gss_webshop_shopify.runtime import ShopOwnedRuntimeAdapter
from gss_webshop_shopify.settings import ShopifyProviderSettings, load_settings
from gss_webshop_shopify.shopify_client import ShopifyAdminClient, map_shopify_order


def create_shopify_app(
    *,
    settings: ShopifyProviderSettings | None = None,
    runtime: ShopOwnedRuntimeAdapter | None = None,
    client: ShopifyAdminClient | None = None,
) -> FastAPI:
    cfg = settings or load_settings()
    state = runtime or ShopOwnedRuntimeAdapter()
    shopify = client or ShopifyAdminClient(
        shop_domain=cfg.shop_domain,
        admin_token=cfg.admin_token,
        api_version=cfg.api_version,
    )
    app = FastAPI(title="GSS Shopify Webshop Provider", version="0.2.1")
    verification_store: dict[str, dict[str, Any]] = {}

    def _normalize_email(value: str | None) -> str:
        return (value or "").strip().lower()

    def _normalize_phone(value: str | None) -> str:
        raw = (value or "").strip()
        return "".join(ch for ch in raw if ch.isdigit())

    def _masked_email(value: str | None) -> str | None:
        email = _normalize_email(value)
        if "@" not in email:
            return None
        local, domain = email.split("@", 1)
        if len(local) <= 2:
            local_mask = local[0] + "***" if local else "***"
        else:
            local_mask = f"{local[0]}***{local[-1]}"
        return f"{local_mask}@{domain}"

    def _masked_phone(value: str | None) -> str | None:
        digits = _normalize_phone(value)
        if len(digits) < 4:
            return None
        return f"***{digits[-4:]}"

    def _customer_matches_identifiers(
        mapped_order: dict[str, Any],
        *,
        email: str | None,
        phone: str | None,
    ) -> bool:
        normalized_email = _normalize_email(email)
        normalized_phone = _normalize_phone(phone)
        order_email = _normalize_email(mapped_order.get("customer_email"))
        order_phone = _normalize_phone(mapped_order.get("customer_phone"))
        email_match = bool(normalized_email and order_email and normalized_email == order_email)
        phone_match = bool(normalized_phone and order_phone and normalized_phone == order_phone)
        return email_match or phone_match

    def _matches_customer_identity(order: dict[str, Any], customer_id: str) -> bool:
        # In this webshop project, customer identity is represented by either
        # Shopify customer id (numeric string) or customer email.
        return matches_customer_identity(
            customer_id,
            str(order.get("customer_id") or ""),
            str(order.get("customer_email") or ""),
        )

    def _request_id(request: Request) -> str:
        return request.headers.get("GSS-Request-Id", f"req-{uuid4().hex}")

    def _ctx(
        *,
        authorization: str | None,
        consumer_id: str | None,
        consumer_type: str | None,
        version: str | None,
        request_id: str | None,
    ):
        return validate_headers(
            adapter=state,
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            gss_version=version,
            request_id=request_id,
        )

    def _translate_shopify_error(exc: Exception) -> GssError:
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            if status in {401, 403}:
                return err(
                    "UPSTREAM_AUTH_ERROR",
                    "Shopify rejected credentials or app permissions. Verify shop domain, token, and scopes.",
                    status_code=502,
                    details={"upstream_status": status},
                )
            if status == 429:
                return err(
                    "UPSTREAM_RATE_LIMITED",
                    "Shopify rate limit reached. Retry shortly.",
                    status_code=503,
                    details={"upstream_status": status},
                )
            return err(
                "UPSTREAM_HTTP_ERROR",
                "Shopify API request failed.",
                status_code=502,
                details={"upstream_status": status},
            )
        if isinstance(exc, httpx.RequestError):
            return err(
                "UPSTREAM_NETWORK_ERROR",
                "Could not reach Shopify API.",
                status_code=503,
            )
        return err("SERVICE_UNAVAILABLE", "Unexpected upstream error", status_code=503)

    @app.exception_handler(GssError)
    async def gss_error_handler(request: Request, exc: GssError) -> JSONResponse:
        rid = _request_id(request)
        return JSONResponse(status_code=exc.status_code, content=fail(exc.code, exc.message, rid, exc.details))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        rid = _request_id(request)
        return JSONResponse(
            status_code=422,
            content=fail("VALIDATION_ERROR", "Request validation failed", rid, {"errors": exc.errors()}),
        )

    @app.get("/v1/describe")
    def describe_shop(request: Request) -> dict[str, Any]:
        rid = _request_id(request)
        authorization = AuthorizationMetadata(
            gss_scopes_supported=[
                "orders:read",
                "shipping:read",
            ],
            scope_policy={
                "deny_by_default": True,
                "least_privilege_required": True,
                "action_level_enforced": True,
            },
            scope_mapping_hints=[
                {
                    "gss_scope": "orders:read",
                    "adapter_scope": "shopify:read_orders",
                    "note": "Maps to Shopify Admin API read_orders scope",
                },
                {
                    "gss_scope": "shipping:read",
                    "adapter_scope": "shopify:read_orders",
                    "note": "Shipping tracking is derived from order fulfillments",
                },
            ],
            custom_scopes=[],
        )
        compliance = ComplianceMetadata(
            level=cfg.compliance_level,
            certified=cfg.certified,
            test_suite_version=cfg.test_suite_version,
            responsibility_boundary=(
                "GSS defines contracts. This webshop implementation owns auth/session/audit infrastructure."
            ),
        )
        return ok(
            {
                "shop": cfg.shop_domain or "shopify-test-store",
                "name": cfg.shop_name,
                "gss_version": "1.0",
                "domains": ["orders", "shipping", "account", "payments", "auth", "protocols"],
                "auth_methods": ["oauth2", "api_key", "delegated_verification"],
                "endpoint": cfg.endpoint,
                "authorization": authorization.model_dump(),
                "compliance": compliance.model_dump(),
            },
            rid,
        )

    @app.post("/v1/auth/login")
    def auth_login(payload: AuthLoginRequest, request: Request) -> dict[str, Any]:
        rid = _request_id(request)
        if "@" not in payload.customer_id and not payload.customer_id.isdigit():
            raise err(
                "INVALID_CUSTOMER_ID",
                "For Shopify webshop demo, customer_id must be a customer email or numeric Shopify customer id.",
                status_code=400,
            )
        issued = state.issue_token(customer_id=payload.customer_id, method=payload.method, ttl_seconds=cfg.token_ttl_seconds)
        return ok(
            {
                "access_token": issued.access_token,
                "token_type": issued.token_type,
                "expires_in_seconds": issued.expires_in_seconds,
                "customer_id": issued.customer_id,
                "method": issued.method,
                "issued_via": "legacy_login",
            },
            rid,
        )

    @app.post("/v1/auth/verify-customer")
    def auth_verify_customer(payload: AuthVerifyCustomerRequest, request: Request) -> dict[str, Any]:
        rid = _request_id(request)
        if not shopify.configured:
            raise err("SERVICE_UNAVAILABLE", "Shopify credentials not configured", status_code=503)

        provided_email = _normalize_email(payload.email)
        provided_phone = _normalize_phone(payload.phone)
        if not provided_email and not provided_phone:
            raise err(
                "VALIDATION_ERROR",
                "Provide at least one identity field (email or phone).",
                status_code=400,
            )

        # Standard flow: order context + identity proof.
        if payload.order_id:
            validate_resource_id(field_name="order_id", value=payload.order_id)
            try:
                order = shopify.get_order(order_id=payload.order_id)
            except Exception as exc:
                raise _translate_shopify_error(exc) from exc
            if not order:
                raise err("NOT_FOUND", f"Order '{payload.order_id}' not found", status_code=404)

            mapped = map_shopify_order(order)
            if not _customer_matches_identifiers(mapped, email=provided_email, phone=provided_phone):
                raise err(
                    "VERIFICATION_FAILED",
                    "Provided customer identifiers do not match this order.",
                    status_code=403,
                )
            customer_ref = str(mapped.get("customer_id") or mapped.get("customer_email") or "")
            if not customer_ref:
                raise err("VERIFICATION_FAILED", "Customer identity could not be resolved.", status_code=403)

            verification_id = f"ver-{uuid4().hex[:16]}"
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
            verification_store[verification_id] = {
                "customer_id": customer_ref,
                "expires_at": expires_at,
                "consumed": False,
            }
            return ok(
                {
                    "status": "verified",
                    "verification_id": verification_id,
                    "expires_at": expires_at.isoformat(),
                    "customer_hint": {
                        "email": _masked_email(mapped.get("customer_email")),
                        "phone": _masked_phone(mapped.get("customer_phone")),
                    },
                    "next_action": "auth issue-token",
                },
                rid,
            )

        # Recovery path: no order id, phone-only lookup.
        if not provided_phone:
            raise err(
                "VALIDATION_ERROR",
                "If order_id is missing, phone is required for recovery lookup.",
                status_code=400,
            )
        try:
            candidate_orders = [map_shopify_order(row) for row in shopify.list_orders(limit=50, status=None)]
        except Exception as exc:
            raise _translate_shopify_error(exc) from exc

        matches = [row for row in candidate_orders if _normalize_phone(row.get("customer_phone")) == provided_phone]
        unique_customers = {
            str(row.get("customer_id") or row.get("customer_email") or ""): row
            for row in matches
            if str(row.get("customer_id") or row.get("customer_email") or "")
        }
        if len(unique_customers) != 1:
            return ok(
                {
                    "status": "manual_verification_required",
                    "reason": "Could not uniquely identify a single customer from provided details.",
                    "next_action": "manual identity verification outside GSS flow",
                },
                rid,
            )

        resolved = next(iter(unique_customers.values()))
        verification_id = f"ver-{uuid4().hex[:16]}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        customer_ref = str(resolved.get("customer_id") or resolved.get("customer_email"))
        verification_store[verification_id] = {
            "customer_id": customer_ref,
            "expires_at": expires_at,
            "consumed": False,
        }
        return ok(
            {
                "status": "verified_via_phone_recovery",
                "verification_id": verification_id,
                "expires_at": expires_at.isoformat(),
                "customer_hint": {
                    "email": _masked_email(resolved.get("customer_email")),
                    "phone": _masked_phone(resolved.get("customer_phone")),
                },
                "next_action": "auth issue-token",
            },
            rid,
        )

    @app.post("/v1/auth/issue-token")
    def auth_issue_token(payload: AuthIssueTokenRequest, request: Request) -> dict[str, Any]:
        rid = _request_id(request)
        row = verification_store.get(payload.verification_id)
        now = datetime.now(timezone.utc)
        if not row:
            raise err("INVALID_VERIFICATION_ID", "Unknown verification_id", status_code=400)
        if row.get("consumed"):
            raise err("INVALID_VERIFICATION_ID", "Verification already used", status_code=400)
        if row["expires_at"] <= now:
            verification_store.pop(payload.verification_id, None)
            raise err("INVALID_VERIFICATION_ID", "Verification expired", status_code=400)

        issued = state.issue_token(customer_id=row["customer_id"], method=payload.method, ttl_seconds=cfg.token_ttl_seconds)
        row["consumed"] = True
        return ok(
            {
                "access_token": issued.access_token,
                "token_type": issued.token_type,
                "expires_in_seconds": issued.expires_in_seconds,
                "customer_id": issued.customer_id,
                "method": issued.method,
                "issued_via": "verify_customer",
            },
            rid,
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
        ctx = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        if not shopify.configured:
            raise err("SERVICE_UNAVAILABLE", "Shopify credentials not configured", status_code=503)
        query = OrdersListQuery(status=status, since=since, limit=limit)
        try:
            mapped_orders = [map_shopify_order(row) for row in shopify.list_orders(limit=query.limit, status=query.status)]
        except Exception as exc:
            raise _translate_shopify_error(exc) from exc
        orders = [row for row in mapped_orders if _matches_customer_identity(row, ctx.customer_id)]
        state.append_event(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "customer_id": ctx.customer_id,
                "consumer_id": ctx.consumer_id,
                "consumer_type": ctx.consumer_type.value,
                "action": "orders list",
                "action_level": "read",
                "result": "ok",
            }
        )
        return ok(orders, ctx.request_id)

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
        ctx = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        if not shopify.configured:
            raise err("SERVICE_UNAVAILABLE", "Shopify credentials not configured", status_code=503)
        try:
            order = shopify.get_order(order_id=order_id)
        except Exception as exc:
            raise _translate_shopify_error(exc) from exc
        if not order:
            raise err("NOT_FOUND", f"Order '{order_id}' not found", status_code=404)
        mapped = map_shopify_order(order)
        if not _matches_customer_identity(mapped, ctx.customer_id):
            raise err("FORBIDDEN", "Order does not belong to authenticated customer", status_code=403)
        return ok(mapped, ctx.request_id)

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
        ctx = _ctx(
            authorization=authorization,
            consumer_id=consumer_id,
            consumer_type=consumer_type,
            version=gss_version,
            request_id=gss_request_id,
        )
        if not shopify.configured:
            raise err("SERVICE_UNAVAILABLE", "Shopify credentials not configured", status_code=503)
        try:
            order = shopify.get_order(order_id=order_id)
        except Exception as exc:
            raise _translate_shopify_error(exc) from exc
        if not order:
            raise err("NOT_FOUND", f"Order '{order_id}' not found", status_code=404)
        mapped = map_shopify_order(order)
        if not _matches_customer_identity(mapped, ctx.customer_id):
            raise err("FORBIDDEN", "Order does not belong to authenticated customer", status_code=403)
        fulfillments = order.get("fulfillments", [])
        latest = fulfillments[0] if fulfillments else {}
        return ok(
            {
                "order_id": str(order.get("id")),
                "carrier": latest.get("tracking_company"),
                "tracking_number": latest.get("tracking_number"),
                "tracking_url": latest.get("tracking_url"),
                "status": order.get("fulfillment_status") or "pending",
            },
            ctx.request_id,
        )

    @app.get("/v1/account/get")
    def account_get() -> dict[str, Any]:
        raise err(
            "ACTION_NOT_SUPPORTED",
            "account get is not implemented for this shop yet",
            status_code=501,
        )

    @app.get("/v1/payments/get/{order_id}")
    def payments_get(order_id: str) -> dict[str, Any]:
        raise err(
            "ACTION_NOT_SUPPORTED",
            f"payments get for order '{order_id}' is not implemented for this shop yet",
            status_code=501,
        )

    return app


app = create_shopify_app()


def run() -> None:
    cfg = load_settings()
    uvicorn.run("gss_webshop_shopify.app:app", host=cfg.host, port=cfg.port, reload=cfg.debug)
