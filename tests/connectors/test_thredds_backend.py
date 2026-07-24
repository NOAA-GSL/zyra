# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the THREDDS connector backend (hermetic, no network)."""

from __future__ import annotations

import pytest

from zyra.connectors.backends import thredds as thr

CATALOG_URL = "https://thredds.example.com/thredds/catalog/foo/catalog.xml"

FLAT_CATALOG = """<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"
         xmlns:xlink="http://www.w3.org/1999/xlink" name="Foo">
  <service name="all" serviceType="Compound" base="">
    <service name="http" serviceType="HTTPServer" base="/thredds/fileServer/"/>
    <service name="dap" serviceType="OPENDAP" base="/thredds/dodsC/"/>
  </service>
  <dataset name="Foo Collection" ID="foo">
    <dataset name="foo_20240101.grib2" ID="foo/20240101"
             urlPath="foo/foo_20240101.grib2">
      <date type="modified">2024-01-01T00:00:00Z</date>
    </dataset>
    <dataset name="foo_20240102.grib2" ID="foo/20240102"
             urlPath="foo/foo_20240102.grib2"/>
    <dataset name="readme.txt" ID="foo/readme" urlPath="foo/readme.txt"/>
  </dataset>
</catalog>
"""

ROOT_CATALOG = """<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"
         xmlns:xlink="http://www.w3.org/1999/xlink" name="Root">
  <service name="http" serviceType="HTTPServer" base="/thredds/fileServer/"/>
  <dataset name="top.grib2" urlPath="root/top.grib2"/>
  <catalogRef xlink:href="sub/catalog.xml" xlink:title="Sub"/>
</catalog>
"""

SUB_CATALOG = """<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"
         xmlns:xlink="http://www.w3.org/1999/xlink" name="Sub">
  <service name="http" serviceType="HTTPServer" base="/thredds/fileServer/"/>
  <dataset name="nested.grib2" urlPath="root/sub/nested.grib2"/>
</catalog>
"""


def test_absolute_http_server_base_points_at_declared_host():
    # A catalog whose HTTPServer service declares an absolute base must yield
    # download URLs on that host, not the catalog's host.
    xml = (
        '<catalog xmlns="http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0">'
        '<service name="http" serviceType="HTTPServer" '
        'base="https://files.example.org/thredds/fileServer/"/>'
        '<dataset name="x.grib2" urlPath="a/x.grib2"/>'
        "</catalog>"
    )
    datasets, _ = thr.parse_catalog(xml, CATALOG_URL)
    assert (
        datasets[0].download_url
        == "https://files.example.org/thredds/fileServer/a/x.grib2"
    )
    # Sanity: it did not get rooted at the catalog host.
    assert "thredds.example.com" not in datasets[0].download_url


def test_parse_catalog_builds_fileserver_urls():
    datasets, refs = thr.parse_catalog(FLAT_CATALOG, CATALOG_URL)
    assert refs == []
    urls = {d.url_path: d.download_url for d in datasets}
    assert (
        urls["foo/foo_20240101.grib2"]
        == "https://thredds.example.com/thredds/fileServer/foo/foo_20240101.grib2"
    )
    # The collection wrapper (no urlPath) is excluded; only leaf datasets remain.
    assert len(datasets) == 3
    # Date element is captured.
    d0 = next(d for d in datasets if d.url_path == "foo/foo_20240101.grib2")
    assert d0.date == "2024-01-01T00:00:00Z"


def test_pattern_filter():
    out = thr.list_files(CATALOG_URL, catalog_xml=FLAT_CATALOG, pattern=r"\.grib2$")
    assert all(u.endswith(".grib2") for u in out)
    assert len(out) == 2


def test_date_filter():
    out = thr.enumerate_datasets(
        CATALOG_URL,
        catalog_xml=FLAT_CATALOG,
        pattern=r"\.grib2$",
        since="2024-01-02",
        date_format="%Y%m%d",
    )
    assert [d.url_path for d in out] == ["foo/foo_20240102.grib2"]


def test_no_recursion_by_default():
    out = thr.list_files(CATALOG_URL, catalog_xml=ROOT_CATALOG)
    assert out == ["https://thredds.example.com/thredds/fileServer/root/top.grib2"]


def test_recursion_follows_catalog_ref():
    def fetcher(url: str) -> str:
        if url.endswith("sub/catalog.xml"):
            return SUB_CATALOG
        raise AssertionError(f"unexpected fetch: {url}")

    out = thr.list_files(
        ROOT_CATALOG_URL
        := "https://thredds.example.com/thredds/catalog/root/catalog.xml",
        catalog_xml=ROOT_CATALOG,
        recursive=True,
        fetcher=fetcher,
    )
    assert out == [
        "https://thredds.example.com/thredds/fileServer/root/top.grib2",
        "https://thredds.example.com/thredds/fileServer/root/sub/nested.grib2",
    ]


def test_recursion_respects_max_depth():
    def fetcher(url: str) -> str:
        return SUB_CATALOG

    out = thr.list_files(
        "https://thredds.example.com/thredds/catalog/root/catalog.xml",
        catalog_xml=ROOT_CATALOG,
        recursive=True,
        max_depth=0,
        fetcher=fetcher,
    )
    # Depth 0 means only the root catalog is read.
    assert out == ["https://thredds.example.com/thredds/fileServer/root/top.grib2"]


