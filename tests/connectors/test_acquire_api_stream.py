# SPDX-License-Identifier: Apache-2.0
import types
from pathlib import Path

from zyra.connectors.ingest import _cmd_api  # type: ignore


class _Resp:
    def __init__(self, status=200, headers=None, chunks=None):
        self.status_code = status
        self.headers = headers or {}
        self._chunks = chunks or []

    def iter_content(self, chunk_size=1024 * 1024):  # noqa: ARG002
        yield from self._chunks


def _ns(**kw):
    # Build a simple argparse.Namespace-like via SimpleNamespace
    ns = types.SimpleNamespace(
        verbose=False,
        quiet=False,
        trace=False,
        header=[],
        params=None,
        content_type=None,
        data=None,
        method="GET",
        paginate="none",
        timeout=30,
        max_retries=0,
        retry_backoff=0.1,
        allow_non_2xx=False,
        preset=None,
        stream=True,
        head_first=False,
        accept=None,
        expect_content_type="audio/ogg",
        output="-",
        resume=False,
        newline_json=False,
        url="https://api.example/binary",
        detect_filename=False,
    )
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


def test_stream_download_writes_chunks(tmp_path, monkeypatch):
    out = tmp_path / "out.ogg"

    def fake_request(
        method,
        url,
        headers=None,
        params=None,
        data=None,
        timeout=None,
        stream=False,
        allow_redirects=True,
    ):  # noqa: ARG001
        return _Resp(
            200,
            headers={"Content-Type": "audio/ogg"},
            chunks=[b"abc", b"def"],
        )

    import requests

    monkeypatch.setattr(requests, "request", fake_request)
    ns = _ns(output=str(out))
    rc = _cmd_api(ns)
    assert rc == 0
    assert out.read_bytes() == b"abcdef"


def test_detect_filename_from_content_disposition(tmp_path, monkeypatch):
    out_dir = tmp_path / "dl"
    out_dir.mkdir()

    def fake_request(
        method,
        url,
        headers=None,
        params=None,
        data=None,
        timeout=None,
        stream=False,
        allow_redirects=True,
    ):  # noqa: ARG001
        return _Resp(
            200,
            headers={
                "Content-Type": "audio/ogg",
                "Content-Disposition": 'attachment; filename="foo.ogg"',
            },
            chunks=[b"xyz"],
        )

    import requests

    monkeypatch.setattr(requests, "request", fake_request)
    # Do not enforce a specific expected content type for image download
    ns = _ns(output=str(out_dir), detect_filename=True, expect_content_type=None)
    rc = _cmd_api(ns)
    assert rc == 0
    # File foo.ogg should exist in directory
    out = Path(out_dir / "foo.ogg")
    assert out.exists() and out.read_bytes() == b"xyz"


def test_detect_filename_from_content_type_mapping(tmp_path, monkeypatch):
    out_dir = tmp_path / "dlimg"
    out_dir.mkdir()

    def fake_request(
        method,
        url,
        headers=None,
        params=None,
        data=None,
        timeout=None,
        stream=False,
        allow_redirects=True,
    ):  # noqa: ARG001
        return _Resp(
            200,
            headers={
                "Content-Type": "image/png",
            },
            chunks=[b"\x89PNG..."],
        )

    import requests

    monkeypatch.setattr(requests, "request", fake_request)
    ns = _ns(output=str(out_dir), detect_filename=True, expect_content_type=None)
    rc = _cmd_api(ns)
    assert rc == 0
    # Should have written download.png
    out = Path(out_dir / "download.png")
    assert out.exists()


def test_directory_without_detect_flag_errors(tmp_path, monkeypatch):
    out_dir = tmp_path / "dl2"
    out_dir.mkdir()

    def fake_request(
        method,
        url,
        headers=None,
        params=None,
        data=None,
        timeout=None,
        stream=False,
        allow_redirects=True,
    ):  # noqa: ARG001
        return _Resp(200, headers={"Content-Type": "audio/ogg"}, chunks=[b"x"])

    import requests

    monkeypatch.setattr(requests, "request", fake_request)
    ns = _ns(output=str(out_dir), detect_filename=False)
    try:
        _cmd_api(ns)
    except SystemExit as e:  # noqa: PT012
        assert "detect-filename" in str(e)
    else:  # pragma: no cover
        assert (
            False
        ), "Expected SystemExit when writing to directory without --detect-filename"


