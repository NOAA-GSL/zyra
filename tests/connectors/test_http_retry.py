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


def test_patching_time_sleep_actually_stops_the_sleeping():
    """The obvious way to keep a retry test fast has to work.

    ``sleep`` used to default to ``time.sleep`` in the signature, which
    binds the original function once at definition time — so patching
    ``_retry.time.sleep`` left the default untouched and the test spent
    the delay for real. Resolving the default inside the body fixes it;
    this pins that, because the failure mode is invisible (a passing
    test that is merely slower and nondeterministic).
    """
    import time as _time
    from unittest.mock import patch

    from zyra.connectors.backends import _retry

    seen: list[float] = []
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _HTTPError(503)
        return "ok"

    started = _time.monotonic()
    with patch("zyra.connectors.backends._retry.time.sleep", seen.append):
        assert _retry.with_retries(flaky, base_delay=5.0) == "ok"
    elapsed = _time.monotonic() - started

    assert len(seen) == 2, "the patched sleep must be the one that runs"
    # base_delay=5s over two retries would be plainly visible if the
    # real time.sleep were still bound.
    assert elapsed < 1.0, f"slept for real: {elapsed:.2f}s"


def test_connection_refused_is_not_retried():
    """A refused connection is the transport twin of a 404.

    The host answered and said nothing is listening. Repeating that
    produces the identical failure, only slower — which is how a
    mistyped URL turned into the full backoff ladder before reporting
    the obvious, and how one CLI test went from 0.5s to 4.3s.

    Built from a real refused socket rather than a hand-made exception
    so the cause chain is the one `requests` actually raises.
    """
    import socket

    from zyra.connectors.backends._retry import is_retryable

    # Bind and close, so the port is definitely free and refusing.
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    requests = pytest.importorskip("requests")
    try:
        requests.get(f"http://127.0.0.1:{port}/x", timeout=5, proxies={"http": None})
    except Exception as exc:
        assert is_retryable(exc) is False
        # And it really is the wrapped shape, not a bare OSError.
        assert type(exc).__name__ == "ConnectionError"
    else:  # pragma: no cover - would mean something is listening
        pytest.fail("expected the connection to be refused")


def test_other_connection_errors_are_still_retried():
    # The narrowing must not swallow the transient cases: a reset
    # mid-stream, or a one-off DNS failure in a container, are both
    # worth another attempt.
    reset = ConnectionError("reset")
    reset.__cause__ = ConnectionResetError(104, "Connection reset by peer")
    assert is_retryable(reset) is True
    assert is_retryable(ConnectionError("dns hiccup")) is True


def test_refused_survives_a_self_referential_cause_chain():
    # Defensive: a cycle in __cause__/__context__ must not hang the walk.
    a = ConnectionError("a")
    b = ConnectionError("b")
    a.__cause__ = b
    b.__cause__ = a
    assert is_retryable(a) is True


@pytest.mark.parametrize(("env", "expected"), [("0", 1), ("-3", 1), ("", 5), ("2", 2)])
def test_max_attempts_is_floored_at_one(monkeypatch, env, expected):
    """`ZYRA_HTTP_MAX_ATTEMPTS=0` must mean one attempt, not a crash.

    with_retries rejects max_attempts < 1, so an unfloored env value
    turned "do not retry" — a reasonable reading of 0 — into a
    ValueError raised out of every fetch, before any request was made.
    default_max_workers already floors the same way.
    """
    from zyra.connectors.backends import http as http_backend

    if env:
        monkeypatch.setenv("ZYRA_HTTP_MAX_ATTEMPTS", env)
    else:
        monkeypatch.delenv("ZYRA_HTTP_MAX_ATTEMPTS", raising=False)
    assert http_backend._retry_opts()["max_attempts"] == expected


def test_zero_attempts_still_makes_exactly_one_request(monkeypatch):
    """The floor has to hold at the fetch path, not just in the opts.

    Patches only ``requests.get`` — deliberately not via
    ``_patch_requests_get``, which substitutes its own ``_retry_opts``
    and would hide the very thing under test.
    """
    requests = pytest.importorskip("requests")
    from zyra.connectors.backends import http as http_backend

    monkeypatch.setenv("ZYRA_HTTP_MAX_ATTEMPTS", "0")
    calls = {"n": 0}

    def _get(url, **kw):
        calls["n"] += 1
        raise _HTTPError(503)

    monkeypatch.setattr(requests, "get", _get)
    with pytest.raises(Exception) as excinfo:
        http_backend.fetch_bytes("https://example.org/x")
    # A 503 should surface, not "max_attempts must be >= 1".
    assert "max_attempts" not in str(excinfo.value), "floor was not applied"
    assert calls["n"] == 1, "0 must mean one attempt, not zero and not five"
