# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pytest

from zyra.api.mcp_tools.generic import api_fetch, api_process_json


class _MockResponse:
    def __init__(
        self,
        headers: dict[str, str] | None = None,
        status: int = 200,
        body: bytes = b"ok",
    ) -> None:
        self.headers = headers or {"Content-Type": "text/plain"}
        self.status_code = status
        self._body = body

    def iter_content(self, chunk_size: int = 1024) -> Iterator[bytes]:  # noqa: ARG002
        yield self._body


def _set_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = tmp_path / "data"
    base.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ZYRA_DATA_DIR", str(base))
    return base


def test_output_dir_traversal_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = _set_data_dir(tmp_path, monkeypatch)

    # Mock requests.request so no network happens
    def _req(
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        data: Any | None = None,
        timeout: int = 60,
        stream: bool = True,
        allow_redirects: bool = False,
    ):  # noqa: ARG001
        return _MockResponse()

    # Force DNS resolution to a public IP to reach the write phase
    def _ga(host: str, port: int, proto: int):  # noqa: ARG001
        return [(0, 0, 0, "", ("93.184.216.34", port))]

    monkeypatch.setenv("ZYRA_MCP_FETCH_HTTPS_ONLY", "false")
    monkeypatch.setenv("ZYRA_MCP_FETCH_ALLOW_PORTS", "80,443")
    monkeypatch.setenv("ZYRA_MCP_FETCH_DENY_HOSTS", "")
    monkeypatch.setenv("ZYRA_MCP_FETCH_ALLOW_HOSTS", "")
    monkeypatch.setenv("ZYRA_MCP_FETCH_MAX_BYTES", "0")
    monkeypatch.setattr("requests.request", _req)
    monkeypatch.setattr("socket.getaddrinfo", _ga)

    # Attempt traversal in output_dir
    with pytest.raises(ValueError):
        api_fetch(url="http://example.com/", output_dir="../../etc")

    # Verify base dir remains empty
    assert not any(base.iterdir())


def test_filename_sanitized_from_content_disposition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = _set_data_dir(tmp_path, monkeypatch)

    # Malicious header attempts to escape via filename
    resp = _MockResponse(
        headers={
            "Content-Type": "text/plain",
            "Content-Disposition": "attachment; filename=../../evil.txt",
        },
        body=b"hello",
    )

    def _req(
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        data: Any | None = None,
        timeout: int = 60,
        stream: bool = True,
        allow_redirects: bool = False,
    ):  # noqa: ARG001
        return resp

    def _ga(host: str, port: int, proto: int):  # noqa: ARG001
        return [(0, 0, 0, "", ("93.184.216.34", port))]

    monkeypatch.setenv("ZYRA_MCP_FETCH_HTTPS_ONLY", "false")
    monkeypatch.setattr("requests.request", _req)
    monkeypatch.setattr("socket.getaddrinfo", _ga)

    res = api_fetch(url="http://example.com/", output_dir="downloads")
    # Path returned is relative to base
    out_rel = Path(res["path"])
    out_abs = (base / out_rel).resolve()
    assert out_abs.exists()
    # Name should be sanitized to strip traversal
    assert out_abs.parent == (base / "downloads").resolve()
    assert out_abs.name in {"evil.txt", "download.bin"}


def test_https_required_default_and_http_allowed_via_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_data_dir(tmp_path, monkeypatch)

    # HTTPS only by default
    with pytest.raises(ValueError):
        api_fetch(url="http://127.0.0.1/")

    # Allow http when override provided, but still block private IP
    monkeypatch.setenv("ZYRA_MCP_FETCH_HTTPS_ONLY", "false")
    with pytest.raises(ValueError):
        api_fetch(url="http://127.0.0.1/")


def test_block_hostname_resolving_to_private_ip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_data_dir(tmp_path, monkeypatch)

    def _ga(host: str, port: int, proto: int):  # noqa: ARG001
        # Resolve to private IP
        return [(0, 0, 0, "", ("10.0.0.5", port))]

    monkeypatch.setenv("ZYRA_MCP_FETCH_HTTPS_ONLY", "true")
    monkeypatch.setattr("socket.getaddrinfo", _ga)
    with pytest.raises(ValueError):
        api_fetch(url="https://example.internal/")


