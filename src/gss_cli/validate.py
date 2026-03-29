from __future__ import annotations

from typing import Any


def _check(required: bool, condition: bool, message: str) -> dict[str, Any]:
    return {
        "level": "MUST" if required else "SHOULD",
        "ok": condition,
        "message": message,
    }


def run_validate(
    *,
    shop: str,
    endpoint: str,
    level: str,
    request_fn,
) -> dict[str, Any]:
    describe = request_fn(method="GET", endpoint=endpoint, path="/describe")
    data = describe.get("data", {})
    compliance = data.get("compliance") if isinstance(data.get("compliance"), dict) else {}
    policies = data.get("consumer_policies") if isinstance(data.get("consumer_policies"), dict) else {}

    checks: list[dict[str, Any]] = [
        _check(True, isinstance(data.get("shop"), str), "Describe exposes shop identifier"),
        _check(True, isinstance(data.get("auth_methods"), list), "Describe exposes auth methods"),
        _check(True, isinstance(data.get("endpoint"), str), "Describe exposes endpoint"),
        _check(level != "basic", isinstance(data.get("domains"), list), "Describe exposes supported domains"),
        _check(level == "complete", isinstance(data.get("channels"), list), "Describe exposes channels metadata"),
        _check(False, isinstance(compliance.get("test_suite_version"), str), "Compliance test suite is published"),
        _check(False, isinstance(policies.get("requires_customer_auth_for_data"), bool), "Consumer policies are published"),
    ]
    failed_must = [c for c in checks if c["level"] == "MUST" and not c["ok"]]
    failed_should = [c for c in checks if c["level"] == "SHOULD" and not c["ok"]]
    return {
        "shop": shop,
        "level": level,
        "result": "pass" if not failed_must else "fail",
        "failed_must": len(failed_must),
        "failed_should": len(failed_should),
        "checks": checks,
    }
