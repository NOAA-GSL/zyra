#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Iterable

SPDX_PY = "# SPDX-License-Identifier: Apache-2.0\n"
SPDX_SH = "# SPDX-License-Identifier: Apache-2.0\n"
SPDX_YAML = "# SPDX-License-Identifier: Apache-2.0\n"


def iter_files(base: Path, exts: set[str]) -> Iterable[Path]:
    for root, _dirs, files in os.walk(base):
        # Skip common vendor/build dirs
        if any(
            part in {".venv", ".git", "dist", "build", "__pycache__", ".ruff_cache"}
            for part in Path(root).parts
        ):
            continue
        for f in files:
            p = Path(root) / f
            if p.suffix in exts:
                yield p


def has_spdx(text: str) -> bool:
    return (
        re.search(r"^\s*#\s*SPDX-License-Identifier:\s*Apache-2.0\s*$", text, re.M)
        is not None
    )


ENCODING_RE = re.compile(r"^#\s*.*coding[:=]\s*utf-8", re.I)


def ensure_py_spdx(path: Path) -> bool:
    """Ensure a Python file has an SPDX header. Returns True if modified."""
    raw = path.read_text(encoding="utf-8", errors="ignore")
    if has_spdx(raw):
        return False

    lines = raw.splitlines(keepends=True)
    insert_idx = 0
    if lines and lines[0].startswith("#!"):
        insert_idx = 1
        if len(lines) > 1 and ENCODING_RE.match(lines[1]):
            insert_idx = 2
    elif lines and ENCODING_RE.match(lines[0]):
        insert_idx = 1

    lines.insert(insert_idx, SPDX_PY)
    path.write_text("".join(lines), encoding="utf-8")
    return True


def ensure_sh_spdx(path: Path) -> bool:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    if has_spdx(raw):
        return False
    lines = raw.splitlines(keepends=True)
    insert_idx = 0
    if lines and lines[0].startswith("#!"):
        insert_idx = 1
    lines.insert(insert_idx, SPDX_SH)
    path.write_text("".join(lines), encoding="utf-8")
    return True


def ensure_yaml_spdx(path: Path) -> bool:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    if has_spdx(raw):
        return False
    lines = raw.splitlines(keepends=True)
    insert_idx = 0
    if lines and lines[0].lstrip().startswith("---"):
        insert_idx = 1
    lines.insert(insert_idx, SPDX_YAML)
    path.write_text("".join(lines), encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Add SPDX headers to source files")
    ap.add_argument("--write", action="store_true", help="Write changes to files")
    ap.add_argument("--base", default=".", help="Base directory (default: .)")
    args = ap.parse_args()

    base = Path(args.base).resolve()
    modified = 0

    # Python sources
    py_dirs = [base / "src", base / "tests", base / "scripts"]
    for d in py_dirs:
        if d.exists():
            for p in iter_files(d, {".py"}):
                if args.write:
                    if ensure_py_spdx(p):
                        modified += 1
                else:
                    raw = p.read_text(encoding="utf-8", errors="ignore")
                    if not has_spdx(raw):
                        print(f"MISSING SPDX: {p}")

    # Shell scripts
    for d in [base / "scripts"]:
        if d.exists():
            for p in iter_files(d, {".sh"}):
                if args.write:
                    if ensure_sh_spdx(p):
                        modified += 1
                else:
                    raw = p.read_text(encoding="utf-8", errors="ignore")
                    if not has_spdx(raw):
                        print(f"MISSING SPDX: {p}")

    # YAML files (repo-wide, excluding vendor dirs via iter_files filter)
    for p in iter_files(base, {".yml", ".yaml"}):
        # Skip virtual env / git / dist handled in iter_files; no extra skip
        if args.write:
            if ensure_yaml_spdx(p):
                modified += 1
        else:
            raw = p.read_text(encoding="utf-8", errors="ignore")
            if not has_spdx(raw):
                print(f"MISSING SPDX: {p}")

    if args.write:
        print(f"SPDX updated in {modified} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
