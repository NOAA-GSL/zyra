#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
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
import re
import socket
import sys
import time
import urllib.request
from json import JSONDecodeError
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlparse


def fetch_json(url: str, timeout: float = 10.0) -> dict[str, Any]:
    """Fetch JSON from PyPI, enforcing HTTPS and pypi.org host.

    This validation mitigates SSRF risks when the URL is constructed from
    untrusted input in future refactors.
    """
    with _urlopen(url, "pypi.org", timeout=timeout) as r:
        return json.load(r)


def pep503_normalize(name: str) -> str:
    """Normalize a package name per PEP 503 (simple API canonical form)."""
    import re

    return re.sub(r"[-_.]+", "-", name).lower()


#: Host serving the actual distribution files. The simple index lives on
#: pypi.org and links out to here, and the two propagate independently.
FILES_HOST = "files.pythonhosted.org"


def _require_allowed_url(url: str, *hosts: str) -> None:
    """Reject anything not HTTPS on one of ``hosts``.

    Guards against SSRF if a URL ever reaches here from untrusted input.
    ``files.pythonhosted.org`` is allowed alongside ``pypi.org`` because
    the file check below has to follow the index's own links.

    Compares ``hostname`` rather than ``netloc``: netloc carries the port
    and any userinfo, so an explicit ``https://pypi.org:443/...`` — same
    host, same default port — would be refused as a stranger. ``hostname``
    normalises the port away, strips userinfo, and lowercases.
    """
    allowed = tuple(h.lower() for h in hosts)
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "") not in allowed:
        raise ValueError(
            f"Refusing to fetch {url}: not HTTPS on {' or '.join(allowed)}"
        )


class _AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-check the allowlist on each redirect hop.

    urllib follows redirects by itself, so validating only the URL we ask
    for checks the one hop that was never in doubt: a 302 pointing off the
    allowlist would be followed, and the request issued, before anything
    looked at it. Checking ``geturl()`` after ``urlopen`` returns is too
    late for the same reason — by then it has been fetched. Refusing here
    stops the hop before it goes out.
    """

    def __init__(self, hosts: tuple[str, ...]) -> None:
        super().__init__()
        self._hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        _require_allowed_url(newurl, *self._hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _urlopen(url_or_req, *hosts: str, timeout: float = 10.0):  # type: ignore[no-untyped-def]
    """``urlopen`` with the allowlist enforced on the request *and* redirects.

    The single seam every fetch in this module goes through, so the guard
    cannot be bypassed by adding a call site that forgets it.
    """
    target = url_or_req if isinstance(url_or_req, str) else url_or_req.full_url
    _require_allowed_url(target, *hosts)
    opener = urllib.request.build_opener(
        _AllowlistRedirectHandler(tuple(h.lower() for h in hosts))
    )
    return opener.open(url_or_req, timeout=timeout)


def file_urls_for_version(
    package: str, version: str, timeout: float = 10.0
) -> list[str]:
    """Return the simple index's file links for exactly ``version``.

    The match is anchored on the full filename rather than a substring:
    a bare ``<pkg>-<version>`` needle also matches ``0.1.53.1``, which
    would let a *different* release satisfy the wait.
    """
    normalized = pep503_normalize(package)
    simple_url = f"https://pypi.org/simple/{normalized}/"
    with _urlopen(simple_url, "pypi.org", timeout=timeout) as r:
        html = r.read().decode("utf-8", errors="replace")

    # Wheels escape the name with underscores (PEP 427); sdists use the
    # raw project name. Accept either, then require the version to be
    # followed by a wheel's '-' or an sdist's extension.
    stem = re.escape(normalized).replace(r"\-", "[-_]")
    pattern = re.compile(
        rf"^{stem}-{re.escape(version)}(?:-[^/]*\.whl|\.tar\.gz|\.zip)$",
        re.IGNORECASE,
    )
    urls: list[str] = []
    for href in re.findall(r'href=[\'"]([^\'"]+)[\'"]', html):
        # PEP 503 permits relative links; PyPI serves absolute ones to
        # files.pythonhosted.org. Resolve against the index either way.
        clean = urljoin(simple_url, href.split("#", 1)[0])
        filename = unquote(clean.rsplit("/", 1)[-1])
        if pattern.match(filename):
            urls.append(clean)
    return urls


def is_fetchable(url: str, timeout: float = 10.0) -> bool:
    """Whether ``url`` actually serves bytes right now.

    Asks for a single byte. The simple index can list a release before
    every CDN edge is serving the file, and pip downloads from a
    different host than the index it resolved against — so "listed" and
    "downloadable" are separate facts, and only the second one is the
    condition a build actually needs.
    """
    req = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
    with _urlopen(req, FILES_HOST, "pypi.org", timeout=timeout) as r:
        return r.status in (200, 206)


def is_version_available(package: str, version: str, timeout: float = 10.0) -> bool:
    """Whether ``version`` is both listed *and* downloadable.

    Listing alone is what this used to check, and it is not enough: a
    green check followed immediately by a 404 inside a Docker build is
    exactly the failure this guard exists to prevent.
    """
    urls = file_urls_for_version(package, version, timeout=timeout)
    if not urls:
        return False
    return all(is_fetchable(u, timeout=timeout) for u in urls)


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

    print(f"Waiting for {package} {version} to appear on PyPI...", flush=True)

    for _ in range(retries):
        try:
            # Check the Simple API used by pip to avoid JSON/simple propagation skew
            if is_version_available(package, version):
                print(f"Found {package} {version} on PyPI (listed and downloadable).")
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
