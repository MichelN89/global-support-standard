from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GssError(Exception):
    code: str
    message: str
    status_code: int = 400
    details: dict[str, Any] | None = None


def err(
    code: str,
    message: str,
    *,
    status_code: int = 400,
    details: dict[str, Any] | None = None,
) -> GssError:
    return GssError(code=code, message=message, status_code=status_code, details=details)
