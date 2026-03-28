from __future__ import annotations

import re

from gss_core.errors import err

RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def validate_resource_id(*, field_name: str, value: str) -> None:
    if not RESOURCE_ID_RE.fullmatch(value):
        raise err(
            "VALIDATION_ERROR",
            f"Invalid {field_name} format",
            status_code=400,
            details={"field": field_name, "rule": RESOURCE_ID_RE.pattern},
        )


def matches_customer_identity(customer_id: str, *candidates: str | None) -> bool:
    normalized = customer_id.strip().lower()
    if not normalized:
        return False
    return any((candidate or "").strip().lower() == normalized for candidate in candidates)
