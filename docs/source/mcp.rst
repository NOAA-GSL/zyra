MCP Adapter
===========

Overview
--------

Zyra exposes an MCP-compatible endpoint for discovery and invocation.

Discovery
---------

``GET /mcp`` or ``OPTIONS /mcp`` returns a spec-shaped payload suitable for MCP clients::

  {
    "mcp_version": "0.1",
    "name": "zyra",
    "description": "Zyra MCP server for domain-specific data visualization",
    "capabilities": {
      "commands": [
        { "name": "process.decode-grib2", "description": "...",
          "parameters": { "type": "object", "properties": { ... } } }
      ]
    }
  }

JSON-RPC Methods (``POST /mcp``)
---------------------------------

- ``listTools``: returns the same discovery payload as ``GET /mcp``
- ``callTool``: runs a CLI tool via the existing ``/cli/run`` pathway
  - Params: ``{ stage: str, command: str, args?: object, mode?: 'sync'|'async' }``
  - Result (sync): ``{ status: 'ok', stdout?, stderr?, exit_code? }``
  - Result (async): ``{ status: 'accepted', job_id, poll, ws, download, manifest }``
- ``statusReport``: returns a minimal status object with version

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
    http://127.0.0.1:8000/mcp

List tools::

  curl -sS -H 'Content-Type: application/json' -H 'X-API-Key: $ZYRA_API_KEY' \
    -d '{"jsonrpc":"2.0","method":"listTools","id":2}' \
    http://127.0.0.1:8000/mcp

Call a tool (sync)::

  curl -sS -H 'Content-Type: application/json' -H 'X-API-Key: $ZYRA_API_KEY' \
    -d '{"jsonrpc":"2.0","method":"callTool","params":{"stage":"visualize","command":"heatmap","args":{"input":"samples/demo.npy","output":"/tmp/heatmap.png"},"mode":"sync"},"id":3}' \
  http://127.0.0.1:8000/mcp

Error Mapping
-------------

- Validation errors → JSON-RPC error ``-32602`` with an explanation of invalid params.
- Execution failures (non-zero exit codes) → JSON-RPC error ``-32000`` with ``data``: ``{ exit_code, stderr?, stdout?, stage, command }``.

Progress Streaming
------------------

MCP clients can observe async job progress via WebSocket or Server-Sent Events (SSE):

- WebSocket: ``/ws/jobs/{job_id}`` (supports ``?stream=stdout,stderr,progress``)
- SSE: ``/mcp/progress/{job_id}?interval_ms=200&max_ms=10000``

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

  curl -sS -H "X-API-Key: $ZYRA_API_KEY" http://127.0.0.1:8000/mcp | jq .

Or via OPTIONS::

  curl -sS -X OPTIONS -H "X-API-Key: $ZYRA_API_KEY" http://127.0.0.1:8000/mcp | jq .

JSON-RPC examples
~~~~~~~~~~~~~~~~~

Status:

.. code-block:: bash

  curl -sS -H 'Content-Type: application/json' -H "X-API-Key: $ZYRA_API_KEY" \
    -d '{"jsonrpc":"2.0","method":"statusReport","id":1}' \
    http://127.0.0.1:8000/mcp | jq .

List tools:

.. code-block:: bash

  curl -sS -H 'Content-Type: application/json' -H "X-API-Key: $ZYRA_API_KEY" \
    -d '{"jsonrpc":"2.0","method":"listTools","id":2}' \
    http://127.0.0.1:8000/mcp | jq .

Call a tool (sync):

.. code-block:: bash

  curl -sS -H 'Content-Type: application/json' -H "X-API-Key: $ZYRA_API_KEY" \
    -d '{"jsonrpc":"2.0","method":"callTool","params":{"stage":"visualize","command":"heatmap","args":{"input":"samples/demo.npy","output":"/tmp/heatmap.png"},"mode":"sync"},"id":3}' \
    http://127.0.0.1:8000/mcp | jq .

Observe progress (async):

.. code-block:: bash

  # After submitting an async callTool and capturing the job_id
  curl -N -H "X-API-Key: $ZYRA_API_KEY" \
    "http://127.0.0.1:8000/mcp/progress/$JOB_ID?interval_ms=200"

IDE integration notes
~~~~~~~~~~~~~~~~~~~~~

- Claude Desktop / Cursor / VS Code MCP clients typically probe ``GET /mcp``. Ensure Zyra is running and accessible (default port 8000).
- If an API key is set, configure the client to send ``X-API-Key: <value>`` with requests.
- The MCP discovery response uses names like ``process.decode-grib2`` and includes JSON Schema parameters for each tool.

See also
~~~~~~~~

- Example client script: ``scripts/mcp_client_example.py``
- MCP spec: https://modelcontextprotocol.io/docs
