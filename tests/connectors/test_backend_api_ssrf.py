# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest

from zyra.connectors.backends import api as backend


def test_paginate_link_stays_same_host_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Simulate first response with Link header pointing to a different host
    calls = {"urls": []}

    def _rwr(
        method: str,
        url: str,
        *,
        headers=None,
        params=None,
        data=None,
        timeout=60,
        max_retries=3,
        retry_backoff=0.5,
    ):  # noqa: ARG001
        calls["urls"].append(url)
        if len(calls["urls"]) == 1:
            # First page: provide Link to a different host
            return 200, {"Link": '<https://evil.example.com/next>; rel="next"'}, b"{}"
        # Should not be called again by default
        return 200, {}, b"{}"

    monkeypatch.setattr(backend, "request_with_retries", _rwr)

    it = backend.paginate_link("GET", "https://api.example.com/items")
    items = list(it)
    # Only the first URL should be fetched; next host is rejected by default
    assert calls["urls"] == ["https://api.example.com/items"]
    assert len(items) == 1
