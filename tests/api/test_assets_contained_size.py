# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path

from zyra.api.utils.assets import infer_assets


def test_contained_path_size_reported(tmp_path) -> None:
    # Create a contained file under the default RESULTS_DIR (/tmp/zyra_results)
    base = Path("/tmp/zyra_results")
    base.mkdir(parents=True, exist_ok=True)
    f = base / "unit_test_asset.bin"
    data = b"abc"
    f.write_bytes(data)

    assets = infer_assets("decimate", "local", {"input": "-", "path": str(f)})
    # Find matching asset by URI
    match = next((a for a in assets if getattr(a, "uri", None) == str(f)), None)
    assert match is not None, "Contained file should be included as asset"
    assert getattr(match, "size", None) == len(
        data
    ), "Contained file size must be reported"
