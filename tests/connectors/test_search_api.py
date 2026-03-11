# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import json
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

import zyra.connectors.discovery as disco


def test_parse_helpers(tmp_path):
    from zyra.connectors.discovery import api_search as mod

    assert mod._parse_kv_list(["a=1", "b = two"]) == {"a": "1", "b": "two"}
    assert mod._parse_kv_list(["noval", "c=3"]) == {"c": "3"}
    assert mod._parse_kv_list({"Auth": "Bearer"}) == {"Auth": "Bearer"}

    body = mod._parse_json_body('{"x":1, "y":"z"}')
    assert isinstance(body, dict) and body["x"] == 1 and body["y"] == "z"

    p = tmp_path / "body.json"
    p.write_text(json.dumps({"k": "v"}), encoding="utf-8")
    body2 = mod._parse_json_body("@" + str(p))
    assert body2 == {"k": "v"}


class _DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeRequests:
    def __init__(self, payload):
        self.payload = payload
        self.last = SimpleNamespace(get=None, post=None)

    def get(self, url, params=None, headers=None, timeout=None):
        self.last.get = {
            "url": url,
            "params": params,
            "headers": headers,
            "timeout": timeout,
        }
        return _DummyResponse(self.payload)

    def post(self, url, json=None, headers=None, timeout=None):
        self.last.post = {
            "url": url,
            "json": json,
            "headers": headers,
            "timeout": timeout,
        }
        return _DummyResponse(self.payload)


def test_query_single_api_get_list_response(monkeypatch):
    from zyra.connectors.discovery import api_search as mod

    # Bypass optional dependency check
    monkeypatch.setattr(mod, "_ensure_requests", lambda: None)
    # Fake requests returning a simple list payload
    fake = _FakeRequests(
        [
            {"name": "Dataset A", "description": "desc", "uri": "http://x/a"},
            {"title": "Dataset B", "url": "http://x/b"},
        ]
    )
    monkeypatch.setitem(__import__("sys").modules, "requests", fake)

    rows = mod.query_single_api(
        "http://example/api",
        "temperature",
        limit=2,
        no_openapi=True,
        endpoint="/search",
        qp_name="q",
    )
    assert len(rows) == 2
    assert {"source", "dataset", "description", "link"}.issubset(rows[0].keys())
    # Ensure query param was used
    assert fake.last.get["params"]["q"] == "temperature"


def test_query_single_api_headers_mapping(monkeypatch):
    from zyra.connectors.discovery import api_search as mod

    monkeypatch.setattr(mod, "_ensure_requests", lambda: None)
    fake = _FakeRequests([])
    monkeypatch.setitem(__import__("sys").modules, "requests", fake)

    mod.query_single_api(
        "http://example/api",
        "wind",
        limit=1,
        no_openapi=True,
        endpoint="/search",
        qp_name="q",
        headers={"Authorization": "Bearer abc"},
    )
    assert fake.last.get["headers"]["Authorization"] == "Bearer abc"


def test_query_single_api_result_key(monkeypatch):
    from zyra.connectors.discovery import api_search as mod

    monkeypatch.setattr(mod, "_ensure_requests", lambda: None)
    fake = _FakeRequests({"results": [{"id": "x", "name": "X", "uri": "http://x"}]})
    monkeypatch.setitem(__import__("sys").modules, "requests", fake)

    rows = mod.query_single_api(
        "http://example/api",
        "q",
        limit=5,
        no_openapi=True,
        endpoint="/search",
        qp_name="q",
        result_key="results",
    )
    assert len(rows) == 1 and rows[0]["dataset"] == "X"


