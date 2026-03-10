# SPDX-License-Identifier: Apache-2.0
"""Regression test: stage='search' must be accepted by POST /v1/cli/run."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from zyra.api.server import app
from zyra.api.workers.executor import RunResult


def test_cli_run_accepts_search_stage():
    """POST /v1/cli/run with stage='search' must not return 422 or 400."""
    client = TestClient(app)
    # Patch run_cli to avoid actually executing the CLI command
    with patch(
        "zyra.api.routers.cli.run_cli",
        return_value=RunResult(stdout="ok", stderr="", exit_code=0),
    ):
        r = client.post(
            "/v1/cli/run",
            json={
                "stage": "search",
                "command": "api",
                "args": {"url": "https://example.com/api", "api_query": "temperature"},
            },
        )
    assert r.status_code == 200, f"unexpected status: {r.json()}"
    body = r.json()
    assert body.get("status") == "success"
    assert body.get("stdout") == "ok"
