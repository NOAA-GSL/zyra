# SPDX-License-Identifier: Apache-2.0
import argparse
import warnings
from unittest.mock import patch

import pytest

from zyra.connectors.backends import ftp as ftp_backend


def test_parse_ftp_path_warns_on_explicit_override():
    with pytest.warns(
        UserWarning, match="username overrides username embedded in the URL"
    ):
        host, path, user, pwd = ftp_backend.parse_ftp_path(
            "ftp://urluser:urlpass@ftp.example.com/path/file.bin",
            username="explicit",
        )
    assert host == "ftp.example.com"
    assert path == "path/file.bin"
    assert user == "explicit"
    assert pwd == "urlpass"


def test_parse_ftp_path_warns_on_password_override():
    with pytest.warns(UserWarning, match="password overrides credentials"):
        host, path, user, pwd = ftp_backend.parse_ftp_path(
            "ftp://urluser:urlpass@ftp.example.com/path/file.bin",
            password="newpass",
        )
    assert pwd == "newpass"
    assert user == "urluser"


def test_parse_ftp_path_uses_url_credentials_when_explicit_missing():
    host, path, user, pwd = ftp_backend.parse_ftp_path(
        "ftp://urluser:urlpass@ftp.example.com/path/file.bin"
    )
    assert (host, path, user, pwd) == (
        "ftp.example.com",
        "path/file.bin",
        "urluser",
        "urlpass",
    )


def test_parse_ftp_path_no_warning_when_values_match():
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        host, path, user, pwd = ftp_backend.parse_ftp_path(
            "ftp://urluser:urlpass@ftp.example.com/path/file.bin",
            username="urluser",
            password="urlpass",
        )
    assert not captured
    assert (user, pwd) == ("urluser", "urlpass")


def test_list_files_with_date_filter_and_credentials(monkeypatch):
    # Mock ftplib FTP.nlst
    class _FTP:
        def __init__(self, timeout=30):
            self.timeout = timeout

        def connect(self, host):
            return None

        def login(self, user=None, passwd=None):
            return None

        def set_pasv(self, flag):
            return None

        def cwd(self, d):
            return None

        def nlst(self):
            return [
                "/SOS/DroughtRisk_Weekly/DroughtRisk_Weekly_20240101.png",
                "/SOS/DroughtRisk_Weekly/DroughtRisk_Weekly_20250101.png",
            ]

    with patch("zyra.connectors.backends.ftp.FTP", _FTP):
        names = ftp_backend.list_files(
            "ftp://anonymous:test%40example.com@ftp.host/SOS/DroughtRisk_Weekly",
            pattern=r"DroughtRisk_Weekly_(\d{8})\.png",
            since="2024-06-01T00:00:00",
            date_format="%Y%m%d",
        )
        assert names and all("2025" in n for n in names)


def test_sync_directory_cleans_zero_byte(tmp_path):
    # Create a zero-byte file and verify it gets removed with clean_zero_bytes
    d = tmp_path / "frames"
    d.mkdir()
    fz = d / "z.png"
    fz.write_bytes(b"")

    class _FTP2:
        def __init__(self, timeout=30):
            pass

        def connect(self, host):
            return None

        def login(self, user=None, passwd=None):
            return None

        def set_pasv(self, flag):
            return None

        def cwd(self, d):
            return None

        def nlst(self):
            return ["a.png"]

        def retrbinary(self, cmd, cb):
            cb(b"x")

        def quit(self):
            return None

    with patch("zyra.connectors.backends.ftp.FTP", _FTP2):
        ftp_backend.sync_directory("ftp://host/dir", str(d), clean_zero_bytes=True)
        assert not fz.exists()


# ============================================================================
# Tests for new sync options functionality (issue #11)
# ============================================================================


class TestParseMinSize:
    """Tests for _parse_min_size helper function."""

    def test_parse_min_size_none(self):
        assert ftp_backend._parse_min_size(None, 1000) is None

    def test_parse_min_size_int(self):
        assert ftp_backend._parse_min_size(500, 1000) == 500

    def test_parse_min_size_string_bytes(self):
        assert ftp_backend._parse_min_size("500", 1000) == 500

    def test_parse_min_size_percentage(self):
        # 10% increase from 1000 = 1000 * 1.10 = 1100
        assert ftp_backend._parse_min_size("10%", 1000) == 1100

    def test_parse_min_size_percentage_zero(self):
        # 0% = same as original
        assert ftp_backend._parse_min_size("0%", 1000) == 1000

    def test_parse_min_size_invalid_string(self):
        assert ftp_backend._parse_min_size("abc", 1000) is None

    def test_parse_min_size_invalid_percentage(self):
        assert ftp_backend._parse_min_size("abc%", 1000) is None


