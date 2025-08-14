from __future__ import annotations

from typing import Optional


def fetch_bytes(url: str, *, timeout: int = 60) -> bytes:
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("HTTP backend requires the 'requests' extra") from exc

    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.content


def post_bytes(url: str, data: bytes, *, timeout: int = 60, content_type: Optional[str] = None) -> int:
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("HTTP backend requires the 'requests' extra") from exc

    headers = {"Content-Type": content_type} if content_type else None
    r = requests.post(url, data=data, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.status_code

