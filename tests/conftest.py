from __future__ import annotations

import os

# Keep legacy compatibility paths enabled for test fixtures that still rely on /auth/login.
os.environ.setdefault("GSS_ENABLE_LEGACY_LOGIN", "1")
os.environ.setdefault("GSS_ENABLE_AGENT_AUTH", "1")
