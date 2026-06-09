from __future__ import annotations

import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


@dataclass(frozen=True)
class ProviderSettings:
    protocol_dir: Path
    endpoint: str
    host: str
    port: int
    debug: bool
    token_ttl_seconds: int
    confirmation_ttl_seconds: int
    compliance_level: str
    certified: bool
    test_suite_version: str
    enable_legacy_login: bool = False
    enable_agent_auth: bool = False
    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = 60
    rate_limit_auth_max_requests: int = 30
    rate_limit_data_max_requests: int = 120
    intent_summary: str = (
        "GSS handles post-purchase customer support self-service on behalf of an "
        "authenticated customer."
    )
    intent_in_scope: tuple[str, ...] = (
        "order status and history",
        "returns, refunds and exchanges",
        "shipping and delivery issues",
        "account, subscription and loyalty management",
        "reading the shop's resolution protocols",
        "escalating to a human when self-service cannot resolve the request",
    )
    intent_out_of_scope: tuple[str, ...] = (
        "browsing, search or product recommendations",
        "placing new orders or shopping",
        "payments not tied to an existing order",
        "actions requiring human-only identity proof",
    )


def _csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None:
        return default
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _default_protocol_dir() -> Path:
    # Dev mode: use repository protocols directory when running from source tree.
    repo_candidate = Path(__file__).resolve().parents[2] / "protocols"
    if repo_candidate.exists():
        return repo_candidate
    # Installed mode: fallback to bundled package data.
    return Path(resources.files("gss_provider").joinpath("protocols"))


def load_settings() -> ProviderSettings:
    return ProviderSettings(
        protocol_dir=Path(os.getenv("GSS_PROTOCOL_DIR", str(_default_protocol_dir()))),
        endpoint=os.getenv("GSS_PROVIDER_ENDPOINT", "http://127.0.0.1:8000/v1"),
        host=os.getenv("GSS_PROVIDER_HOST", "127.0.0.1"),
        port=int(os.getenv("GSS_PROVIDER_PORT", "8000")),
        debug=os.getenv("GSS_PROVIDER_DEBUG", "0").lower() in {"1", "true", "yes"},
        token_ttl_seconds=int(os.getenv("GSS_TOKEN_TTL_SECONDS", "3600")),
        confirmation_ttl_seconds=int(os.getenv("GSS_CONFIRMATION_TTL_SECONDS", "900")),
        compliance_level=os.getenv("GSS_COMPLIANCE_LEVEL", "basic"),
        certified=os.getenv("GSS_CERTIFIED", "false").lower() in {"1", "true", "yes"},
        test_suite_version=os.getenv("GSS_TEST_SUITE_VERSION", "unverified"),
        enable_legacy_login=os.getenv("GSS_ENABLE_LEGACY_LOGIN", "0").lower() in {"1", "true", "yes"},
        enable_agent_auth=os.getenv("GSS_ENABLE_AGENT_AUTH", "0").lower() in {"1", "true", "yes"},
        rate_limit_enabled=os.getenv("GSS_RATE_LIMIT_ENABLED", "1").lower() in {"1", "true", "yes"},
        rate_limit_window_seconds=int(os.getenv("GSS_RATE_LIMIT_WINDOW_SECONDS", "60")),
        rate_limit_auth_max_requests=int(os.getenv("GSS_RATE_LIMIT_AUTH_MAX_REQUESTS", "30")),
        rate_limit_data_max_requests=int(os.getenv("GSS_RATE_LIMIT_DATA_MAX_REQUESTS", "120")),
        intent_summary=os.getenv("GSS_INTENT_SUMMARY", ProviderSettings.intent_summary),
        intent_in_scope=_csv_env("GSS_INTENT_IN_SCOPE", ProviderSettings.intent_in_scope),
        intent_out_of_scope=_csv_env("GSS_INTENT_OUT_OF_SCOPE", ProviderSettings.intent_out_of_scope),
    )
