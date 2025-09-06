Domain APIs (v1)
================

Zyra exposes high-level, domain-oriented endpoints that delegate to the
underlying CLI via ``/cli/run``. These endpoints provide clearer grouping by
intent while retaining full CLI capability.

Endpoints
---------

- ``POST /process`` — Orchestration and data processing
- ``POST /visualize`` — Static images, animations, plots
- ``POST /decimate`` — Export, write, egress (local path, S3, etc.)
- ``POST /assets`` — Convenience alias for asset I/O (maps to decimate or acquire)

Request/Response Shape
----------------------

Request body::

  {
    "tool": "<command>",
    "args": { /* key/value pairs */ },
    "options": { "mode": "sync" | "async", "timeout_ms": 60000, "dry_run": false }
  }

Response (sync)::

  { "status": "ok" | "error", "stdout"?: "...", "stderr"?: "...", "exit_code"?: 0 }

Response (async)::

  {
    "status": "accepted",
    "job_id": "...",
    "poll": "/jobs/{id}",
    "download": "/jobs/{id}/download",
    "manifest": "/jobs/{id}/manifest"
  }

Auth
----

If an API key is configured (``ZYRA_API_KEY``), include ``X-API-Key`` with
each request (or set ``API_KEY_HEADER`` to customize the header name).

Examples
--------

Process: convert format (stdout)::

  curl -sS -H 'Content-Type: application/json' -H "X-API-Key: $ZYRA_API_KEY" \\
    -d '{
          "tool": "convert-format",
          "args": { "file_or_url": "https://example.com/sample.grib2", "format": "netcdf", "stdout": true },
          "options": { "mode": "sync" }
        }' \\
    http://localhost:8000/process

Visualize: heatmap to PNG::

  curl -sS -H 'Content-Type: application/json' -H "X-API-Key: $ZYRA_API_KEY" \\
    -d '{
          "tool": "heatmap",
          "args": { "input": "samples/demo.npy", "output": "/tmp/heatmap.png", "width": 800, "height": 400 },
          "options": { "mode": "sync" }
        }' \\
    http://localhost:8000/visualize

Decimate: write to local::

  curl -sS -H 'Content-Type: application/json' -H "X-API-Key: $ZYRA_API_KEY" \\
    -d '{
          "tool": "local",
          "args": { "input": "-", "output": "/tmp/out.bin" },
          "options": { "mode": "sync" }
        }' \\
    http://localhost:8000/decimate --data-binary @file.bin

Assets: convenience alias::

  curl -sS -H 'Content-Type: application/json' -H "X-API-Key: $ZYRA_API_KEY" \\
    -d '{
          "tool": "s3",
          "args": { "input": "samples/demo.nc", "url": "s3://bucket/path/demo.nc" },
          "options": { "mode": "sync" }
        }' \\
    http://localhost:8000/assets

Notes
-----

- The ``tool`` must be a valid command within the target domain; otherwise a
  400 error is returned with the list of allowed commands.
- ``/assets`` tries to route tools to ``decimate`` first, then to ``acquire``
  if the tool exists there. This keeps simple asset I/O calls under one path.

