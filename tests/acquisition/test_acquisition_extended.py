from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch, mock_open

import pytest
from botocore.exceptions import ClientError

from datavizhub.acquisition.base import DataAcquirer
from datavizhub.acquisition.s3_manager import S3Manager
from datavizhub.acquisition.http_manager import HTTPHandler
from datavizhub.acquisition.ftp_manager import FTPManager


# ---- S3/HTTP/FTP: pattern filters and retries -----------------------------------------

def test_s3_list_files_pattern_filters():
    with patch("datavizhub.acquisition.s3_manager.boto3.client") as m_client:
        client = Mock()
        m_client.return_value = client
        paginator = Mock()
        client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {"Contents": [{"Key": "a/grib1.grib2"}, {"Key": "a/readme.txt"}]},
            {"Contents": [{"Key": "a/grib2.grib2"}]},
        ]
        s3 = S3Manager(None, None, "bucket", unsigned=True)
        out = list(s3.list_files("a/", pattern=r"\.grib2$"))
        assert out == ["a/grib1.grib2", "a/grib2.grib2"]


def test_http_list_files_pattern_filters():
    html = '<a href="f1.bin">f1.bin</a> <a href="page.html">page</a> <a href="f2.grib2">f2</a>'
    with patch("datavizhub.acquisition.http_manager.requests.get") as m_get:
        resp = Mock()
        resp.raise_for_status = lambda: None
        resp.text = html
        m_get.return_value = resp
        urls = HTTPHandler().list_files("https://example.com/dir/", pattern=r"\.grib2$")
        assert urls and all(u.endswith("f2.grib2") for u in urls)


class _RetryFTP:
    def __init__(self, timeout=30):
        self.timeout = timeout
        self.sock = object()
        self.cwd_dir = "/dir"
        self.files = {
            "/dir/file.idx": b"1:0:a\n",
            "/dir/file.grib2": b"0123",
        }
        self._retr_attempts = 0

    def connect(self, host, port):
        return None

    def login(self, user, passwd):
        return None

    def set_pasv(self, flag):
        return None

    def quit(self):
        return None

    def cwd(self, d):
        self.cwd_dir = d

    def size(self, filename):
        path = f"{self.cwd_dir.rstrip('/')}/{filename}"
        return len(self.files.get(path, b""))

    def nlst(self, directory=None):
        return ["file.grib2", "other.txt"]

    def retrbinary(self, cmd, callback, blocksize=8192, rest=None):
        self._retr_attempts += 1
        if self._retr_attempts == 1:
            raise ConnectionError("temp")
        _, fname = cmd.split()
        path = f"{self.cwd_dir.rstrip('/')}/{fname}"
        callback(self.files[path])


def test_ftp_list_files_pattern_and_get_idx_retry():
    with patch("datavizhub.acquisition.ftp_manager.FTP", _RetryFTP):
        ftp = FTPManager("host")
        ftp.connect()
        files = ftp.list_files("/dir", pattern=r"\.grib2$")
        assert files == ["file.grib2"]
        lines = ftp.get_idx_lines("/dir/file")
        assert lines == ["1:0:a"]


def test_http_get_idx_lines_retries_then_success():
    url = "https://example.com/file.grib2"
    with patch("datavizhub.acquisition.http_manager.requests.get") as m_get:
        import requests

        e = requests.exceptions.RequestException("boom")
        good = Mock(); good.raise_for_status = lambda: None; good.content = b"1:0:a\n"
        m_get.side_effect = [e, good]
        lines = HTTPHandler().get_idx_lines(url)
        assert lines == ["1:0:a"]


def test_s3_get_idx_lines_retry_and_write_and_get_size_error(tmp_path):
    with patch("datavizhub.acquisition.s3_manager.boto3.client") as m_client:
        client = Mock()
        m_client.return_value = client
        client.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
        )

        def _get_object(Bucket=None, Key=None, Range=None):
            if not hasattr(_get_object, "calls"):
                _get_object.calls = 0
            _get_object.calls += 1
            if _get_object.calls == 1:
                raise Exception("temp")
            return {"Body": Mock(read=lambda: b"1:0:a\n")}

        client.get_object.side_effect = _get_object

        s3 = S3Manager(None, None, "bucket", unsigned=True)
        assert s3.get_size("key") is None
        outfile = tmp_path / "idxout"
        lines = s3.get_idx_lines("file", write_to=str(outfile))
        assert lines == ["1:0:a"]


# ---- Additional coverage: base, HTTP errors, S3/FTP ops -------------------------


