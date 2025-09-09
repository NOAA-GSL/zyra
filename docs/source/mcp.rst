MCP Adapter
===========

Overview
--------

Zyra exposes an MCP-compatible endpoint for discovery and invocation.

Discovery
---------

``GET /v1/mcp`` or ``OPTIONS /v1/mcp`` returns a spec-shaped payload suitable for MCP clients::

  {
    "mcp_version": "0.1",
    "name": "zyra",
    "description": "Zyra MCP server for domain-specific data visualization",
    "capabilities": {
      "commands": [
        { "name": "process-decode-grib2", "description": "...",
          "parameters": { "type": "object", "properties": { ... } } }
      ]
    }
  }

JSON-RPC Methods (``POST /v1/mcp``)
---------------------------------

- ``initialize``: MCP handshake.
  - Result: ``{ protocolVersion: '2025-06-18', serverInfo: { name, version }, capabilities: { tools: true } }``
- ``tools/list``: returns ``{ tools: [ { name, description, inputSchema } ] }``
- ``tools/call``: invokes a tool by namespaced name (e.g., ``process-decode-grib2``)
  - Params (MCP shape): ``{ name: str, arguments?: object, mode?: 'sync'|'async' }``
  - Params (legacy alias ``callTool``): ``{ stage: str, command: str, args?: object, mode?: 'sync'|'async' }``
  - Result (sync): ``{ status: 'ok', stdout?, stderr?, exit_code? }``
  - Result (async): ``{ status: 'accepted', job_id, poll, ws, download, manifest }``
- ``listTools``: alias of ``tools/list`` (returns the same shape)
- ``statusReport`` (alias: ``status/report``): minimal status with version

Authentication
--------------

If an API key is configured (``ZYRA_API_KEY``), include it in the
``X-API-Key`` header (or the value of ``API_KEY_HEADER``).

Feature Flags
-------------

- ``ZYRA_ENABLE_MCP``: enable/disable the MCP endpoint (default: enabled)
- ``ZYRA_MCP_MAX_BODY_BYTES``: optional request body limit in bytes; requests
  exceeding the limit are rejected with a JSON-RPC error

Examples
--------

Curl status report::

  curl -sS -H 'Content-Type: application/json' -H 'X-API-Key: $ZYRA_API_KEY' \
    -d '{"jsonrpc":"2.0","method":"statusReport","id":1}' \
    http://127.0.0.1:8000/v1/mcp

Initialize and list tools::

  curl -sS -H 'Content-Type: application/json' -H 'X-API-Key: $ZYRA_API_KEY' \
    -d '{"jsonrpc":"2.0","method":"initialize","id":2}' \
    http://127.0.0.1:8000/v1/mcp

  curl -sS -H 'Content-Type: application/json' -H 'X-API-Key: $ZYRA_API_KEY' \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":3}' \
    http://127.0.0.1:8000/v1/mcp

Call a tool (sync)::

  curl -sS -H 'Content-Type: application/json' -H 'X-API-Key: $ZYRA_API_KEY' \
    -d '{"jsonrpc":"2.0","method":"callTool","params":{"stage":"visualize","command":"heatmap","args":{"input":"samples/demo.npy","output":"/tmp/heatmap.png"},"mode":"sync"},"id":3}' \
  http://127.0.0.1:8000/v1/mcp

Error Mapping
-------------

- Validation errors → JSON-RPC error ``-32602`` with an explanation of invalid params.
- Execution failures (non-zero exit codes) → JSON-RPC error ``-32000`` with ``data``: ``{ exit_code, stderr?, stdout?, stage, command }``.

Progress Streaming
------------------

MCP clients can observe async job progress via WebSocket or Server-Sent Events (SSE):

- WebSocket: ``/ws/jobs/{job_id}`` (supports ``?stream=stdout,stderr,progress``)
- SSE: ``/v1/mcp/progress/{job_id}?interval_ms=200&max_ms=10000``

SSE emits JSON events as ``data: {...}\n\n`` until a terminal status (``succeeded``, ``failed``, or ``canceled``) or the optional ``max_ms`` timeout elapses.


Quickstart
----------

Prerequisites
~~~~~~~~~~~~~

- Install with API extras::

    poetry install --with dev -E api

- Run the API locally::

    poetry run uvicorn zyra.api.server:app --reload --host 0.0.0.0 --port 8000

- Optional: set an API key and include it in requests::

    export ZYRA_API_KEY=devkey
    # Header to include in requests: X-API-Key: devkey

Discover tools (HTTP)
~~~~~~~~~~~~~~~~~~~~~

Fetch Zyra's capabilities in MCP format::

  curl -sS -H "X-API-Key: $ZYRA_API_KEY" http://127.0.0.1:8000/v1/mcp | jq .