class TestShouldDownload:
    """Tests for should_download decision logic."""

    def test_should_download_new_file(self, tmp_path):
        """New files should always be downloaded."""
        local_path = tmp_path / "new_file.png"
        options = ftp_backend.SyncOptions()
        result, reason = ftp_backend.should_download(
            "new_file.png", local_path, None, None, options
        )
        assert result is True
        assert "new file" in reason

    def test_should_download_zero_byte_local(self, tmp_path):
        """Zero-byte local files should be replaced."""
        local_path = tmp_path / "empty.png"
        local_path.write_bytes(b"")
        options = ftp_backend.SyncOptions()
        result, reason = ftp_backend.should_download(
            "empty.png", local_path, 100, None, options
        )
        assert result is True
        assert "zero bytes" in reason

    def test_should_download_overwrite_existing(self, tmp_path):
        """--overwrite-existing forces download."""
        local_path = tmp_path / "existing.png"
        local_path.write_bytes(b"existing content")
        options = ftp_backend.SyncOptions(overwrite_existing=True)
        result, reason = ftp_backend.should_download(
            "existing.png", local_path, 100, None, options
        )
        assert result is True
        assert "overwrite-existing" in reason

    def test_should_download_prefer_remote(self, tmp_path):
        """--prefer-remote forces download."""
        local_path = tmp_path / "existing.png"
        local_path.write_bytes(b"existing content")
        options = ftp_backend.SyncOptions(prefer_remote=True)
        result, reason = ftp_backend.should_download(
            "existing.png", local_path, 100, None, options
        )
        assert result is True
        assert "prefer-remote" in reason

    def test_should_download_skip_if_done_marker_exists(self, tmp_path):
        """--skip-if-local-done respects .done markers."""
        local_path = tmp_path / "processed.png"
        local_path.write_bytes(b"content")
        done_marker = tmp_path / "processed.png.done"
        done_marker.write_text("done")
        options = ftp_backend.SyncOptions(skip_if_local_done=True)
        result, reason = ftp_backend.should_download(
            "processed.png", local_path, 100, None, options
        )
        assert result is False
        assert ".done marker" in reason

    def test_should_download_skip_if_done_no_marker(self, tmp_path):
        """Without .done marker, file may be downloaded."""
        local_path = tmp_path / "not_processed.png"
        local_path.write_bytes(b"content")
        options = ftp_backend.SyncOptions(
            skip_if_local_done=True, overwrite_existing=True
        )
        result, reason = ftp_backend.should_download(
            "not_processed.png", local_path, 100, None, options
        )
        assert result is True

    def test_should_download_size_mismatch_recheck(self, tmp_path):
        """--recheck-existing downloads when sizes differ."""
        local_path = tmp_path / "file.png"
        local_path.write_bytes(b"short")  # 5 bytes
        options = ftp_backend.SyncOptions(recheck_existing=True)
        result, reason = ftp_backend.should_download(
            "file.png",
            local_path,
            100,
            None,
            options,  # Remote is 100 bytes
        )
        assert result is True
        assert "size mismatch" in reason

    def test_should_download_size_match_no_recheck(self, tmp_path):
        """Same size with --recheck-existing should not download."""
        local_path = tmp_path / "file.png"
        local_path.write_bytes(b"12345")  # 5 bytes
        options = ftp_backend.SyncOptions(recheck_existing=True)
        result, reason = ftp_backend.should_download(
            "file.png",
            local_path,
            5,
            None,
            options,  # Same size
        )
        assert result is False
        assert "up-to-date" in reason

    def test_should_download_min_remote_size_met(self, tmp_path):
        """--min-remote-size downloads when threshold is met."""
        local_path = tmp_path / "file.png"
        local_path.write_bytes(b"x" * 100)  # 100 bytes
        options = ftp_backend.SyncOptions(min_remote_size="10%")  # threshold = 110
        result, reason = ftp_backend.should_download(
            "file.png",
            local_path,
            120,
            None,
            options,  # Remote 120 >= 110
        )
        assert result is True
        assert "threshold" in reason

    def test_should_download_min_remote_size_not_met(self, tmp_path):
        """--min-remote-size skips when threshold not met."""
        local_path = tmp_path / "file.png"
        local_path.write_bytes(b"x" * 100)  # 100 bytes
        options = ftp_backend.SyncOptions(min_remote_size="10%")  # threshold = 110
        result, reason = ftp_backend.should_download(
            "file.png",
            local_path,
            105,
            None,
            options,  # Remote 105 < 110
        )
        assert result is False
        assert "up-to-date" in reason

    def test_should_download_mtime_newer_remote(self, tmp_path):
        """Default behavior downloads when remote mtime is newer."""
        import time
        from datetime import datetime

        local_path = tmp_path / "file.png"
        local_path.write_bytes(b"content")
        # Set local mtime to past
        old_time = time.time() - 86400  # 1 day ago
        import os

        os.utime(local_path, (old_time, old_time))

        options = ftp_backend.SyncOptions()
        remote_mtime = datetime.now()  # Current time (newer)
        result, reason = ftp_backend.should_download(
            "file.png", local_path, 100, remote_mtime, options
        )
        assert result is True
        assert "mtime newer" in reason

    def test_should_download_mtime_older_remote(self, tmp_path):
        """Default behavior skips when remote mtime is older."""
        from datetime import datetime, timedelta

        local_path = tmp_path / "file.png"
        local_path.write_bytes(b"content")
        # Note: local file has current mtime from write_bytes

        options = ftp_backend.SyncOptions()
        remote_mtime = datetime.now() - timedelta(days=7)  # 7 days ago
        result, reason = ftp_backend.should_download(
            "file.png", local_path, 100, remote_mtime, options
        )
        assert result is False
        assert "up-to-date" in reason

    def test_should_download_prefer_remote_if_meta_newer(self, tmp_path):
        """--prefer-remote-if-meta-newer uses frames-meta.json timestamps."""
        import time
        from datetime import datetime

        local_path = tmp_path / "frame_001.png"
        local_path.write_bytes(b"content")
        # Set local mtime to past
        old_time = time.time() - 86400
        import os

        os.utime(local_path, (old_time, old_time))

        options = ftp_backend.SyncOptions(prefer_remote_if_meta_newer=True)
        frames_meta = {
            "frames": [
                {"filename": "frame_001.png", "timestamp": datetime.now().isoformat()}
            ]
        }
        result, reason = ftp_backend.should_download(
            "frame_001.png", local_path, 100, None, options, frames_meta
        )
        assert result is True
        assert "meta timestamp newer" in reason

    def test_should_download_recheck_missing_meta(self, tmp_path):
        """--recheck-missing-meta downloads files without metadata."""
        local_path = tmp_path / "orphan.png"
        local_path.write_bytes(b"content")
        options = ftp_backend.SyncOptions(recheck_missing_meta=True)
        frames_meta = {
            "frames": [
                {"filename": "other_file.png", "timestamp": "2024-01-01T00:00:00"}
            ]
        }
        result, reason = ftp_backend.should_download(
            "orphan.png", local_path, 100, None, options, frames_meta
        )
        assert result is True
        assert "missing companion metadata" in reason


