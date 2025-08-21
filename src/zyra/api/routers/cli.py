"""FastAPI router that exposes CLI discovery and execution endpoints.

Endpoints
- GET /cli/commands: return a schema of CLI groups, commands, and arg metadata
- GET /cli/examples: curated request bodies for /cli/run and pipeline configs
- POST /cli/run: run a CLI request synchronously or asynchronously
- GET /examples: interactive examples page with Run buttons (HTML)

Implementation notes
- Builds parser schemas by invoking each group's ``register_cli`` function.
- Supports dry-run toggles and example request bodies that demonstrate common
  flows (e.g., pipeline dry-runs, conversions, uploads).
"""

from __future__ import annotations

import argparse
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import HTMLResponse
from zyra.api.models.cli_request import (
    CLIRunRequest,
    CLIRunResponse,
)
from zyra.api.workers import jobs as jobs_backend
from zyra.api.workers.executor import resolve_upload_placeholders, run_cli
from zyra.utils.env import env

router = APIRouter(tags=["cli"])


_CLI_MATRIX: dict[str, Any] | None = None


def _type_name(t: Any) -> str | None:
    if t is None:
        return None
    if t in (str, int, float, bool):
        return t.__name__
    try:
        return t.__class__.__name__
    except Exception:
        return None


def _extract_parser_schema(p: argparse.ArgumentParser) -> list[dict[str, Any]]:
    """Extract a simple argument schema from an argparse parser."""
    out: list[dict[str, Any]] = []
    for act in getattr(p, "_actions", []):
        # Skip help actions
        if (
            getattr(act, "help", None) == argparse.SUPPRESS
            or act.__class__.__name__ == "_HelpAction"
        ):
            continue
        if getattr(act, "dest", None) in {"help", "_help"}:
            continue
        item: dict[str, Any] = {
            "name": getattr(act, "dest", None),
            "flags": list(getattr(act, "option_strings", []) or []),
            "positional": not bool(getattr(act, "option_strings", [])),
            "required": bool(getattr(act, "required", False)),
            "nargs": getattr(act, "nargs", None),
            "choices": list(getattr(act, "choices", []) or []) or None,
            "default": getattr(act, "default", None),
            "help": getattr(act, "help", None),
        }
        # Type detection
        tp = getattr(act, "type", None)
        if tp is None:
            # Infer bool switches
            cname = act.__class__.__name__
            if cname in {"_StoreTrueAction", "_StoreFalseAction"}:
                item["type"] = "bool"
            else:
                item["type"] = None
        else:
            item["type"] = _type_name(tp)
        out.append(item)
    return out


