#!/usr/bin/env python3
"""Wait for a given package version to appear on PyPI.

Usage:
  python scripts/wait_for_pypi.py <package> <version> [retries] [delay_seconds]

Defaults:
  retries: 60
  delay_seconds: 10

Exits with code 0 when the version is available, 1 on timeout or error.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from typing import Any


def fetch_json(url: str, timeout: float = 10.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as r:  # nosec: B310 (trusted URL template)
        return json.load(r)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(
            "Usage: wait_for_pypi.py <package> <version> [retries] [delay_seconds]",
            file=sys.stderr,
        )
        return 1

    package = argv[1]
    version = argv[2]
    retries = int(argv[3]) if len(argv) > 3 else 60
    delay = int(argv[4]) if len(argv) > 4 else 10

    url = f"https://pypi.org/pypi/{package}/json"
    print(f"Waiting for {package} {version} to appear on PyPI...", flush=True)

    for _ in range(retries):
        try:
            data = fetch_json(url)
            releases = data.get("releases", {})
            if version in releases and releases[version]:
                print(f"Found {package} {version} on PyPI.")
                return 0
        except Exception:
            # Transient errors are expected; retry.
            pass
        print("Not yet available; retrying...", flush=True)
        time.sleep(delay)

    print("Timed out waiting for PyPI release.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
