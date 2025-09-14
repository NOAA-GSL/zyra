# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from zyra.api.models.cli_request import CLIRunRequest
from zyra.api.routers.cli import run_cli_endpoint
from zyra.utils.env import env_path


def _infer_filename(headers: dict[str, str], default: str = "download.bin") -> str:
    cd = headers.get("Content-Disposition") or headers.get("content-disposition") or ""
    if "filename=" in cd:
        return cd.split("filename=", 1)[1].strip().strip('"') or default
    ct = headers.get("Content-Type") or headers.get("content-type") or ""
    if ct:
        main = ct.split(";", 1)[0].strip().lower()
        mapping = {
            "application/json": ".json",
            "application/x-ndjson": ".jsonl",
            "text/plain": ".txt",
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "audio/ogg": ".ogg",
        }
        if main in mapping:
            return f"download{mapping[main]}"
    return default


def api_fetch(
    *,
    url: str,
    method: str | None = None,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    data: Any | None = None,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """Fetch an API endpoint and save response under DATA_DIR.

    Returns { path, content_type, size_bytes, status_code }.
    """
    base = env_path("DATA_DIR", "_work")
    out_dir = base / (output_dir or "downloads")
    out_dir.mkdir(parents=True, exist_ok=True)

    m = (method or "GET").upper()
    body = json.dumps(data).encode("utf-8") if isinstance(data, (dict, list)) else data
    r = requests.request(
        m,
        url,
        headers=headers or {},
        params=params or {},
        data=body,
        timeout=60,
        stream=True,
    )
    ct = r.headers.get("Content-Type") or "application/octet-stream"
    name = _infer_filename(r.headers)
    out = out_dir / name
    size = 0
    with out.open("wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            if not chunk:
                continue
            f.write(chunk)
            size += len(chunk)
    return {
        "path": str(out.relative_to(base)),
        "content_type": ct,
        "size_bytes": size,
        "status_code": r.status_code,
    }


def api_process_json(
    *,
    file_or_url: str,
    records_path: str | None = None,
    fields: str | None = None,
    flatten: bool | None = None,
    explode: list[str] | None = None,
    derived: str | None = None,
    format: str | None = None,
    output_dir: str | None = None,
    output_name: str | None = None,
) -> dict[str, Any]:
    """Transform JSON/NDJSON to CSV/JSONL via CLI path and save under DATA_DIR.

    Returns { path, size_bytes, format }.
    """
    base = env_path("DATA_DIR", "_work")
    out_dir = base / (output_dir or "outputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt = (format or "csv").lower()
    name = output_name or ("output.jsonl" if fmt == "jsonl" else "output.csv")
    out_path = out_dir / name

    args: dict[str, Any] = {
        "file_or_url": file_or_url,
        "output": str(out_path),
        "format": fmt,
    }
    if records_path:
        args["records_path"] = records_path
    if fields:
        args["fields"] = fields
    if flatten is not None:
        args["flatten"] = bool(flatten)
    if explode:
        args["explode"] = list(explode)
    if derived:
        args["derived"] = derived

    cr = run_cli_endpoint(
        CLIRunRequest(stage="process", command="api-json", args=args, mode="sync"), None
    )
    if cr.exit_code != 0:
        raise RuntimeError(cr.stderr or "Processing failed")
    size = 0
    try:
        size = Path(out_path).stat().st_size
    except Exception:
        size = 0
    return {"path": str(out_path.relative_to(base)), "size_bytes": size, "format": fmt}
