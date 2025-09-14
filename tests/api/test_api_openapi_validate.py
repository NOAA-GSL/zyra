# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from zyra.api.server import create_app


def _spec_required_q() -> dict:
    return {
        "openapi": "3.0.0",
        "paths": {
            "/v1/items": {
                "get": {
                    "parameters": [
                        {
                            "in": "query",
                            "name": "q",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                }
            }
        },
    }


def _spec_enum_and_type() -> dict:
    return {
        "openapi": "3.0.0",
        "paths": {
            "/v1/items": {
                "get": {
                    "parameters": [
                        {
                            "in": "query",
                            "name": "mode",
                            "required": False,
                            "schema": {"type": "string", "enum": ["a", "b"]},
                        },
                        {
                            "in": "query",
                            "name": "limit",
                            "required": False,
                            "schema": {"type": "integer"},
                        },
                    ],
                }
            }
        },
    }


def test_openapi_validate_missing_query_param(monkeypatch):
    client = TestClient(create_app())

    from zyra.connectors.openapi import validate as _ov

    monkeypatch.setattr(_ov, "load_openapi", lambda base: _spec_required_q())
    # Mock outbound request to avoid network when proceeding
    import requests

    def fake_request(method, url, **kwargs):  # noqa: ARG001
        class _R:
            status_code = 200
            headers = {"Content-Type": "application/json"}
            content = json.dumps({"ok": True}).encode("utf-8")

        return _R()

    monkeypatch.setattr(requests, "request", fake_request)
    r = client.post(
        "/v1/acquire/api",
        json={
            "url": "https://api.example/v1/items",
            "openapi_validate": True,
        },
    )
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body.get("errors"), list) and any(
        e.get("name") == "q" for e in body["errors"]
    )  # type: ignore[index]


def test_openapi_validate_ok_when_param_present(monkeypatch):
    client = TestClient(create_app())
    from zyra.connectors.openapi import validate as _ov

    monkeypatch.setattr(_ov, "load_openapi", lambda base: _spec_required_q())
    import requests

    def fake_request(method, url, **kwargs):  # noqa: ARG001
        class _R:
            status_code = 200
            headers = {"Content-Type": "application/json"}
            content = json.dumps({"ok": True}).encode("utf-8")

        return _R()

    monkeypatch.setattr(requests, "request", fake_request)
    r = client.post(
        "/v1/acquire/api",
        json={
            "url": "https://api.example/v1/items",
            "params": {"q": "wind"},
            "openapi_validate": True,
        },
    )
    # No validation errors; returns single-shot body
    assert r.status_code == 200
    assert r.headers.get("content-type") is not None


def test_openapi_validate_enum_violation(monkeypatch):
    client = TestClient(create_app())
    from zyra.connectors.openapi import validate as _ov

    monkeypatch.setattr(_ov, "load_openapi", lambda base: _spec_enum_and_type())
    import requests

    def fake_request(method, url, **kwargs):  # noqa: ARG001
        class _R:
            status_code = 200
            headers = {"Content-Type": "application/json"}
            content = json.dumps({"ok": True}).encode("utf-8")

        return _R()

    monkeypatch.setattr(requests, "request", fake_request)
    r = client.post(
        "/v1/acquire/api",
        json={
            "url": "https://api.example/v1/items",
            "params": {"mode": "c"},
            "openapi_validate": True,
        },
    )
    assert r.status_code == 400
    body = r.json()
    assert any("not in enum" in e.get("message", "") for e in body.get("errors", []))


def test_openapi_validate_type_violation(monkeypatch):
    client = TestClient(create_app())
    from zyra.connectors.openapi import validate as _ov

    monkeypatch.setattr(_ov, "load_openapi", lambda base: _spec_enum_and_type())
    import requests

    def fake_request(method, url, **kwargs):  # noqa: ARG001
        class _R:
            status_code = 200
            headers = {"Content-Type": "application/json"}
            content = json.dumps({"ok": True}).encode("utf-8")

        return _R()

    monkeypatch.setattr(requests, "request", fake_request)
    r = client.post(
        "/v1/acquire/api",
        json={
            "url": "https://api.example/v1/items",
            "params": {"limit": "abc"},
            "openapi_validate": True,
        },
    )
    assert r.status_code == 400
    assert any(
        "Invalid type" in e.get("message", "") for e in r.json().get("errors", [])
    )