def _compute_cli_matrix() -> dict[str, Any]:
    import zyra.connectors.egress as egress
    import zyra.connectors.ingest as ingest
    import zyra.processing as processing
    import zyra.transform as transform
    import zyra.visualization as visualization

    def parsers_from_register(register_fn) -> dict[str, argparse.ArgumentParser]:
        parser = argparse.ArgumentParser(prog="zyra")
        sub = parser.add_subparsers(dest="sub")
        register_fn(sub)
        # type: ignore[attr-defined]
        return dict(getattr(sub, "choices", {}))

    result: dict[str, Any] = {}

    def _with_examples(
        stage: str, command: str, schema_list: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        def ex(name: str, meta: dict[str, Any]) -> Any:
            # Heuristic examples by name
            if name in {"url"}:
                if stage in {"acquire"} and command == "http":
                    return "https://example.com/sample.grib2"
                if stage in {"decimate"} and command in {"post"}:
                    return "https://example.com/upload"
                if command == "s3":
                    return "s3://my-bucket/path/to/object.bin"
            if name in {"bucket"}:
                return "my-bucket"
            if name in {"key"}:
                return "path/to/object.bin"
            if name in {"file_or_url"}:
                return "samples/demo.nc"
            if name in {"input"}:
                return "samples/demo.nc"
            if name in {"output"}:
                return "/tmp/output.bin"
            if name in {"path"}:
                return "/tmp/output.bin"
            if name in {"format"}:
                return "netcdf"
            if name in {"var", "pattern"}:
                return "temperature"
            if name in {"frames"}:
                return "/data/frames"
            if name in {"frames_dir"}:
                return "./frames"
            if name in {"fps"}:
                return 30
            if name in {"basemap"}:
                return "/data/basemap.png"
            if name in {"uvar"}:
                return "u10"
            if name in {"vvar"}:
                return "v10"
            if name in {"u"}:
                return "samples/u_stack.npy"
            if name in {"v"}:
                return "samples/v_stack.npy"
            if name in {"content_type"}:
                return "application/octet-stream"
            if name in {"tile_source"}:
                return "OpenStreetMap"
            if name in {"tile_zoom"}:
                return 3
            if name in {"width"}:
                return 800
            if name in {"height"}:
                return 400
            if name in {"dpi"}:
                return 96
            if name in {"unsigned", "stdout", "colorbar", "reproject", "streamlines"}:
                return False
            if name in {"datetime_format"}:
                return "%Y%m%d"
            if name in {"period_seconds"}:
                return 3600
            return None

        for m in schema_list:
            example = ex(m.get("name"), m)
            if example is not None:
                m["example"] = example
        return schema_list

    for stage, reg in (
        ("acquire", ingest.register_cli),
        ("process", processing.register_cli),
        ("visualize", visualization.register_cli),
        ("decimate", egress.register_cli),
        ("transform", transform.register_cli),
    ):
        parsers = parsers_from_register(reg)
        cmds = sorted(list(parsers.keys()))
        schema = {
            name: _with_examples(stage, name, _extract_parser_schema(parsers[name]))
            for name in cmds
        }
        result[stage] = {"commands": cmds, "schema": schema}

    # Top-level 'run'
    from zyra.pipeline_runner import register_cli_run as _register_run

    parsers = parsers_from_register(_register_run)
    schema = {
        name: _with_examples("run", name, _extract_parser_schema(parsers[name]))
        for name in parsers
    }
    result["run"] = {"commands": sorted(list(parsers.keys())), "schema": schema}
    return result


def get_cli_matrix() -> dict[str, Any]:
    global _CLI_MATRIX
    if _CLI_MATRIX is None:
        _CLI_MATRIX = _compute_cli_matrix()
    return _CLI_MATRIX


@router.get("/cli/commands")
def list_cli_commands() -> dict[str, Any]:
    """Return a discovery matrix mapping stages to commands and argument schemas.

    The schema includes basic per-argument metadata and heuristic example values
    to help UI generators build forms.
    """
    return get_cli_matrix()


@router.get("/cli/examples")
def list_cli_examples() -> dict[str, Any]:
    """Return curated example bodies for /cli/run and sample pipeline paths."""
    """Curated examples for common workflows.

    These are example request bodies for POST /cli/run and pipeline configs.
    """
    examples: list[dict[str, Any]] = []

    # 1) Acquire HTTP -> convert to NetCDF -> write to local file (via pipeline)
    examples.append(
        {
            "name": "http_to_netcdf_local",
            "description": "Fetch bytes over HTTP, convert to NetCDF, and write to a local file using the runner.",
            "pipeline_config": "samples/pipelines/nc_to_file.json",
            "request": {
                "stage": "run",
                "command": "run",
                "mode": "sync",
                "args": {
                    "config": "samples/pipelines/nc_to_file.json",
                    "dry_run": True,
                },
            },
        }
    )

    # 2) Extract a variable from a GRIB2 and save to NetCDF (pipeline)
    examples.append(
        {
            "name": "extract_variable_to_file",
            "description": "Extract a matching variable from GRIB2 and save to NetCDF.",
            "pipeline_config": "samples/pipelines/extract_variable_to_file.json",
            "request": {
                "stage": "run",
                "command": "run",
                "mode": "sync",
                "args": {
                    "config": "samples/pipelines/extract_variable_to_file.json",
                    "dry_run": True,
                },
            },
        }
    )

    # 3) One-off: Convert remote GRIB2 URL to NetCDF and return bytes in response
    examples.append(
        {
            "name": "convert_grib2_url_to_netcdf_stdout",
            "description": "Convert a remote GRIB2 file to NetCDF and stream bytes via API response.",
            "request": {
                "stage": "process",
                "command": "convert-format",
                "mode": "sync",
                "args": {
                    "file_or_url": "https://example.com/sample.grib2",
                    "format": "netcdf",
                    "stdout": True,
                },
            },
        }
    )

    # 3b) Upload then convert: use an uploaded file by file_id placeholder
    examples.append(
        {
            "name": "upload_then_convert",
            "description": "Convert an uploaded GRIB2/NetCDF file using a file_id placeholder (replace with real id).",
            "request": {
                "stage": "process",
                "command": "convert-format",
                "mode": "sync",
                "args": {
                    "file_or_url": "file_id:REPLACE_WITH_FILE_ID",
                    "format": "netcdf",
                    "stdout": True,
                },
            },
        }
    )

    # 4) Visualize: heatmap from a sample NPY to PNG
    examples.append(
        {
            "name": "visualize_heatmap",
            "description": "Render a heatmap from a sample NPY array to a PNG file.",
            "request": {
                "stage": "visualize",
                "command": "heatmap",
                "mode": "sync",
                "args": {
                    "input": "samples/demo.npy",
                    "output": "/tmp/heatmap.png",
                    "width": 800,
                    "height": 400,
                },
            },
        }
    )

    # 5) Decimate: upload a local file to S3 (one-off)
    examples.append(
        {
            "name": "decimate_to_s3",
            "description": "Upload a local file to S3 using the decimate s3 command.",
            "request": {
                "stage": "decimate",
                "command": "s3",
                "mode": "sync",
                "args": {
                    "input": "samples/demo.nc",
                    "url": "s3://my-bucket/path/output/demo.nc",
                },
            },
        }
    )

    # 6) Visualization to video using ffmpeg: animate with --to-video (NPY)
    examples.append(
        {
            "name": "visualize_to_video",
            "description": "Animate frames from a sample NPY stack and compose to MP4 using ffmpeg.",
            "request": {
                "stage": "visualize",
                "command": "animate",
                "mode": "sync",
                "args": {
                    "mode": "heatmap",
                    "input": "samples/demo.npy",
                    "output_dir": "/tmp/frames",
                    "to_video": "/tmp/output.mp4",
                    "fps": 24,
                },
            },
        }
    )

    # 7) FTP → Transform → Video → S3 (pipeline; dry-run only)
    examples.append(
        {
            "name": "ftp_to_s3_video_pipeline",
            "description": "Sync frames from FTP, compute metadata, compose to MP4, and upload to S3 (dry-run showcases pipeline mapping).",
            "pipeline_config": "samples/pipelines/ftp_to_s3.yaml",
            "request": {
                "stage": "run",
                "command": "run",
                "mode": "sync",
                "args": {"config": "samples/pipelines/ftp_to_s3.yaml", "dry_run": True},
            },
        }
    )

    # 8) FTP → Transform → Video → Local (pipeline; dry-run only)
    examples.append(
        {
            "name": "ftp_to_local_pipeline",
            "description": "Sync frames from FTP, compute metadata, compose to MP4, and copy outputs locally (no S3/Vimeo).",
            "pipeline_config": "samples/pipelines/ftp_to_local.yaml",
            "request": {
                "stage": "run",
                "command": "run",
                "mode": "sync",
                "args": {
                    "config": "samples/pipelines/ftp_to_local.yaml",
                    "dry_run": True,
                },
            },
        }
    )

    return {"examples": examples}


@router.post(
    "/cli/run",
    response_model=CLIRunResponse,
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "Run Pipeline (dry-run)": {
                            "summary": "Run a pipeline config (dry-run)",
                            "value": {
                                "stage": "run",
                                "command": "run",
                                "mode": "sync",
                                "args": {
                                    "config": "samples/pipelines/nc_to_file.yaml",
                                    "dry_run": True,
                                },
                            },
                        },
                        "Convert GRIB2 to NetCDF": {
                            "summary": "Convert remote GRIB2 to NetCDF and return bytes",
                            "value": {
                                "stage": "process",
                                "command": "convert-format",
                                "mode": "sync",
                                "args": {
                                    "file_or_url": "https://example.com/sample.grib2",
                                    "format": "netcdf",
                                    "stdout": True,
                                },
                            },
                        },
                        "Visualize Heatmap": {
                            "summary": "Render a heatmap PNG from NPY",
                            "value": {
                                "stage": "visualize",
                                "command": "heatmap",
                                "mode": "sync",
                                "args": {
                                    "input": "samples/demo.npy",
                                    "output": "/tmp/heatmap.png",
                                    "width": 800,
                                    "height": 400,
                                },
                            },
                        },
                        "Run FTP→Transform→Video→S3 (dry-run)": {
                            "summary": "Run the FTP→Transform→Video→S3 pipeline (dry-run)",
                            "value": {
                                "stage": "run",
                                "command": "run",
                                "mode": "sync",
                                "args": {
                                    "config": "samples/pipelines/ftp_to_s3.yaml",
                                    "dry_run": True,
                                },
                            },
                        },
                        "Upload then Convert": {
                            "summary": "Convert an uploaded file by file_id (replace with real id)",
                            "value": {
                                "stage": "process",
                                "command": "convert-format",
                                "mode": "sync",
                                "args": {
                                    "file_or_url": "file_id:REPLACE_WITH_FILE_ID",
                                    "format": "netcdf",
                                    "stdout": True,
                                },
                            },
                        },
                        "Visualize Animate to MP4": {
                            "summary": "Animate frames and compose to MP4 (ffmpeg, NPY)",
                            "value": {
                                "stage": "visualize",
                                "command": "animate",
                                "mode": "sync",
                                "args": {
                                    "mode": "heatmap",
                                    "input": "samples/demo.npy",
                                    "output_dir": "/tmp/frames",
                                    "to_video": "/tmp/output.mp4",
                                    "fps": 24,
                                },
                            },
                        },
                        "Decimate to S3": {
                            "summary": "Upload a local file to S3",
                            "value": {
                                "stage": "decimate",
                                "command": "s3",
                                "mode": "sync",
                                "args": {
                                    "input": "samples/demo.nc",
                                    "url": "s3://my-bucket/path/output/demo.nc",
                                },
                            },
                        },
                        "Run FTP→Transform→Video→Local (dry-run)": {
                            "summary": "Run the FTP→Transform→Video→Local pipeline (dry-run)",
                            "value": {
                                "stage": "run",
                                "command": "run",
                                "mode": "sync",
                                "args": {
                                    "config": "samples/pipelines/ftp_to_local.yaml",
                                    "dry_run": True,
                                },
                            },
                        },
                    }
                }
            }
        }
    },
)
def run_cli_endpoint(req: CLIRunRequest, bg: BackgroundTasks) -> CLIRunResponse:
    """Execute a CLI request.

    - Async mode enqueues an in-memory or Redis job and returns `job_id`
    - Sync mode runs inline and returns stdout/stderr/exit_code
    - Strict file_id resolution can be enabled via `ZYRA_STRICT_FILE_ID=1` (or legacy `DATAVIZHUB_STRICT_FILE_ID=1`)
    """
    # Validate requested stage/command
    matrix = get_cli_matrix()
    if req.stage not in matrix:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Invalid stage '{req.stage}'",
                "allowed": sorted(list(matrix.keys())),
            },
        )
    allowed_cmds = set(matrix[req.stage].get("commands", []) or [])
    if req.command not in allowed_cmds:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Invalid command '{req.command}' for stage '{req.stage}'",
                "allowed": sorted(list(allowed_cmds)),
            },
        )
    # Optional strict file_id resolution
    from zyra.utils.env import env

    strict = str(env("STRICT_FILE_ID", "0") or "0").lower() in {
        "1",
        "true",
        "yes",
    }
    try:
        _resolved_args, _paths, unresolved = resolve_upload_placeholders(req.args)
        if strict and unresolved:
            raise HTTPException(
                status_code=404,
                detail={"error": "Unresolved file_id", "file_ids": unresolved},
            )
    except HTTPException:
        raise
    except Exception:
        # Non-strict environments ignore resolution errors
        pass
    if req.mode == "async":
        job_id = jobs_backend.submit_job(req.stage, req.command, req.args)
        # Kick off execution in the background (in-memory only; Redis workers run separately)
        bg.add_task(jobs_backend.start_job, job_id, req.stage, req.command, req.args)
        return CLIRunResponse(status="accepted", job_id=job_id)

    # Synchronous execution
    res = run_cli(req.stage, req.command, req.args)
    return CLIRunResponse(
        status="success" if res.exit_code == 0 else "error",
        stdout=res.stdout,
        stderr=res.stderr,
        exit_code=res.exit_code,
    )


