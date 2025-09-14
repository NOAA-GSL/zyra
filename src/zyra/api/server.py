# SPDX-License-Identifier: Apache-2.0
"""FastAPI application factory and system endpoints.

This module wires together the API routers and adds a few system routes
(`/health`, `/ready`, and `/`) along with CORS settings and a background
results cleanup task. It is designed to be run with uvicorn or similar ASGI
servers in development or production.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from contextlib import asynccontextmanager, suppress

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from zyra.api import __version__ as dvh_version
from zyra.api.routers import api_generic as api_router
from zyra.api.routers import cli as cli_router
from zyra.api.routers import domain_acquire as acquire_router
from zyra.api.routers import domain_assets as assets_router
from zyra.api.routers import domain_decide as decide_router
from zyra.api.routers import domain_disseminate as disseminate_router
from zyra.api.routers import domain_narrate as narrate_router
from zyra.api.routers import domain_process as process_router
from zyra.api.routers import domain_simulate as simulate_router
from zyra.api.routers import domain_transform as transform_router
from zyra.api.routers import domain_verify as verify_router
from zyra.api.routers import domain_visualize as visualize_router
from zyra.api.routers import files as files_router
from zyra.api.routers import jobs as jobs_router
from zyra.api.routers import manifest as manifest_router
from zyra.api.routers import mcp as mcp_router
from zyra.api.routers import search as search_router
from zyra.api.routers import ws as ws_router
from zyra.api.security import require_api_key
from zyra.utils.env import env, env_bool, env_int, env_path, env_seconds

# Note: .env loading happens inside create_app(), gated by a skip flag.


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    - Adds optional CORS middleware based on env vars
    - Registers routers (CLI, Files, WS, Jobs)
    - Defines `/`, `/health`, and `/ready` routes
    - On startup, launches a background cleanup loop for result TTL pruning
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Launch background cleanup loop for results on startup
        task = asyncio.create_task(_results_cleanup_loop())
        try:
            yield
        finally:
            # Cancel and await the cleanup task on shutdown
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    # Best-effort: load environment variables from a local .env if present,
    # unless explicitly skipped via ZYRA_SKIP_DOTENV/DATAVIZHUB_SKIP_DOTENV.
    try:  # pragma: no cover - environment dependent
        skip = (
            os.environ.get("ZYRA_SKIP_DOTENV")
            or os.environ.get("DATAVIZHUB_SKIP_DOTENV")
            or "0"
        ).strip().lower() in {"1", "true", "yes"}
        if not skip:
            from dotenv import find_dotenv, load_dotenv

            _ENV_PATH = find_dotenv(usecwd=True)
            if _ENV_PATH:
                load_dotenv(_ENV_PATH, override=False)
    except Exception:
        # Ignore if python-dotenv is unavailable; environment vars still work
        pass

    app = FastAPI(
        title="Zyra API",
        version=dvh_version,
        lifespan=lifespan,
        root_path=env("API_ROOT_PATH", ""),
        root_path_in_servers=True,
    )
    # Snapshot feature flags that control router inclusion
    try:
        app.state.mcp_enabled = bool(env_bool("ENABLE_MCP", False))
    except Exception:
        app.state.mcp_enabled = False

    @app.exception_handler(RequestValidationError)
    async def _map_validation_errors(request: Request, exc: RequestValidationError):
        # For domain endpoints, map Pydantic 422 to our 400 validation_error envelope
        path = request.url.path
        # Normalize versioned prefixes (/v1, /v2, etc.) for matching
        import re as _re

        norm = _re.sub(r"^/v\d+", "", path)
        domain_paths = {
            "/acquire",
            "/import",
            "/transform",
            "/process",
            "/visualize",
            "/render",
            "/decimate",
            "/export",
            "/disseminate",
            "/decide",
            "/optimize",
            "/simulate",
            "/narrate",
            "/verify",
            "/assets",
        }
        if norm in domain_paths:
            from zyra.api.utils.errors import domain_error_response

            # Preserve error details for debugging
            try:
                details = {"errors": exc.errors()}
            except Exception:
                details = None
            return domain_error_response(
                status_code=400,
                err_type="validation_error",
                message="Invalid arguments",
                details=details,  # type: ignore[arg-type]
            )
        # Fallback to FastAPI's default 422 for non-domain routes
        return await request_validation_exception_handler(request, exc)

    # CORS (env-configurable)
    allow_all = (env("CORS_ALLOW_ALL", "0") or "0").lower() in {
        "1",
        "true",
        "yes",
    }
    origins_env = env("CORS_ORIGINS", "") or ""
    origins = [o.strip() for o in origins_env.split(",") if o.strip()]
    if allow_all or origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"] if allow_all else origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Include versioned routes (/v1/...) in schema and legacy aliases without schema
    def _inc(router, *, deps=True):
        kw = {"dependencies": [Depends(require_api_key)]} if deps else {}
        app.include_router(router, prefix="/v1", **kw)
        app.include_router(router, include_in_schema=False, **kw)

    _inc(cli_router.router)
    _inc(api_router.router)
    _inc(files_router.router)
    # WS auth handled inside via query param
    _inc(ws_router.router, deps=False)
    _inc(manifest_router.router)
    _inc(search_router.router)
    _inc(jobs_router.router)
    # Domain routers (v1 minimal, delegate to /cli/run)
    _inc(process_router.router)
    _inc(visualize_router.router)
    _inc(assets_router.router)
    _inc(disseminate_router.router)
    _inc(acquire_router.router)
    _inc(decide_router.router)
    _inc(simulate_router.router)
    _inc(narrate_router.router)
    _inc(verify_router.router)
    _inc(transform_router.router)
    # MCP adapter routes are always registered so OpenAPI remains stable.
    # Handlers themselves enforce ENABLE_MCP and return 404 when disabled.
    _inc(mcp_router.router)

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
        min_disk_mb = env_int("MIN_DISK_MB", 100)
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
        from zyra.api.workers.jobs import is_redis_enabled, queue_name, redis_url

        use_redis = is_redis_enabled()
        queue = {
            "mode": "redis" if use_redis else "in_memory",
            "connected": (not use_redis),
        }
        if use_redis:
            try:
                import redis  # type: ignore

                from zyra.api.workers.jobs import (
                    _get_redis_and_queue,  # type: ignore
                )

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
                        queue["length"] = (
                            int(cnt_attr) if cnt_attr is not None else None
                        )
                except Exception:
                    queue["length"] = None
            except Exception:
                queue["connected"] = False
                queue["url"] = redis_url()

        # Optional binaries (FFmpeg/ffprobe)
        ffmpeg_ok = shutil.which("ffmpeg") is not None
        ffprobe_ok = shutil.which("ffprobe") is not None
        require_ffmpeg = env_bool("REQUIRE_FFMPEG", False)
        binaries = {
            "ffmpeg": ffmpeg_ok,
            "ffprobe": ffprobe_ok,
            "required": require_ffmpeg,
        }

        # LLM configuration (provider and model only; no hostnames)
        # Resolve from environment with sensible defaults that match the Wizard.

        prov = (env("LLM_PROVIDER") or "openai").strip().lower()
        model_env = env("LLM_MODEL")
        if model_env and model_env.strip():
            model_resolved = model_env.strip()
        else:
            # Provider-specific defaults mirror zyra.wizard.llm_client
            if prov == "openai":
                model_resolved = "gpt-4o-mini"
            elif prov == "ollama":
                model_resolved = "mistral"
            else:
                model_resolved = None  # mock/unknown
        llm = {"provider": prov, "model": model_resolved}

        overall_ok = (
            exists
            and writable
            and probe_ok
            and disk_ok
            and (queue.get("connected", False))
        )
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
                "llm": llm,
            },
        }

    @app.get("/llm/test", tags=["system"])  # type: ignore[misc]
    def llm_test(
        request: Request, provider: str | None = None, model: str | None = None
    ) -> dict:
        """Probe LLM connectivity similarly to `zyra wizard --test-llm`.

        Optional query params `provider` and `model` override environment/config.
        """
        try:
            from zyra.wizard import _test_llm_connectivity
        except (
            ImportError,
            ModuleNotFoundError,
        ):  # pragma: no cover - optional dependency
            # Avoid leaking internal import errors to the client
            return {"status": "error", "message": "LLM test unavailable in this build."}

        ok, msg = _test_llm_connectivity(provider, model)

        # Also surface the resolved provider/model shown in /ready for consistency
        from zyra.utils.env import env

        prov = (env("LLM_PROVIDER") or "openai").strip().lower()
        model_env = env("LLM_MODEL")
        if model_env and model_env.strip():
            model_resolved = model_env.strip()
        else:
            model_resolved = (
                "gpt-4o-mini"
                if prov == "openai"
                else "mistral"
                if prov == "ollama"
                else None
            )

        return {
            "status": "ok" if ok else "error",
            "message": msg,
            "llm": {"provider": prov, "model": model_resolved},
        }

    # Versioned aliases for system endpoints
    app.add_api_route("/v1/health", health, methods=["GET"], tags=["system"])
    app.add_api_route("/v1/ready", ready, methods=["GET"], tags=["system"])
    app.add_api_route("/v1/llm/test", llm_test, methods=["GET"], tags=["system"])  # type: ignore[arg-type]

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
        # Respect root_path so links work when mounted under a subpath (proxies)
        root_path = str(request.scope.get("root_path") or "")

        def _p(path: str) -> str:
            return f"{root_path}{path}" if root_path else path

        endpoints_list = [
            _p("/health"),
            _p("/ready"),
            _p("/llm/test"),
            _p("/commands"),
            _p("/cli/commands"),
            _p("/cli/examples"),
            _p("/cli/run"),
            _p("/jobs/{job_id}"),
            _p("/jobs/{job_id}/manifest"),
            _p("/jobs/{job_id}/download"),
            _p("/upload"),
            _p("/examples"),
        ]
        # Conditionally expose MCP endpoint in discovery list
        if getattr(request.app.state, "mcp_enabled", False):
            endpoints_list.append("/mcp")

        meta = {
            "name": "Zyra API",
            "version": dvh_version,
            "links": {
                "docs": "/docs",
                "redoc": "/redoc",
                "examples": "/examples",
                "openapi": "/openapi.json",
            },
            "endpoints": endpoints_list,
        }
        if not prefer_html:
            return meta
        # Build a simple HTML index with clickable links
        import html as _html

        header_name = _html.escape(env("API_KEY_HEADER", "X-API-Key") or "X-API-Key")
        version_text = _html.escape(str(dvh_version))
        mcp_line = ""
        if getattr(request.app.state, "mcp_enabled", False):
            mcp_line = (
                f'<li><a href="{_p("/mcp")}">GET /mcp</a> — MCP discovery</li>'
                f'<li>POST /mcp — MCP JSON-RPC (see <a href="{_p("/docs#/%2Fmcp")}">/docs</a>)</li>'
                f'<li><a href="{_p("/ws/mcp")}">WS /ws/mcp</a> — MCP WebSocket</li>'
            )

        html = f"""
        <!doctype html>
        <html lang=\"en\">
          <head>
            <meta charset=\"utf-8\" />
            <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
            <title>Zyra API</title>
            <style>
              body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem; }}
              h1 {{ margin-bottom: .25rem; }}
              .muted {{ color: #666; }}
              ul {{ line-height: 1.8; }}
              code {{ background: #f6f8fa; padding: 0 .25rem; border-radius: 3px; }}
            </style>
          </head>
          <body>
      <h1>Zyra API</h1>
            <div class=\"muted\">Version {version_text}</div>
            <h2>Quick Links</h2>
            <ul>
              <li><a href=\"{_p('/docs')}\">Swagger UI</a></li>
              <li><a href=\"{_p('/redoc')}\">ReDoc</a></li>
              <li><a href=\"{_p('/openapi.json')}\">OpenAPI JSON</a></li>
              <li><a href=\"{_p('/examples')}\">Interactive Examples</a></li>
            </ul>
            <h2>Endpoints</h2>
            <ul>
              <li><a href=\"{_p('/health')}\">GET /health</a> — health probe</li>
              <li><a href=\"{_p('/ready')}\">GET /ready</a> — readiness checks</li>
              <li><a href=\"{_p('/commands')}\">GET /commands</a> — list/summary/json, fuzzy details</li>
              <li><a href=\"{_p('/cli/commands')}\">GET /cli/commands</a> — discovery: stages, commands, args</li>
              <li><a href=\"{_p('/cli/examples')}\">GET /cli/examples</a> — curated examples for /cli/run</li>
              <li>POST /cli/run — see <a href=\"{_p('/docs#/%2Fcli%2Frun')}\">/docs</a></li>
              {mcp_line}
              <li><a href=\"{_p('/search')}\">GET /search</a> — dataset discovery</li>
              <li><a href=\"{_p('/search/profiles')}\">GET /search/profiles</a> — bundled profiles</li>
              <li>POST /semantic_search — discovery + LLM analysis (see /docs)</li>
              <li><a href=\"{_p('/jobs/{{job_id}}')}\">GET /jobs/{{job_id}}</a> — job status</li>
              <li><a href=\"{_p('/jobs/{{job_id}}/manifest')}\">GET /jobs/{{job_id}}/manifest</a> — artifacts</li>
              <li><a href=\"{_p('/jobs/{{job_id}}/download')}\">GET /jobs/{{job_id}}/download</a> — download</li>
              <li>POST /upload — multipart upload (try in <a href=\"{_p('/docs#/%2Fupload')}\">/docs</a>)</li>
            </ul>
            <h2>Nomenclature</h2>
            <p class=\"muted\">Egress is now referred to as <code>export</code>/<code>disseminate</code>. The legacy name <code>decimate</code> remains supported across CLI, API, and MCP, but is deprecated.</p>
            <h2>Auth</h2>
            <p class=\"muted\">If <code>ZYRA_API_KEY</code> (or legacy <code>DATAVIZHUB_API_KEY</code>) is set, include <code>{header_name}</code> in requests. WebSockets use <code>?api_key=</code>.</p>
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
    ttl = env_seconds("RESULTS_TTL_SECONDS", 86400)
    interval = env_seconds("RESULTS_CLEAN_INTERVAL_SECONDS", 3600)
    # Prefer new Zyra default; also clean legacy base if present
    from pathlib import Path

    root = env_path("RESULTS_DIR", "/tmp/zyra_results")
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
            # Also attempt cleanup of legacy base to avoid stale artifacts during transition
            try:
                legacy = Path(
                    os.environ.get("DATAVIZHUB_RESULTS_DIR", "/tmp/datavizhub_results")
                )
                if legacy.exists():
                    now = time.time()
                    for job_dir in legacy.iterdir():
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
                            try:
                                if empty or not any(job_dir.iterdir()):
                                    job_dir.rmdir()
                            except Exception:
                                pass
                        except Exception:
                            continue
            except Exception:
                pass
        except Exception:
            pass
        await asyncio.sleep(interval)


app = create_app()
# Uvicorn entrypoint: `uvicorn zyra.api.server:app --reload`
