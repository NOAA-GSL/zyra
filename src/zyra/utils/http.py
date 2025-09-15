# SPDX-License-Identifier: Apache-2.0
"""HTTP utilities shared across routers and backends."""

from __future__ import annotations

from typing import Mapping


def strip_hop_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    """Return a copy of headers with hop-by-hop and host headers removed.

    Removes headers commonly abused for header-based SSRF or proxy spoofing:
    - Host
    - X-Forwarded-For
    - X-Forwarded-Host
    - X-Real-IP
    - Forwarded
    """
    out = dict(headers or {})
    for k in list(out.keys()):
        if k.lower() in {
            "host",
            "x-forwarded-for",
            "x-forwarded-host",
            "x-real-ip",
            "forwarded",
        }:
            out.pop(k, None)
    return out
