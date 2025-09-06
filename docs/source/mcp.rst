MCP Adapter
===========

Overview
--------

Zyra exposes a minimal MCP-style JSON-RPC endpoint at ``POST /mcp`` to enable
tool discovery and invocation by LLM-friendly clients.

Methods
-------

- ``listTools``: returns the capabilities manifest (same data as ``/commands``)
- ``callTool``: runs a CLI tool via the existing ``/cli/run`` pathway
  - Params: ``{ stage: str, command: str, args?: object, mode?: 'sync'|'async' }``
  - Result (sync): ``{ status: 'ok'|'error', stdout?, stderr?, exit_code? }``
  - Result (async): ``{ status: 'accepted', job_id, poll, download, manifest }``
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