def test_federated_api_concurrency(monkeypatch):
    from zyra.connectors.discovery import api_search as mod

    monkeypatch.setattr(mod, "_ensure_requests", lambda: None)

    def _stub_query_single_api(u, *a, **k):
        pu = urlparse(u)
        scheme = pu.scheme or "http"
        host = pu.netloc or u
        return [
            {
                "source": host,
                "dataset": f"D-{host}",
                "link": f"{scheme}://{host}/d",
            }
        ]

    monkeypatch.setattr(mod, "query_single_api", _stub_query_single_api)

    urls = ["http://a.test", "http://b.test", "http://c.test"]
    rows = mod.federated_api_search(urls, "q", concurrency=3)
    assert len(rows) == 3
    sources = {r["source"] for r in rows}
    assert sources == {"a.test", "b.test", "c.test"}


def test_cli_api_output_shaping_csv(monkeypatch, capsys):
    # Monkeypatch the federated search to controlled rows with duplicates
    rows = [
        {"source": "s2", "dataset": "B", "description": "x", "link": "L1"},
        {
            "source": "s1",
            "dataset": "A",
            "description": "y",
            "link": "L1",
        },  # duplicate link
        {"source": "s1", "dataset": "C", "description": "z", "link": "L2"},
    ]
    monkeypatch.setattr(
        __import__(
            "zyra.connectors.discovery.api_search", fromlist=["federated_api_search"]
        ),
        "federated_api_search",
        lambda *a, **k: rows,
    )

    p = argparse.ArgumentParser()
    disco.register_cli(p)
    ns = p.parse_args(
        [
            "api",
            "--url",
            "http://x",
            "--query",
            "t",
            "--csv",
            "--fields",
            "source,dataset,link",
            "--dedupe",
            "link",
            "--sort",
            "source,dataset",
        ]
    )
    rc = ns.func(ns)
    assert rc == 0
    out = capsys.readouterr().out.strip().splitlines()
    # Header then two rows (L1 deduped)
    assert out[0] == "source,dataset,link"
    assert len(out) == 3
    # After dedupe (keep first L1 -> s2,B) and sort, expect s1,C then s2,B
    assert out[1].startswith("s1,C,")
    assert out[2].startswith("s2,B,")


def test_cli_api_applies_credentials(monkeypatch):
    from zyra.connectors.credentials import ResolvedCredentials

    captured: dict[str, Any] = {}

    def _fake_federated(*args, **kwargs):
        captured["headers"] = kwargs.get("headers")
        captured["headers_by_url"] = kwargs.get("headers_by_url")
        return []

    monkeypatch.setattr(
        __import__(
            "zyra.connectors.discovery.api_search", fromlist=["federated_api_search"]
        ),
        "federated_api_search",
        _fake_federated,
    )

    def _fake_resolve(entries, credential_file=None):
        values: dict[str, str] = {}
        for item in entries:
            if "=" in item:
                field, value = item.split("=", 1)
                values[field.strip()] = value.strip()
        return ResolvedCredentials(
            values=values,
            masked={k: "***" for k in values},
        )

    monkeypatch.setattr(
        "zyra.connectors.discovery.resolve_credentials",
        _fake_resolve,
    )

    parser = argparse.ArgumentParser()
    disco.register_cli(parser)
    ns = parser.parse_args(
        [
            "api",
            "--url",
            "http://auth.example/api",
            "--query",
            "q",
            "--credential",
            "token=global",
            "--url-credential",
            "http://auth.example/api",
            "token=scoped",
        ]
    )

    rc = ns.func(ns)
    assert rc == 0
    assert captured["headers"]["Authorization"] == "Bearer global"
    assert (
        captured["headers_by_url"]["http://auth.example/api"]["Authorization"]
        == "Bearer scoped"
    )


def test_cli_api_url_auth(monkeypatch):
    captured: dict[str, Any] = {}

    def _fake_federated(*args, **kwargs):
        captured["headers_by_url"] = kwargs.get("headers_by_url")
        return []

    monkeypatch.setattr(
        __import__(
            "zyra.connectors.discovery.api_search", fromlist=["federated_api_search"]
        ),
        "federated_api_search",
        _fake_federated,
    )

    parser = argparse.ArgumentParser()
    disco.register_cli(parser)
    ns = parser.parse_args(
        [
            "api",
            "--url",
            "http://auth.example/api",
            "--query",
            "q",
            "--url-auth",
            "http://auth.example/api",
            "bearer:scoped",
        ]
    )

    rc = ns.func(ns)
    assert rc == 0
    assert (
        captured["headers_by_url"]["http://auth.example/api"]["Authorization"]
        == "Bearer scoped"
    )


