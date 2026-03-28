from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ShopifyProviderSettings:
    endpoint: str
    host: str
    port: int
    debug: bool
    shop_name: str
    shop_domain: str
    admin_token: str
    api_version: str
    token_ttl_seconds: int
    compliance_level: str
    certified: bool
    test_suite_version: str


def load_settings() -> ShopifyProviderSettings:
    return ShopifyProviderSettings(
        endpoint=os.getenv("GSS_PROVIDER_ENDPOINT", "http://127.0.0.1:8010/v1"),
        host=os.getenv("GSS_PROVIDER_HOST", "127.0.0.1"),
        port=int(os.getenv("GSS_PROVIDER_PORT", "8010")),
        debug=os.getenv("GSS_PROVIDER_DEBUG", "0").lower() in {"1", "true", "yes"},
        shop_name=os.getenv("GSS_SHOP_NAME", "Shopify Test Store"),
        shop_domain=os.getenv("SHOPIFY_SHOP_DOMAIN", ""),
        admin_token=os.getenv("SHOPIFY_ADMIN_TOKEN", ""),
        api_version=os.getenv("SHOPIFY_API_VERSION", "2024-10"),
        token_ttl_seconds=int(os.getenv("GSS_TOKEN_TTL_SECONDS", "3600")),
        compliance_level=os.getenv("GSS_COMPLIANCE_LEVEL", "basic"),
        certified=os.getenv("GSS_CERTIFIED", "false").lower() in {"1", "true", "yes"},
        test_suite_version=os.getenv("GSS_TEST_SUITE_VERSION", "unverified"),
    )
