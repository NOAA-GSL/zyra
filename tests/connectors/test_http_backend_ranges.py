from unittest.mock import Mock, patch

from datavizhub.connectors.backends import http as http_backend


def test_http_get_size_and_idx_and_ranges():
    url = "https://example.com/file.grib2"

    # Mock HEAD for size
    import sys
    import types

    resp = Mock()
    resp.headers = {"Content-Length": "1000"}
    resp.raise_for_status = lambda: None
    fake_requests = types.SimpleNamespace(head=lambda *a, **k: resp)
    with patch.dict(sys.modules, {"requests": fake_requests}):
        assert http_backend.get_size(url) == 1000

    # Mock GET for idx and range
    import sys
    import types

    # first call returns idx, second/third return ranged bytes
    idx_resp = Mock()
    idx_resp.raise_for_status = lambda: None
    idx_resp.content = b"1:0:date:VAR:a:b:\n2:10:date:VAR:a:b:\n"

    r1 = Mock()
    r1.raise_for_status = lambda: None
    r1.content = b"ABCDEFGHIJ"  # 10 bytes
    r2 = Mock()
    r2.raise_for_status = lambda: None
    r2.content = b"KLMNOPQRST"  # next 10 bytes

    # fake requests.get yields idx then range responses
    fake_requests = types.SimpleNamespace(get=Mock(side_effect=[idx_resp, r1, r2]))
    with patch.dict(sys.modules, {"requests": fake_requests}):
        lines = http_backend.get_idx_lines(url)
        assert lines
        assert len(lines) == 2
        # Two ranges: 0-10 and 10-EOF
        from datavizhub.utils.grib import idx_to_byteranges

        br = idx_to_byteranges(lines, r"VAR")
        with patch.dict(sys.modules, {"requests": fake_requests}):
            data = http_backend.download_byteranges(url, br.keys(), max_workers=2)
        assert data == b"ABCDEFGHIJKLMNOPQRST"


def test_http_list_files_scrape():
    page = "https://example.com/list/"
    html = '<a href="file1.bin">file1.bin</a> <a href="sub/">sub/</a>'
    import sys
    import types

    resp = Mock()
    resp.raise_for_status = lambda: None
    resp.text = html
    fake_requests = types.SimpleNamespace(get=lambda *a, **k: resp)
    with patch.dict(sys.modules, {"requests": fake_requests}):
        files = http_backend.list_files(page)
        assert any("file1.bin" in f for f in files)
