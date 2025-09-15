# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from typing import Any

import pytest

from zyra.api.routers.api_generic import acquire_api
from zyra.api.schemas.domain_args import AcquireApiArgs


def test_acquire_api_blocks_private_ip_and_http_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # By default HTTPS-only and public-only
    monkeypatch.delenv("ZYRA_API_FETCH_HTTPS_ONLY", raising=False)

    # Private IP
    with pytest.raises(Exception):
        acquire_api(AcquireApiArgs(url="http://127.0.0.1/", head_first=True))


def test_acquire_api_head_first_uses_no_redirects_and_strips_hop_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, Any] = {}

    def _ga(*args, **kwargs):  # noqa: ARG001
        # Resolve to a public IP to pass DNS checks
        host = args[0] if args else "93.184.216.34"
        port = args[1] if len(args) > 1 else 80
        return [(0, 0, 0, "", ("93.184.216.34", port))]

    class _Resp:
        headers = {"Content-Type": "application/json"}

    def _head(
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        allow_redirects: bool = True,
        timeout: int = 60,
    ):  # noqa: ARG001
        called["headers"] = dict(headers or {})
        called["allow_redirects"] = allow_redirects
        return _Resp()

    monkeypatch.setenv("ZYRA_API_FETCH_HTTPS_ONLY", "false")
    monkeypatch.setattr("socket.getaddrinfo", _ga)
    monkeypatch.setattr("requests.head", _head)
    # Avoid network in follow-up single-shot call
    from zyra.connectors.backends import api as backend

    monkeypatch.setattr(
        backend,
        "request_with_retries",
        lambda *a, **k: (200, {"Content-Type": "application/json"}, b"{}"),
    )

    acquire_api(
        AcquireApiArgs(
            url="http://example.com/",
            head_first=True,
            headers={
                "Host": "evil",
                "X-Forwarded-For": "1.2.3.4",
                "X-Real-IP": "1.2.3.4",
                "Forwarded": "for=1.2.3.4",
                "Accept": "*/*",
            },
        )
    )
    sent = called.get("headers", {})
    assert "Host" not in sent
    assert "X-Forwarded-For" not in sent
    assert "X-Real-IP" not in sent
    assert "Forwarded" not in sent
    assert called.get("allow_redirects") is False


def test_streaming_blocks_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    def _ga(host: str, port: int, proto: int):  # noqa: ARG001
        return [(0, 0, 0, "", ("93.184.216.34", port))]

    class _Resp:
        status_code = 200
        headers = {"Content-Type": "text/plain"}

        def iter_content(self, chunk_size: int = 1024):  # noqa: ARG002
            yield b"ok"

    called = {"allow_redirects": None}

    def _req(
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        data: Any | None = None,
        timeout: int = 60,
        stream: bool = False,
        allow_redirects: bool = True,
    ):  # noqa: ARG001
        called["allow_redirects"] = allow_redirects
        return _Resp()

    monkeypatch.setenv("ZYRA_API_FETCH_HTTPS_ONLY", "false")
    monkeypatch.setattr("socket.getaddrinfo", _ga)
    monkeypatch.setattr("requests.request", _req)

    acquire_api(AcquireApiArgs(url="http://example.com/", stream=True))
    assert called["allow_redirects"] is False
