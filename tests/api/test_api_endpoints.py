import time

import pytest
from fastapi.testclient import TestClient

from datavizhub.api.server import app


client = TestClient(app)


def test_arg_aliases_normalization_internal():
    # Validate internal normalization path for friendliness
    from datavizhub.api.workers.executor import _normalize_args

    args = _normalize_args("process", "convert-format", {"src": "in", "dest": "out.nc"})
    assert args["file_or_url"] == "in"
    assert args["output"] == "out.nc"

    args2 = _normalize_args("decimate", "local", {"src": "-", "dest": "./o.bin"})
    assert args2["input"] == "-"
    assert args2["path"] == "./o.bin"


def test_sync_cli_run_success_and_failure(tmp_path):
    # Success: decimate local should write 0-byte file from stdin '-'
    out_path = tmp_path / "ok.bin"
    resp = client.post(
        "/cli/run",
        json={
            "stage": "decimate",
            "command": "local",
            "args": {"input": "-", "output": str(out_path)},
            "mode": "sync",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["exit_code"] == 0
    assert out_path.exists()

    # Failure: process decode-grib2 on nonexistent file should error
    resp2 = client.post(
        "/cli/run",
        json={
            "stage": "process",
            "command": "decode-grib2",
            "args": {"input": str(tmp_path / "missing.grib2")},
            "mode": "sync",
        },
    )
    assert resp2.status_code == 200
    d2 = resp2.json()
    assert d2["exit_code"] != 0


@pytest.mark.redis
def test_async_job_lifecycle_and_ws(tmp_path):
    # Submit async job that will quickly fail (nonexistent input) to exercise lifecycle
    r = client.post(
        "/cli/run",
        json={
            "stage": "process",
            "command": "decode-grib2",
            "args": {"input": str(tmp_path / "missing.grib2")},
            "mode": "async",
        },
    )
    assert r.status_code == 200
    job_id = r.json().get("job_id")
    assert job_id

    # WebSocket stream: expect at least a final payload
    with client.websocket_connect(f"/ws/jobs/{job_id}") as ws:
        seen_stdout = False
        seen_stderr = False
        seen_final = False
        t0 = time.time()
        while time.time() - t0 < 5.0:
            try:
                msg = ws.receive_json(timeout=5)
            except Exception:
                break
            if "stdout" in msg:
                seen_stdout = True
            if "stderr" in msg:
                seen_stderr = True
            if "exit_code" in msg:
                seen_final = True
                break
        assert seen_final or seen_stdout or seen_stderr

    # Poll status until finished
    for _ in range(10):
        s = client.get(f"/jobs/{job_id}")
        assert s.status_code == 200
        body = s.json()
        if body["status"] in {"succeeded", "failed", "canceled"}:
            assert "exit_code" in body
            break
        time.sleep(0.2)
