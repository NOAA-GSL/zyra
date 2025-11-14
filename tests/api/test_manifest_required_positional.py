# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from fastapi.testclient import TestClient

from zyra.api.server import app


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    return TestClient(app)


def test_required_positional_decode_grib2(monkeypatch) -> None:
    client = _client(monkeypatch)
    r = client.get("/v1/commands", headers={"X-API-Key": "k"})
    assert r.status_code == 200
    body = r.json()
    cmds = body.get("commands") or {}
    assert isinstance(cmds, dict)
    key = "process decode-grib2"
    assert key in cmds, f"missing {key} in manifest"
    pos = cmds[key].get("positionals") or []
    assert any(
        (p.get("name") == "file_or_url" and bool(p.get("required")) is True)
        for p in pos
    ), f"file_or_url should be required for {key}"


def test_optional_positional_convert_format(monkeypatch) -> None:
    client = _client(monkeypatch)
    r = client.get("/v1/commands", headers={"X-API-Key": "k"})
    assert r.status_code == 200
    body = r.json()
    cmds = body.get("commands") or {}
    key = "process convert-format"
    assert key in cmds, f"missing {key} in manifest"
    pos = cmds[key].get("positionals") or []
    # convert-format has file_or_url as an optional positional (nargs='?')
    assert any(
        (p.get("name") == "file_or_url" and bool(p.get("required")) is False)
        for p in pos
    ), f"file_or_url should be optional for {key}"


def test_commands_domain_filter(monkeypatch) -> None:
    client = _client(monkeypatch)
    r = client.get("/v1/commands?domain=visualize", headers={"X-API-Key": "k"})
    assert r.status_code == 200
    body = r.json()
    cmds = body.get("commands") or {}
    assert "visualize heatmap" in cmds
    assert "acquire http" not in cmds


def test_commands_hash_endpoint(monkeypatch) -> None:
    client = _client(monkeypatch)
    r = client.get("/v1/commands/hash", headers={"X-API-Key": "k"})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data.get("sha256"), str) and len(data["sha256"]) == 64