class _Stub(DataAcquirer):
    def connect(self):
        pass

    def fetch(self, remote_path: str, local_filename: str | None = None) -> bool:
        return True

    def list_files(self, remote_path: str | None = None):
        return []

    def disconnect(self) -> None:
        pass

    def upload(self, local_path: str, remote_path: str) -> bool:
        return True


def test_base_with_retries_before_retry_and_final_raise():
    calls = {"n": 0}
    seen = {"retry": []}

    def func():
        calls["n"] += 1
        raise ValueError("boom")

    def hook(i, e):
        seen["retry"].append((i, str(e)))

    stub = _Stub()
    with pytest.raises(ValueError):
        stub._with_retries(func, attempts=2, exceptions=(ValueError,), before_retry=hook)
    assert len(seen["retry"]) == 1


def test_http_head_without_content_length_and_no_anchors():
    with patch("datavizhub.acquisition.http_manager.requests.head") as m_head:
        r = Mock(); r.raise_for_status = lambda: None; r.headers = {}
        m_head.return_value = r
        assert HTTPHandler().get_size("https://x") is None

    with patch("datavizhub.acquisition.http_manager.requests.get") as m_get:
        g = Mock(); g.raise_for_status = lambda: None; g.text = "<html>no links</html>"
        m_get.return_value = g
        assert HTTPHandler().list_files("https://x") == []


def test_s3_upload_success_and_failure(tmp_path):
    with patch("datavizhub.acquisition.s3_manager.boto3.client") as m_client:
        client = Mock(); m_client.return_value = client
        s3 = S3Manager(None, None, "bucket", unsigned=True)
        client.upload_file.return_value = None
        assert s3.upload_file(str(tmp_path / "f.txt"), "k") is True
        client.upload_file.side_effect = ClientError(
            {"Error": {"Code": "403", "Message": "Forbidden"}}, "PutObject"
        )
        assert s3.upload_file(str(tmp_path / "f.txt"), "k") is False


def test_s3_list_files_error_returns_none():
    with patch("datavizhub.acquisition.s3_manager.boto3.client") as m_client:
        client = Mock(); m_client.return_value = client
        paginator = Mock(); client.get_paginator.return_value = paginator
        paginator.paginate.side_effect = ClientError(
            {"Error": {"Code": "ExpiredToken", "Message": "Expired"}}, "ListObjectsV2"
        )
        s3 = S3Manager(None, None, "bucket", unsigned=True)
        assert s3.list_files("prefix/") is None


class _UploadRetryFTP:
    _global_calls = 0
    def __init__(self, timeout=30):
        self.timeout = timeout
        self.sock = object()
        self.cwd_dir = "/"

    def connect(self, host, port):
        return None

    def login(self, user, passwd):
        return None

    def set_pasv(self, flag):
        return None

    def quit(self):
        return None

    def storbinary(self, cmd, fileobj):
        type(self)._global_calls += 1
        if type(self)._global_calls == 1:
            from ftplib import error_temp

            raise error_temp("temp")
        fileobj.read()


def test_ftp_upload_retries_then_success(tmp_path):
    f = tmp_path / "local.bin"
    f.write_bytes(b"data")
    with patch("datavizhub.acquisition.ftp_manager.FTP", _UploadRetryFTP):
        ftp = FTPManager("host")
        ftp.connect()
        ftp.upload_file(str(f), "/remote.bin")


class _FTPBasic:
    def __init__(self, timeout=30):
        self.timeout = timeout
        self.sock = object()
        self.cwd_dir = "/dir"
        self.files = ["a.txt", "b.bin"]
        self.sizes = {"b.bin": 10}

    def connect(self, *a, **k):
        return None

    def login(self, *a, **k):
        return None

    def set_pasv(self, *a, **k):
        return None

    def quit(self):
        return None

    def cwd(self, d):
        self.cwd_dir = d

    def nlst(self, d=None):
        return list(self.files)

    def delete(self, name):
        if name not in self.files:
            raise Exception("nope")
        self.files.remove(name)

    def size(self, name):
        return self.sizes.get(name)


def test_ftp_exists_delete_stat_paths():
    with patch("datavizhub.acquisition.ftp_manager.FTP", _FTPBasic):
        ftp = FTPManager("host")
        ftp.connect()
        assert ftp.exists("/dir/b.bin") is True
        assert ftp.exists("/dir/missing.bin") is False
        assert ftp.delete("/dir/b.bin") is True
        assert ftp.delete("/dir/missing.bin") is False
        assert ftp.stat("/dir/b.bin") == {"size": 10}
        assert ftp.stat("/dir/missing.bin") == {"size": None}

