from __future__ import annotations

from gss_core.errors import GssError
from gss_core.security import matches_customer_identity, validate_resource_id


def test_validate_resource_id_accepts_safe_values() -> None:
    validate_resource_id(field_name="order_id", value="ORD-1001")
    validate_resource_id(field_name="order_id", value="abc_123")


def test_validate_resource_id_rejects_unsafe_values() -> None:
    try:
        validate_resource_id(field_name="order_id", value="ORD.1001")
        raise AssertionError("Expected GssError for invalid id")
    except GssError as exc:
        assert exc.code == "VALIDATION_ERROR"


def test_matches_customer_identity_is_case_insensitive() -> None:
    assert matches_customer_identity("User@example.com", "user@example.com")
    assert not matches_customer_identity("user@example.com", "other@example.com")
