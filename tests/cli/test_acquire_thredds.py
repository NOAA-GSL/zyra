# SPDX-License-Identifier: Apache-2.0
"""CLI-level tests for ``zyra acquire thredds`` (hermetic, no network)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from zyra.cli import main as cli_main

SINGLE_CATALOG = """<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"
         xmlns:xlink="http://www.w3.org/1999/xlink" name="Foo">
  <service name="http" serviceType="HTTPServer" base="/thredds/fileServer/"/>
  <dataset name="a.grib2" urlPath="foo/a.grib2"/>
  <dataset name="b.txt" urlPath="foo/b.txt"/>
</catalog>
"""

CATALOG = """<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"
         xmlns:xlink="http://www.w3.org/1999/xlink" name="Foo">
  <service name="http" serviceType="HTTPServer" base="/thredds/fileServer/"/>
  <dataset name="a.grib2" urlPath="foo/a.grib2"/>
  <dataset name="b.txt" urlPath="foo/b.txt"/>
</catalog>
"""


def test_acquire_thredds_list(capsys):
    with patch("zyra.connectors.backends.http.fetch_text", return_value=CATALOG):
        rc = cli_main(
            [
                "acquire",
                "thredds",
                "https://thredds.example.com/thredds/catalog/foo/catalog.xml",
                "--list",
                "--pattern",
                r"\.grib2$",
            ]
        )
    assert rc in (0, None)
    out = capsys.readouterr().out
    assert "https://thredds.example.com/thredds/fileServer/foo/a.grib2" in out
    assert "b.txt" not in out


def test_acquire_thredds_sync(tmp_path):
    with (
        patch("zyra.connectors.backends.http.fetch_text", return_value=CATALOG),
        patch("zyra.connectors.backends.http.fetch_bytes", return_value=b"DATA"),
    ):
        rc = cli_main(
            [
                "acquire",
                "thredds",
                "https://thredds.example.com/thredds/catalog/foo/catalog.xml",
                "--sync-dir",
                str(tmp_path),
                "--pattern",
                r"\.grib2$",
            ]
        )
    assert rc in (0, None)
    assert (tmp_path / "a.grib2").read_bytes() == b"DATA"
    assert not (tmp_path / "b.txt").exists()


def test_acquire_thredds_single_to_output(tmp_path):
    out = tmp_path / "only.grib2"
    with (
        patch("zyra.connectors.backends.http.fetch_text", return_value=SINGLE_CATALOG),
        patch("zyra.connectors.backends.http.fetch_bytes", return_value=b"DATA"),
    ):
        rc = cli_main(
            [
                "acquire",
                "thredds",
                "https://thredds.example.com/thredds/catalog/foo/catalog.xml",
                "--pattern",
                r"\.grib2$",
                "-o",
                str(out),
            ]
        )
    assert rc in (0, None)
    assert out.read_bytes() == b"DATA"


def test_acquire_thredds_multi_without_output_dir_errors():
    with (
        patch("zyra.connectors.backends.http.fetch_text", return_value=SINGLE_CATALOG),
        patch("zyra.connectors.backends.http.fetch_bytes", return_value=b"DATA"),
        pytest.raises(SystemExit),
    ):
        cli_main(
            [
                "acquire",
                "thredds",
                "https://thredds.example.com/thredds/catalog/foo/catalog.xml",
                "-o",
                "-",
            ]
        )
