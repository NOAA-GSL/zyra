# SPDX-License-Identifier: Apache-2.0
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.cli
def test_decimate_local_creates_parent_dirs_and_writes(tmp_path: Path):
    data = b"hello-world"
    nested = tmp_path / "a" / "b" / "c" / "out.bin"
    cmd = [
        sys.executable,
        "-m",
        "zyra.cli",
        "decimate",
        "local",
        "-i",
        "-",
        str(nested),
    ]
    res = subprocess.run(cmd, input=data, capture_output=True)
    assert res.returncode == 0, res.stderr.decode(errors="ignore")
    assert nested.exists()
    assert nested.read_bytes() == data
