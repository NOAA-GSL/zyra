# SPDX-License-Identifier: Apache-2.0
import time as _time

from zyra.connectors.backends import api as api_backend


def test_request_with_retries_respects_retry_after(monkeypatch):
    calls = {"i": 0}

    seq = [
        (429, {"Retry-After": "1"}, b""),
        (200, {}, b"ok"),
    ]

    def fake_request_once(method, url, **kwargs):  # noqa: ARG001
        i = calls["i"]
        calls["i"] = min(i + 1, len(seq) - 1)
        return seq[i]

    sleeps: list[float] = []

    def fake_sleep(d):
        sleeps.append(float(d))

    monkeypatch.setattr(api_backend, "request_once", fake_request_once)
    monkeypatch.setattr(_time, "sleep", fake_sleep)
    status, headers, content = api_backend.request_with_retries(
        "GET", "https://api.example", max_retries=3, retry_backoff=0.5
    )
    assert status == 200
    # Should have slept once, taking Retry-After into account (>= 1.0)
    assert len(sleeps) == 1 and sleeps[0] >= 1.0


def test_request_with_retries_exponential_backoff(monkeypatch):
    calls = {"i": 0}
    seq = [
        (500, {}, b""),
        (502, {}, b""),
        (200, {}, b"ok"),
    ]

    def fake_request_once(method, url, **kwargs):  # noqa: ARG001
        i = calls["i"]
        calls["i"] = min(i + 1, len(seq) - 1)
        return seq[i]

    sleeps: list[float] = []

    def fake_sleep(d):
        sleeps.append(float(d))

    monkeypatch.setattr(api_backend, "request_once", fake_request_once)
    monkeypatch.setattr(_time, "sleep", fake_sleep)
    status, headers, content = api_backend.request_with_retries(
        "GET", "https://api.example", max_retries=5, retry_backoff=0.5
    )
    assert status == 200
    # Expect backoff sequence 0.5, 1.0 for first two retries
    assert len(sleeps) >= 2
    assert abs(sleeps[0] - 0.5) < 1e-6
    assert abs(sleeps[1] - 1.0) < 1e-6
