# SPDX-License-Identifier: Apache-2.0
"""Convert the print-layout poster HTML to a press-ready PDF.

Output : poster/html/zyra-poster-print.pdf
Paper  : 48 × 36 inches, landscape (standard conference poster)
Quality: Text and SVGs are resolution-independent (vector). Raster images are
         embedded at their native resolution; 300 DPI assets render at 300 DPI.

Requirements (auto-installed on first run):
    pip install playwright
    playwright install chromium

Run from the repository root:
    python poster/scripts/build_pdf.py

Options (env vars):
    POSTER_HTML   Path to input HTML  (default: poster/html/zyra-poster-print.html)
    POSTER_PDF    Path to output PDF  (default: poster/html/zyra-poster-print.pdf)
    POSTER_OPEN   Set to 1 to open the PDF when done
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

HTML_PATH = Path(os.environ.get(
    "POSTER_HTML",
    REPO_ROOT / "poster" / "html" / "zyra-poster-print.html",
))
PDF_PATH = Path(os.environ.get(
    "POSTER_PDF",
    REPO_ROOT / "poster" / "html" / "zyra-poster-print.pdf",
))

# ── Poster geometry ─────────────────────────────────────────────────────────
# The print CSS defines the poster at exactly 14400 × 10800 CSS pixels,
# which is 48 × 36 inches at 300 DPI.
#
# Playwright's PDF renderer works at 96 CSS px per inch.  To map the 14400 px
# layout onto a 48-inch PDF page we need:
#
#   scale = (48 in × 96 px/in) / 14400 px = 4608 / 14400 ≈ 0.32
#
# Text and SVG paths are vector in the PDF, so they print crisply at any size.
# PNG/JPEG assets are embedded at their original pixel resolution.

PAPER_W_IN = 48   # inches
PAPER_H_IN = 36   # inches
CSS_PX_W   = 14400
CSS_PX_H   = 10800
CSS_DPI    = 96   # Playwright's assumed CSS px density
SCALE      = round((PAPER_W_IN * CSS_DPI) / CSS_PX_W, 6)  # ≈ 0.32


# ── Dependency bootstrap ────────────────────────────────────────────────────

def _ensure_playwright() -> None:
    """Install the playwright Python package and Chromium if missing."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("playwright not found — installing …", flush=True)
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-q", "playwright"],
        )

    # Verify the Chromium browser binary exists; install if not.
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            exe = pw.chromium.executable_path
            if not Path(exe).exists():
                raise FileNotFoundError(exe)
    except Exception:
        print("Chromium browser not found — running 'playwright install chromium' …",
              flush=True)
        subprocess.check_call(
            [sys.executable, "-m", "playwright", "install", "chromium"],
        )


# ── Main build ──────────────────────────────────────────────────────────────

def build_pdf() -> None:
    _ensure_playwright()

    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    if not HTML_PATH.exists():
        print(
            f"ERROR: {HTML_PATH} not found.\n"
            "Run  python poster/scripts/build_poster.py  first.",
            file=sys.stderr,
        )
        sys.exit(1)

    html_url = HTML_PATH.as_uri()

    print(f"Source  {HTML_PATH.relative_to(REPO_ROOT)}")
    print(f"Output  {PDF_PATH.relative_to(REPO_ROOT)}")
    print(f"Paper   {PAPER_W_IN}″ × {PAPER_H_IN}″  (landscape)")
    print(f"Scale   {SCALE}  ({CSS_PX_W} px → {PAPER_W_IN} in)")
    print("Rendering …", flush=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            args=[
                "--no-sandbox",           # required in WSL / container
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",  # avoids /dev/shm crashes in containers
                "--font-render-hinting=none",  # crisper font rendering in PDF
            ],
        )

        page = browser.new_page(
            viewport={"width": CSS_PX_W, "height": CSS_PX_H},
        )

        # Navigate and wait for the full page render (fonts, images, iframes).
        page.goto(html_url, wait_until="networkidle", timeout=90_000)

        # Extra dwell time for web-font FOUT and deferred image loads.
        page.wait_for_timeout(3_000)

        pdf_bytes = page.pdf(
            width=f"{PAPER_W_IN}in",
            height=f"{PAPER_H_IN}in",
            print_background=True,
            scale=SCALE,
        )

        browser.close()

    PDF_PATH.write_bytes(pdf_bytes)

    size_mb = PDF_PATH.stat().st_size / (1024 * 1024)
    print(f"Done    {size_mb:.1f} MB  →  {PDF_PATH.name}")

    if os.environ.get("POSTER_OPEN") == "1":
        _open_file(PDF_PATH)


def _open_file(path: Path) -> None:
    """Best-effort: open the PDF in the system viewer."""
    import shutil
    for cmd in ("xdg-open", "open", "start"):
        if shutil.which(cmd):
            subprocess.Popen([cmd, str(path)])
            return


if __name__ == "__main__":
    build_pdf()