class TestGetRemoteMtime:
    """Tests for get_remote_mtime function."""

    def test_get_remote_mtime_success(self, monkeypatch):
        """MDTM response is parsed correctly."""

        class _FTPMdtm:
            def __init__(self, timeout=30):
                pass

            def connect(self, host):
                return None

            def login(self, user=None, passwd=None):
                return None

            def set_pasv(self, flag):
                return None

            def cwd(self, d):
                return None

            def sendcmd(self, cmd):
                return "213 20240615120000"  # 2024-06-15 12:00:00

            def quit(self):
                return None

        with patch("zyra.connectors.backends.ftp.FTP", _FTPMdtm):
            result = ftp_backend.get_remote_mtime("ftp://host/path/file.txt")
            from datetime import datetime

            assert result == datetime(2024, 6, 15, 12, 0, 0)

    def test_get_remote_mtime_not_supported(self, monkeypatch):
        """MDTM not supported returns None gracefully."""
        from ftplib import error_perm

        class _FTPNoMdtm:
            def __init__(self, timeout=30):
                pass

            def connect(self, host):
                return None

            def login(self, user=None, passwd=None):
                return None

            def set_pasv(self, flag):
                return None

            def cwd(self, d):
                return None

            def sendcmd(self, cmd):
                raise error_perm("500 MDTM not understood")

            def quit(self):
                return None

        with patch("zyra.connectors.backends.ftp.FTP", _FTPNoMdtm):
            result = ftp_backend.get_remote_mtime("ftp://host/path/file.txt")
            assert result is None