Or via OPTIONS::

  curl -sS -X OPTIONS -H "X-API-Key: $ZYRA_API_KEY" http://127.0.0.1:8000/v1/mcp | jq .

JSON-RPC examples
~~~~~~~~~~~~~~~~~

Status:

.. code-block:: bash

  curl -sS -H 'Content-Type: application/json' -H "X-API-Key: $ZYRA_API_KEY" \
    -d '{"jsonrpc":"2.0","method":"statusReport","id":1}' \
    http://127.0.0.1:8000/v1/mcp | jq .

Initialize and list tools:

.. code-block:: bash

  curl -sS -H 'Content-Type: application/json' -H "X-API-Key: $ZYRA_API_KEY" \
    -d '{"jsonrpc":"2.0","method":"initialize","id":2}' \
    http://127.0.0.1:8000/v1/mcp | jq .

  curl -sS -H 'Content-Type: application/json' -H "X-API-Key: $ZYRA_API_KEY" \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":3}' \
    http://127.0.0.1:8000/v1/mcp | jq .

Call a tool (sync) via ``tools/call``:

.. code-block:: bash

  curl -sS -H 'Content-Type: application/json' -H "X-API-Key: $ZYRA_API_KEY" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"visualize-heatmap","arguments":{"input":"samples/demo.npy","output":"/tmp/heatmap.png"},"mode":"sync"},"id":4}' \
    http://127.0.0.1:8000/v1/mcp | jq .

WebSocket Transport
-------------------

Zyra also provides a native WebSocket MCP endpoint for persistent connections and server-initiated notifications.

- Endpoint: ``/v1/ws/mcp`` (query param ``api_key`` when enabled)
- Protocol: JSON-RPC 2.0 frames over WebSocket
- Handshake:
  1. Client sends ``initialize``
  2. Server replies with result then emits ``notifications/initialized``
- Discovery: send ``tools/list`` and receive ``{ tools: [...] }``
- Invocation: send ``tools/call`` with ``{ name, arguments, mode }``
- Progress: when mode=``async``, Zyra emits progress notifications on the same socket:
  - ``{"jsonrpc":"2.0","method":"notifications/progress","params":{ "job_id": "...", ... }}``
  - Params mirror the job progress stream (e.g., ``progress``, ``stdout``, ``stderr``, ``status``, ``exit_code``, ``output_file``)

Example (WS frames):

.. code-block:: json

  { "jsonrpc":"2.0", "id": 1, "method": "initialize", "params": {} }
  { "jsonrpc":"2.0", "id": 1, "result": { "protocolVersion": "2025-06-18", "serverInfo": {"name":"zyra","version":"..."}, "capabilities": {"tools": {"listChanged": true}} } }
  { "jsonrpc":"2.0", "method": "notifications/initialized", "params": {} }

  { "jsonrpc":"2.0", "id": 2, "method": "tools/list", "params": {} }
  { "jsonrpc":"2.0", "id": 2, "result": { "tools": [ {"name": "process-decode-grib2", "inputSchema": {"type":"object", ...} } ] } }

  { "jsonrpc":"2.0", "id": 3, "method": "tools/call", "params": { "name": "process-decode-grib2", "arguments": {"file_or_url": "s3://..."}, "mode": "async" } }
  { "jsonrpc":"2.0", "id": 3, "result": { "status": "accepted", "job_id": "abc123", "poll": "/jobs/abc123", "ws": "/ws/jobs/abc123", "download": "/jobs/abc123/download", "manifest": "/jobs/abc123/manifest" } }
  { "jsonrpc":"2.0", "method": "notifications/progress", "params": { "job_id": "abc123", "progress": 0.0 } }
  { "jsonrpc":"2.0", "method": "notifications/progress", "params": { "job_id": "abc123", "stdout": "..." } }
  { "jsonrpc":"2.0", "method": "notifications/progress", "params": { "job_id": "abc123", "status": "succeeded", "exit_code": 0, "output_file": "/v1/jobs/abc123/download" } }


Observe progress (async):

.. code-block:: bash

  # After submitting an async callTool and capturing the job_id
  curl -N -H "X-API-Key: $ZYRA_API_KEY" \
    "http://127.0.0.1:8000/v1/mcp/progress/$JOB_ID?interval_ms=200"

IDE integration notes
~~~~~~~~~~~~~~~~~~~~~

- Claude Desktop / Cursor / VS Code MCP clients typically probe ``GET /mcp``. Ensure Zyra is running and accessible (default port 8000).
- If an API key is set, configure the client to send ``X-API-Key: <value>`` with requests.
- The MCP discovery response uses names like ``process-decode-grib2`` and includes JSON Schema parameters for each tool.

See also
~~~~~~~~

- Example client script: ``scripts/mcp_client_example.py``
- MCP spec: https://modelcontextprotocol.io/docs
