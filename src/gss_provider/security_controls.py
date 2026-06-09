from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime

from gss_core.actions import action_by_path, scope_for


def required_scope(path: str, method: str) -> str | None:
    if not path.startswith("/v1/"):
        return None
    if path in {"/v1/describe"} or path.endswith("/describe"):
        return None
    if path.startswith("/v1/auth/"):
        return None
    # The shared action registry is the source of truth for scopes. It encodes
    # read-level-on-POST exceptions (e.g. returns check-eligibility) declaratively.
    action = action_by_path(method, path)
    if action is not None:
        return scope_for(action)
    # Fallback for any path not (yet) modelled in the registry: same heuristic
    # the standard has always used.
    domain = path.split("/")[2]
    level = "read" if method.upper() == "GET" else "request"
    return f"{domain}:{level}"


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[datetime]] = defaultdict(deque)

    def allow(self, *, bucket: str, client_id: str, window_seconds: int, max_requests: int) -> bool:
        now = datetime.now(UTC)
        key = f"{bucket}:{client_id}"
        hits = self._hits[key]
        while hits and (now - hits[0]).total_seconds() > window_seconds:
            hits.popleft()
        if len(hits) >= max_requests:
            return False
        hits.append(now)
        return True
