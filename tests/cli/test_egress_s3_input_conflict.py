import pytest


def test_egress_s3_input_and_read_stdin_conflict(tmp_path):
    from zyra.cli import main as cli_main

    dummy = tmp_path / "dummy.txt"
    dummy.write_text("hi", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        cli_main(
            [
                "decimate",
                "s3",
                "--input",
                str(dummy),
                "--read-stdin",
                "--url",
                "s3://bucket/key",
            ]
        )
    assert "mutually exclusive" in str(exc.value)
