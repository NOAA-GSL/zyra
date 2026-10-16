# SPDX-License-Identifier: Apache-2.0
"""Gzip-compressed GRIB2 input (issue #370, MRMS ``.grib2.gz`` on NODD).

``read_bytes_any`` gunzips by magic bytes so every reader (local path,
stdin, HTTP(S), S3) works the same way, and ``grib_decode`` treats zero
decoded messages as a failure instead of an empty success.
"""

from __future__ import annotations

import gzip
import io
import struct
import sys
from types import SimpleNamespace

import pytest

from zyra.utils.io_utils import read_bytes_any


def _make_grib2(values=(270, 271, 272, 273)) -> bytes:
    """Build a minimal valid GRIB2 message: 2x2 lat/lon TMP, simple packing."""

    def sec(num: int, body: bytes) -> bytes:
        return struct.pack(">IB", 5 + len(body), num) + body

    s1 = sec(
        1, struct.pack(">HHBBBHBBBBBBB", 7, 0, 2, 1, 1, 2023, 4, 1, 12, 0, 0, 0, 1)
    )
    grid = struct.pack(">BBIBIBI", 6, 0, 0, 0, 0, 0, 0) + struct.pack(
        ">IIIIiiBiiIIB",
        2,
        2,
        0,
        0,
        11_000_000,
        0,
        48,
        10_000_000,
        1_000_000,
        1_000_000,
        1_000_000,
        0,
    )
    s3 = sec(3, struct.pack(">BIBBH", 0, len(values), 0, 0, 0) + grid)
    s4 = sec(
        4,
        struct.pack(">HH", 0, 0)
        + struct.pack(
            ">BBBBBHBBIBBIBBI", 0, 0, 2, 0, 96, 0, 0, 1, 0, 103, 0, 2, 255, 0, 0
        ),
    )
    ref = min(values)
    s5 = sec(5, struct.pack(">IHfhhBB", len(values), 0, float(ref), 0, 0, 8, 0))
    s6 = sec(6, b"\xff")
    s7 = sec(7, bytes(int(v - ref) for v in values))
    body = s1 + s3 + s4 + s5 + s6 + s7 + b"7777"
    return b"GRIB\x00\x00\x00\x02" + struct.pack(">Q", 16 + len(body)) + body


GRIB = _make_grib2()
GRIB_GZ = gzip.compress(GRIB)


def test_local_gz_path_is_decompressed(tmp_path):
    p = tmp_path / "MRMS_x.grib2.gz"
    p.write_bytes(GRIB_GZ)
    assert read_bytes_any(str(p)) == GRIB


def test_detection_uses_magic_bytes_not_extension(tmp_path):
    p = tmp_path / "no_suffix.grib2"
    p.write_bytes(GRIB_GZ)
    assert read_bytes_any(str(p)) == GRIB


def test_uncompressed_input_passes_through(tmp_path):
    p = tmp_path / "plain.grib2"
    p.write_bytes(GRIB)
    assert read_bytes_any(str(p)) == GRIB


def test_stdin_gz_is_decompressed(monkeypatch):
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(GRIB_GZ)))
    assert read_bytes_any("-") == GRIB


def test_http_gz_fetch_is_decompressed(monkeypatch):
    from zyra.connectors.backends import http as http_backend

    monkeypatch.setattr(http_backend, "fetch_bytes", lambda url, **kw: GRIB_GZ)
    assert read_bytes_any("https://example.org/MRMS_x.grib2.gz") == GRIB


def test_s3_gz_fetch_is_decompressed(monkeypatch):
    from zyra.connectors.backends import s3 as s3_backend

    monkeypatch.setattr(s3_backend, "fetch_bytes", lambda url, **kw: GRIB_GZ)
    out = read_bytes_any("s3://noaa-mrms-pds/CONUS/x.grib2.gz", unsigned=True)
    assert out == GRIB


def test_corrupt_gzip_raises_runtime_error(tmp_path):
    p = tmp_path / "bad.grib2.gz"
    p.write_bytes(GRIB_GZ[:20])
    with pytest.raises(RuntimeError, match="Failed to decompress gzip"):
        read_bytes_any(str(p))


