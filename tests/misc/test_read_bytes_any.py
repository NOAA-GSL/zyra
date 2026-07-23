# SPDX-License-Identifier: Apache-2.0
"""Shared URL-aware reader (issue: decode-grib2 URL inputs crashed).

`read_bytes_any` unifies the previously duplicated logic: local paths,
stdin, and HTTP(S)/S3 URLs with GRIB `.idx` byte-range subsetting. The
`process` handlers and `zyra.cli` both route through it.
"""

from __future__ import annotations

import pytest

from zyra.utils.io_utils import read_bytes_any

IDX_LINES = [
    "1:0:d=2026072318:REFC:entire atmosphere:anl:",
    "2:266325:d=2026072318:RETOP:cloud top:anl:",
    "3:511819:d=2026072318:VIS:surface:anl:",
]


def test_local_file(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"GRIBdata")
    assert read_bytes_any(str(p)) == b"GRIBdata"


def test_missing_input_raises_runtime_error():
    with pytest.raises(RuntimeError, match="not found or unsupported"):
        read_bytes_any("/definitely/not/here.grib2")


def test_http_url_plain_fetch(monkeypatch):
    from zyra.connectors.backends import http as http_backend

    monkeypatch.setattr(http_backend, "fetch_bytes", lambda url, **kw: b"FULLFILE")
    assert read_bytes_any("https://example.org/f.grib2") == b"FULLFILE"


def test_http_url_idx_subset(monkeypatch):
    from zyra.connectors.backends import http as http_backend

    calls = {}

    def fake_idx(url, **kw):
        calls["idx_url"] = url
        return IDX_LINES

    def fake_ranges(url, ranges, **kw):
        calls["ranges"] = list(ranges)
        return b"SUBSET"

    monkeypatch.setattr(http_backend, "get_idx_lines", fake_idx)
    monkeypatch.setattr(http_backend, "download_byteranges", fake_ranges)
    out = read_bytes_any("https://example.org/f.grib2", idx_pattern="REFC")
    assert out == b"SUBSET"
    assert calls["idx_url"] == "https://example.org/f.grib2"
    # Only the REFC range is requested, not the whole file.
    assert len(calls["ranges"]) == 1


def test_http_fetch_failure_wrapped(monkeypatch):
    from zyra.connectors.backends import http as http_backend

    def boom(url, **kw):
        raise OSError("connection refused")

    monkeypatch.setattr(http_backend, "fetch_bytes", boom)
    with pytest.raises(RuntimeError, match="Failed to fetch from URL"):
        read_bytes_any("https://example.org/f.grib2")


def test_cli_decode_grib2_url_wiring(monkeypatch, capsysbinary):
    # The registered handler must route URLs through read_bytes_any —
    # previously it Path()-opened them and crashed.
    import argparse

    from zyra.processing import register_cli
    from zyra.utils import io_utils

    seen = {}

    def fake_read(path_or_url, *, idx_pattern=None, unsigned=False):
        seen.update(url=path_or_url, pattern=idx_pattern, unsigned=unsigned)
        return b"GRIB-bytes"

    monkeypatch.setattr(io_utils, "read_bytes_any", fake_read)
    parser = argparse.ArgumentParser()
    register_cli(parser.add_subparsers(dest="cmd"))
    ns = parser.parse_args(
        [
            "decode-grib2",
            "https://example.org/hrrr.grib2",
            "--pattern",
            "REFC",
            "--unsigned",
            "--raw",
        ]
    )
    assert ns.func(ns) == 0
    assert capsysbinary.readouterr().out == b"GRIB-bytes"
    assert seen == {
        "url": "https://example.org/hrrr.grib2",
        "pattern": "REFC",
        "unsigned": True,
    }
