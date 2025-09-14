# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

from zyra.api.server import create_app


class _Resp:
    def __init__(self, status=200, headers=None, content=b"{}"):
        self.status_code = status
        self.headers = headers or {"Content-Type": "application/json"}
        self.content = content
        self.text = content.decode("utf-8")


def test_api_auth_header_injected(monkeypatch):
    seen = {"headers": None}

    def fake_request(
        method,
        url,
        headers=None,
        params=None,
        data=None,
        timeout=None,
        stream=False,
        allow_redirects=True,
    ):  # noqa: ARG001
        seen["headers"] = headers
        return _Resp(200)

    import requests

    monkeypatch.setattr(requests, "request", fake_request)
    client = TestClient(create_app())
    r = client.post(
        "/v1/acquire/api",
        json={"url": "https://api.example/v1/items", "auth": "bearer:abc"},
    )
    assert r.status_code == 200
    assert seen["headers"]["Authorization"] == "Bearer abc"


def test_api_auth_header_basic(monkeypatch):
    seen = {"headers": None}

    def fake_request(
        method,
        url,
        headers=None,
        params=None,
        data=None,
        timeout=None,
        stream=False,
        allow_redirects=True,
    ):  # noqa: ARG001
        seen["headers"] = headers
        return _Resp(200)

    import requests

    monkeypatch.setattr(requests, "request", fake_request)
    client = TestClient(create_app())
    r = client.post(
        "/v1/acquire/api",
        json={"url": "https://api.example/v1/items", "auth": "basic:user:pass"},
    )
    assert r.status_code == 200
    assert seen["headers"]["Authorization"].startswith("Basic ")


def test_api_auth_header_custom(monkeypatch):
    seen = {"headers": None}

    def fake_request(
        method,
        url,
        headers=None,
        params=None,
        data=None,
        timeout=None,
        stream=False,
        allow_redirects=True,
    ):  # noqa: ARG001
        seen["headers"] = headers
        return _Resp(200)

    import requests

    monkeypatch.setattr(requests, "request", fake_request)
    client = TestClient(create_app())
    r = client.post(
        "/v1/acquire/api",
        json={"url": "https://api.example/v1/items", "auth": "header:X-Api-Key:xyz"},
    )
    assert r.status_code == 200
    assert seen["headers"]["X-Api-Key"] == "xyz"
