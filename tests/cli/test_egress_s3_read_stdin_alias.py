import io
import sys


def test_egress_s3_read_stdin_alias(monkeypatch):
    from zyra.cli import main as cli_main

    sent = b"hello world\n"
    fake_stdin = type("S", (), {"buffer": io.BytesIO(sent)})()
    monkeypatch.setattr(sys, "stdin", fake_stdin)

    captured = {}

    def _fake_upload_bytes(
        data: bytes, url_or_bucket: str, key: str | None = None
    ) -> bool:
        captured["data"] = data
        captured["url_or_bucket"] = url_or_bucket
        captured["key"] = key
        return True

    import zyra.connectors.backends.s3 as s3_backend

    monkeypatch.setattr(s3_backend, "upload_bytes", _fake_upload_bytes)

    rc = cli_main(["decimate", "s3", "--read-stdin", "--url", "s3://b/k"])
    assert rc == 0
    assert captured["data"] == sent
    assert captured["url_or_bucket"] == "s3://b/k"
    assert captured["key"] is None
