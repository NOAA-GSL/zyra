MCP Adapter
===========

Overview
--------

Zyra exposes a minimal MCP-style JSON-RPC endpoint at ``POST /mcp`` to enable
tool discovery and invocation by LLM-friendly clients.

Methods
-------

- ``listTools``: returns an enriched capabilities view
  - ``result.manifest``: JSON from ``GET /commands`` (includes ``domain``, ``args_schema``, and ``example_args``)
  - ``result.tools``: flattened array of tools with fields: ``name``, ``domain``, ``tool``, ``args_schema``, ``example_args``, ``options``, ``positionals``, ``description``
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