def test_resume_appends_and_sets_range(tmp_path, monkeypatch):
    # Prepare existing file with content to be resumed
    out = tmp_path / "resume.ogg"
    out.write_bytes(b"old")

    seen = {"range": None}

    def fake_request(
        method,
        url,
        headers=None,
        params=None,
        data=None,
        timeout=None,
        stream=False,
        allow_redirects=True,
    ):  # noqa: ARG001
        # Ensure Range header is set based on existing file size (3 bytes)
        seen["range"] = (headers or {}).get("Range")
        return _Resp(200, headers={"Content-Type": "audio/ogg"}, chunks=[b"new"])

    import requests

    monkeypatch.setattr(requests, "request", fake_request)
    ns = _ns(output=str(out), resume=True)
    rc = _cmd_api(ns)
    assert rc == 0
    assert seen["range"] == "bytes=3-"
    assert out.read_bytes() == b"oldnew"


def test_head_first_content_type_mismatch_raises(tmp_path, monkeypatch):
    # HEAD preflight returns unexpected content type
    def fake_head(url, headers=None, params=None, allow_redirects=True, timeout=None):  # noqa: ARG001
        return _Resp(200, headers={"Content-Type": "audio/mpeg"})

    def should_not_call_request(*a, **kw):  # noqa: ARG001
        raise AssertionError(
            "request() should not be called when head_first mismatches"
        )

    import requests

    monkeypatch.setattr(requests, "head", fake_head)
    monkeypatch.setattr(requests, "request", should_not_call_request)
    ns = _ns(output="-", head_first=True, expect_content_type="audio/ogg")
    try:
        _cmd_api(ns)
    except SystemExit as e:  # noqa: PT012
        assert "Unexpected Content-Type" in str(e)
    else:  # pragma: no cover
        assert False, "Expected SystemExit on content type mismatch"


def test_stream_content_type_mismatch_raises(tmp_path, monkeypatch):
    # Streaming GET returns unexpected content type
    def fake_request(
        method,
        url,
        headers=None,
        params=None,
        data=None,
        timeout=None,
        stream=False,
        allow_redirects=True,
    ):  # noqa: ARG001
        return _Resp(200, headers={"Content-Type": "audio/mpeg"}, chunks=[b"x"])

    import requests

    monkeypatch.setattr(requests, "request", fake_request)
    ns = _ns(output=str(tmp_path / "out.bin"), expect_content_type="audio/ogg")
    try:
        _cmd_api(ns)
    except SystemExit as e:  # noqa: PT012
        assert "Unexpected Content-Type" in str(e)
    else:  # pragma: no cover
        assert False, "Expected SystemExit on content type mismatch"


def test_ndjson_cursor_writes_lines(tmp_path, monkeypatch):
    # Verify NDJSON writing for cursor pagination
    out = tmp_path / "out.jsonl"

    from zyra.connectors.backends import api as api_backend

    def fake_paginate_cursor(method, url, **kwargs):  # noqa: ARG001
        yield 200, {}, b'{"page":1}'
        yield 200, {}, b'{"page":2}'

    monkeypatch.setattr(api_backend, "paginate_cursor", fake_paginate_cursor)
    ns = _ns(
        stream=False,
        paginate="cursor",
        newline_json=True,
        output=str(out),
    )
    rc = _cmd_api(ns)
    assert rc == 0
    lines = [ln for ln in out.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2


def test_ndjson_page_writes_lines(tmp_path, monkeypatch):
    # Verify NDJSON writing for page pagination
    out = tmp_path / "out2.jsonl"

    from zyra.connectors.backends import api as api_backend

    def fake_paginate_page(method, url, **kwargs):  # noqa: ARG001
        yield 200, {}, b'{"i":1}'
        yield 200, {}, b'{"i":2}'

    monkeypatch.setattr(api_backend, "paginate_page", fake_paginate_page)
    ns = _ns(
        stream=False,
        paginate="page",
        newline_json=True,
        output=str(out),
    )
    rc = _cmd_api(ns)
    assert rc == 0
    lines = [ln for ln in out.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2


def test_ndjson_link_writes_lines(tmp_path, monkeypatch):
    # Verify NDJSON writing for link pagination
    out = tmp_path / "out3.jsonl"

    from zyra.connectors.backends import api as api_backend

    def fake_paginate_link(method, url, **kwargs):  # noqa: ARG001
        yield 200, {}, b'{"x":1}'
        yield 200, {}, b'{"x":2}'

    monkeypatch.setattr(api_backend, "paginate_link", fake_paginate_link)
    ns = _ns(
        stream=False,
        paginate="link",
        newline_json=True,
        output=str(out),
    )
    rc = _cmd_api(ns)
    assert rc == 0
    lines = [ln for ln in out.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
