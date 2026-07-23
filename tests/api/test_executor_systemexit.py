# SPDX-License-Identifier: Apache-2.0
"""Executor handling of SystemExit codes (issue: string-code crash).

~105 CLI raise sites use the ``raise SystemExit("message")`` idiom,
where ``.code`` is the message string. The executor previously coerced
the code with ``int()``, crashing the handler and losing the message.
It now mirrors CPython: non-int codes print to stderr and exit 1.
"""

import os
import tempfile

from fastapi.testclient import TestClient

from zyra.api.server import app
from zyra.api.workers.executor import run_cli


def test_systemexit_string_message_surfaces_as_exit_1():
    # compose-video's missing-frames check is a real string-raise site.
    result = run_cli(
        "visualize",
        "compose-video",
        {"frames": "/definitely/not/a/dir", "output": "/tmp/out.mp4"},
    )
    assert result.exit_code == 1
    assert "Frames directory not found" in result.stderr


def test_systemexit_integer_code_preserved():
    # argparse rejects unknown flags with SystemExit(2); the integer
    # path must pass through unchanged.
    result = run_cli(
        "visualize",
        "compose-video",
        {"frames": "/tmp", "output": "/tmp/out.mp4", "bogus_flag": "1"},
    )
    assert result.exit_code == 2


def test_api_surfaces_message_as_execution_error(monkeypatch):
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(app)
    with tempfile.TemporaryDirectory() as td:
        missing = os.path.join(td, "no_frames_here")
        r = client.post(
            "/v1/visualize",
            json={
                "tool": "compose-video",
                "args": {"frames": missing, "output": os.path.join(td, "o.mp4")},
                "options": {"sync": True},
            },
            headers={"X-API-Key": "k"},
        )
    assert r.status_code == 200
    js = r.json()
    assert js.get("status") == "error"
    assert js.get("exit_code") == 1
    err = js.get("error") or {}
    assert err.get("type") == "execution_error"
    assert "Frames directory not found" in (err.get("message") or "")
