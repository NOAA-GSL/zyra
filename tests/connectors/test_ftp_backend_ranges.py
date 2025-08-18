from unittest.mock import patch

from datavizhub.connectors.backends import ftp as ftp_backend


class FakeFTP:
    def __init__(self, timeout=30):
        self.timeout = timeout
        self.cwd_path = "/"
        self.files = {
            "/dir/file.grib2": b"0123456789abcdefghij",
            "/dir/file.grib2.idx": b"1:0:a:b:c:d:e\n2:10:a:b:c:d:e\n",
        }
        self.sock = object()

    def connect(self, host, port=None):
        return None

    def login(self, user, passwd):
        return None

    def set_pasv(self, flag):
        return None

    def quit(self):
        return None

    def abort(self):
        return None

    def cwd(self, d):
        if not d.startswith("/"):
            d = "/" + d
        self.cwd_path = d

    def nlst(self, d=None):
        return ["file.grib2", "file.grib2.idx"]

    def size(self, filename):
        path = self.cwd_path.rstrip("/") + "/" + filename
        return len(self.files.get(path, b""))

    def retrbinary(self, cmd, callback, blocksize=8192, rest=None):
        _, fname = cmd.split()
        path = self.cwd_path.rstrip("/") + "/" + fname
        data = self.files[path]
        start = int(rest) if rest is not None else 0
        view = memoryview(data)[start:]
        step = min(blocksize, len(view)) or 1
        for i in range(0, len(view), step):
            callback(view[i : i + step].tobytes())


def test_ftp_get_size_and_ranges_and_idx():
    with patch("datavizhub.connectors.backends.ftp.FTP", FakeFTP):
        url = "ftp://host/dir/file.grib2"
        assert ftp_backend.get_size(url) == 20
        lines = ftp_backend.get_idx_lines(url)
        assert lines
        assert len(lines) == 2
        from datavizhub.utils.grib import idx_to_byteranges

        br = idx_to_byteranges(lines, r"b")
        data = ftp_backend.download_byteranges(url, br.keys(), max_workers=2)
        assert data == b"0123456789abcdefghij"