@router.get("/examples", include_in_schema=False)
def examples_page(request: Request) -> HTMLResponse:
    """Serve a minimal interactive examples page with Run buttons.

    When `ZYRA_REQUIRE_KEY_FOR_EXAMPLES=1` (or legacy `DATAVIZHUB_REQUIRE_KEY_FOR_EXAMPLES=1`) and an API key is set, this
    route returns 401 unless a valid key is provided via header or `?api_key=`.
    The UI includes a field that propagates the key to HTTP headers and WS URLs.
    """
    # Optional: require API key for accessing the examples page itself
    require = (env("REQUIRE_KEY_FOR_EXAMPLES", "0") or "0").lower() in {
        "1",
        "true",
        "yes",
    }
    expected = env("API_KEY")
    if require and expected:
        header_name = env("API_KEY_HEADER", "X-API-Key") or "X-API-Key"
        provided = request.headers.get(header_name) or request.query_params.get(
            "api_key"
        )
        try:
            import secrets as _secrets

            ok = (
                isinstance(provided, str)
                and isinstance(expected, str)
                and _secrets.compare_digest(provided, expected)
            )
        except Exception:
            ok = False
        if not ok:
            return HTMLResponse(
                content="<h1>Unauthorized</h1><p>Provide a valid API key to access examples.</p>",
                status_code=401,
            )
    """Serve a minimal interactive examples page with Run buttons."""
    html = """<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Zyra API Examples</title>
    <style>
      body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem; }
      h1 { margin-bottom: 0.5rem; }
      .example { border: 1px solid #ddd; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; }
      .row { display: flex; gap: 1rem; align-items: center; }
      textarea { width: 100%; height: 8rem; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.9rem; }
      button { padding: 0.4rem 0.8rem; }
      .status { font-size: 0.9rem; color: #555; }
      pre { background: #f8f8f8; padding: 0.5rem; overflow: auto; }
      .header { display: flex; gap: 1rem; align-items: baseline; }
      .small { color: #666; font-size: 0.9rem; }
    </style>
  </head>
  <body>
    <div class=\"header\">
      <h1>Zyra API Examples</h1>
      <a class=\"small\" href=\"/docs\">OpenAPI Docs</a>
    </div>
    <section class=\"example\">
      <h2>Upload → Run → Download</h2>
      <div class=\"small\">1) Choose a file to upload, 2) Run a conversion using the returned file_id, 3) Download the result.</div>
      <div class=\"row\" style=\"margin-top:.5rem\">
        <input type=\"file\" id=\"upl\" />
        <button id=\"btnUpload\">Upload</button>
        <span class=\"status\" id=\"uplStatus\"></span>
      </div>
    <div class=\"small\" style=\"margin:.25rem 0\">
      <label><input type=\"checkbox\" id=\"useWS\" checked /> Use WebSocket streaming</label>
      <span style=\"margin-left:1rem\">Filters:</span>
      <label><input type=\"checkbox\" id=\"fltOut\" checked /> stdout</label>
      <label><input type=\"checkbox\" id=\"fltErr\" checked /> stderr</label>
      <label><input type=\"checkbox\" id=\"fltProg\" checked /> progress</label>
      <span style=\"margin-left:1rem\">API Key:</span>
      <input type=\"password\" id=\"apiKey\" placeholder=\"X-API-Key\" style=\"width:12rem\" />
    </div>
      <div class=\"small\" id=\"uplMeta\"></div>
      <textarea id=\"uplReq\" style=\"margin-top:.5rem\"></textarea>
      <div class=\"row\">
        <button id=\"btnRunSync\">Run (sync)</button>
        <button id=\"btnRunAsync\">Run (async)</button>
        <span class=\"status\" id=\"runStatus\"></span>
      </div>
      <pre id=\"runOut\"></pre>
      <div class=\"row\">
        <a id=\"dlLink\" href=\"#\" download>Download</a>
        <a id=\"mfLink\" href=\"#\" target=\"_blank\">Manifest</a>
      </div>
    </section>

    <div id=\"container\">Loading examples…</div>
    <script>
      const el = (tag, props={}, children=[]) => {
        const e = document.createElement(tag);
        Object.assign(e, props);
        for (const c of children) e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
        return e;
      };

      async function load() {
        // Seed upload→run example body
        const uplReq = document.getElementById('uplReq');
        uplReq.value = JSON.stringify({
          stage: 'process',
          command: 'convert-format',
          mode: 'sync',
          args: { file_or_url: 'file_id:REPLACE_WITH_FILE_ID', format: 'netcdf', stdout: true }
        }, null, 2);
        const dlLink = document.getElementById('dlLink');
        const mfLink = document.getElementById('mfLink');
        const runOut = document.getElementById('runOut');
        const runStatus = document.getElementById('runStatus');
        let lastJobId = null;

        document.getElementById('btnUpload').onclick = async () => {
          const f = document.getElementById('upl').files[0];
          const st = document.getElementById('uplStatus');
          const meta = document.getElementById('uplMeta');
          if (!f) { st.textContent = 'Choose a file first'; return; }
          const fd = new FormData(); fd.append('file', f);
          st.textContent = 'Uploading…'; meta.textContent='';
          try {
            const apiKey = document.getElementById('apiKey').value;
            const r = await fetch('/upload', { method: 'POST', body: fd, headers: apiKey ? { 'X-API-Key': apiKey } : {} });
            const js = await r.json();
            st.textContent = 'HTTP ' + r.status;
            meta.textContent = 'file_id: ' + js.file_id + ' — ' + (js.path || '');
            // Replace placeholder in request body
            try { const obj = JSON.parse(uplReq.value); obj.args = obj.args || {}; obj.args.file_or_url = 'file_id:' + js.file_id; uplReq.value = JSON.stringify(obj, null, 2); } catch {}
          } catch (e) {
            st.textContent = 'Upload failed'; meta.textContent = String(e);
          }
        };

        async function runReq(mode) {
          runOut.textContent=''; runStatus.textContent='Running…';
          try {
            const body = JSON.parse(uplReq.value); body.mode = mode;
            const apiKey = document.getElementById('apiKey').value;
            const headers = { 'Content-Type': 'application/json' };
            if (apiKey) headers['X-API-Key'] = apiKey;
            const r = await fetch('/cli/run', { method: 'POST', headers, body: JSON.stringify(body)});
            const t = await r.text();
            runStatus.textContent = 'HTTP ' + r.status;
            runOut.textContent = t;
            try { const js = JSON.parse(t); if (js.job_id) { lastJobId = js.job_id; } } catch {}
          } catch (e) { runStatus.textContent='Error'; runOut.textContent = String(e); }
        }
        document.getElementById('btnRunSync').onclick = async () => { await runReq('sync'); };
        document.getElementById('btnRunAsync').onclick = async () => {
          await runReq('async');
          if (lastJobId) {
            const useWS = document.getElementById('useWS').checked;
            const buildStream = () => {
              const sel = [];
              if (document.getElementById('fltOut').checked) sel.push('stdout');
              if (document.getElementById('fltErr').checked) sel.push('stderr');
              if (document.getElementById('fltProg').checked) sel.push('progress');
              return sel.join(',');
            }
            dlLink.href = '/jobs/' + lastJobId + '/download';
            mfLink.href = '/jobs/' + lastJobId + '/manifest';
            if (useWS) {
              const stream = buildStream();
              const proto = location.protocol === 'https:' ? 'wss' : 'ws';
              const apiKey = document.getElementById('apiKey').value;
              let url = proto + '://' + location.host + '/ws/jobs/' + lastJobId;
              const params = [];
              if (stream) params.push('stream=' + encodeURIComponent(stream));
              if (apiKey) params.push('api_key=' + encodeURIComponent(apiKey));
              if (params.length) url += '?' + params.join('&');
              try {
                const ws = new WebSocket(url);
                ws.onmessage = (ev) => { try { runOut.textContent = JSON.stringify(JSON.parse(ev.data), null, 2); } catch { runOut.textContent=ev.data; } }
                ws.onclose = () => { runStatus.textContent = 'WebSocket closed'; };
              } catch (e) {
                runStatus.textContent = 'WS failed; falling back to polling';
              }
            } else {
              // Poll async job
              let tries=0; const max=60;
              const timer = setInterval(async () => {
                tries++;
                try {
                  const jr = await fetch('/jobs/' + lastJobId);
                  const js = await jr.json();
                  runStatus.textContent = 'Job ' + lastJobId + ': ' + js.status;
                  runOut.textContent = JSON.stringify(js, null, 2);
                  if (['succeeded','failed','canceled'].includes(String(js.status))) { clearInterval(timer); }
                  if (tries>=max) { clearInterval(timer); runStatus.textContent += ' (timeout)'; }
                } catch (e) { clearInterval(timer); runStatus.textContent='Polling error'; }
              }, 1000);
            }
          }
        };

        try {
          const res = await fetch('/cli/examples');
          const data = await res.json();
          const wrap = document.getElementById('container');
          wrap.innerHTML = '';
          (data.examples || []).forEach((ex, idx) => {
            const area = el('textarea', { value: JSON.stringify(ex.request, null, 2) });
            const status = el('div', { className: 'status' }, []);
            const out = el('pre', { textContent: ''});
            const runSync = el('button', { textContent: 'Run (sync)' });
            const runAsync = el('button', { textContent: 'Run (async)' });
            const controls = el('div', { className: 'row' }, []);
            const warn = el('div', { className: 'small', textContent: '' });
            // Add Dry-run toggle for pipeline run examples
            try {
              const body = ex.request || {};
              if (body.stage === 'run' && body.command === 'run') {
                const dry = el('input', { type: 'checkbox', checked: true });
                const lbl = el('label', {}, [dry, ' Dry-run']);
                controls.appendChild(lbl);
                controls.appendChild(el('span', { textContent: ' (validates and prints argv only)' }));
                const updateBody = () => {
                  try {
                    const obj = JSON.parse(area.value);
                    obj.args = obj.args || {};
                    obj.args.dry_run = !!dry.checked;
                    area.value = JSON.stringify(obj, null, 2);
                    warn.textContent = dry.checked ? '' : 'Warning: This will attempt network I/O and may require credentials.';
                  } catch {}
                };
                dry.onchange = updateBody;
                updateBody();
              }
            } catch {}
            runSync.onclick = async () => {
              out.textContent = ''; status.textContent = 'Running…';
              try {
                const body = JSON.parse(area.value);
                body.mode = 'sync';
                const r = await fetch('/cli/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)});
                const t = await r.text();
                status.textContent = 'HTTP ' + r.status;
                out.textContent = t;
              } catch (e) {
                status.textContent = 'Error'; out.textContent = String(e);
              }
            };
            runAsync.onclick = async () => {
              out.textContent = ''; status.textContent = 'Submitting…';
              try {
                const body = JSON.parse(area.value);
                body.mode = 'async';
                const r = await fetch('/cli/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)});
                const js = await r.json();
                status.textContent = 'HTTP ' + r.status + (js.job_id ? (', job ' + js.job_id) : '');
                out.textContent = JSON.stringify(js, null, 2);
                if (js.job_id) {
                  const jobId = js.job_id;
                  // Poll job status up to ~30 seconds
                  let tries = 0;
                  const timer = setInterval(async () => {
                    tries += 1;
                    try {
                      const jr = await fetch('/jobs/' + jobId);
                      const jjs = await jr.json();
                      status.textContent = 'Job ' + jobId + ': ' + (jjs.status || '');
                      out.textContent = JSON.stringify(jjs, null, 2);
                      if (['succeeded','failed','canceled'].includes(String(jjs.status))) {
                        clearInterval(timer);
                      }
                      if (tries > 30) {
                        clearInterval(timer);
                        status.textContent += ' (timeout)';
                      }
                    } catch (e) {
                      clearInterval(timer);
                      status.textContent = 'Polling error';
                    }
                  }, 1000);
                }
              } catch (e) {
                status.textContent = 'Error'; out.textContent = String(e);
              }
            };
            const card = el('div', { className: 'example' }, [
              el('h3', { textContent: ex.name || ('Example #' + (idx+1)) }),
              el('div', { className: 'small', textContent: ex.description || '' }),
              area,
              controls,
              warn,
              el('div', { className: 'row' }, [ runSync, runAsync, status ]),
              out,
            ]);
            wrap.appendChild(card);
          });
        } catch (e) {
          document.getElementById('container').textContent = 'Failed to load examples: ' + e;
        }
      }
      load();
    </script>
  </body>
  </html>"""
    return HTMLResponse(content=html)
