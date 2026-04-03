from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import typer

from gss_cli.validate import run_validate

app = typer.Typer(add_completion=False, no_args_is_help=True)
TOKEN_PATH = Path.home() / ".gss" / "tokens.json"
LOCAL_DEFAULT_ENDPOINT = "http://127.0.0.1:8000/v1"


def _shop_env_key(shop: str) -> str:
    normalized = "".join(c if c.isalnum() else "_" for c in shop).upper()
    return f"GSS_SHOP_{normalized}_ENDPOINT"


def _normalize_endpoint(endpoint: str) -> str:
    return endpoint.rstrip("/")


def _safe_path_segment(value: Any) -> str:
    return quote(str(value), safe="")


def _looks_like_domain(shop: str) -> bool:
    return "." in shop and "/" not in shop and ":" not in shop


def _extract_endpoint_from_well_known(payload: dict[str, Any], shop: str) -> str | None:
    for key in ("endpoint", "gss_endpoint", "base_endpoint", "url"):
        value = payload.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return _normalize_endpoint(value)
    shops = payload.get("shops")
    if isinstance(shops, dict):
        value = shops.get(shop)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return _normalize_endpoint(value)
    return None


def _discover_from_well_known(shop: str) -> str | None:
    url = f"https://{shop}/.well-known/gss.json"
    try:
        with httpx.Client(timeout=3.0, follow_redirects=True) as client:
            response = client.get(url)
        if response.status_code >= 400:
            return None
        payload = response.json()
        if not isinstance(payload, dict):
            return None
        return _extract_endpoint_from_well_known(payload, shop)
    except Exception:
        return None


def _discover_from_dns_txt(shop: str) -> str | None:
    try:
        import dns.resolver  # type: ignore[import-not-found]
    except Exception:
        return None
    record_name = f"_gss.{shop}"
    try:
        answers = dns.resolver.resolve(record_name, "TXT")
    except Exception:
        return None
    for answer in answers:
        txt = "".join(part.decode("utf-8") for part in answer.strings).strip()
        for prefix in ("endpoint=", "gss_endpoint=", "gss="):
            if txt.startswith(prefix):
                value = txt.split("=", 1)[1].strip()
                if value.startswith(("http://", "https://")):
                    return _normalize_endpoint(value)
        if txt.startswith(("http://", "https://")):
            return _normalize_endpoint(txt)
    return None


def _discover_endpoint(shop: str) -> str | None:
    if os.getenv("GSS_DISABLE_DISCOVERY", "0").lower() in {"1", "true", "yes"}:
        return None
    if not _looks_like_domain(shop) or shop.endswith(".local"):
        return None
    well_known = _discover_from_well_known(shop)
    if well_known:
        return well_known
    return _discover_from_dns_txt(shop)


def _resolve_endpoint(shop: str) -> str:
    shop_override = os.getenv(_shop_env_key(shop))
    if shop_override:
        return _normalize_endpoint(shop_override)
    global_override = os.getenv("GSS_DEFAULT_ENDPOINT")
    if global_override:
        return _normalize_endpoint(global_override)
    discovered = _discover_endpoint(shop)
    if discovered:
        return discovered
    return LOCAL_DEFAULT_ENDPOINT


def _load_tokens() -> dict[str, str]:
    if os.getenv("GSS_STORE_TOKENS", "1").lower() in {"0", "false", "no"}:
        return {}
    if not TOKEN_PATH.exists():
        return {}
    return json.loads(TOKEN_PATH.read_text())


def _save_tokens(tokens: dict[str, str]) -> None:
    if os.getenv("GSS_STORE_TOKENS", "1").lower() in {"0", "false", "no"}:
        return
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(tokens, indent=2))
    os.chmod(TOKEN_PATH, 0o600)


def _token_for(shop: str) -> str | None:
    inline_token = os.getenv("GSS_CUSTOMER_TOKEN")
    if inline_token:
        return inline_token
    return _load_tokens().get(shop)


