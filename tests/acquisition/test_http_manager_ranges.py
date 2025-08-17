from unittest.mock import patch, Mock

from datavizhub.acquisition.http_manager import HTTPHandler


def test_http_get_size_and_idx_and_ranges():
    mgr = HTTPHandler()
    url = "https://example.com/file.grib2"

    # Mock HEAD for size
    with patch("datavizhub.acquisition.http_manager.requests.head") as m_head:
        resp = Mock()
        resp.headers = {"Content-Length": "1000"}
        resp.raise_for_status = lambda: None
        m_head.return_value = resp
        assert mgr.get_size(url) == 1000

    # Mock GET for idx and range
    with patch("datavizhub.acquisition.http_manager.requests.get") as m_get:
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

        m_get.side_effect = [idx_resp, r1, r2]

        lines = mgr.get_idx_lines(url)
        assert lines and len(lines) == 2
        # Two ranges: 0-10 and 10-EOF
        br = mgr.idx_to_byteranges(lines, r"VAR")
        data = mgr.download_byteranges(url, br.keys(), max_workers=2)
        assert data == b"ABCDEFGHIJKLMNOPQRST"


def test_http_list_files_scrape():
    mgr = HTTPHandler()
    page = "https://example.com/list/"
    html = '<a href="file1.bin">file1.bin</a> <a href="sub/">sub/</a>'
    with patch("datavizhub.acquisition.http_manager.requests.get") as m_get:
        resp = Mock()
        resp.raise_for_status = lambda: None
        resp.text = html
        m_get.return_value = resp
        files = mgr.list_files(page)
        assert any("file1.bin" in f for f in files)