def test_federated_api_scoped_headers(monkeypatch):
    from zyra.connectors.discovery import api_search as mod

    calls: list[tuple[str, dict[str, str] | None]] = []

    def _fake_query_single_api(url, *args, headers=None, **kwargs):
        calls.append((url, headers))
        return []

    monkeypatch.setattr(mod, "query_single_api", _fake_query_single_api)

    mod.federated_api_search(
        ["http://a.test/api", "http://b.test/api"],
        "q",
        headers={"Global": "1"},
        headers_by_url={"http://a.test/api": {"Authorization": "Bearer scoped"}},
        concurrency=2,
    )

    assert calls[0][1]["Authorization"] == "Bearer scoped"
    assert calls[1][1]["Global"] == "1"


def test_query_single_api_post_json_body(monkeypatch, tmp_path):
    from zyra.connectors.discovery import api_search as mod

    monkeypatch.setattr(mod, "_ensure_requests", lambda: None)
    payload = [
        {"id": "x1", "name": "Alpha", "uri": "http://h/x1"},
        {"id": "x2", "name": "Beta", "uri": "http://h/x2"},
    ]
    fake = _FakeRequests(payload)
    monkeypatch.setitem(__import__("sys").modules, "requests", fake)

    body_file = tmp_path / "body.json"
    body_file.write_text(
        json.dumps({"query": "temperature", "limit": 2}), encoding="utf-8"
    )

    rows = mod.query_single_api(
        "http://example/api",
        "IGNORED-QUERY",
        limit=2,
        no_openapi=True,
        endpoint="/search",
        use_post=True,
        json_body="@" + str(body_file),
        headers=["X-Test=1"],
        timeout=5.0,
    )
    # Used POST and sent our JSON body
    assert fake.last.post is not None
    assert fake.last.post["json"] == {"query": "temperature", "limit": 2}
    assert len(rows) == 2 and rows[0]["dataset"] == "Alpha"


def test_cli_api_openapi_diagnostics(monkeypatch, capsys):
    from zyra.connectors.discovery import api_search as mod

    # Mock OpenAPI discovery
    spec = {
        "openapi": "3.0.0",
        "paths": {
            "/search": {
                "get": {
                    "parameters": [
                        {"in": "query", "name": "q"},
                        {"in": "query", "name": "limit"},
                    ]
                }
            }
        },
    }
    monkeypatch.setattr(mod, "_load_openapi", lambda base: spec)

    # Print endpoint and qp
    p = argparse.ArgumentParser()
    disco.register_cli(p)
    ns = p.parse_args(["api", "--url", "http://x", "--query", "t", "--print-openapi"])
    rc = ns.func(ns)
    assert rc == 0
    out = capsys.readouterr().out
    assert "endpoint=/search" in out and "query_param=q" in out

    # Suggest flags
    p = argparse.ArgumentParser()
    disco.register_cli(p)
    ns = p.parse_args(["api", "--url", "http://x", "--query", "t", "--suggest-flags"])
    rc = ns.func(ns)
    assert rc == 0
    out = capsys.readouterr().out
    assert "suggest --param for: q,limit" in out


def test_extract_name_string_passthrough():
    from zyra.connectors.discovery.api_search import _extract_name

    assert _extract_name("hello") == "hello"
    assert _extract_name(None) is None
    assert _extract_name(42) == "42"


