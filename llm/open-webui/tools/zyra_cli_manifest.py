from __future__ import annotations

import difflib
import json
import os
from typing import Any

import requests

# Public GitHub raw (fallback for public access)
DEFAULT_GITHUB_CAPS_URL = "https://raw.githubusercontent.com/NOAA-GSL/zyra/main/src/zyra/wizard/zyra_capabilities.json"

# Default timeouts (seconds)
DEFAULT_API_TIMEOUT = 1.5
DEFAULT_NET_TIMEOUT = 2.0

# Tool-level Valves (shown in Open WebUI Tools UI)
VALVES = [
    {
        "name": "zyra_api_base",
        "label": "Zyra API Base",
        "type": "string",
        "value": "http://localhost:8000",
        "help": "Base URL for Zyra API; the tool calls /commands here first.",
    },
    {
        "name": "zyra_api_key",
        "label": "API Key",
        "type": "string",
        "value": "",
        "secret": True,
        "help": "Optional API key if your Zyra API enforces it.",
        "required": False,
        "optional": True,
    },
    {
        "name": "api_key_header",
        "label": "API Key Header",
        "type": "string",
        "value": "X-API-Key",
    },
    {
        "name": "api_timeout",
        "label": "API Timeout (seconds)",
        "type": "number",
        "value": 6.0,
    },
    {
        "name": "api_connect_timeout",
        "label": "API Connect Timeout (s)",
        "type": "number",
        "value": 3.0,
        "required": False,
        "optional": True,
    },
    {
        "name": "api_read_timeout",
        "label": "API Read Timeout (s)",
        "type": "number",
        "value": 6.0,
        "required": False,
        "optional": True,
    },
    {
        "name": "net_timeout",
        "label": "Net Timeout (seconds)",
        "type": "number",
        "value": 6.0,
    },
    {
        "name": "net_connect_timeout",
        "label": "Net Connect Timeout (s)",
        "type": "number",
        "value": 3.0,
        "required": False,
        "optional": True,
    },
    {
        "name": "net_read_timeout",
        "label": "Net Read Timeout (s)",
        "type": "number",
        "value": 6.0,
        "required": False,
        "optional": True,
    },
    {
        "name": "caps_url",
        "label": "Capabilities URL (override)",
        "type": "string",
        "value": "",
        "help": "Optional direct URL to zyra_capabilities.json; used if API is unreachable.",
        "required": False,
        "optional": True,
    },
    {
        "name": "offline",
        "label": "Offline Mode",
        "type": "boolean",
        "value": False,
    },
]

try:  # pragma: no cover - only needed in Open WebUI runtime
    from pydantic import BaseModel, Field  # type: ignore
except Exception:  # pragma: no cover
    BaseModel = object  # type: ignore[misc,assignment]

    def Field(*_args: object, **_kwargs: object):  # type: ignore[func-returns-value]
        return _kwargs.get("default")


class Pipeline:
    class Valves(BaseModel):  # type: ignore[misc]
        target_user_roles: list[str] = ["user"]
        zyra_api_base: str | None = os.getenv("ZYRA_API_BASE", "http://localhost:8000")
        zyra_api_key: str | None = os.getenv("ZYRA_API_KEY")
        api_key_header: str = os.getenv("API_KEY_HEADER", "X-API-Key") or "X-API-Key"
        api_timeout: float = float(
            os.getenv("ZYRA_API_TIMEOUT", str(DEFAULT_API_TIMEOUT))
            or DEFAULT_API_TIMEOUT
        )
        net_timeout: float = float(
            os.getenv("ZYRA_NET_TIMEOUT", str(DEFAULT_NET_TIMEOUT))
            or DEFAULT_NET_TIMEOUT
        )
        caps_url: str | None = os.getenv("ZYRA_CAPABILITIES_URL")
        offline: bool = (os.getenv("ZYRA_OFFLINE", "0") or "0").strip().lower() in {
            "1",
            "true",
            "yes",
        }

    def __init__(self) -> None:
        self.valves = self.Valves()  # type: ignore[call-arg]


def _valve_value(valves: Any, name: str, default: Any) -> Any:
    if valves is None:
        return default
    if isinstance(valves, dict):
        v = valves.get(name, default)
        if isinstance(v, dict) and "value" in v:
            return v.get("value", default)
        return v
    try:
        return getattr(valves, name, default)
    except Exception:
        return default


def _api_headers(valves: Any = None) -> dict[str, str]:
    """Optional API auth header for Zyra API calls.

    Reads `ZYRA_API_KEY` and `API_KEY_HEADER` (default `X-API-Key`).
    """
    api_key = _valve_value(valves, "zyra_api_key", os.getenv("ZYRA_API_KEY")) or ""
    if not str(api_key).strip():
        return {}
    header_name = _valve_value(
        valves, "api_key_header", os.getenv("API_KEY_HEADER", "X-API-Key")
    )
    return {header_name: api_key}


