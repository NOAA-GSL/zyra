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
import socket
import sys
import time
import urllib.request
from json import JSONDecodeError
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse


def fetch_json(url: str, timeout: float = 10.0) -> dict[str, Any]:
    """Fetch JSON from PyPI, enforcing HTTPS and pypi.org host.

    This validation mitigates SSRF risks when the URL is constructed from
    untrusted input in future refactors.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "pypi.org":
        raise ValueError(f"Refusing to fetch non-PyPI URL: {url}")
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def pep503_normalize(name: str) -> str:
    """Normalize a package name per PEP 503 (simple API canonical form)."""
    import re

    return re.sub(r"[-_.]+", "-", name).lower()


def is_version_available(package: str, version: str, timeout: float = 10.0) -> bool:
    """Check PyPI Simple API for availability of a specific version.

    Uses the PEP 503 simple index HTML, which pip consults when installing.
    Returns True if any file link appears to contain the version string.
    """
    normalized = pep503_normalize(package)
    simple_url = f"https://pypi.org/simple/{normalized}/"
    parsed = urlparse(simple_url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "pypi.org":
        raise ValueError(f"Refusing to fetch non-PyPI URL: {simple_url}")
    with urllib.request.urlopen(simple_url, timeout=timeout) as r:
        html = r.read().decode("utf-8", errors="replace")
    # Look for filename prefix like '<pkg>-<version>'
    needle = f"{normalized}-{version}"
    return needle in html


def main(argv: list[str]) -> int:
    """CLI entry for waiting until a PyPI release exists.

    Parameters:
    - argv: Command-line arguments where:
      - argv[1]: package name (e.g., "zyra")
      - argv[2]: version string (e.g., "1.2.3")
      - argv[3]: optional retries (int, default 60)
      - argv[4]: optional delay seconds between retries (int, default 10)

    Returns:
    - 0 when the package version is found on PyPI.
    - 1 on usage error or timeout after all retries.
    """
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
            # Check the Simple API used by pip to avoid JSON/simple propagation skew
            if is_version_available(package, version):
                print(f"Found {package} {version} on PyPI (simple index).")
                return 0
        except (URLError, HTTPError, JSONDecodeError, socket.timeout) as exc:
            # Expected transient issues; log for CI visibility and retry.
            print(
                f"Transient error while checking PyPI: {type(exc).__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )
        print("Not yet available; retrying...", flush=True)
        time.sleep(delay)

    print("Timed out waiting for PyPI release.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