def test_strip_hop_headers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_data_dir(tmp_path, monkeypatch)

    captured: dict[str, Any] = {}

    def _req(
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        data: Any | None = None,
        timeout: int = 60,
        stream: bool = True,
        allow_redirects: bool = False,
    ):  # noqa: ARG001
        captured["headers"] = dict(headers or {})
        return _MockResponse()

    def _ga(host: str, port: int, proto: int):  # noqa: ARG001
        return [(0, 0, 0, "", ("93.184.216.34", port))]

    monkeypatch.setenv("ZYRA_MCP_FETCH_HTTPS_ONLY", "false")
    monkeypatch.setattr("requests.request", _req)
    monkeypatch.setattr("socket.getaddrinfo", _ga)

    api_fetch(
        url="http://example.com/",
        headers={
            "Host": "attacker",
            "X-Forwarded-For": "1.2.3.4",
            "X-Real-IP": "1.2.3.4",
            "Forwarded": "for=1.2.3.4",
            "Accept": "*/*",
        },
    )
    sent = captured.get("headers", {})
    assert "Host" not in sent
    assert "X-Forwarded-For" not in sent
    assert "X-Real-IP" not in sent
    assert "Forwarded" not in sent
    assert sent.get("Accept") == "*/*"


def test_api_process_json_output_dir_traversal_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Isolate DATA_DIR
    base = _set_data_dir(tmp_path, monkeypatch)

    # Patch run_cli_endpoint to a no-op successful result
    class _Res:
        exit_code = 0
        stderr = ""

    monkeypatch.setenv("ZYRA_MCP_FETCH_HTTPS_ONLY", "true")
    monkeypatch.setattr(
        "zyra.api.mcp_tools.generic.run_cli_endpoint", lambda *a, **k: _Res()
    )

    with pytest.raises(ValueError):
        api_process_json(file_or_url="file.json", output_dir="../../etc")
    assert not any(base.iterdir())


def test_api_process_json_filename_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = _set_data_dir(tmp_path, monkeypatch)

    written = {}

    class _Res:
        exit_code = 0
        stderr = ""

    def _run(req, bg=None):  # noqa: ARG001
        # Create the file path requested by the function to simulate CLI output
        out_path = Path(req.args.get("output"))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        data = b"abc123"
        out_path.write_bytes(data)
        written["out_path"] = out_path
        return _Res()

    monkeypatch.setattr("zyra.api.mcp_tools.generic.run_cli_endpoint", _run)

    res = api_process_json(
        file_or_url="file.json",
        output_dir="outputs",
        output_name="../../evil.csv",
        format="csv",
    )
    # Returned path is relative to DATA_DIR
    out_rel = Path(res["path"])
    out_abs = (base / out_rel).resolve()
    assert out_abs.exists()
    # Path remains contained
    assert out_abs.parent == (base / "outputs").resolve()
    # Sanitized name should not include traversal segments
    assert out_abs.name in {"evil.csv", "output.csv"}
    # Size propagated
    assert res["size_bytes"] == out_abs.stat().st_size


def test_port_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_data_dir(tmp_path, monkeypatch)

    def _ga(host: str, port: int, proto: int):  # noqa: ARG001
        return [(0, 0, 0, "", ("93.184.216.34", port))]

    monkeypatch.setattr("socket.getaddrinfo", _ga)

    # 444 not allowed by default
    with pytest.raises(ValueError):
        api_fetch(url="https://example.com:444/")

    # Allow when configured
    monkeypatch.setenv("ZYRA_MCP_FETCH_ALLOW_PORTS", "80,443,444")

    def _req(
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        data: Any | None = None,
        timeout: int = 60,
        stream: bool = True,
        allow_redirects: bool = False,
    ):  # noqa: ARG001
        return _MockResponse()

    monkeypatch.setattr("requests.request", _req)
    res = api_fetch(url="https://example.com:444/")
    assert isinstance(res, dict)