class TestSyncDirectoryWithOptions:
    """Tests for sync_directory with SyncOptions."""

    def test_sync_directory_with_overwrite_existing(self, tmp_path):
        """sync_directory respects overwrite_existing option."""
        d = tmp_path / "frames"
        d.mkdir()
        existing = d / "file.png"
        existing.write_bytes(b"old content")

        class _FTPSync:
            def __init__(self, timeout=30):
                pass

            def connect(self, host):
                return None

            def login(self, user=None, passwd=None):
                return None

            def set_pasv(self, flag):
                return None

            def cwd(self, path):
                return None

            def nlst(self):
                return ["file.png"]

            def size(self, filename):
                return 100

            def sendcmd(self, cmd):
                return "213 20240101120000"

            def retrbinary(self, cmd, cb):
                cb(b"new content")

            def quit(self):
                return None

        sync_opts = ftp_backend.SyncOptions(overwrite_existing=True)
        with patch("zyra.connectors.backends.ftp.FTP", _FTPSync):
            ftp_backend.sync_directory("ftp://host/dir", str(d), sync_options=sync_opts)
            # File should be replaced with new content
            assert existing.read_bytes() == b"new content"

    def test_sync_directory_skip_with_done_marker(self, tmp_path):
        """sync_directory skips files with .done markers."""
        d = tmp_path / "frames"
        d.mkdir()
        existing = d / "done_file.png"
        existing.write_bytes(b"original")
        done_marker = d / "done_file.png.done"
        done_marker.write_text("processed")

        download_called = []

        class _FTPSkip:
            def __init__(self, timeout=30):
                pass

            def connect(self, host):
                return None

            def login(self, user=None, passwd=None):
                return None

            def set_pasv(self, flag):
                return None

            def cwd(self, path):
                return None

            def nlst(self):
                return ["done_file.png"]

            def sendcmd(self, cmd):
                # For get_remote_mtime if it's called
                return "213 20240101120000"

            def retrbinary(self, cmd, cb):
                download_called.append(cmd)
                cb(b"new content")

            def quit(self):
                return None

        sync_opts = ftp_backend.SyncOptions(skip_if_local_done=True)
        with patch("zyra.connectors.backends.ftp.FTP", _FTPSkip):
            ftp_backend.sync_directory("ftp://host/dir", str(d), sync_options=sync_opts)
            # File should NOT be downloaded
            assert len(download_called) == 0
            assert existing.read_bytes() == b"original"


# ============================================================================
# CLI integration tests for SyncOptions (issue #11)
# ============================================================================