def test_extract_name_drills_into_dict():
    from zyra.connectors.discovery.api_search import _extract_name

    assert (
        _extract_name({"name": "Synoptic-UAS", "path": "data/Synoptic-UAS"})
        == "Synoptic-UAS"
    )
    assert _extract_name({"path": "data/Synoptic-UAS"}) == "data/Synoptic-UAS"
    assert _extract_name({"title": "My Title"}) == "My Title"
    assert _extract_name({"id": "abc123"}) == "abc123"
    assert _extract_name({"label": "Atmospheric CO2"}) == "Atmospheric CO2"
    # Non-string values in name-like keys should be stringified
    assert _extract_name({"id": 123}) == "123"
    assert _extract_name({"name": 42}) == "42"
    # Nested dict in a name-like key is recursively drilled into
    assert _extract_name({"name": {"id": "x"}}) == "x"
    assert _extract_name({"name": {"title": "inner", "id": "y"}}) == "inner"


def test_normalize_item_nested_dataset_dict():
    from zyra.connectors.discovery.api_search import _normalize_item

    item = {
        "dataset": {"path": "data/Synoptic-UAS", "name": "Synoptic-UAS"},
        "score": 1,
    }
    row = _normalize_item(item, "example.com")
    assert row["dataset"] == "Synoptic-UAS"
    assert row["source"] == "example.com"


def test_normalize_item_nested_dataset_dict_no_name():
    from zyra.connectors.discovery.api_search import _normalize_item

    item = {"dataset": {"path": "data/foo"}}
    row = _normalize_item(item, "host")
    assert row["dataset"] == "data/foo"


def test_normalize_item_nested_description_and_link():
    from zyra.connectors.discovery.api_search import _normalize_item

    item = {
        "name": "DS1",
        "description": {"title": "A long description object"},
        "uri": {"path": "http://example.com/ds1"},
    }
    row = _normalize_item(item, "host")
    assert row["dataset"] == "DS1"
    assert row["description"] == "A long description object"
    assert row["link"] == "http://example.com/ds1"


def test_extract_name_url_like_dict_keys():
    from zyra.connectors.discovery.api_search import _extract_name

    assert _extract_name({"url": "http://x/data"}) == "http://x/data"
    assert _extract_name({"href": "http://x/ref"}) == "http://x/ref"
    assert _extract_name({"uri": "http://x/uri"}) == "http://x/uri"
    assert _extract_name({"link": "http://x/link"}) == "http://x/link"


def test_normalize_item_href_link():
    from zyra.connectors.discovery.api_search import _normalize_item

    item = {"name": "DS", "href": "http://example.com/ds"}
    row = _normalize_item(item, "host")
    assert row["link"] == "http://example.com/ds"


def test_extract_name_mapping_type():
    from collections import OrderedDict

    from zyra.connectors.discovery.api_search import _extract_name

    assert _extract_name(OrderedDict([("name", "ordered")])) == "ordered"
    assert _extract_name(OrderedDict([("id", 99)])) == "99"


def test_extract_name_skips_unresolvable_nested_dict():
    from zyra.connectors.discovery.api_search import _extract_name

    # name is a dict with no recognizable keys; should skip to title
    assert _extract_name({"name": {"foo": "bar"}, "title": "Fallback"}) == "Fallback"
    # All keys are unresolvable nested dicts → returns None
    assert _extract_name({"name": {"foo": "bar"}}) is None


def test_normalize_item_falls_back_on_unresolvable_field():
    from zyra.connectors.discovery.api_search import _normalize_item

    # name is unresolvable dict → should fall back to title
    item = {"name": {"foo": "bar"}, "title": "Fallback Title", "uri": "http://x"}
    row = _normalize_item(item, "host")
    assert row["dataset"] == "Fallback Title"

    # uri is unresolvable dict → should fall back to url
    item2 = {"name": "DS", "uri": {"foo": "bar"}, "url": "http://example.com"}
    row2 = _normalize_item(item2, "host")
    assert row2["link"] == "http://example.com"

    # description is unresolvable dict → should fall back to abstract
    item3 = {"name": "DS", "description": {"foo": "bar"}, "abstract": "A summary"}
    row3 = _normalize_item(item3, "host")
    assert row3["description"] == "A summary"
