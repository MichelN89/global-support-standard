from __future__ import annotations

from gss_provider.settings import load_settings


def test_default_protocol_dir_is_resolvable() -> None:
    settings = load_settings()
    assert settings.protocol_dir.exists()
    assert (settings.protocol_dir / "delivery-not-received.yaml").exists()
