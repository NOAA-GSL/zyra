# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from zyra.api.server import create_app


@pytest.fixture(autouse=True)
def _force_inmemory_for_mcp_ws(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
):
    """Force in-memory job mode for MCP WS tests only.

    Tests marked with ``@pytest.mark.mcp_ws`` will have Redis disabled so that
    async job execution runs in-process and progress frames are published.
    """
    if request.node.get_closest_marker("mcp_ws") is not None:
        monkeypatch.setenv("ZYRA_USE_REDIS", "0")
        monkeypatch.setenv("DATAVIZHUB_USE_REDIS", "0")


@pytest.fixture(autouse=True, scope="session")
def _api_speed_defaults():
    """Speed up API tests by disabling heavy extras and dotenv loading.

    - Disable MCP to avoid extra routers and schema bloat
    - Force in-memory (no Redis) for all tests by default
    - Skip .env loading to avoid bringing in devcontainer flags/secrets
    - Remove any auth-induced delays
    """
    import os

    os.environ["ZYRA_ENABLE_MCP"] = "0"
    os.environ["ENABLE_MCP"] = "0"
    os.environ["ZYRA_USE_REDIS"] = "0"
    os.environ["DATAVIZHUB_USE_REDIS"] = "0"
    os.environ["ZYRA_SKIP_DOTENV"] = "1"
    # Ensure auth is disabled and no failure sleep applies
    os.environ.pop("API_KEY", None)
    os.environ["AUTH_FAIL_DELAY_MS"] = "0"


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Session-scoped TestClient to avoid repeated app startup in API tests."""
    return TestClient(create_app())


@pytest.fixture(scope="session")
def client_mcp() -> TestClient:
    """Session-scoped TestClient with MCP enabled.

    Overrides the autouse defaults to include MCP routers in the app.
    """
    import os as _os

    _os.environ["ZYRA_ENABLE_MCP"] = "1"
    return TestClient(create_app())
