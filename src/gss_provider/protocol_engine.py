from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from gss_core.errors import err
from gss_provider.mock_data import enriched_context


class ProtocolEngine:
    def __init__(self, protocols_dir: Path) -> None:
        self.protocols_dir = protocols_dir

    def _path_for_trigger(self, trigger: str) -> Path:
        return self.protocols_dir / f"{trigger}.yaml"

    def _matches(self, condition: dict[str, Any], context: dict[str, Any]) -> bool:
        for key, expected in condition.items():
            actual = context.get(key)
            if isinstance(expected, dict):
                if "gte" in expected and not (actual is not None and actual >= expected["gte"]):
                    return False
                if "lte" in expected and not (actual is not None and actual <= expected["lte"]):
                    return False
                if "eq" in expected and actual != expected["eq"]:
                    return False
            elif actual != expected:
                return False
        return True

    def get(self, trigger: str, context_received: dict[str, Any]) -> dict[str, Any]:
        path = self._path_for_trigger(trigger)
        if not path.exists():
            raise err("PROTOCOL_NOT_FOUND", f"No protocol found for trigger '{trigger}'", status_code=404)
        payload = yaml.safe_load(path.read_text()) or {}
        context_enriched = dict(context_received)
        context_enriched.update(enriched_context(context_received.get("order_id")))

        selected = payload.get("default_response", {})
        selected_rule = "default"
        for rule in payload.get("rules", []):
            if self._matches(rule.get("when", {}), context_enriched):
                selected = rule.get("response", {})
                selected_rule = rule.get("id", "rule")
                break

        return {
            "trigger": trigger,
            "protocol_version": payload.get("version", "1.0"),
            "context_received": context_received,
            "context_enriched": context_enriched,
            "resolution": {
                "message_to_customer": selected.get("message_to_customer", ""),
                "actions": selected.get("actions", []),
                "requires_confirmation": selected.get("requires_confirmation", False),
            },
            "protocol_used": f"{trigger} {payload.get('version', '1.0')}, {selected_rule}",
        }
