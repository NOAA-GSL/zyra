# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest


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
