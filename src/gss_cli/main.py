from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
import typer

app = typer.Typer(add_completion=False, no_args_is_help=True)
TOKEN_PATH = Path.home() / ".gss" / "tokens.json"


def _shop_env_key(shop: str) -> str:
    normalized = "".join(c if c.isalnum() else "_" for c in shop).upper()
    return f"GSS_SHOP_{normalized}_ENDPOINT"


def _resolve_endpoint(shop: str) -> str:
    return os.getenv(_shop_env_key(shop), os.getenv("GSS_DEFAULT_ENDPOINT", "http://127.0.0.1:8000/v1"))


def _load_tokens() -> dict[str, str]:
    if not TOKEN_PATH.exists():
        return {}
    return json.loads(TOKEN_PATH.read_text())


def _save_tokens(tokens: dict[str, str]) -> None:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(tokens, indent=2))


def _token_for(shop: str) -> str | None:
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


def _headers(shop: str) -> dict[str, str]:
    token = _token_for(shop)
    if not token:
        raise typer.BadParameter(f"No auth token for {shop}. Run: gss {shop} auth login --method api_key")
    return {
        "Authorization": f"Bearer {token}",
        "GSS-Consumer-Id": os.getenv("GSS_CONSUMER_ID", "support-squad-ai"),
        "GSS-Consumer-Type": os.getenv("GSS_CONSUMER_TYPE", "ai_agent"),
        "GSS-Version": "1.0",
    }


def _request(
    *,
    method: str,
    endpoint: str,
    path: str,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with httpx.Client(timeout=20.0) as client:
        response = client.request(method, f"{endpoint}{path}", headers=headers, params=params, json=body)
    data = response.json()
    if response.status_code >= 400:
        msg = data.get("error", {}).get("message", "Request failed")
        raise typer.BadParameter(msg)
    return data


def _emit(value: dict[str, Any]) -> None:
    typer.echo(json.dumps(value, indent=2))


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    add_help_option=True,
)
def main(ctx: typer.Context, shop: str, parts: list[str] = typer.Argument(...)) -> None:
    endpoint = _resolve_endpoint(shop)
    positionals, flags = _parse_flags(parts + list(ctx.args))

    if not positionals:
        raise typer.BadParameter("Expected command pattern: gss <shop> <domain> <action>")

    if positionals[0] == "describe":
        _emit(_request(method="GET", endpoint=endpoint, path="/describe"))
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
        tokens = _load_tokens()
        tokens[shop] = token
        _save_tokens(tokens)
        _emit(res)
        return

    if action == "describe":
        _emit(_request(method="GET", endpoint=endpoint, path=f"/{domain}/describe"))
        return

    headers = _headers(shop)

    if domain == "orders" and action == "list":
        _emit(_request(method="GET", endpoint=endpoint, path="/orders", headers=headers, params=flags))
        return
    if domain == "orders" and action == "get":
        _emit(_request(method="GET", endpoint=endpoint, path=f"/orders/{flags['id']}", headers=headers))
        return
    if domain == "shipping" and action == "track":
        _emit(_request(method="GET", endpoint=endpoint, path=f"/shipping/track/{flags['order_id']}", headers=headers))
        return
    if domain == "returns" and action == "check-eligibility":
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
    if domain == "returns" and action == "initiate":
        _emit(
            _request(
                method="POST",
                endpoint=endpoint,
                path="/returns/initiate",
                headers=headers,
                body={
                    "order_id": flags["order_id"],
                    "item_id": flags["item_id"],
                    "reason": flags["reason"],
                },
            )
        )
        return
    if domain == "returns" and action == "confirm":
        _emit(
            _request(
                method="POST",
                endpoint=endpoint,
                path="/returns/confirm",
                headers=headers,
                body={"token": flags["token"]},
            )
        )
        return
    if domain == "protocols" and action == "get":
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
    if domain == "account" and action == "audit-log":
        _emit(_request(method="GET", endpoint=endpoint, path="/account/audit-log", headers=headers))
        return

    raise typer.BadParameter(f"Unknown command path: {' '.join(positionals)}")


def run() -> None:
    app()
