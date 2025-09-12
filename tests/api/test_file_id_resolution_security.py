# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path

from zyra.api.routers import files as files_router
from zyra.api.workers.executor import resolve_upload_placeholders


def test_file_id_resolution_prevents_symlink_escape(
    tmp_path: Path, monkeypatch
) -> None:
    # Point uploads directory to a temp dir for isolation
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(files_router, "UPLOAD_DIR", upload_dir, raising=False)

    # Create a benign file outside the upload directory
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    # Create a symlink inside uploads that points outside (attempted escape)
    bad_fid = "badfid123"
    bad_link = upload_dir / f"{bad_fid}_link.txt"
    bad_link.symlink_to(outside)

    # Create a valid uploaded file inside uploads
    good_fid = "goodfid456"
    good_file = upload_dir / f"{good_fid}_data.bin"
    good_file.write_bytes(b"ok")

    # Build args containing both placeholders
    args = {
        "input": f"file_id:{good_fid}",
        "extra": f"file_id:{bad_fid}",
        "files": [f"file_id:{good_fid}", "noop"],
    }

    resolved, paths, unresolved = resolve_upload_placeholders(args)

    # Good fid resolves to a path inside upload_dir
    assert Path(resolved["input"]).resolve() == good_file.resolve()
    # Bad fid should remain unresolved and not be replaced
    assert resolved["extra"] == f"file_id:{bad_fid}"
    assert bad_fid in set(unresolved)
    # Resolved paths should include only the good file path
    assert good_file.resolve() in {Path(p).resolve() for p in paths}
    # Ensure no resolved path points outside the upload directory
    for p in paths:
        rp = Path(p).resolve()
        assert str(rp).startswith(str(upload_dir.resolve()))
