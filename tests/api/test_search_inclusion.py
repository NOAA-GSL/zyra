from __future__ import annotations

from fastapi.testclient import TestClient


class _FakeLocal:
    calls = 0

    def __init__(self, *a, **k):  # noqa: D401 - minimal fake
        pass

    def search(self, q: str, *, limit: int = 10):  # noqa: D401 - minimal fake
        _FakeLocal.calls += 1
        # Return a sentinel row to assert inclusion logic
        return [
            {
                "id": "sentinel-id",
                "name": f"SENTINEL {q}",
                "description": None,
                "source": "sos-catalog",
                "format": "HTML",
                "uri": "https://example/sentinel",
            }
        ]


def test_get_search_includes_local_when_no_remote(monkeypatch):
    import zyra.connectors.discovery as disco
    from zyra.api.server import app

    monkeypatch.setattr(disco, "LocalCatalogBackend", _FakeLocal)
    _FakeLocal.calls = 0

    client = TestClient(app)
    r = client.get("/v1/search", params={"q": "temperature", "limit": 2})
    assert r.status_code == 200
    data = r.json()
    assert any(d.get("id") == "sentinel-id" for d in data)
    assert _FakeLocal.calls == 1


def test_get_search_excludes_local_when_remote_only(monkeypatch):
    import zyra.connectors.discovery as disco
    from zyra.api.server import app

    # Local should NOT be called when remote_only=true, even with no remote urls
    called = {"n": 0}

    class _NoCallLocal:
        def __init__(self, *a, **k):
            pass

        def search(self, *a, **k):
            called["n"] += 1
            return []

    monkeypatch.setattr(disco, "LocalCatalogBackend", _NoCallLocal)

    client = TestClient(app)
    r = client.get(
        "/v1/search", params={"q": "temperature", "limit": 2, "remote_only": True}
    )
    assert r.status_code == 200
    assert called["n"] == 0


def test_post_search_include_local_toggle(monkeypatch):
    import zyra.connectors.discovery as disco
    from zyra.api.server import app

    calls = {"n": 0}

    class _CountLocal:
        def __init__(self, *a, **k):
            pass

        def search(self, *a, **k):
            calls["n"] += 1
            return []

    monkeypatch.setattr(disco, "LocalCatalogBackend", _CountLocal)

    client = TestClient(app)

    # Default include_local False, no remote → still included (policy prefers local)
    calls["n"] = 0
    r = client.post("/v1/search", json={"query": "wind", "limit": 1})
    assert r.status_code == 200
    assert calls["n"] == 1

    # Force remote_only True → exclude local
    calls["n"] = 0
    r = client.post(
        "/v1/search", json={"query": "wind", "limit": 1, "remote_only": True}
    )
    assert r.status_code == 200
    assert calls["n"] == 0
