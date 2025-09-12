from __future__ import annotations

import json

from fastapi.testclient import TestClient

from zyra.api.server import app


def test_get_search_catalog_file_allowlist_accept(tmp_path, monkeypatch):
    # Prepare allowlisted directory and catalog file
    base = tmp_path / "catalogs"
    base.mkdir()
    monkeypatch.setenv("ZYRA_CATALOG_DIR", str(base))
    cat = base / "cat.json"
    data = [
        {
            "url": "http://example.com/datasets/alpha",
            "title": "Alpha dataset",
            "description": "Alpha description",
            "keywords": ["alpha"],
        }
    ]
    cat.write_text(json.dumps(data), encoding="utf-8")

    client = TestClient(app)
    r = client.get(
        "/search", params={"q": "alpha", "limit": 3, "catalog_file": str(cat)}
    )
    assert r.status_code == 200, r.text
    items = r.json()
    assert (
        isinstance(items, list) and items
    ), "Expected results from allowlisted catalog"


def test_get_search_catalog_file_allowlist_reject(tmp_path, monkeypatch):
    # Create a catalog outside of any allowlisted directory
    cat = tmp_path / "cat.json"
    data = [
        {
            "url": "http://example.com/datasets/beta",
            "title": "Beta dataset",
            "description": "Beta description",
            "keywords": ["beta"],
        }
    ]
    cat.write_text(json.dumps(data), encoding="utf-8")
    # Ensure no allowlist is set
    monkeypatch.delenv("ZYRA_CATALOG_DIR", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)

    client = TestClient(app)
    r = client.get(
        "/search", params={"q": "beta", "limit": 3, "catalog_file": str(cat)}
    )
    assert r.status_code == 400


def test_post_search_profile_file_allowlist_accept(tmp_path, monkeypatch):
    # Prepare allowlisted directory and profile file
    base = tmp_path / "profiles"
    base.mkdir()
    monkeypatch.setenv("ZYRA_PROFILE_DIR", str(base))
    prof = base / "p.json"
    prof.write_text(json.dumps({"enrichment": {"defaults": {}}}), encoding="utf-8")

    client = TestClient(app)
    r = client.post(
        "/search",
        json={
            "query": "tsunami",
            "limit": 2,
            "profile_file": str(prof),
        },
    )
    assert r.status_code == 200, r.text
    items = r.json().get("items") if isinstance(r.json(), dict) else r.json()
    assert items is not None


def test_post_search_profile_file_allowlist_reject(tmp_path, monkeypatch):
    prof = tmp_path / "p.json"
    prof.write_text(json.dumps({"enrichment": {"defaults": {}}}), encoding="utf-8")
    monkeypatch.delenv("ZYRA_PROFILE_DIR", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)

    client = TestClient(app)
    r = client.post(
        "/search",
        json={
            "query": "tsunami",
            "limit": 2,
            "profile_file": str(prof),
        },
    )
    assert r.status_code == 400
