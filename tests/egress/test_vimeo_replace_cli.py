# SPDX-License-Identifier: Apache-2.0
from unittest.mock import patch

from zyra.cli import main as cli_main


def test_decimate_vimeo_replace_and_description(capsys):
    with patch("zyra.connectors.backends.vimeo.update_video") as rep, patch(
        "zyra.connectors.backends.vimeo.update_description"
    ) as upd:
        rep.return_value = "/videos/999"
        upd.return_value = "/videos/999"
        try:
            cli_main(
                [
                    "decimate",
                    "vimeo",
                    "-i",
                    "samples/demo.npy",
                    "--replace-uri",
                    "/videos/123",
                    "--description",
                    "Updated",
                ]
            )
        except SystemExit as e:
            assert int(getattr(e, "code", 0) or 0) == 0
        out = capsys.readouterr().out
        assert "/videos/999" in out
        assert upd.called
