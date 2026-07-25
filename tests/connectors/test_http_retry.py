# SPDX-License-Identifier: Apache-2.0
"""Backoff for HTTP fetches (issue: batches tripped S3 "503 Slow Down").

A 16-frame GRIB2 batch is ~176 requests against one S3 prefix — one
``.idx`` GET plus up to ten concurrent ranged GETs per frame — and the
backend treated the resulting throttle as fatal, losing the whole stage.
503 and 429 are documented as retryable; 404 is not.

No network here: ``requests`` is stubbed, and ``sleep``/``rand`` are
injected so the delay sequence can be asserted without spending it.
"""

from __future__ import annotations

import pytest

from zyra.connectors.backends._retry import (
    backoff_delay,
    is_retryable,
    retry_after_seconds,
    with_retries,
)


class _Resp:
    def __init__(self, status, headers=None):
        self.status_code = status
        self.headers = headers or {}


class _HTTPError(Exception):
    """Stands in for requests.HTTPError (carries .response)."""

    def __init__(self, status, headers=None):
        super().__init__(f"{status} error")
        self.response = _Resp(status, headers)


class ConnectionError(Exception):  # noqa: A001 - mirrors requests' class name
    """Name-matched transport failure; the policy keys off the class name."""


# ---- policy ---------------------------------------------------------------


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_retryable_statuses(status):
    assert is_retryable(_HTTPError(status)) is True


@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 422])
def test_client_errors_are_not_retryable(status):
    # Repeating these produces the identical failure; retrying only
    # delays the error and adds load.
    assert is_retryable(_HTTPError(status)) is False


def test_transport_errors_are_retryable_by_class_name():
    assert is_retryable(ConnectionError("boom")) is True
    assert is_retryable(ValueError("not a transport problem")) is False


def test_backoff_grows_and_is_jittered():
    # Full jitter: the ceiling doubles per attempt, and the actual delay
    # is a fraction of it, so concurrent retries do not run in lockstep.
    ceilings = [
        backoff_delay(i, base_delay=1.0, max_delay=100.0, rand=lambda: 1.0)
        for i in range(5)
    ]
    assert ceilings == [1.0, 2.0, 4.0, 8.0, 16.0]
    assert backoff_delay(0, base_delay=1.0, rand=lambda: 0.0) == 0.0
    # max_delay caps the ceiling.
    assert backoff_delay(20, base_delay=1.0, max_delay=30.0, rand=lambda: 1.0) == 30.0


def test_retry_after_header_is_honoured():
    assert retry_after_seconds(_HTTPError(503, {"Retry-After": "7"})) == 7.0
    assert retry_after_seconds(_HTTPError(503, {})) is None
    # HTTP-date form is deliberately ignored rather than parsed, so a
    # far-future date cannot stall a pipeline.
    assert (
        retry_after_seconds(
            _HTTPError(503, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})
        )
        is None
    )


# ---- driver ---------------------------------------------------------------


def test_succeeds_after_transient_failures():
    calls = {"n": 0}
    slept = []

    def call():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _HTTPError(503)
        return b"payload"

    out = with_retries(call, sleep=slept.append, rand=lambda: 1.0, base_delay=1.0)
    assert out == b"payload"
    assert calls["n"] == 3
    assert slept == [1.0, 2.0], "delay must grow between attempts"


def test_non_retryable_fails_on_first_attempt():
    calls = {"n": 0}
    slept = []

    def call():
        calls["n"] += 1
        raise _HTTPError(404)

    with pytest.raises(_HTTPError):
        with_retries(call, sleep=slept.append)
    assert calls["n"] == 1, "a 404 must not be retried"
    assert slept == []


def test_gives_up_after_max_attempts_and_reraises():
    calls = {"n": 0}

    def call():
        calls["n"] += 1
        raise _HTTPError(503)

    with pytest.raises(_HTTPError):
        with_retries(call, max_attempts=4, sleep=lambda _: None)
    assert calls["n"] == 4


