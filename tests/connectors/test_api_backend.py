# SPDX-License-Identifier: Apache-2.0
import json

from zyra.connectors.backends import api as api_backend


def test_paginate_cursor_uses_next_cursor_path(monkeypatch):
    pages = [
        {
            "data": {"lifelogs": [1, 2]},
            "meta": {"lifelogs": {"nextCursor": "abc"}},
        },
        {"data": {"lifelogs": [3]}, "meta": {"lifelogs": {"nextCursor": None}}},
    ]
    calls = {"i": 0}

    def fake_request_with_retries(method, url, **kwargs):  # noqa: ARG001
        i = calls["i"]
        calls["i"] = min(i + 1, len(pages) - 1)
        body = json.dumps(pages[i]).encode("utf-8")
        return 200, {}, body

    monkeypatch.setattr(api_backend, "request_with_retries", fake_request_with_retries)

    seen = []
    for status, headers, content in api_backend.paginate_cursor(
        "GET",
        "https://api.example/v1/lifelogs",
        headers={"X-API-Key": "x"},
        params={},
        cursor_param="cursor",
        next_cursor_json_path="meta.lifelogs.nextCursor",
    ):
        assert status == 200
        assert isinstance(headers, dict)
        seen.append(json.loads(content.decode("utf-8")))

    assert len(seen) == 2
    assert seen[0]["data"]["lifelogs"] == [1, 2]
    assert seen[1]["data"]["lifelogs"] == [3]


def test_paginate_link_follows_next_rel(monkeypatch):
    pages = [
        (
            200,
            {"Link": '<https://api.example/v1/lifelogs?page=2>; rel="next"'},
            {"data": {"lifelogs": [1, 2]}},
        ),
        (
            200,
            {"Link": '<https://api.example/v1/lifelogs?page=3>; rel="next"'},
            {"data": {"lifelogs": [3]}},
        ),
        (200, {"Link": ""}, {"data": {"lifelogs": [4]}}),
    ]
    calls = {"i": 0, "urls": []}

    def fake_request_with_retries(method, url, **kwargs):  # noqa: ARG001
        i = calls["i"]
        calls["i"] = min(i + 1, len(pages) - 1)
        calls["urls"].append(url)
        status, headers, body = pages[i]
        import json as _json

        return status, headers, _json.dumps(body).encode("utf-8")

    monkeypatch.setattr(api_backend, "request_with_retries", fake_request_with_retries)

    seen = []
    for status, headers, content in api_backend.paginate_link(
        "GET",
        "https://api.example/v1/lifelogs",
        headers={"X-API-Key": "x"},
        params={"limit": "2"},
        link_rel="next",
    ):
        assert status == 200
        assert isinstance(headers, dict)
        seen.append(json.loads(content.decode("utf-8")))

    # Should have followed two next links then stopped
    assert len(seen) == 3
    assert calls["urls"][0].startswith("https://api.example/v1/lifelogs")
    assert calls["urls"][1].endswith("page=2")
    assert calls["urls"][2].endswith("page=3")
