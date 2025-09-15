# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json

from fastapi.testclient import TestClient


class _Resp:
    def __init__(self, status=200, headers=None, content=b"", text=None, chunks=None):
        self.status_code = status
        self.headers = headers or {}
        self.content = content
        self.text = (
            text
            if text is not None
            else (
                content.decode("utf-8", errors="ignore")
                if isinstance(content, (bytes, bytearray))
                else ""
            )
        )
        self._chunks = chunks or []

    def iter_content(self, chunk_size=1024 * 1024):  # noqa: ARG002
        if self._chunks:
            yield from self._chunks
        elif self.content:
            # Fallback: yield full content once
            yield self.content


def test_acquire_api_streams_binary_and_headers(monkeypatch, client: TestClient):
    # Mock requests.request to return streaming response with headers
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
        return _Resp(200, headers={"Content-Type": "audio/ogg", "Content-Disposition": 'attachment; filename="a.ogg"'}, chunks=[b"abc", b"def"])  # fmt: skip

    import requests

    monkeypatch.setattr(requests, "request", fake_request)
    r = client.post(
        "/v1/acquire/api",
        json={
            "url": "https://api.example/download",
            "stream": True,
            "expect_content_type": "audio/ogg",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("content-type") == "audio/ogg"
    assert "filename=" in (r.headers.get("content-disposition") or "")
    assert r.content == b"abcdef"


def test_acquire_api_head_first_content_type_mismatch(monkeypatch, client: TestClient):
    # HEAD preflight does not match expected content type
    def fake_head(url, headers=None, params=None, allow_redirects=True, timeout=None):  # noqa: ARG001
        return _Resp(200, headers={"Content-Type": "application/octet-stream"})

    def should_not_call_request(*a, **kw):  # noqa: ARG001
        raise AssertionError("request() should not be called when HEAD fails")

    import requests

    monkeypatch.setattr(requests, "head", fake_head)
    monkeypatch.setattr(requests, "request", should_not_call_request)
    r = client.post(
        "/v1/acquire/api",
        json={
            "url": "https://api.example/download",
            "stream": True,
            "head_first": True,
            "expect_content_type": "audio/ogg",
        },
    )
    assert r.status_code == 415


def test_process_api_json_csv_from_file(tmp_path, client: TestClient):
    obj = {
        "data": {
            "chat": {
                "messages": [{"id": "m1", "text": "hi"}, {"id": "m2", "text": "there"}]
            }
        }
    }
    p = tmp_path / "in.json"
    p.write_text(json.dumps(obj), encoding="utf-8")
    r = client.post(
        "/v1/process/api-json",
        json={
            "file_or_url": str(p),
            "records_path": "data.chat.messages",
            "fields": "id,text",
            "format": "csv",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("text/csv")
    body = r.text.splitlines()
    assert body and body[0].startswith("id,")
    assert any("m1" in ln for ln in body[1:])


def test_process_api_json_jsonl_from_upload(tmp_path, client: TestClient):
    # Two pages NDJSON with records at data.items
    page1 = json.dumps({"data": {"items": [{"id": 1}, {"id": 2}]}})
    page2 = json.dumps({"data": {"items": [{"id": 3}]}})
    content = (page1 + "\n" + page2 + "\n").encode("utf-8")
    files = {"file": ("pages.jsonl", content, "application/x-ndjson")}
    r = client.post(
        "/v1/process/api-json",
        data={
            "records_path": "data.items",
            "fields": "id",
            "format": "jsonl",
        },
        files=files,
    )
    assert r.status_code == 200
    assert r.headers.get("content-type") == "application/x-ndjson"
    lines = [ln for ln in r.text.splitlines() if ln.strip()]
    assert len(lines) == 3
    assert json.loads(lines[0])["id"] == 1


def test_acquire_api_paginated_ndjson_link(monkeypatch, client: TestClient):
    # Mock backend link iterator to produce two pages
    from zyra.connectors.backends import api as api_backend

    def fake_paginate_link(method, url, **kwargs):  # noqa: ARG001
        yield 200, {}, b'{"page":1}'
        yield 200, {}, b'{"page":2}'

    monkeypatch.setattr(api_backend, "paginate_link", fake_paginate_link)
    r = client.post(
        "/v1/acquire/api",
        json={
            "url": "https://api.example/list",
            "paginate": "link",
            "link_rel": "next",
            "newline_json": True,
        },
    )
    assert r.status_code == 200
    assert r.headers.get("content-type") == "application/x-ndjson"
    lines = [ln for ln in r.text.splitlines() if ln.strip()]
    assert len(lines) == 2


def test_acquire_api_paginated_json_array_cursor(monkeypatch, client: TestClient):
    # Mock backend cursor iterator to produce two JSON objects
    import json as _json  # noqa: I001
    from zyra.connectors.backends import api as api_backend  # noqa: I001

    objs = [{"x": 1}, {"x": 2}]

    def fake_paginate_cursor(method, url, **kwargs):  # noqa: ARG001
        for o in objs:
            yield 200, {}, _json.dumps(o).encode("utf-8")

    monkeypatch.setattr(api_backend, "paginate_cursor", fake_paginate_cursor)
    r = client.post(
        "/v1/acquire/api",
        json={
            "url": "https://api.example/list",
            "paginate": "cursor",
            "cursor_param": "cursor",
            "next_cursor_json_path": "next",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("content-type") == "application/json"
    arr = r.json()
    assert isinstance(arr, list) and len(arr) == 2


def test_acquire_api_paginated_ndjson_page(monkeypatch, client: TestClient):
    from zyra.connectors.backends import api as api_backend

    def fake_paginate_page(method, url, **kwargs):  # noqa: ARG001
        yield 200, {}, b'{"i":1}'
        yield 200, {}, b'{"i":2}'

    monkeypatch.setattr(api_backend, "paginate_page", fake_paginate_page)
    r = client.post(
        "/v1/acquire/api",
        json={
            "url": "https://api.example/items",
            "paginate": "page",
            "page_param": "page",
            "page_start": 1,
            "newline_json": True,
        },
    )
    assert r.status_code == 200
    assert r.headers.get("content-type") == "application/x-ndjson"
    lines = [ln for ln in r.text.splitlines() if ln.strip()]
    assert len(lines) == 2


def test_acquire_api_paginated_ndjson_cursor(monkeypatch, client: TestClient):
    import json as _json  # noqa: I001
    from zyra.connectors.backends import api as api_backend  # noqa: I001

    objs = [{"p": 1}, {"p": 2}]

    def fake_paginate_cursor(method, url, **kwargs):  # noqa: ARG001
        for o in objs:
            yield 200, {}, _json.dumps(o).encode("utf-8")

    monkeypatch.setattr(api_backend, "paginate_cursor", fake_paginate_cursor)
    r = client.post(
        "/v1/acquire/api",
        json={
            "url": "https://api.example/list",
            "paginate": "cursor",
            "cursor_param": "cursor",
            "next_cursor_json_path": "next",
            "newline_json": True,
        },
    )
    assert r.status_code == 200
    assert r.headers.get("content-type") == "application/x-ndjson"
    lines = [ln for ln in r.text.splitlines() if ln.strip()]
    assert len(lines) == 2


def test_acquire_api_paginated_json_array_page(monkeypatch, client: TestClient):
    from zyra.connectors.backends import api as api_backend

    def fake_paginate_page(method, url, **kwargs):  # noqa: ARG001
        yield 200, {}, b'{"i":1}'
        yield 200, {}, b'{"i":2}'

    monkeypatch.setattr(api_backend, "paginate_page", fake_paginate_page)
    r = client.post(
        "/v1/acquire/api",
        json={
            "url": "https://api.example/items",
            "paginate": "page",
            "page_param": "page",
            "page_start": 1,
        },
    )
    assert r.status_code == 200
    assert r.headers.get("content-type") == "application/json"
    arr = r.json()
    assert isinstance(arr, list) and len(arr) == 2
