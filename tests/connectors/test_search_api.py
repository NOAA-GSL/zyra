from __future__ import annotations

import argparse
import json
from types import SimpleNamespace
from urllib.parse import urlparse

import zyra.connectors.discovery as disco


def test_parse_helpers(tmp_path):
    from zyra.connectors.discovery import api_search as mod

    assert mod._parse_kv_list(["a=1", "b = two"]) == {"a": "1", "b": "two"}
    assert mod._parse_kv_list(["noval", "c=3"]) == {"c": "3"}

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
