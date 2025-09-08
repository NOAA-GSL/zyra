from __future__ import annotations

from pathlib import Path

from zyra.api.utils.assets import infer_assets


def test_uncontained_paths_not_probed_for_size() -> None:
    # Use a common system file that exists and is outside allowed bases
    # (/tmp/zyra_uploads and /tmp/zyra_results). This should not be probed for
    # file size or magic in infer_assets; size should remain None.
    sys_file = Path("/etc/hosts")
    assert sys_file.exists(), "/etc/hosts not found in test environment"

    assets = infer_assets("decimate", "local", {"input": "-", "path": str(sys_file)})
    # Ensure the system file is included as an asset reference
    match = next((a for a in assets if getattr(a, "uri", None) == str(sys_file)), None)
    assert match is not None, "Uncontained path should be referenced but not probed"
    # Size should be None for uncontained paths (no stat probing)
    assert getattr(match, "size", None) is None
