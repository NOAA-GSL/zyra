#!/usr/bin/env python3
"""Simple API smoke test for DataVizHub.

Checks /health and /ready, then uploads a tiny file to /upload.

Usage:
  poetry run python samples/api_smoke.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


def _print_section(title: str, payload: Any) -> None:
    print(f"\n== {title} ==")
    if isinstance(payload, (dict, list)):
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(str(payload))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DataVizHub API smoke test")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("DVH_BASE_URL", "http://localhost:8000"),
        help="Base URL of the running API (default: http://localhost:8000)",
    )
    args = parser.parse_args(argv)
    base = args.base_url.rstrip("/")

    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover
        print("This script requires the 'requests' package.")
        print("Install via Poetry extras or pip, then retry.")
        print(f"Import error: {exc}")
        return 2

    # Health
    r = requests.get(f"{base}/health", timeout=5)
    _print_section("GET /health", r.json())

    # Ready
    r = requests.get(f"{base}/ready", timeout=5)
    _print_section("GET /ready", r.json())

    # Upload a small file
    with tempfile.NamedTemporaryFile("w+b", suffix=".txt", delete=True) as tmp:
        content = b"hello from api_smoke\n"
        tmp.write(content)
        tmp.flush()
        tmp.seek(0)
        files = {"file": (Path(tmp.name).name or "smoke.txt", tmp, "text/plain")}
        r = requests.post(f"{base}/upload", files=files, timeout=10)
        try:
            payload: dict[str, Any] = r.json()
        except Exception:
            payload = {"status": r.status_code, "text": r.text}
        _print_section("POST /upload", payload)

    return 0


if __name__ == "__main__":
    sys.exit(main())
