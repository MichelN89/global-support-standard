from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from typer.testing import CliRunner

import gss_cli.main as cli_main
from gss_provider.app import app


def _install_test_transport(monkeypatch, client: TestClient) -> None:
    def fake_request(
        *,
        method: str,
        endpoint: str,
        path: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = client.request(method, f"/v1{path}", headers=headers, params=params, json=body)
        return response.json()

    monkeypatch.setattr(cli_main, "_request", fake_request)


def test_cli_login_then_orders_list(monkeypatch, tmp_path: Path) -> None:
    client = TestClient(app)
    _install_test_transport(monkeypatch, client)
    monkeypatch.setattr(cli_main, "TOKEN_PATH", tmp_path / "tokens.json")

    runner = CliRunner()
    login = runner.invoke(cli_main.app, ["mockshop.local", "auth", "login", "--method", "api_key"])
    assert login.exit_code == 0, login.output
    login_payload = json.loads(login.output)
    assert login_payload["status"] == "ok"

    orders = runner.invoke(cli_main.app, ["mockshop.local", "orders", "list"])
    assert orders.exit_code == 0, orders.output
    orders_payload = json.loads(orders.output)
    assert orders_payload["status"] == "ok"
    assert isinstance(orders_payload["data"], list)


def test_cli_returns_two_step_flow(monkeypatch, tmp_path: Path) -> None:
    client = TestClient(app)
    _install_test_transport(monkeypatch, client)
    monkeypatch.setattr(cli_main, "TOKEN_PATH", tmp_path / "tokens.json")

    runner = CliRunner()
    runner.invoke(cli_main.app, ["mockshop.local", "auth", "login", "--method", "api_key"])

    initiate = runner.invoke(
        cli_main.app,
        [
            "mockshop.local",
            "returns",
            "initiate",
            "--order-id",
            "ORD-1001",
            "--item-id",
            "ITEM-1",
            "--reason",
            "defective",
        ],
    )
    assert initiate.exit_code == 0, initiate.output
    payload = json.loads(initiate.output)
    token = payload["data"]["confirmation_token"]

    confirm = runner.invoke(cli_main.app, ["mockshop.local", "returns", "confirm", "--token", token])
    assert confirm.exit_code == 0, confirm.output
    assert json.loads(confirm.output)["data"]["status"] == "submitted"


def test_cli_describe_warns_if_uncertified(monkeypatch, tmp_path: Path) -> None:
    client = TestClient(app)
    _install_test_transport(monkeypatch, client)
    monkeypatch.setattr(cli_main, "TOKEN_PATH", tmp_path / "tokens.json")
    runner = CliRunner()
    res = runner.invoke(cli_main.app, ["mockshop.local", "describe"])
    assert res.exit_code == 0, res.output
    assert "not GSS certified" in res.stderr


def test_cli_channel_flag_passed_to_provider(monkeypatch, tmp_path: Path) -> None:
    client = TestClient(app)
    _install_test_transport(monkeypatch, client)
    monkeypatch.setattr(cli_main, "TOKEN_PATH", tmp_path / "tokens.json")
    runner = CliRunner()
    runner.invoke(cli_main.app, ["mockshop.local", "auth", "login", "--method", "api_key"])
    res = runner.invoke(
        cli_main.app,
        ["mockshop.local", "shipping", "track", "--order-id", "ORD-1002", "--channel", "email"],
    )
    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert payload["meta"]["channel"] == "email"


def test_cli_validate_command(monkeypatch, tmp_path: Path) -> None:
    client = TestClient(app)
    _install_test_transport(monkeypatch, client)
    monkeypatch.setattr(cli_main, "TOKEN_PATH", tmp_path / "tokens.json")
    runner = CliRunner()
    res = runner.invoke(cli_main.app, ["validate", "mockshop.local", "--level", "basic"])
    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert payload["shop"] == "mockshop.local"
    assert payload["level"] == "basic"