def _timeouts(valves: Any, prefix: str) -> tuple[float, float]:
    """Return (connect_timeout, read_timeout) for a given prefix ('api' or 'net')."""

    def _vv(name: str, default: float) -> float:
        try:
            return float(_valve_value(valves, name, default))
        except Exception:
            return default

    if prefix == "api":
        base = _vv("api_timeout", DEFAULT_API_TIMEOUT)
        cto = _vv("api_connect_timeout", base)
        rto = _vv("api_read_timeout", base)
        return (cto, rto)
    base = _vv("net_timeout", DEFAULT_NET_TIMEOUT)
    cto = _vv("net_connect_timeout", base)
    rto = _vv("net_read_timeout", base)
    return (cto, rto)


def _load_manifest_via_api(
    format: str = "json", *, valves: Any = None, **params: Any
) -> dict[str, Any] | None:
    """Fetch manifest via the running Zyra API if available.

    Controlled by `ZYRA_API_BASE` (e.g., http://localhost:8000).
    Returns the parsed JSON or None on failure.
    """
    base = _valve_value(
        valves, "zyra_api_base", os.getenv("ZYRA_API_BASE", "http://localhost:8000")
    )
    if base is None or not str(base).strip():
        return None
    url = f"{base.rstrip('/')}/commands"
    q = {"format": format, **{k: v for k, v in params.items() if v is not None}}
    try:
        cto, rto = _timeouts(valves, "api")
        r = requests.get(
            url, params=q, headers=_api_headers(valves), timeout=(cto, rto)
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _load_manifest(valves: Any = None) -> dict[str, Any] | None:
    """Resolve the Zyra CLI capabilities manifest.

    Resolution order:
    1) Zyra API `/commands` (via `zyra_api_base` valve; default http://localhost:8000)
    2) Direct URL override (`caps_url` valve or `ZYRA_CAPABILITIES_URL`)
    3) GitHub raw fallback (skipped if `offline` valve/env is true)
    """

    # 1) Zyra API (default base http://localhost:8000)
    api = _load_manifest_via_api("json", valves=valves)
    if api and isinstance(api, dict) and isinstance(api.get("commands"), dict):
        return api["commands"]

    # 2) Optional URL override
    url_env = _valve_value(valves, "caps_url", os.getenv("ZYRA_CAPABILITIES_URL"))
    if url_env and str(url_env).strip():
        try:
            cto, rto = _timeouts(valves, "net")
            r = requests.get(url_env, timeout=(cto, rto))
            r.raise_for_status()
            obj = r.json()
            if isinstance(obj, dict) and isinstance(obj.get("commands"), dict):
                return obj["commands"]
            return obj
        except Exception:
            pass

    # 3) Fallback to default GitHub URL (skip if offline is requested)
    if str(
        _valve_value(valves, "offline", os.getenv("ZYRA_OFFLINE", "0"))
    ).strip().lower() in {"1", "true", "yes"}:
        return None
    try:
        cto, rto = _timeouts(valves, "net")
        r = requests.get(DEFAULT_GITHUB_CAPS_URL, timeout=(cto, rto))
        r.raise_for_status()
        obj = r.json()
        if isinstance(obj, dict) and isinstance(obj.get("commands"), dict):
            return obj["commands"]
        return obj
    except Exception:
        return None


class Tools:
    pipeline: Pipeline | None = None

    # Open WebUI may inject a dict-like `valves`, but we also declare a schema
    # here so the Tools UI can render configurable fields.
    class Valves(BaseModel):  # type: ignore[misc]
        zyra_api_base: str = Field(
            default="http://localhost:8000",
            description="Base URL for Zyra API; the tool calls /commands here first.",
        )
        # Use empty string defaults so UI does not mark these as required
        zyra_api_key: str = Field(
            default="",
            description="Optional API key if your Zyra API enforces it.",
        )
        api_key_header: str = Field(
            default="X-API-Key",
            description="Header name to carry the API key.",
        )
        api_timeout: float = Field(
            default=6.0,
            description="Timeout (seconds) for Zyra API requests.",
        )
        api_connect_timeout: float = Field(
            default=3.0,
            description="Connect timeout (seconds) for Zyra API requests.",
        )
        api_read_timeout: float = Field(
            default=6.0,
            description="Read timeout (seconds) for Zyra API requests.",
        )
        net_timeout: float = Field(
            default=6.0,
            description="Timeout (seconds) for non-API HTTP fetches.",
        )
        net_connect_timeout: float = Field(
            default=3.0,
            description="Connect timeout (seconds) for non-API HTTP fetches.",
        )
        net_read_timeout: float = Field(
            default=6.0,
            description="Read timeout (seconds) for non-API HTTP fetches.",
        )
        caps_url: str = Field(
            default="",
            description="Optional direct URL to zyra_capabilities.json; used if API is unreachable.",
        )
        offline: bool = Field(
            default=False,
            description="If true, skip all network fetches and return only from overrides.",
        )

    def __init__(self, valves: dict | None = None) -> None:
        # Prefer valves injected by Open WebUI; otherwise seed with defaults.
        if valves is not None:
            self.valves = valves
        else:
            try:
                self.valves = self.Valves()  # type: ignore[call-arg]
            except Exception:
                self.valves = None
        # Some Open WebUI builds expect this flag for source/context display
        self.citation = True

    def zyra_cli_manifest(
        self,
        command_name: str | None = None,
        format: str = "json",
        details: str | None = None,
    ) -> str:
        """
        Fetch the Zyra CLI command manifest and return structured info.

        Returns structured JSON with:
          - commands[].name — CLI command name (e.g., "acquire http")
          - commands[].description — human-readable explanation
          - commands[].options[] — flags with descriptions and types

        Arguments:
          - command_name (string, optional): Return details only for a specific command.
                                            Fuzzy matching supported.
          - format (string, optional): "json" (raw JSON, default), "list" (just command names),
                                       or "summary" (human-readable descriptions).
          - details (string, optional):
              - "options": returns only option flags for the given command
              - "example": returns a runnable CLI example for the given command
        """

        valves = getattr(getattr(self, "pipeline", None), "valves", None)

        # Prefer server-side filtering/formatting via Zyra API
        if command_name:
            api_resp = _load_manifest_via_api(
                format=format, valves=valves, command_name=command_name, details=details
            )
            if isinstance(api_resp, dict):
                try:
                    payload = json.dumps(api_resp)
                except Exception:
                    payload = str(api_resp)
                return (
                    f"Show Zyra CLI command '{command_name}' from API with this data:\n\n"
                    + payload
                )

        manifest = _load_manifest(valves)
        if manifest is None:
            err = {
                "error": "Failed to load Zyra capabilities manifest",
                "tried": [
                    "zyra_api_base valve -> /commands (json; default http://localhost:8000)",
                    "caps_url valve or ZYRA_CAPABILITIES_URL (if set)",
                    DEFAULT_GITHUB_CAPS_URL,
                ],
            }
            try:
                payload = json.dumps(err)
            except Exception:
                payload = str(err)
            return "Show Zyra CLI manifest error with this data:\n\n" + payload

        # Build list/summary/json locally from the resolved manifest to avoid extra API calls

        # Normalize manifest to a dict of command name -> info
        if not isinstance(manifest, dict):
            manifest = {}
        commands = list(manifest.keys())

        # No specific command requested: format-level views
        if not command_name:
            if format == "list":
                data = {"commands": commands}
            elif format == "summary":
                items = []
                for name in commands:
                    info = manifest.get(name, {})
                    desc = ""
                    if isinstance(info, dict):
                        desc = str(info.get("description", ""))
                    items.append({"name": name, "description": desc})
                data = {"commands": items}
            else:
                data = {"commands": manifest}
            try:
                payload = json.dumps(data)
            except Exception:
                payload = str(data)
            return f"Show Zyra CLI commands ({format}) with this data:\n\n" + payload

        # Specific command requested: fuzzy match & detail handling
        match = difflib.get_close_matches(command_name, commands, n=1, cutoff=0.5)
        if not match:
            data = {
                "error": f"No matching command found for '{command_name}'",
                "requested": command_name,
                "available": commands,
            }
            try:
                payload = json.dumps(data)
            except Exception:
                payload = str(data)
            return (
                f"Show Zyra CLI command lookup error for '{command_name}' with this data:\n\n"
                + payload
            )

        cmd = match[0]
        cmd_info = manifest[cmd]

        if details == "options":
            data = {"command": cmd, "options": cmd_info.get("options", {})}
            try:
                payload = json.dumps(data)
            except Exception:
                payload = str(data)
            return (
                f"Show Zyra CLI command '{cmd}' options with this data:\n\n" + payload
            )

        if details == "example":
            example = f"zyra {cmd}"
            options = list(cmd_info.get("options", {}).keys())
            if options:
                example += f" {options[0]} <value>"
            data = {"command": cmd, "example": example}
            try:
                payload = json.dumps(data)
            except Exception:
                payload = str(data)
            return (
                f"Show Zyra CLI command '{cmd}' example with this data:\n\n" + payload
            )
        data = {"command": cmd, "info": cmd_info}
        try:
            payload = json.dumps(data)
        except Exception:
            payload = str(data)
        return f"Show Zyra CLI command '{cmd}' info with this data:\n\n" + payload

    # Simple execution sanity method (kept consistent with GitHub tool)
    def health(self) -> str:
        return "ready"