def test_recursion_dedups_on_download_url_not_urlpath():
    # A cross-host catalogRef whose dataset shares the same urlPath as the root
    # must NOT be dropped: it resolves to a different download URL.
    root = """<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"
         xmlns:xlink="http://www.w3.org/1999/xlink" name="Root">
  <service name="http" serviceType="HTTPServer" base="/thredds/fileServer/"/>
  <dataset name="dup.grib2" urlPath="shared/dup.grib2"/>
  <catalogRef xlink:href="https://other.example.com/thredds/catalog/x/catalog.xml" xlink:title="Other"/>
</catalog>
"""
    other = """<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"
         xmlns:xlink="http://www.w3.org/1999/xlink" name="Other">
  <service name="http" serviceType="HTTPServer" base="/thredds/fileServer/"/>
  <dataset name="dup.grib2" urlPath="shared/dup.grib2"/>
</catalog>
"""

    def fetcher(url: str) -> str:
        assert url.startswith("https://other.example.com/")
        return other

    out = thr.list_files(
        "https://host.example.com/thredds/catalog/root/catalog.xml",
        catalog_xml=root,
        recursive=True,
        fetcher=fetcher,
    )
    assert out == [
        "https://host.example.com/thredds/fileServer/shared/dup.grib2",
        "https://other.example.com/thredds/fileServer/shared/dup.grib2",
    ]


def test_recursion_skips_non_xml_subcatalog():
    # A server may return an HTML error page / auth redirect for a catalogRef.
    def fetcher(url: str) -> str:
        return "<html><body>403 Forbidden</body></html>"

    out = thr.list_files(
        "https://thredds.example.com/thredds/catalog/root/catalog.xml",
        catalog_xml=ROOT_CATALOG,
        recursive=True,
        fetcher=fetcher,
    )
    # Root datasets are still returned; the bad sub-catalog is logged and skipped.
    assert out == ["https://thredds.example.com/thredds/fileServer/root/top.grib2"]


def test_sync_directory_downloads_and_skips(tmp_path, monkeypatch):
    calls: list[str] = []

    def fake_fetch_bytes(url, *, timeout=60, headers=None):
        calls.append(url)
        return b"DATA"

    monkeypatch.setattr(thr.http_backend, "fetch_bytes", fake_fetch_bytes)

    written = thr.sync_directory(
        CATALOG_URL,
        str(tmp_path),
        catalog_xml=FLAT_CATALOG,
        pattern=r"\.grib2$",
    )
    assert len(written) == 2
    assert (tmp_path / "foo_20240101.grib2").read_bytes() == b"DATA"

    # Second sync skips existing non-empty files (no new downloads).
    calls.clear()
    written2 = thr.sync_directory(
        CATALOG_URL,
        str(tmp_path),
        catalog_xml=FLAT_CATALOG,
        pattern=r"\.grib2$",
    )
    assert written2 == []
    assert calls == []


def test_sync_directory_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(
        thr.http_backend,
        "fetch_bytes",
        lambda url, *, timeout=60, headers=None: b"NEW",
    )
    (tmp_path / "foo_20240102.grib2").write_bytes(b"OLD")
    written = thr.sync_directory(
        CATALOG_URL,
        str(tmp_path),
        catalog_xml=FLAT_CATALOG,
        pattern=r"foo_20240102",
        sync_options=thr.SyncOptions(overwrite_existing=True),
    )
    assert (tmp_path / "foo_20240102.grib2").read_bytes() == b"NEW"
    assert len(written) == 1


def test_recheck_existing_keeps_local_when_size_unknown(tmp_path, monkeypatch):
    # When --recheck-existing is set but the server provides no Content-Length,
    # the local copy must be kept (no re-download), matching the FTP backend.
    monkeypatch.setattr(thr.http_backend, "get_size", lambda *a, **k: None)
    fetched: list[str] = []

    def fake_fetch_bytes(url, *, timeout=60, headers=None):
        fetched.append(url)
        return b"NEW"

    monkeypatch.setattr(thr.http_backend, "fetch_bytes", fake_fetch_bytes)
    (tmp_path / "foo_20240102.grib2").write_bytes(b"OLD")
    written = thr.sync_directory(
        CATALOG_URL,
        str(tmp_path),
        catalog_xml=FLAT_CATALOG,
        pattern=r"foo_20240102",
        sync_options=thr.SyncOptions(recheck_existing=True),
    )
    assert written == []
    assert fetched == []
    assert (tmp_path / "foo_20240102.grib2").read_bytes() == b"OLD"


def test_missing_http_server_defaults_base():
    xml = (
        '<catalog xmlns="http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0">'
        '<dataset name="x" urlPath="a/x.grib2"/></catalog>'
    )
    datasets, _ = thr.parse_catalog(xml, CATALOG_URL)
    assert datasets[0].download_url.endswith("/thredds/fileServer/a/x.grib2")


def test_cli_thredds_auth_and_credential_flags(monkeypatch, tmp_path, capsysbinary):
    # Parity with acquire http: --auth and --credential resolve into
    # request headers instead of requiring secrets in raw --header.
    import argparse

    from zyra.connectors import ingest

    seen = {}

    def fake_list_files(url, **kw):
        seen["headers"] = kw.get("headers")
        return [f"{url.rsplit('/', 1)[0]}/fileServer/a/x.grib2"]

    def fake_fetch(url, headers=None):
        seen["fetch_headers"] = headers
        return b"DATA"

    monkeypatch.setattr(ingest.thredds_backend, "list_files", fake_list_files)
    monkeypatch.setattr(ingest.thredds_backend, "fetch_bytes", fake_fetch)
    monkeypatch.setenv("MY_TOKEN", "sekrit")

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    ingest.register_cli(sub)
    out_file = tmp_path / "out.bin"
    ns = parser.parse_args(
        [
            "thredds",
            CATALOG_URL,
            "--auth",
            "bearer:$MY_TOKEN",
            "-o",
            str(out_file),
        ]
    )
    assert ns.func(ns) == 0
    assert seen["fetch_headers"]["Authorization"] == "Bearer sekrit"
    assert out_file.read_bytes() == b"DATA"


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
