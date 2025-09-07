from __future__ import annotations

from fastapi.testclient import TestClient
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
    r = client.post("/decimate", json=body, headers={"X-API-Key": "k"})
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
        "/process",
        json={"tool": "nope", "args": {}},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 400
    js = r.json()
    assert "error" in js and isinstance(js["error"], dict)


def test_acquire_transform_invalid_tool(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(app)
    for path in ("/acquire", "/transform"):
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
        "/visualize",
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
        "/decimate",
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
        "/process",
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
        "/acquire",
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
        "/process",
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
