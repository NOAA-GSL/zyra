from unittest.mock import patch

from datavizhub.cli import main as cli_main


def test_decimate_vimeo_prints_uri(capsys, monkeypatch):
    with patch("datavizhub.connectors.backends.vimeo.upload_path") as up:
        up.return_value = "/videos/12345"
        # use input path (no actual file read since backend is mocked)
        try:
            cli_main(["decimate", "vimeo", "-i", "samples/demo.npy", "--name", "Test"])
        except SystemExit as e:
            # CLI may return 0 via SystemExit
            assert int(getattr(e, "code", 0) or 0) == 0
        out = capsys.readouterr().out
        assert "/videos/12345" in out
