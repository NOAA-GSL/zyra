from __future__ import annotations

import os
import shutil
import asyncio
import time
from pathlib import Path
from fastapi import FastAPI, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from datavizhub.api import __version__ as dvh_version
from datavizhub.api.routers import cli as cli_router
from datavizhub.api.routers import files as files_router
from datavizhub.api.routers import ws as ws_router
from datavizhub.api.routers import jobs as jobs_router
from datavizhub.api.security import require_api_key


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    - Adds optional CORS middleware based on env vars
    - Registers routers (CLI, Files, WS, Jobs)
    - Defines `/`, `/health`, and `/ready` routes
    - On startup, launches a background cleanup loop for result TTL pruning
    """
    app = FastAPI(title="DataVizHub API", version=dvh_version)

    # CORS (env-configurable)
    allow_all = os.environ.get("DATAVIZHUB_CORS_ALLOW_ALL", "0").lower() in {"1", "true", "yes"}
    origins_env = os.environ.get("DATAVIZHUB_CORS_ORIGINS", "")
    origins = [o.strip() for o in origins_env.split(",") if o.strip()]
    if allow_all or origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"] if allow_all else origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(cli_router.router, dependencies=[Depends(require_api_key)])
    app.include_router(files_router.router, dependencies=[Depends(require_api_key)])
    app.include_router(ws_router.router)  # auth handled inside via query param
    app.include_router(jobs_router.router, dependencies=[Depends(require_api_key)])

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "version": dvh_version}

    @app.get("/ready", tags=["system"])
    def ready() -> dict:
        # Upload directory checks
        upload_dir_path = files_router.UPLOAD_DIR
        exists = upload_dir_path.exists()
        writable = os.access(upload_dir_path, os.W_OK) if exists else False
        probe_ok = False
        if exists and writable:
            try:
                probe = upload_dir_path / ".ready_probe"
                with probe.open("w") as f:
                    f.write("ok")
                try:
                    probe.unlink(missing_ok=True)  # type: ignore[arg-type]
                except TypeError:
                    # Python <3.8 fallback (shouldn't happen here)
                    if probe.exists():
                        probe.unlink()
                probe_ok = True
            except Exception:
                probe_ok = False

        # Disk space check on upload volume
        min_disk_mb = int(os.environ.get("DATAVIZHUB_MIN_DISK_MB", "100") or 0)
        disk_ok = False
        disk = {"free_mb": None, "min_mb": min_disk_mb}
        try:
            usage = shutil.disk_usage(upload_dir_path)
            free_mb = int(usage.free // (1024 * 1024))
            disk["free_mb"] = free_mb
            disk_ok = free_mb >= min_disk_mb
        except Exception:
            disk_ok = False

        # Queue/worker readiness (Redis optional)
        from datavizhub.api.workers.jobs import is_redis_enabled, redis_url, queue_name

        use_redis = is_redis_enabled()
        queue = {"mode": "redis" if use_redis else "in_memory", "connected": (not use_redis)}
        if use_redis:
            try:
                import redis  # type: ignore
                from datavizhub.api.workers.jobs import _get_redis_and_queue  # type: ignore

                url = redis_url()
                client = redis.Redis.from_url(url, socket_connect_timeout=0.5)  # type: ignore[arg-type]
                client.ping()
                queue["connected"] = True
                queue["url"] = url
                queue["queue_name"] = queue_name()
                try:
                    _r, rq = _get_redis_and_queue()
                    cnt_attr = getattr(rq, "count", None)
                    if callable(cnt_attr):
                        queue["length"] = int(cnt_attr())
                    else:
                        queue["length"] = int(cnt_attr) if cnt_attr is not None else None
                except Exception:
                    queue["length"] = None
            except Exception:
                queue["connected"] = False
                queue["url"] = redis_url()

        # Optional binaries (FFmpeg/ffprobe)
        ffmpeg_ok = shutil.which("ffmpeg") is not None
        ffprobe_ok = shutil.which("ffprobe") is not None
        require_ffmpeg = os.environ.get("DATAVIZHUB_REQUIRE_FFMPEG", "0").lower() in {"1", "true", "yes"}
        binaries = {
            "ffmpeg": ffmpeg_ok,
            "ffprobe": ffprobe_ok,
            "required": require_ffmpeg,
        }

        overall_ok = exists and writable and probe_ok and disk_ok and (queue.get("connected", False))
        if require_ffmpeg and not (ffmpeg_ok and ffprobe_ok):
            overall_ok = False
        return {
            "status": "ok" if overall_ok else "error",
            "version": dvh_version,
            "checks": {
                "upload_dir": {
                    "path": str(upload_dir_path),
                    "exists": exists,
                    "writable": writable,
                    "probe": probe_ok,
                },
                "disk": disk,
                "queue": queue,
                "binaries": binaries,
            },
        }

    @app.get("/")
    def root(request: Request):
        """Root landing page.

        Returns a small HTML index when the client prefers HTML; otherwise
        returns a JSON metadata object with links and endpoint list. Force
        formats via `?format=html|json`.
        """
        fmt = request.query_params.get("format")
        accept = request.headers.get("accept", "")
        prefer_html = (fmt == "html") or ("text/html" in accept and fmt != "json")
        meta = {
            "name": "DataVizHub API",
            "version": dvh_version,
            "links": {
                "docs": "/docs",
                "redoc": "/redoc",
                "examples": "/examples",
                "openapi": "/openapi.json",
            },
            "endpoints": [
                "/health",
                "/ready",
                "/cli/commands",
                "/cli/examples",
                "/cli/run",
                "/jobs/{job_id}",
                "/jobs/{job_id}/manifest",
                "/jobs/{job_id}/download",
                "/upload",
                "/examples",
            ],
        }
        if not prefer_html:
            return meta
        # Build a simple HTML index with clickable links
        html = f"""
        <!doctype html>
        <html lang=\"en\">
          <head>
            <meta charset=\"utf-8\" />
            <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
            <title>DataVizHub API</title>
            <style>
              body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem; }}
              h1 {{ margin-bottom: .25rem; }}
              .muted {{ color: #666; }}
              ul {{ line-height: 1.8; }}
              code {{ background: #f6f8fa; padding: 0 .25rem; border-radius: 3px; }}
            </style>
          </head>
          <body>
            <h1>DataVizHub API</h1>
            <div class=\"muted\">Version {dvh_version}</div>
            <h2>Quick Links</h2>
            <ul>
              <li><a href=\"/docs\">Swagger UI</a></li>
              <li><a href=\"/redoc\">ReDoc</a></li>
              <li><a href=\"/openapi.json\">OpenAPI JSON</a></li>
              <li><a href=\"/examples\">Interactive Examples</a></li>
            </ul>
            <h2>Endpoints</h2>
            <ul>
              <li><a href=\"/health\">GET /health</a> — health probe</li>
              <li><a href=\"/ready\">GET /ready</a> — readiness checks</li>
              <li><a href=\"/cli/commands\">GET /cli/commands</a> — discovery: stages, commands, args</li>
              <li><a href=\"/cli/examples\">GET /cli/examples</a> — curated examples for /cli/run</li>
              <li>POST /cli/run — see <a href=\"/docs#/%2Fcli%2Frun\">/docs</a></li>
              <li><a href=\"/jobs/{{job_id}}\">GET /jobs/{{job_id}}</a> — job status</li>
              <li><a href=\"/jobs/{{job_id}}/manifest\">GET /jobs/{{job_id}}/manifest</a> — artifacts</li>
              <li><a href=\"/jobs/{{job_id}}/download\">GET /jobs/{{job_id}}/download</a> — download</li>
              <li>POST /upload — multipart upload (try in <a href=\"/docs#/%2Fupload\">/docs</a>)</li>
            </ul>
            <h2>Auth</h2>
            <p class=\"muted\">If <code>DATAVIZHUB_API_KEY</code> is set, include <code>{{os.environ.get('DATAVIZHUB_API_KEY_HEADER','X-API-Key')}}</code> header with your key. WebSockets use <code>?api_key=</code>.</p>
          </body>
        </html>
        """
        return HTMLResponse(content=html)

    return app


def _seconds_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)) or default)
    except Exception:
        return default


async def _results_cleanup_loop() -> None:
    ttl = _seconds_env("DATAVIZHUB_RESULTS_TTL_SECONDS", 86400)
    interval = _seconds_env("DATAVIZHUB_RESULTS_CLEAN_INTERVAL_SECONDS", 3600)
    root = Path(os.environ.get("DATAVIZHUB_RESULTS_DIR", "/tmp/datavizhub_results"))
    while True:
        try:
            if root.exists():
                now = time.time()
                for job_dir in root.iterdir():
                    if not job_dir.is_dir():
                        continue
                    try:
                        empty = True
                        for f in job_dir.iterdir():
                            if not f.is_file():
                                continue
                            empty = False
                            try:
                                if now - f.stat().st_mtime > ttl:
                                    f.unlink()
                            except Exception:
                                pass
                        # Remove dir if empty after cleanup
                        try:
                            if empty or not any(job_dir.iterdir()):
                                job_dir.rmdir()
                        except Exception:
                            pass
                    except Exception:
                        continue
        except Exception:
            pass
        await asyncio.sleep(interval)


# Uvicorn entrypoint: `uvicorn datavizhub.api.server:app --reload`
app = create_app()


@app.on_event("startup")
async def _startup_tasks() -> None:
    # Launch background cleanup loop for results
    asyncio.create_task(_results_cleanup_loop())