class TestCLIIntegration:
    """Test that CLI arguments correctly construct SyncOptions and pass to backend."""

    def _make_namespace(self, **kwargs) -> argparse.Namespace:
        """Helper to create a Namespace with default values."""
        defaults = {
            "path": "ftp://host/dir",
            "sync_dir": "/tmp/sync",
            "pattern": None,
            "since": None,
            "since_period": None,
            "until": None,
            "date_format": None,
            "credential": [],
            "credential_file": None,
            "user": None,
            "password": None,
            "clean_zero_bytes": False,
            "overwrite_existing": False,
            "recheck_existing": False,
            "min_remote_size": None,
            "prefer_remote": False,
            "prefer_remote_if_meta_newer": False,
            "skip_if_local_done": False,
            "recheck_missing_meta": False,
            "frames_meta": None,
            "list": False,
            "verbose": False,
            "quiet": False,
            "trace": False,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def test_cli_overwrite_existing_flag(self, tmp_path):
        """--overwrite-existing CLI flag constructs correct SyncOptions."""
        from zyra.connectors.ingest import _cmd_ftp

        ns = self._make_namespace(
            sync_dir=str(tmp_path),
            overwrite_existing=True,
        )

        captured_opts = []

        def mock_sync_directory(path, local_dir, **kwargs):
            captured_opts.append(kwargs.get("sync_options"))

        with patch.object(ftp_backend, "sync_directory", mock_sync_directory):
            _cmd_ftp(ns)

        assert len(captured_opts) == 1
        assert captured_opts[0].overwrite_existing is True
        assert captured_opts[0].recheck_existing is False

    def test_cli_recheck_existing_flag(self, tmp_path):
        """--recheck-existing CLI flag constructs correct SyncOptions."""
        from zyra.connectors.ingest import _cmd_ftp

        ns = self._make_namespace(
            sync_dir=str(tmp_path),
            recheck_existing=True,
        )

        captured_opts = []

        def mock_sync_directory(path, local_dir, **kwargs):
            captured_opts.append(kwargs.get("sync_options"))

        with patch.object(ftp_backend, "sync_directory", mock_sync_directory):
            _cmd_ftp(ns)

        assert len(captured_opts) == 1
        assert captured_opts[0].recheck_existing is True

    def test_cli_min_remote_size_percentage(self, tmp_path):
        """--min-remote-size with percentage is passed correctly."""
        from zyra.connectors.ingest import _cmd_ftp

        ns = self._make_namespace(
            sync_dir=str(tmp_path),
            min_remote_size="10%",
        )

        captured_opts = []

        def mock_sync_directory(path, local_dir, **kwargs):
            captured_opts.append(kwargs.get("sync_options"))

        with patch.object(ftp_backend, "sync_directory", mock_sync_directory):
            _cmd_ftp(ns)

        assert len(captured_opts) == 1
        assert captured_opts[0].min_remote_size == "10%"

    def test_cli_skip_if_local_done_flag(self, tmp_path):
        """--skip-if-local-done CLI flag constructs correct SyncOptions."""
        from zyra.connectors.ingest import _cmd_ftp

        ns = self._make_namespace(
            sync_dir=str(tmp_path),
            skip_if_local_done=True,
        )

        captured_opts = []

        def mock_sync_directory(path, local_dir, **kwargs):
            captured_opts.append(kwargs.get("sync_options"))

        with patch.object(ftp_backend, "sync_directory", mock_sync_directory):
            _cmd_ftp(ns)

        assert len(captured_opts) == 1
        assert captured_opts[0].skip_if_local_done is True

    def test_cli_prefer_remote_if_meta_newer_with_frames_meta(self, tmp_path):
        """--prefer-remote-if-meta-newer with --frames-meta path is passed correctly."""
        from zyra.connectors.ingest import _cmd_ftp

        meta_file = tmp_path / "frames-meta.json"
        meta_file.write_text('{"frames": []}')

        ns = self._make_namespace(
            sync_dir=str(tmp_path),
            prefer_remote_if_meta_newer=True,
            frames_meta=str(meta_file),
        )

        captured_opts = []

        def mock_sync_directory(path, local_dir, **kwargs):
            captured_opts.append(kwargs.get("sync_options"))

        with patch.object(ftp_backend, "sync_directory", mock_sync_directory):
            _cmd_ftp(ns)

        assert len(captured_opts) == 1
        assert captured_opts[0].prefer_remote_if_meta_newer is True
        assert captured_opts[0].frames_meta_path == str(meta_file)

    def test_cli_multiple_sync_options_combined(self, tmp_path):
        """Multiple sync options can be combined correctly."""
        from zyra.connectors.ingest import _cmd_ftp

        ns = self._make_namespace(
            sync_dir=str(tmp_path),
            recheck_existing=True,
            skip_if_local_done=True,
            min_remote_size="5%",
        )

        captured_opts = []

        def mock_sync_directory(path, local_dir, **kwargs):
            captured_opts.append(kwargs.get("sync_options"))

        with patch.object(ftp_backend, "sync_directory", mock_sync_directory):
            _cmd_ftp(ns)

        assert len(captured_opts) == 1
        opts = captured_opts[0]
        assert opts.recheck_existing is True
        assert opts.skip_if_local_done is True
        assert opts.min_remote_size == "5%"
        # Others should be defaults
        assert opts.overwrite_existing is False
        assert opts.prefer_remote is False