def test_retry_after_overrides_backoff():
    calls = {"n": 0}
    slept = []

    def call():
        calls["n"] += 1
        if calls["n"] == 1:
            raise _HTTPError(503, {"Retry-After": "12"})
        return b"ok"

    with_retries(call, sleep=slept.append, base_delay=1.0, rand=lambda: 1.0)
    assert slept == [12.0]


def test_retry_after_is_capped_by_max_delay():
    def call():
        raise _HTTPError(503, {"Retry-After": "9999"})

    slept = []
    with pytest.raises(_HTTPError):
        with_retries(call, max_attempts=2, max_delay=30.0, sleep=slept.append)
    assert slept == [30.0], "a hostile Retry-After must not stall the run"


# ---- backend integration --------------------------------------------------


def _patch_requests_get(monkeypatch, fake_get):
    """Patch the real ``requests.get``.

    ``fetch_bytes`` does a function-local ``import requests``, which
    shadows the module-level attribute the backend keeps for patching,
    so setting that attribute has no effect on this path.
    """
    requests = pytest.importorskip("requests")
    monkeypatch.setattr(requests, "get", fake_get)
    from zyra.connectors.backends import http as http_backend

    monkeypatch.setattr(
        http_backend,
        "_retry_opts",
        lambda: {"max_attempts": 5, "base_delay": 0, "max_delay": 0},
    )
    return http_backend


class _OK:
    content = b"DATA"

    def raise_for_status(self):
        return None


def test_fetch_bytes_retries_a_throttle(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _HTTPError(503)
        return _OK()

    http_backend = _patch_requests_get(monkeypatch, fake_get)
    assert http_backend.fetch_bytes("https://example.org/x.grib2") == b"DATA"
    assert calls["n"] == 3, "a 503 must be retried until it succeeds"


def test_fetch_bytes_does_not_retry_a_404(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, **kw):
        calls["n"] += 1
        raise _HTTPError(404)

    http_backend = _patch_requests_get(monkeypatch, fake_get)
    with pytest.raises(_HTTPError):
        http_backend.fetch_bytes("https://example.org/missing.grib2")
    assert calls["n"] == 1, "a 404 must not be retried"


def test_ranged_gets_retry_a_throttle(monkeypatch):
    # The path that actually failed in production: concurrent ranged GETs
    # for one file, throttled mid-batch.
    calls = {"n": 0}

    def fake_get(url, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _HTTPError(503)
        return _OK()

    http_backend = _patch_requests_get(monkeypatch, fake_get)
    out = http_backend.download_byteranges(
        "https://example.org/x.grib2", ["bytes=0-9"], max_workers=1
    )
    assert out == b"DATA"
    assert calls["n"] == 2


def test_idx_lines_retry_uses_backoff_not_a_tight_loop(monkeypatch):
    # get_idx_lines already retried, but with no delay between attempts,
    # which makes a rate limiter worse rather than better.
    slept = []
    calls = {"n": 0}

    def fake_get(url, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _HTTPError(503)
        return type(
            "R",
            (),
            {
                "content": b"1:0:d=2026:VAR:lev:anl:\n",
                "raise_for_status": lambda self: None,
            },
        )()

    requests = pytest.importorskip("requests")
    monkeypatch.setattr(requests, "get", fake_get)
    from zyra.connectors.backends import http as http_backend

    monkeypatch.setattr(
        http_backend,
        "_retry_opts",
        lambda: {
            "max_attempts": 5,
            "base_delay": 1.0,
            "max_delay": 30.0,
            "sleep": slept.append,
            "rand": lambda: 1.0,
        },
    )
    http_backend.get_idx_lines("https://example.org/x.grib2")
    assert calls["n"] == 3
    assert slept == [1.0, 2.0], "attempts must be spaced, not immediate"


def test_max_workers_is_env_configurable(monkeypatch):
    from zyra.connectors.backends import http as http_backend

    assert http_backend.default_max_workers() == 10
    monkeypatch.setenv("ZYRA_HTTP_MAX_WORKERS", "3")
    assert http_backend.default_max_workers() == 3
    # A nonsense value must not collapse concurrency to zero.
    monkeypatch.setenv("ZYRA_HTTP_MAX_WORKERS", "0")
    assert http_backend.default_max_workers() == 1
