from __future__ import annotations


def fetch_bytes(video_id: str) -> bytes:  # pragma: no cover - placeholder
    raise NotImplementedError("Ingest from Vimeo is not implemented yet")


def upload_path(
    video_path: str, *, name: str | None = None, description: str | None = None
) -> str:
    """Upload a local video file to Vimeo using PyVimeo.

    Returns the Vimeo video URI on success.
    """
    try:
        import vimeo  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("Vimeo backend requires the 'PyVimeo' extra") from exc

    # Expect credentials via env vars per utils.credential_manager guidance
    client = vimeo.VimeoClient(
        token=None,
        key=None,
        secret=None,
    )
    uri = client.upload(
        video_path,
        data={
            k: v
            for k, v in {"name": name, "description": description}.items()
            if v is not None
        },
    )
    return uri


def update_video(video_path: str, video_uri: str) -> str:
    """Replace an existing Vimeo video file and return the URI."""
    try:
        import vimeo  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("Vimeo backend requires the 'PyVimeo' extra") from exc

    client = vimeo.VimeoClient(token=None, key=None, secret=None)
    resp = client.replace(video_uri, video_path)
    if isinstance(resp, str):
        return resp
    raise RuntimeError("Unexpected response from Vimeo replace API")


def update_description(video_uri: str, text: str) -> str:
    """Update the description metadata for a Vimeo video."""
    try:
        import vimeo  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("Vimeo backend requires the 'PyVimeo' extra") from exc

    client = vimeo.VimeoClient(token=None, key=None, secret=None)
    resp = client.patch(video_uri, data={"description": text})
    status = getattr(resp, "status_code", 200)
    if status == 200:
        return video_uri
    raise RuntimeError(f"Failed to update Vimeo description; status={status}")