def _parse_flags(args: list[str]) -> tuple[list[str], dict[str, Any]]:
    positionals: list[str] = []
    flags: dict[str, Any] = {}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--"):
            key = arg[2:].replace("-", "_")
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                value: Any = args[i + 1]
                i += 1
            else:
                value = True
            flags[key] = value
        else:
            positionals.append(arg)
        i += 1
    return positionals, flags


def _headers(shop: str, channel: str | None = None) -> dict[str, str]:
    token = _token_for(shop)
    if not token:
        raise typer.BadParameter(
            f"No auth token for {shop}. Run: gss {shop} auth verify-customer ... then gss {shop} auth issue-token ..."
        )
    headers = {
        "Authorization": f"Bearer {token}",
        "GSS-Consumer-Id": os.getenv("GSS_CONSUMER_ID", "support-squad-ai"),
        "GSS-Consumer-Type": os.getenv("GSS_CONSUMER_TYPE", "ai_agent"),
        "GSS-Version": "1.0",
    }
    if channel:
        headers["GSS-Channel"] = channel
    return headers


def _request(
    *,
    method: str,
    endpoint: str,
    path: str,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.request(method, f"{endpoint}{path}", headers=headers, params=params, json=body)
    except httpx.RequestError as exc:
        typer.secho(
            f"Connection refused: could not reach endpoint {endpoint}. "
            "Set GSS_DEFAULT_ENDPOINT or GSS_SHOP_<SHOP>_ENDPOINT to a reachable URL.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from exc
    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.status_code >= 400:
        msg = data.get("error", {}).get("message", "Request failed")
        raise typer.BadParameter(msg)
    return data


def _emit(value: dict[str, Any]) -> None:
    typer.echo(json.dumps(value, indent=2))


def _required(flags: dict[str, Any], *keys: str) -> None:
    missing = [key for key in keys if key not in flags]
    if missing:
        raise typer.BadParameter(f"Missing required flag(s): {', '.join('--' + m.replace('_', '-') for m in missing)}")


def _first_flag(flags: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in flags:
            return flags[name]
    return None


def _warn_if_uncertified(describe_payload: dict[str, Any]) -> None:
    data = describe_payload.get("data", {})
    compliance = data.get("compliance")
    if not isinstance(compliance, dict):
        typer.echo(
            "Warning: shop is not GSS certified (metadata missing).",
            err=True,
        )
        return
    if not compliance.get("certified", False):
        level = compliance.get("level", "unknown")
        suite = compliance.get("test_suite_version", "unverified")
        typer.echo(
            f"Warning: shop is not GSS certified (level={level}, suite={suite}).",
            err=True,
        )


def _warn_consumer_risks(describe_payload: dict[str, Any]) -> None:
    data = describe_payload.get("data", {})
    if data.get("public_describe"):
        typer.echo("Warning: shop exposes full describe metadata publicly.", err=True)
    policies = data.get("consumer_policies")
    if not isinstance(policies, dict):
        typer.echo("Warning: missing consumer_policies metadata.", err=True)
    compliance = data.get("compliance")
    if not isinstance(compliance, dict) or not compliance.get("test_suite_version"):
        typer.echo("Warning: missing test_suite_version metadata.", err=True)


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    add_help_option=True,
)
def main(ctx: typer.Context, shop: str, parts: list[str] = typer.Argument(...)) -> None:
    positionals, flags = _parse_flags(parts + list(ctx.args))
    if shop == "validate":
        if not positionals:
            raise typer.BadParameter("Usage: gss validate <shop> --level basic|standard|complete")
        target_shop = positionals[0]
        endpoint = _resolve_endpoint(target_shop)
        level = str(flags.get("level", "basic"))
        if level not in {"basic", "standard", "complete"}:
            raise typer.BadParameter("Validation level must be one of: basic, standard, complete")
        _emit(run_validate(shop=target_shop, endpoint=endpoint, level=level, request_fn=_request))
        return

    endpoint = _resolve_endpoint(shop)
    channel = str(flags["channel"]) if "channel" in flags else None

    if not positionals:
        raise typer.BadParameter("Expected command pattern: gss <shop> <domain> <action>")

    if positionals[0] == "describe":
        describe_payload = _request(method="GET", endpoint=endpoint, path="/describe")
        _warn_if_uncertified(describe_payload)
        _warn_consumer_risks(describe_payload)
        _emit(describe_payload)
        return

    domain = positionals[0]
    action = positionals[1] if len(positionals) > 1 else "describe"

    if domain == "auth" and action == "login":
        method = flags.get("method", "api_key")
        customer_id = flags.get("customer_id", "CUST-001")
        res = _request(
            method="POST",
            endpoint=endpoint,
            path="/auth/login",
            body={"method": method, "customer_id": customer_id},
        )
        token = res["data"]["access_token"]
        if os.getenv("GSS_STORE_TOKENS", "1").lower() in {"0", "false", "no"}:
            typer.echo("Token storage disabled. Export GSS_CUSTOMER_TOKEN for subsequent commands.", err=True)
        else:
            tokens = _load_tokens()
            tokens[shop] = token
            _save_tokens(tokens)
        _emit(res)
        return

    if domain == "auth" and action == "verify-customer":
        body: dict[str, Any] = {}
        if "order_id" in flags:
            body["order_id"] = flags["order_id"]
        if "email" in flags:
            body["email"] = flags["email"]
        if "phone" in flags:
            body["phone"] = flags["phone"]
        if "channel" in flags:
            body["channel"] = flags["channel"]
        _emit(
            _request(
                method="POST",
                endpoint=endpoint,
                path="/auth/verify-customer",
                body=body,
            )
        )
        return

    if domain == "auth" and action == "agent":
        _required(flags, "key")
        _emit(_request(method="POST", endpoint=endpoint, path="/auth/agent", body={"key": flags["key"]}))
        return

    if domain == "auth" and action == "issue-token":
        method = flags.get("method", "api_key")
        res = _request(
            method="POST",
            endpoint=endpoint,
            path="/auth/issue-token",
            body={"verification_id": flags["verification_id"], "method": method},
        )
        token = res["data"]["access_token"]
        if os.getenv("GSS_STORE_TOKENS", "1").lower() in {"0", "false", "no"}:
            typer.echo("Token storage disabled. Export GSS_CUSTOMER_TOKEN for subsequent commands.", err=True)
        else:
            tokens = _load_tokens()
            tokens[shop] = token
            _save_tokens(tokens)
        _emit(res)
        return

    if action == "describe":
        _emit(_request(method="GET", endpoint=endpoint, path=f"/{domain}/describe", headers=_headers(shop, channel=channel)))
        return

    headers = _headers(shop, channel=channel)

    if domain == "orders":
        if action == "list":
            _emit(_request(method="GET", endpoint=endpoint, path="/orders", headers=headers, params=flags))
            return
        if action == "get":
            _required(flags, "id")
            _emit(_request(method="GET", endpoint=endpoint, path=f"/orders/{_safe_path_segment(flags['id'])}", headers=headers))
            return
        if action in {"cancel", "modify", "reorder"}:
            _required(flags, "id")
            body: dict[str, Any] = {"id": flags["id"]}
            if "reason" in flags:
                body["reason"] = flags["reason"]
            if "changes" in flags:
                body["changes"] = flags["changes"]
            if "refund" in flags:
                body["refund"] = flags["refund"]
            if "restock" in flags:
                body["restock"] = flags["restock"]
            if "confirm_token" in flags:
                body["confirm_token"] = flags["confirm_token"]
            if "confirmation_token" in flags:
                body["confirm_token"] = flags["confirmation_token"]
            _emit(_request(method="POST", endpoint=endpoint, path=f"/orders/{action}", headers=headers, body=body))
            return

    if domain == "returns":
        if action == "check-eligibility":
            _required(flags, "order_id", "item_id")
            _emit(
                _request(
                    method="POST",
                    endpoint=endpoint,
                    path="/returns/check-eligibility",
                    headers=headers,
                    body={"order_id": flags["order_id"], "item_id": flags["item_id"]},
                )
            )
            return
        if action == "initiate":
            _required(flags, "order_id", "item_id", "reason")
            body = {"order_id": flags["order_id"], "item_id": flags["item_id"], "reason": flags["reason"]}
            if "option" in flags:
                body["option"] = flags["option"]
            _emit(_request(method="POST", endpoint=endpoint, path="/returns/initiate", headers=headers, body=body))
            return
        if action == "confirm":
            _required(flags, "token")
            _emit(_request(method="POST", endpoint=endpoint, path="/returns/confirm", headers=headers, body={"token": flags["token"]}))
            return
        if action == "status":
            _required(flags, "return_id")
            _emit(_request(method="GET", endpoint=endpoint, path=f"/returns/{flags['return_id']}", headers=headers))
            return
        if action == "list":
            _emit(_request(method="GET", endpoint=endpoint, path="/returns", headers=headers, params=flags))
            return
        if action in {"cancel", "dispute", "request-return-back", "accept-partial"}:
            _required(flags, "return_id")
            body = {"return_id": flags["return_id"]}
            if "reason" in flags:
                body["reason"] = flags["reason"]
            if "option" in flags:
                body["option"] = flags["option"]
            _emit(_request(method="POST", endpoint=endpoint, path=f"/returns/{action}", headers=headers, body=body))
            return

    if domain == "refunds":
        if action == "status":
            _required(flags, "refund_id")
            _emit(_request(method="GET", endpoint=endpoint, path=f"/refunds/{flags['refund_id']}", headers=headers))
            return
        if action == "list":
            _emit(_request(method="GET", endpoint=endpoint, path="/refunds", headers=headers, params=flags))
            return

    if domain == "shipping":
        if action == "track":
            _required(flags, "order_id")
            _emit(_request(method="GET", endpoint=endpoint, path=f"/shipping/track/{flags['order_id']}", headers=headers))
            return
        if action in {"report-issue", "change-address", "request-redelivery"}:
            _required(flags, "order_id")
            body = {"order_id": flags["order_id"]}
            if "issue" in flags:
                body["issue"] = flags["issue"]
            if "address" in flags:
                body["address"] = flags["address"]
            if "date" in flags:
                body["date"] = flags["date"]
            _emit(_request(method="POST", endpoint=endpoint, path=f"/shipping/{action}", headers=headers, body=body))
            return
        if action == "delivery-preferences":
            _required(flags, "set")
            _emit(_request(method="POST", endpoint=endpoint, path="/shipping/delivery-preferences", headers=headers, body={"set": flags["set"]}))
            return

    if domain == "products":
        if action == "get":
            _required(flags, "id")
            _emit(_request(method="GET", endpoint=endpoint, path=f"/products/{flags['id']}", headers=headers))
            return
        if action == "search":
            _required(flags, "query")
            _emit(_request(method="GET", endpoint=endpoint, path="/products/search", headers=headers, params=flags))
            return
        if action == "check-availability":
            _required(flags, "id")
            params = {"postal_code": flags["postal_code"]} if "postal_code" in flags else None
            _emit(_request(method="GET", endpoint=endpoint, path=f"/products/check-availability/{flags['id']}", headers=headers, params=params))
            return
        if action == "warranty-status":
            _required(flags, "id", "purchase_date")
            _emit(
                _request(
                    method="GET",
                    endpoint=endpoint,
                    path=f"/products/warranty-status/{flags['id']}",
                    headers=headers,
                    params={"purchase_date": flags["purchase_date"]},
                )
            )
            return
        if action == "notify-restock":
            _required(flags, "id", "email")
            _emit(_request(method="POST", endpoint=endpoint, path="/products/notify-restock", headers=headers, body={"id": flags["id"], "email": flags["email"]}))
            return
        if action == "compare":
            _required(flags, "ids")
            _emit(_request(method="GET", endpoint=endpoint, path="/products/compare", headers=headers, params={"ids": flags["ids"]}))
            return

    if domain == "account":
        if action == "get":
            _emit(_request(method="GET", endpoint=endpoint, path="/account", headers=headers))
            return
        if action == "update":
            _required(flags, "changes")
            _emit(_request(method="POST", endpoint=endpoint, path="/account/update", headers=headers, body={"changes": flags["changes"]}))
            return
        if action == "change-email":
            _required(flags, "new_email")
            _emit(_request(method="POST", endpoint=endpoint, path="/account/change-email", headers=headers, body={"new_email": flags["new_email"]}))
            return
        if action == "change-email-recover":
            _required(flags, "new_email")
            _emit(_request(method="POST", endpoint=endpoint, path="/account/change-email-recover", headers=headers, body={"new_email": flags["new_email"]}))
            return
        if action == "delete-request":
            _emit(_request(method="POST", endpoint=endpoint, path="/account/delete-request", headers=headers))
            return
        if action == "export-data":
            _emit(_request(method="GET", endpoint=endpoint, path="/account/export-data", headers=headers))
            return
        if action == "audit-log":
            _emit(_request(method="GET", endpoint=endpoint, path="/account/audit-log", headers=headers, params=flags))
            return
        if action == "addresses":
            if not positionals or len(positionals) < 3:
                raise typer.BadParameter("Usage: account addresses <list|add|update|delete>")
            subaction = positionals[2]
            if subaction == "list":
                _emit(_request(method="GET", endpoint=endpoint, path="/account/addresses", headers=headers))
                return
            if subaction == "add":
                _required(flags, "address")
                _emit(_request(method="POST", endpoint=endpoint, path="/account/addresses", headers=headers, body={"address": flags["address"]}))
                return
            if subaction == "update":
                _required(flags, "id", "changes")
                _emit(
                    _request(
                        method="POST",
                        endpoint=endpoint,
                        path=f"/account/addresses/{flags['id']}",
                        headers=headers,
                        body={"changes": flags["changes"]},
                    )
                )
                return
            if subaction == "delete":
                _required(flags, "id")
                _emit(_request(method="DELETE", endpoint=endpoint, path=f"/account/addresses/{flags['id']}", headers=headers))
                return
        if action == "payment-methods":
            if not positionals or len(positionals) < 3:
                raise typer.BadParameter("Usage: account payment-methods <list|add|delete>")
            subaction = positionals[2]
            if subaction == "list":
                _emit(_request(method="GET", endpoint=endpoint, path="/account/payment-methods", headers=headers))
                return
            if subaction == "add":
                _required(flags, "method")
                _emit(_request(method="POST", endpoint=endpoint, path="/account/payment-methods", headers=headers, body={"method": flags["method"]}))
                return
            if subaction == "delete":
                _required(flags, "id")
                _emit(_request(method="DELETE", endpoint=endpoint, path=f"/account/payment-methods/{flags['id']}", headers=headers))
                return

    if domain == "payments":
        if action == "list":
            _emit(_request(method="GET", endpoint=endpoint, path="/payments", headers=headers, params=flags))
            return
        if action == "get":
            order_ref = _first_flag(flags, "order_id", "id")
            if not order_ref:
                raise typer.BadParameter("Missing required flag(s): --order-id")
            _emit(_request(method="GET", endpoint=endpoint, path=f"/payments/{order_ref}", headers=headers))
            return
        if action == "invoice":
            order_ref = _first_flag(flags, "order_id", "id")
            if not order_ref:
                raise typer.BadParameter("Missing required flag(s): --order-id")
            _emit(_request(method="GET", endpoint=endpoint, path=f"/payments/{order_ref}/invoice", headers=headers))
            return
        if action == "refund":
            order_ref = _first_flag(flags, "order_id", "id")
            if not order_ref:
                raise typer.BadParameter("Missing required flag(s): --order-id")
            body: dict[str, Any] = {"order_id": order_ref}
            if "amount" in flags:
                body["amount"] = flags["amount"]
            if "reason" in flags:
                body["reason"] = flags["reason"]
            if "confirm_token" in flags:
                body["confirm_token"] = flags["confirm_token"]
            if "confirmation_token" in flags:
                body["confirm_token"] = flags["confirmation_token"]
            _emit(_request(method="POST", endpoint=endpoint, path="/payments/refund", headers=headers, body=body))
            return
        if action == "dispute":
            order_ref = _first_flag(flags, "order_id", "id")
            if not order_ref:
                raise typer.BadParameter("Missing required flag(s): --order-id")
            _required(flags, "reason")
            _emit(_request(method="POST", endpoint=endpoint, path="/payments/dispute", headers=headers, body={"order_id": order_ref, "reason": flags["reason"]}))
            return
        if action == "retry":
            order_ref = _first_flag(flags, "order_id", "id")
            if not order_ref:
                raise typer.BadParameter("Missing required flag(s): --order-id")
            _emit(_request(method="POST", endpoint=endpoint, path="/payments/retry", headers=headers, body={"order_id": order_ref}))
            return

    if domain == "subscriptions":
        if action == "list":
            _emit(_request(method="GET", endpoint=endpoint, path="/subscriptions", headers=headers))
            return
        if action == "get":
            _required(flags, "id")
            _emit(_request(method="GET", endpoint=endpoint, path=f"/subscriptions/{flags['id']}", headers=headers))
            return
        if action in {"pause", "resume", "cancel", "modify", "skip-next", "change-frequency"}:
            _required(flags, "id")
            path = f"/subscriptions/{flags['id']}/{action}"
            body: dict[str, Any] = {}
            if "until" in flags:
                body["until"] = flags["until"]
            if "reason" in flags:
                body["reason"] = flags["reason"]
            if "changes" in flags:
                body["changes"] = flags["changes"]
            if "cycle" in flags:
                body["cycle"] = flags["cycle"]
            _emit(_request(method="POST", endpoint=endpoint, path=path, headers=headers, body=body or None))
            return

    if domain == "loyalty":
        if action == "balance":
            _emit(_request(method="GET", endpoint=endpoint, path="/loyalty/balance", headers=headers))
            return
        if action == "history":
            _emit(_request(method="GET", endpoint=endpoint, path="/loyalty/history", headers=headers, params=flags))
            return
        if action == "redeem":
            _required(flags, "points", "order_id")
            _emit(_request(method="POST", endpoint=endpoint, path="/loyalty/redeem", headers=headers, body={"points": flags["points"], "order_id": flags["order_id"]}))
            return
        if action == "tier-benefits":
            _emit(_request(method="GET", endpoint=endpoint, path="/loyalty/tier-benefits", headers=headers))
            return
        if action == "rewards":
            if len(positionals) < 3:
                raise typer.BadParameter("Usage: loyalty rewards <list|redeem>")
            subaction = positionals[2]
            if subaction == "list":
                _emit(_request(method="GET", endpoint=endpoint, path="/loyalty/rewards", headers=headers))
                return
            if subaction == "redeem":
                _required(flags, "reward_id")
                _emit(_request(method="POST", endpoint=endpoint, path="/loyalty/rewards/redeem", headers=headers, body={"reward_id": flags["reward_id"]}))
                return

    if domain == "protocols" and action == "get":
        _required(flags, "trigger")
        context = flags.get("context", "{}")
        _emit(
            _request(
                method="POST",
                endpoint=endpoint,
                path="/protocols/get",
                headers=headers,
                body={"trigger": flags["trigger"], "context": json.loads(context)},
            )
        )
        return

    # Generic runtime fallback for future/extended command paths.
    # Keep support-hub delegated to the dedicated Support Hub CLI.
    if domain and action and domain != "support-hub":
        _emit(
            _request(
                method="POST",
                endpoint=endpoint,
                path=f"/{domain}/{action}",
                headers=headers,
                body=flags or None,
            )
        )
        return

    raise typer.BadParameter(f"Unknown command path: {' '.join(positionals)}")


def run() -> None:
    app()