@pytest.mark.parametrize(
    "url", ["https://example.org/x.grib2.gz?v=1", "s3://noaa-mrms-pds/x.grib2.gz"]
)
def test_idx_pattern_with_gz_url_fails_before_fetch(monkeypatch, url):
    from zyra.connectors.backends import http as http_backend
    from zyra.connectors.backends import s3 as s3_backend

    def no_idx(*a, **kw):
        pytest.fail("should not fetch .idx for gzip input")

    monkeypatch.setattr(http_backend, "get_idx_lines", no_idx)
    monkeypatch.setattr(s3_backend, "get_idx_lines", no_idx)
    with pytest.raises(RuntimeError, match="not supported for gzip-compressed"):
        read_bytes_any(url, idx_pattern="REFC")


def test_idx_ranges_returning_gzip_fail_clearly(monkeypatch):
    # A URL without a .gz suffix whose byte ranges turn out to be gzip.
    from zyra.connectors.backends import http as http_backend

    monkeypatch.setattr(
        http_backend, "get_idx_lines", lambda url, **kw: ["1:0:d=2023040112:REFC::"]
    )
    monkeypatch.setattr(
        http_backend, "download_byteranges", lambda url, ranges, **kw: GRIB_GZ
    )
    with pytest.raises(RuntimeError, match="not supported for gzip-compressed"):
        read_bytes_any("https://example.org/feed", idx_pattern="REFC")


@pytest.mark.parametrize("url", ["https://example.org/feed", "s3://bucket/feed"])
def test_idx_ranges_past_gzip_header_fail_clearly(monkeypatch, url):
    # Extensionless gzip source whose matched range starts after byte 0:
    # the subset is interior compressed bytes with no gzip header.
    from zyra.connectors.backends import http as http_backend
    from zyra.connectors.backends import s3 as s3_backend

    idx = ["1:0:d=2023040112:TMP::", "2:40:d=2023040112:REFC::"]
    interior = GRIB_GZ[40:]
    assert not interior.startswith((b"GRIB", b"\x1f\x8b"))
    monkeypatch.setattr(http_backend, "get_idx_lines", lambda u, **kw: idx)
    monkeypatch.setattr(s3_backend, "get_idx_lines", lambda u, **kw: idx)
    monkeypatch.setattr(
        http_backend, "download_byteranges", lambda u, r, **kw: interior
    )
    monkeypatch.setattr(
        s3_backend, "download_byteranges", lambda u, b, r, **kw: interior
    )
    with pytest.raises(RuntimeError, match="do not start with a GRIB message"):
        read_bytes_any(url, idx_pattern="REFC")


def test_grib_decode_zero_messages_pygrib_raises():
    pytest.importorskip("pygrib")
    from zyra.processing.grib_utils import grib_decode

    # Still-compressed bytes: pygrib opens them but finds no messages.
    with pytest.raises(RuntimeError, match="no GRIB messages found"):
        grib_decode(GRIB_GZ, backend="pygrib")


def test_grib_decode_zero_messages_default_backend_raises(monkeypatch):
    pytest.importorskip("pygrib")
    from zyra.processing.grib_utils import grib_decode

    # Without wgrib2 to fall back to, the error must name the real problem.
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(RuntimeError, match="no GRIB messages found"):
        grib_decode(b"not a grib file")


def test_gz_path_decodes_end_to_end(tmp_path):
    pytest.importorskip("pygrib")
    from zyra.processing.grib_utils import grib_decode

    p = tmp_path / "MRMS_x.grib2.gz"
    p.write_bytes(GRIB_GZ)
    decoded = grib_decode(read_bytes_any(str(p)), backend="pygrib")
    assert decoded.backend == "pygrib"
    assert len(decoded.messages) == 1
    assert decoded.messages[0].values.tolist() == [[270, 271], [272, 273]]


def test_cli_decode_grib2_raw_emits_decompressed_bytes(tmp_path, capsysbinary):
    import argparse

    from zyra.processing import register_cli

    p = tmp_path / "MRMS_x.grib2.gz"
    p.write_bytes(GRIB_GZ)
    parser = argparse.ArgumentParser()
    register_cli(parser.add_subparsers(dest="cmd"))
    ns = parser.parse_args(["decode-grib2", str(p), "--raw"])
    assert ns.func(ns) == 0
    assert capsysbinary.readouterr().out == GRIB
