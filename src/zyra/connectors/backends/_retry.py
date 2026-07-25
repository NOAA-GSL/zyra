# SPDX-License-Identifier: Apache-2.0
"""Retry policy shared by the HTTP connector's fetch paths.

Object stores answer a burst of requests against one prefix with a
retryable throttle rather than a hard failure — S3 sends ``503 Slow
Down`` — and the documented remedy is to back off and try again. Zyra
treated any non-2xx as fatal, so a batch large enough to be throttled
lost the whole stage: a 16-frame GRIB2 batch is ~176 requests against a
single prefix (one ``.idx`` GET plus up to ten concurrent ranged GETs
per frame) and reliably tripped it.

Kept dependency-light on purpose. ``requests`` is an optional extra and
the backend keeps a module-level patchable stub for tests, so nothing
here imports it; retryable transport errors are recognised by exception
name instead.
"""

from __future__ import annotations

import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")

#: Statuses worth retrying. 429 and 503 are explicit "slow down" signals;
#: 500/502/504 are transient upstream faults; 408 is a server-side
#: timeout. Every other 4xx describes the request itself and will fail
#: identically no matter how many times it is repeated.
RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})

#: Transport-level failures, matched by class name so this module does
#: not have to import ``requests``.
RETRYABLE_EXC_NAMES = frozenset(
    {
        "ConnectionError",
        "ConnectTimeout",
        "ReadTimeout",
        "Timeout",
        "ChunkedEncodingError",
        "IncompleteRead",
    }
)

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_BASE_DELAY = 0.5
DEFAULT_MAX_DELAY = 30.0


def _status_of(exc: BaseException) -> int | None:
    """Best-effort HTTP status from a raised exception, else ``None``."""
    resp = getattr(exc, "response", None)
    status = getattr(resp, "status_code", None)
    return status if isinstance(status, int) else None


def is_retryable(exc: BaseException) -> bool:
    """True when retrying ``exc`` could plausibly succeed."""
    status = _status_of(exc)
    if status is not None:
        return status in RETRYABLE_STATUS
    # No response attached: a transport-level failure, retryable only for
    # the classes that represent a connection problem rather than a bug.
    return type(exc).__name__ in RETRYABLE_EXC_NAMES


def retry_after_seconds(exc: BaseException) -> float | None:
    """Parse a ``Retry-After`` header into seconds, if the server sent one.

    Only the delta-seconds form is honoured; the HTTP-date form is
    ignored so a malformed or far-future date cannot stall a pipeline.
    """
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None)
    if not headers:
        return None
    try:
        raw = headers.get("Retry-After")
    except Exception:
        return None
    if raw is None:
        return None
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def backoff_delay(
    attempt: int,
    *,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    rand: Callable[[], float] = random.random,
) -> float:
    """Exponential delay with full jitter for a zero-based attempt index.

    Jitter matters more than the growth curve here: without it, ten
    concurrent ranged GETs that are throttled together would all sleep
    the same interval and retry in lockstep, reproducing the burst that
    caused the throttle.
    """
    ceiling = min(max_delay, base_delay * (2**attempt))
    return rand() * ceiling


def with_retries(
    call: Callable[[], T],
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    sleep: Callable[[float], None] = time.sleep,
    rand: Callable[[], float] = random.random,
) -> T:
    """Call ``call``, retrying retryable failures with backoff.

    Non-retryable failures (a 404, a bad request) propagate on the first
    attempt rather than being repeated identically. ``sleep`` and
    ``rand`` are injectable so tests can assert the delay sequence
    without spending it.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    attempt = 0
    while True:
        try:
            return call()
        except Exception as exc:
            attempt += 1
            if attempt >= max_attempts or not is_retryable(exc):
                raise
            delay = retry_after_seconds(exc)
            if delay is None:
                delay = backoff_delay(
                    attempt - 1,
                    base_delay=base_delay,
                    max_delay=max_delay,
                    rand=rand,
                )
            else:
                delay = min(delay, max_delay)
            sleep(delay)
