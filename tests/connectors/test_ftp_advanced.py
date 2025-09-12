# SPDX-License-Identifier: Apache-2.0
from unittest.mock import patch

from zyra.connectors.backends import ftp as ftp_backend


def test_ftp_get_size_delegates():
    with patch("zyra.connectors.backends.ftp.FTPManager") as M:
        inst = M.return_value
        inst.get_size.return_value = 123
        assert ftp_backend.get_size("ftp://host/path/file.bin") == 123


def test_ftp_get_idx_and_chunks_and_ranges():
    with patch("zyra.connectors.backends.ftp.FTPManager") as M:
        inst = M.return_value
        inst.get_idx_lines.return_value = ["1:0:a"]
        inst.get_chunks.return_value = ["bytes=0-10", "bytes=11-20"]
        inst.download_byteranges.return_value = b"abc"
        assert ftp_backend.get_idx_lines("ftp://host/file") == ["1:0:a"]
        assert ftp_backend.get_chunks("ftp://host/file") == [
            "bytes=0-10",
            "bytes=11-20",
        ]
        out = ftp_backend.download_byteranges("ftp://host/file", ["bytes=0-1"])
        assert out == b"abc"
