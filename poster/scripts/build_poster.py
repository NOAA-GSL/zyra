# SPDX-License-Identifier: Apache-2.0
"""Build the conference poster HTML from section fragments.

Reads source files from poster/sections/ and assembles a single
self-contained HTML file at poster/html/zyra-poster.html.

Run from the repository root:
    python poster/scripts/build_poster.py

The output file works with file:// protocol — no server required.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SECTIONS_DIR = REPO_ROOT / "poster" / "sections"
OUTPUT_FILE = REPO_ROOT / "poster" / "html" / "zyra-poster.html"


def _read(path: Path) -> str:
    """Read a file preserving original line endings."""
    return path.read_text(encoding="utf-8", errors="strict")


def build() -> None:
    # ── 1. Read structural fragments ──
    head = _read(SECTIONS_DIR / "_head.html")
    styles = _read(SECTIONS_DIR / "_styles.css")
    body_open = _read(SECTIONS_DIR / "_body-open.html")
    footer = _read(SECTIONS_DIR / "_footer.html")

    # ── 2. Discover and sort section files ──
    section_files = sorted(SECTIONS_DIR.glob("sec-*.html"))
    if not section_files:
        print("ERROR: No sec-*.html files found in", SECTIONS_DIR, file=sys.stderr)
        sys.exit(1)

    sections_html = [_read(sf) for sf in section_files]

    # ── 3. Assemble ──
    # Each fragment ends with a newline from the split, so joining
    # with an extra blank line preserves the original spacing.
    parts = [head, styles, body_open]
    parts.extend(sections_html)
    parts.append(footer)

    output = "\n".join(parts)

    # ── 4. Write (preserve LF line endings) ──
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_bytes(output.encode("utf-8"))

    # ── 5. Summary ──
    size_kb = OUTPUT_FILE.stat().st_size / 1024
    line_count = output.count("\n")
    print(f"Built {OUTPUT_FILE.relative_to(REPO_ROOT)}")
    print(
        f"  Sections: {len(section_files)} ({', '.join(f.stem for f in section_files)})"
    )
    print(f"  Size:     {size_kb:.1f} KB")
    print(f"  Lines:    {line_count}")


if __name__ == "__main__":
    build()
