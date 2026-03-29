from __future__ import annotations

from typing import Any

from .models import ErrorPayload, ResponseEnvelope


def ok(data: Any, request_id: str, channel: str | None = None) -> dict[str, Any]:
    meta: dict[str, Any] = {"request_id": request_id}
    if channel:
        meta["channel"] = channel
    return ResponseEnvelope(status="ok", data=data, error=None, meta=meta).model_dump()


def fail(
    code: str,
    message: str,
    request_id: str,
    details: dict[str, Any] | None = None,
    channel: str | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {"request_id": request_id}
    if channel:
        meta["channel"] = channel
    return ResponseEnvelope(
        status="error",
        data=None,
        error=ErrorPayload(code=code, message=message, details=details),
        meta=meta,
    ).model_dump()
