# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from starlette.requests import Request

from zyra.api.models.cli_request import CLIRunRequest, CLIRunResponse
from zyra.api.models.domain_api import (
    AcquireFtpRun,
    AcquireHttpRun,
    DecimateFtpRun,
    DecimatePostRun,
)
from zyra.api.routers import domain_acquire, domain_disseminate
from zyra.api.schemas.domain_args import (
    AcquireFtpArgs,
    AcquireHttpArgs,
    DecimateFtpArgs,
    DecimatePostArgs,
)
from zyra.api.server import app


def test_decimate_domain_local_sync(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(app)
    out_path = tmp_path / "ok.bin"
    body = {
        "tool": "local",
        "args": {"input": "-", "output": str(out_path)},
        "options": {"mode": "sync"},
    }
    r = client.post("/v1/decimate", json=body, headers={"X-API-Key": "k"})
    assert r.status_code == 200
    js = r.json()
    assert js.get("status") == "ok"
    assert js.get("exit_code") in (0, None)
    assert out_path.exists()
    # Assets should include the written file
    assets = js.get("assets") or []
    assert any(a.get("uri") == str(out_path) for a in assets)


def test_process_domain_invalid_tool(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(app)
    r = client.post(
        "/v1/process",
        json={"tool": "nope", "args": {}},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 400
    js = r.json()
    assert "error" in js and isinstance(js["error"], dict)


def test_acquire_transform_invalid_tool(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(app)
    for path in ("/v1/acquire", "/v1/transform"):
        r = client.post(
            path, json={"tool": "nope", "args": {}}, headers={"X-API-Key": "k"}
        )
        assert r.status_code == 400
        js = r.json()
        assert "error" in js and isinstance(js["error"], dict)


def test_visualize_contour_validation_error(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(app)
    # Missing required args (input/output) should trigger validation_error
    r = client.post(
        "/v1/visualize",
        json={"tool": "contour", "args": {}},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 400
    js = r.json()
    assert js.get("status") == "error"
    assert js.get("error", {}).get("type") == "validation_error"


def test_decimate_post_validation_error(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(app)
    # Missing url should trigger validation_error
    r = client.post(
        "/v1/decimate",
        json={"tool": "post", "args": {"input": "-"}},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 400
    js = r.json()
    assert js.get("status") == "error"
    assert js.get("error", {}).get("type") == "validation_error"


def test_process_extract_variable_validation_error(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(app)
    # Missing required 'pattern' should fail validation
    r = client.post(
        "/v1/process",
        json={
            "tool": "extract-variable",
            "args": {"file_or_url": "samples/demo.grib2"},
        },
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 400
    js = r.json()
    assert js.get("status") == "error"
    assert js.get("error", {}).get("type") == "validation_error"


def test_acquire_s3_validation_error(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(app)
    # Missing both url and bucket should fail validation
    r = client.post(
        "/v1/acquire",
        json={"tool": "s3", "args": {}},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 400
    js = r.json()
    assert js.get("status") == "error"
    assert js.get("error", {}).get("type") == "validation_error"


def test_execution_error_mapping_sync(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(app)
    # Run a known failing command (missing file) via domain endpoint and
    # expect status=error with standardized error envelope
    r = client.post(
        "/v1/process",
        json={
            "tool": "decode-grib2",
            "args": {"file_or_url": str(tmp_path / "missing.grib2")},
            "options": {"mode": "sync"},
        },
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 200
    js = r.json()
    assert js.get("status") == "error"
    err = js.get("error", {})
    assert err.get("type") == "execution_error"
    # exit_code should be present in details
    assert isinstance(err.get("details", {}).get("exit_code"), int)


def test_domain_request_size_limit(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    monkeypatch.setenv("ZYRA_DOMAIN_MAX_BODY_BYTES", "100")
    client = TestClient(app)
    # Big pad to exceed limit
    pad = "x" * 200
    r = client.post(
        "/process",
        json={"tool": "decode-grib2", "args": {"file_or_url": "-", "pad": pad}},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 413
    js = r.json()
    assert js.get("status") == "error"
    assert js.get("error", {}).get("type") == "request_too_large"


def test_visualize_animate_validation_error(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(app)
    # Missing output_dir should fail validation
    r = client.post(
        "/visualize",
        json={"tool": "animate", "args": {"input": "samples/demo.npy"}},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 400
    js = r.json()
    assert js.get("status") == "error"
    assert js.get("error", {}).get("type") == "validation_error"


def test_acquire_http_credentials_to_cli(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    captured: dict[str, CLIRunRequest] = {}

    def fake_run(req, bg):  # noqa: ANN001
        captured["req"] = req
        return CLIRunResponse(status="success", exit_code=0)

    monkeypatch.setattr(domain_acquire, "run_cli_endpoint", fake_run)
    monkeypatch.setattr(
        domain_acquire,
        "get_cli_matrix",
        lambda: {"acquire": {"commands": ["http", "ftp"]}},
    )

    args = AcquireHttpArgs(
        url="https://example.com/data.bin",
        headers={"Accept": "application/json"},
        credentials={"token": "$API_TOKEN"},
        credential_file="/tmp/.env",
        auth="bearer:$API_TOKEN",
    )
    req_model = AcquireHttpRun(tool="http", args=args)

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/acquire",
        "headers": [],
        "query_string": b"",
    }
    request = Request(scope, _receive)
    response = domain_acquire.acquire_run(req_model, BackgroundTasks(), request)

    assert response.status == "ok"
    req = captured.get("req")
    assert req is not None
    assert req.stage == "acquire"
    assert req.command == "http"
    args_dict = req.args
    assert args_dict.get("url") == "https://example.com/data.bin"
    assert sorted(args_dict.get("header") or []) == ["Accept: application/json"]
    assert sorted(args_dict.get("credential") or []) == ["token=$API_TOKEN"]
    assert args_dict.get("credential_file") == "/tmp/.env"
    assert args_dict.get("auth") == "bearer:$API_TOKEN"


def test_acquire_ftp_credentials_to_cli(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    captured: dict[str, CLIRunRequest] = {}

    def fake_run(req, bg):  # noqa: ANN001
        captured["req"] = req
        return CLIRunResponse(status="success", exit_code=0)

    monkeypatch.setattr(domain_acquire, "run_cli_endpoint", fake_run)
    monkeypatch.setattr(
        domain_acquire,
        "get_cli_matrix",
        lambda: {"acquire": {"commands": ["http", "ftp"]}},
    )

    args = AcquireFtpArgs(
        path="ftp://example.com/data.bin",
        user="demo",
        credentials={"password": "@FTP_PASS"},
    )
    req_model = AcquireFtpRun(tool="ftp", args=args)

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/acquire",
        "headers": [],
        "query_string": b"",
    }
    request = Request(scope, _receive)
    response = domain_acquire.acquire_run(req_model, BackgroundTasks(), request)

    assert response.status == "ok"
    req = captured.get("req")
    assert req is not None
    assert req.stage == "acquire"
    assert req.command == "ftp"
    args_dict = req.args
    assert args_dict.get("path") == "ftp://example.com/data.bin"
    assert args_dict.get("user") == "demo"
    assert sorted(args_dict.get("credential") or []) == ["password=@FTP_PASS"]


def test_decimate_post_credentials_to_cli(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    captured: dict[str, CLIRunRequest] = {}

    def fake_run(req, bg):  # noqa: ANN001
        captured["req"] = req
        return CLIRunResponse(status="success", exit_code=0)

    monkeypatch.setattr(domain_disseminate, "run_cli_endpoint", fake_run)
    monkeypatch.setattr(
        domain_disseminate,
        "get_cli_matrix",
        lambda: {"decimate": {"commands": ["post", "ftp"]}},
    )

    args = DecimatePostArgs(
        input="-",
        url="https://example.com/upload",
        content_type="application/json",
        headers={"Accept": "application/json"},
        credentials={"token": "$EXPORT_TOKEN"},
        credential_file="/tmp/.env",
        auth="bearer:$EXPORT_TOKEN",
    )
    req_model = DecimatePostRun(tool="post", args=args)

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/disseminate",
        "headers": [],
        "query_string": b"",
    }
    request = Request(scope, _receive)
    response = domain_disseminate._run(
        "disseminate", req_model, BackgroundTasks(), request
    )

    assert response.status == "ok"
    req = captured.get("req")
    assert req is not None
    assert req.stage == "decimate"
    assert req.command == "post"
    args_dict = req.args
    assert args_dict.get("url") == "https://example.com/upload"
    assert sorted(args_dict.get("header") or []) == ["Accept: application/json"]
    assert sorted(args_dict.get("credential") or []) == ["token=$EXPORT_TOKEN"]
    assert args_dict.get("credential_file") == "/tmp/.env"
    assert args_dict.get("auth") == "bearer:$EXPORT_TOKEN"


def test_decimate_ftp_credentials_to_cli(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    captured: dict[str, CLIRunRequest] = {}

    def fake_run(req, bg):  # noqa: ANN001
        captured["req"] = req
        return CLIRunResponse(status="success", exit_code=0)

    monkeypatch.setattr(domain_disseminate, "run_cli_endpoint", fake_run)
    monkeypatch.setattr(
        domain_disseminate,
        "get_cli_matrix",
        lambda: {"decimate": {"commands": ["post", "ftp"]}},
    )

    args = DecimateFtpArgs(
        input="-",
        path="ftp://example.com/data.bin",
        user="demo",
        credentials={"password": "@FTP_PASS"},
    )
    req_model = DecimateFtpRun(tool="ftp", args=args)

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/disseminate",
        "headers": [],
        "query_string": b"",
    }
    request = Request(scope, _receive)
    response = domain_disseminate._run(
        "disseminate", req_model, BackgroundTasks(), request
    )

    assert response.status == "ok"
    req = captured.get("req")
    assert req is not None
    assert req.stage == "decimate"
    assert req.command == "ftp"
    args_dict = req.args
    assert args_dict.get("path") == "ftp://example.com/data.bin"
    assert args_dict.get("user") == "demo"
    assert sorted(args_dict.get("credential") or []) == ["password=@FTP_PASS"]
