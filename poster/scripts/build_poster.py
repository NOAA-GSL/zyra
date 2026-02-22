# SPDX-License-Identifier: Apache-2.0
"""Build the conference poster HTML from section fragments.

Produces two files:
  poster/html/zyra-poster.html       — Web view (scrollable, interactive)
  poster/html/zyra-poster-print.html — Print layout (14400×10800px, 300 DPI)

The print version uses a fully self-contained _print.css (no _styles.css
dependency). Gallery section is excluded from print.

Run from the repository root:
    python poster/scripts/build_poster.py

Output files work with file:// protocol — no server required.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SECTIONS_DIR = REPO_ROOT / "poster" / "sections"
OUTPUT_DIR = REPO_ROOT / "poster" / "html"
WEB_OUTPUT = OUTPUT_DIR / "zyra-poster.html"
PRINT_OUTPUT = OUTPUT_DIR / "zyra-poster-print.html"

# Sections to exclude from print layout
PRINT_EXCLUDE = {"sec-09-gallery"}


def _read(path: Path) -> str:
    """Read a file preserving original line endings."""
    try:
        return path.read_text(encoding="utf-8", errors="strict")
    except FileNotFoundError:
        print(f"ERROR: Missing file: {path}", file=sys.stderr)
        sys.exit(1)
    except OSError as exc:
        print(f"ERROR: Cannot read {path}: {exc}", file=sys.stderr)
        sys.exit(1)


def _write(path: Path, content: str, label: str, section_names: list[str]) -> None:
    """Write output and print summary."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    size_kb = path.stat().st_size / 1024
    line_count = content.count("\n")
    print(f"Built {path.relative_to(REPO_ROOT)} ({label})")
    print(f"  Sections: {len(section_names)} ({', '.join(section_names)})")
    print(f"  Size:     {size_kb:.1f} KB")
    print(f"  Lines:    {line_count}")


def build() -> None:
    # ── Discover section files ──
    section_files = sorted(SECTIONS_DIR.glob("sec-*.html"))
    if not section_files:
        print("ERROR: No sec-*.html files found in", SECTIONS_DIR, file=sys.stderr)
        sys.exit(1)

    # ── Build WEB version ──
    head = _read(SECTIONS_DIR / "_head.html")
    styles = _read(SECTIONS_DIR / "_styles.css")
    body_open = _read(SECTIONS_DIR / "_body-open.html")
    footer = _read(SECTIONS_DIR / "_footer.html")

    sections_html = [_read(sf) for sf in section_files]
    web_parts = [head, styles, body_open, *sections_html, footer]
    _write(
        WEB_OUTPUT,
        "\n".join(web_parts),
        "web",
        [f.stem for f in section_files],
    )

    # ── Build PRINT version ──
    head_print = _read(SECTIONS_DIR / "_head-print.html")
    print_css = _read(SECTIONS_DIR / "_print.css")  # self-contained print styles
    body_open_print = _read(SECTIONS_DIR / "_body-open-print.html")
    footer_print = _read(SECTIONS_DIR / "_footer-print.html")

    print_sections = [
        (sf, _read(sf)) for sf in section_files if sf.stem not in PRINT_EXCLUDE
    ]
    print_parts = [
        head_print,
        print_css,
        body_open_print,
        *[html for _, html in print_sections],
        footer_print,
    ]
    _write(
        PRINT_OUTPUT,
        "\n".join(print_parts),
        "print 300 DPI",
        [sf.stem for sf, _ in print_sections],
    )


if __name__ == "__main__":
    build()
