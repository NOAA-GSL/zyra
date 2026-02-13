# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import logging
import os


def _mask(val: str | None) -> str:
    if not val:
        return "<none>"
    s = str(val)
    if len(s) <= 6:
        return "*" * len(s)
    return f"{'*' * (len(s) - 6)}{s[-6:]}"


def _get_client(
    *,
    token: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
):
    try:
        import vimeo  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("Vimeo backend requires the 'PyVimeo' extra") from exc
    token = token or os.getenv("VIMEO_ACCESS_TOKEN") or os.getenv("VIMEO_TOKEN")
    key = client_id or os.getenv("VIMEO_CLIENT_ID") or os.getenv("VIMEO_KEY")
    secret = (
        client_secret or os.getenv("VIMEO_CLIENT_SECRET") or os.getenv("VIMEO_SECRET")
    )
    if not token and not (key and secret):
        raise RuntimeError(
            "Vimeo credentials missing: set VIMEO_ACCESS_TOKEN or VIMEO_CLIENT_ID/VIMEO_CLIENT_SECRET"
        )
    auth_mode = "access_token" if token else "client_id_secret"
    logging.getLogger(__name__).debug(
        "Vimeo credentials resolved via %s (values not logged)", auth_mode
    )
    return vimeo.VimeoClient(token=token, key=key, secret=secret)


def _summarize_exception(exc: Exception, *, operation: str) -> str:
    """Build a detailed, human-readable error message from a Vimeo/HTTP exception.

    Attempts to capture HTTP status, JSON error payloads, and common fields
    exposed by PyVimeo exceptions without importing optional exception types.
    """
    parts: list[str] = [f"operation={operation}"]
    # Common attributes seen on HTTP-like exceptions
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        parts.append(f"status={status}")
    # PyVimeo often sets `.data` to a JSON mapping
    data = getattr(exc, "data", None)
    if isinstance(data, dict):
        # Include common error fields when present
        for k in ("error", "developer_message", "link", "error_code", "message"):
            if k in data and data[k]:
                parts.append(f"{k}={data[k]}")
    # Requests-like exceptions may have a response object
    resp = getattr(exc, "response", None)
    if resp is not None:
        code = getattr(resp, "status_code", None)
        if isinstance(code, int):
            parts.append(f"http_status={code}")
        text = getattr(resp, "text", None)
        if isinstance(text, str) and text:
            # Avoid dumping huge bodies
            snippet = text.strip().replace("\n", " ")
            if len(snippet) > 300:
                snippet = snippet[:300] + "..."
            parts.append(f"response={snippet}")
    # Fallback: first arg sometimes carries useful text or dict
    if exc.args:
        arg0 = exc.args[0]
        if isinstance(arg0, dict):
            msg = arg0.get("error") or arg0.get("message") or str(arg0)
            parts.append(str(msg))
        elif isinstance(arg0, str) and arg0:
            parts.append(arg0)
    # Always include the exception type for context
    parts.append(f"exception={exc.__class__.__name__}")
    # And the stringified exception as a final catch-all
    s = str(exc).strip()
    if s:
        parts.append(f"detail={s}")
    return "; ".join(parts)


def fetch_bytes(video_id: str) -> bytes:  # pragma: no cover - placeholder
    raise NotImplementedError("Ingest from Vimeo is not implemented yet")


def get_download_url(
    video_id: str,
    *,
    token: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> str | None:
    """Return a progressive download URL for the given Vimeo video.

    Requires PyVimeo credentials (access token or client id/secret). When multiple
    download renditions are available, the highest resolution progressive file is
    returned.
    """

    client = _get_client(token=token, client_id=client_id, client_secret=client_secret)
    video_id = str(video_id).strip("/")
    if not video_id.startswith("videos/"):
        video_uri = f"/videos/{video_id}"
    else:
        video_uri = f"/{video_id}"
    try:
        response = client.get(video_uri)
    except Exception as exc:  # pragma: no cover - network/SDK dependent
        raise RuntimeError(_summarize_exception(exc, operation="get")) from exc

    data = None
    if hasattr(response, "json"):
        try:
            data = response.json()
        except Exception:  # pragma: no cover - defensive
            data = None
    if not data:
        data = getattr(response, "body", None)
    if not isinstance(data, dict):
        return None

    downloads = data.get("download") or []
    best_link = None
    best_pixels = -1
    for entry in downloads:
        if not isinstance(entry, dict):
            continue
        link = entry.get("link")
        if not link:
            continue
        if entry.get("quality") == "source":
            return str(link)
        width = entry.get("width") or 0
        height = entry.get("height") or 0
        pixels = width * height
        if pixels > best_pixels:
            best_pixels = pixels
            best_link = str(link)
    if best_link:
        return best_link

    files = data.get("files") or []
    progressive = [
        entry
        for entry in files
        if entry.get("quality") == "sd" or entry.get("quality") == "hd"
    ]
    if progressive:
        return str(progressive[0].get("link_secure") or progressive[0].get("link"))
    return None


def upload_path(
    video_path: str,
    *,
    name: str | None = None,
    description: str | None = None,
    token: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> str:
    """Upload a local video file to Vimeo using PyVimeo.

    Returns the Vimeo video URI on success.
    """
    client = _get_client(token=token, client_id=client_id, client_secret=client_secret)
    try:
        uri = client.upload(
            video_path,
            data={
                k: v
                for k, v in {"name": name, "description": description}.items()
                if v is not None
            },
        )
        # PyVimeo typically returns a string URI; handle legacy dict form defensively
        if isinstance(uri, dict) and "uri" in uri:
            return str(uri["uri"])
        return str(uri)
    except Exception as exc:  # pragma: no cover - network/SDK dependent
        raise RuntimeError(_summarize_exception(exc, operation="upload")) from exc


def update_video(
    video_path: str,
    video_uri: str,
    *,
    token: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> str:
    """Replace an existing Vimeo video file and return the URI."""
    client = _get_client(token=token, client_id=client_id, client_secret=client_secret)
    try:
        resp = client.replace(video_uri, video_path)
        if isinstance(resp, str):
            return resp
        # Some client versions may return a response-like object
        status = getattr(resp, "status_code", None)
        text = getattr(resp, "text", None)
        if isinstance(status, int) or isinstance(text, str):
            snippet = (text or "").strip().replace("\n", " ")
            if len(snippet) > 300:
                snippet = snippet[:300] + "..."
            raise RuntimeError(
                f"operation=replace; status={status}; response={snippet or 'n/a'}"
            )
        raise RuntimeError("operation=replace; Unexpected response from Vimeo API")
    except Exception as exc:  # pragma: no cover - network/SDK dependent
        raise RuntimeError(_summarize_exception(exc, operation="replace")) from exc


def update_description(
    video_uri: str,
    text: str,
    *,
    token: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> str:
    """Update the description metadata for a Vimeo video."""
    client = _get_client(token=token, client_id=client_id, client_secret=client_secret)
    try:
        resp = client.patch(video_uri, data={"description": text})
        status = getattr(resp, "status_code", 200)
        if status == 200:
            return video_uri
        # Include body snippet for debugging
        body = getattr(resp, "text", "")
        snippet = (body or "").strip().replace("\n", " ")
        if len(snippet) > 300:
            snippet = snippet[:300] + "..."
        raise RuntimeError(
            f"operation=patch; status={status}; response={snippet or 'n/a'}"
        )
    except Exception as exc:  # pragma: no cover - network/SDK dependent
        raise RuntimeError(_summarize_exception(exc, operation="patch")) from exc
