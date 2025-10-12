# SPDX-License-Identifier: Apache-2.0
"""OpenAPI-aided help and request validation utilities.

Lightweight helpers to fetch an OpenAPI spec, locate an operation matching a
given URL+method, and perform simple request validation:

- Required query/header parameters
- Required requestBody presence
- requestBody content-type checks (when provided)

This module intentionally avoids heavy dependencies. JSON Schema validation is
out of scope for the MVP.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlparse

from zyra.connectors.backends import http as _http
from zyra.connectors.discovery.api_search import _load_openapi as _disc_load


@dataclass
class OperationRef:
    path: str
    method: str
    operation: dict[str, Any]
    path_item: dict[str, Any]


def load_openapi(base_url: str) -> dict[str, Any] | None:
    """Load an OpenAPI spec from a base URL using discovery helpers."""
    return _disc_load(base_url)


def load_openapi_url(url: str) -> dict[str, Any] | None:
    """Load an OpenAPI spec from an explicit URL (json or yaml).

    Attempts JSON first; if that fails, falls back to text + YAML parse when
    PyYAML is available. Returns None on failure.
    """
    # Try JSON
    try:
        spec = _http.fetch_json(url)
        if isinstance(spec, dict) and spec.get("paths"):
            return spec  # type: ignore[return-value]
    except Exception:
        pass
    # Try YAML when available
    try:
        text = _http.fetch_text(url)
    except Exception:
        return None
    try:
        import yaml  # type: ignore

        spec = yaml.safe_load(text)  # type: ignore[no-redef]
        if isinstance(spec, dict) and spec.get("paths"):
            return spec  # type: ignore[return-value]
    except Exception:
        return None
    return None


def _iter_params(
    op: dict[str, Any], path_item: dict[str, Any]
) -> Iterable[dict[str, Any]]:
    for p in path_item.get("parameters") or []:
        if isinstance(p, dict):
            yield p
    for p in op.get("parameters") or []:
        if isinstance(p, dict):
            yield p


def find_operation(spec: dict[str, Any], url: str, method: str) -> OperationRef | None:
    """Find the most specific operation matching the URL path and method.

    Matching algorithm:
    - Prefer segment-aware matches where the request path and spec path have the
      same number of segments. Each literal segment match scores higher than a
      template segment (e.g., ``{id}``). The candidate with the highest score
      wins; ties are broken by longer path length.
    - Fallback: when no segment-aware candidates exist, allow a simple suffix
      match and pick the longest suffix that exposes the given method.
    """
    try:
        req_path = urlparse(url).path or "/"
    except Exception:
        req_path = url
    paths = spec.get("paths") if isinstance(spec, dict) else None
    if not isinstance(paths, dict):
        return None

    def _match_score(spec_path: str) -> int | None:
        # Exact suffix still considered, but prefer segment-aware matches
        try:
            req_segs = [s for s in req_path.split("/") if s]
            sp_segs = [s for s in spec_path.split("/") if s]
            if len(req_segs) != len(sp_segs):
                return None
            score = 0
            for a, b in zip(req_segs, sp_segs):
                if b.startswith("{") and b.endswith("}"):
                    # template segment; wildcard match, lower score
                    score += 1
                elif a == b:
                    # literal match; higher score
                    score += 2
                else:
                    return None
            return score
        except Exception:
            return None

    candidates: list[tuple[str, dict[str, Any], int]] = []
    for p, item in paths.items():
        if not isinstance(p, str) or not isinstance(item, dict):
            continue
        # Confirm method exists first
        has_method = any(
            str(k).lower() == method.lower() and isinstance(v, dict)
            for k, v in item.items()
        )
        if not has_method:
            continue
        sc = _match_score(p)
        if sc is not None:
            candidates.append((p, item, sc))
    if not candidates:
        # Fallback: allow suffix match when path lengths differ; pick longest suffix
        for p, item in paths.items():
            if not isinstance(p, str) or not isinstance(item, dict):
                continue
            if req_path.endswith(p) and any(
                str(k).lower() == method.lower() and isinstance(v, dict)
                for k, v in item.items()
            ):
                candidates.append((p, item, len(p)))
        if not candidates:
            return None
    # pick the candidate with best score, tie-breaker by longer path
    candidates.sort(key=lambda t: (t[2], len(t[0])), reverse=True)
    path, item, _ = candidates[0]
    # pick op for method
    op = None
    for k, v in item.items():
        if str(k).lower() == method.lower() and isinstance(v, dict):
            op = v
            break
    if not isinstance(op, dict):
        return None
    return OperationRef(path=path, method=method, operation=op, path_item=item)


def _mask_sensitive(where: str, name: str, value: str | None) -> str | None:
    if value is None:
        return None
    if where == "header":
        lname = name.lower()
        sensitive_terms = {
            "authorization",
            "proxy-authorization",
            "token",
            "secret",
            "key",
        }
        if lname in sensitive_terms:
            return "<redacted>"
    return value


def validate_request(
    *,
    spec: dict[str, Any],
    url: str,
    method: str,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    data: bytes | str | dict | list | None = None,
) -> list[dict[str, str]]:
    """Validate a request against OpenAPI operation requirements.

    Returns a list of issues, each as {loc, name, message}.
    """
    issues: list[dict[str, str]] = []
    opref = find_operation(spec, url, method)
    if not opref:
        return issues
    hdrs = {str(k): str(v) for k, v in (headers or {}).items()}
    q = {str(k): str(v) for k, v in (params or {}).items()}
    # Parameters (query/header): check required presence and simple schema when provided
    for p in _iter_params(opref.operation, opref.path_item):
        try:
            where = str(p.get("in") or "")
            name = str(p.get("name") or "")
            required = bool(p.get("required") or False)
            if not name:
                continue
            # Missing required checks
            if required:
                if where == "query" and name not in q:
                    issues.append(
                        {
                            "loc": "query",
                            "name": name,
                            "message": "Missing required query parameter",
                        }
                    )
                if where == "header" and name not in hdrs:
                    issues.append(
                        {
                            "loc": "header",
                            "name": name,
                            "message": "Missing required header",
                        }
                    )
            # Simple enum/type checks when values are present (even if optional)
            schema = p.get("schema") if isinstance(p.get("schema"), dict) else None
            has_val = (where == "query" and name in q) or (
                where == "header" and name in hdrs
            )
            if schema and has_val:
                val = q.get(name) if where == "query" else hdrs.get(name)
                if isinstance(schema.get("enum"), list) and val is not None:
                    allowed = [str(x) for x in schema["enum"]]
                    if str(val) not in allowed:
                        display_val = _mask_sensitive(where, name, str(val))
                        issues.append(
                            {
                                "loc": where,
                                "name": name,
                                "message": f"Value '{display_val}' not in enum {allowed}",
                            }
                        )
                typ = schema.get("type")
                if typ and val is not None:

                    def _is_type(s: str, t: str) -> bool:
                        try:
                            if t == "string":
                                return True
                            if t == "integer":
                                int(s)
                                return True
                            if t == "number":
                                float(s)
                                return True
                            if t == "boolean":
                                return s.lower() in {"true", "false", "1", "0"}
                        except Exception:
                            return False
                        # Unrecognized types should not be treated as valid
                        return False

                    if not _is_type(str(val), str(typ)):
                        issues.append(
                            {
                                "loc": where,
                                "name": name,
                                "message": f"Invalid type for '{name}': expected {typ}",
                            }
                        )
        except Exception:
            continue
    # requestBody checks
    body = opref.operation.get("requestBody")
    if isinstance(body, dict):
        required = bool(body.get("required") or False)
        has_data = data is not None
        if required and not has_data:
            issues.append(
                {
                    "loc": "body",
                    "name": "requestBody",
                    "message": "Missing required request body",
                }
            )
        # Content types
        try:
            content = body.get("content") or {}
            if content and has_data:
                ct = hdrs.get("Content-Type") or hdrs.get("content-type")
                if not ct:
                    issues.append(
                        {
                            "loc": "header",
                            "name": "Content-Type",
                            "message": "Content-Type header required for body",
                        }
                    )
                else:
                    keys = [str(k).lower() for k in content]
                    main = ct.split(";", 1)[0].strip().lower()
                    if main not in keys:
                        issues.append(
                            {
                                "loc": "header",
                                "name": "Content-Type",
                                "message": f"Unsupported content type: {ct}",
                            }
                        )
                # Optional JSON Schema validation when jsonschema is installed
                if has_data and isinstance(data, (dict, list)):
                    try:
                        import jsonschema  # type: ignore

                        media = None
                        for k in content:
                            if str(k).lower() == "application/json":
                                media = content[k]
                                break
                        if isinstance(media, dict) and isinstance(
                            media.get("schema"), dict
                        ):
                            try:
                                jsonschema.validate(
                                    instance=data, schema=media["schema"]
                                )  # type: ignore[arg-type]
                            except (
                                Exception
                            ) as _ve:  # pragma: no cover - environment dependent
                                # Avoid exposing internal exception details to clients
                                issues.append(
                                    {
                                        "loc": "body",
                                        "name": "requestBody",
                                        "message": "JSON schema validation error",
                                    }
                                )
                    except Exception:
                        # jsonschema not available; skip
                        pass
        except Exception:
            pass
    return issues


def help_text(*, spec: dict[str, Any], url: str, method: str) -> str:
    """Return a one-page hint for the resolved operation.

    Includes resolved path, params (required/optional), and requestBody content types.
    """
    opref = find_operation(spec, url, method)
    if not opref:
        return "OpenAPI: no matching operation found."
    lines: list[str] = []
    lines.append(f"OpenAPI operation: {method.upper()} {opref.path}")
    req: list[str] = []
    opt: list[str] = []
    for p in _iter_params(opref.operation, opref.path_item):
        try:
            where = str(p.get("in") or "")
            if where not in {"query", "header"}:
                continue
            name = str(p.get("name") or "")
            if not name:
                continue
            target = req if bool(p.get("required")) else opt
            target.append(f"{where}:{name}")
        except Exception:
            continue
    if req:
        lines.append("Required: " + ", ".join(sorted(req)))
    if opt:
        lines.append("Optional: " + ", ".join(sorted(opt)))
    body = opref.operation.get("requestBody")
    if isinstance(body, dict):
        content = body.get("content") or {}
        if content:
            types = ", ".join(sorted(content.keys()))
            lines.append(f"requestBody content-types: {types}")
        if body.get("required"):
            lines.append("requestBody: required")
    # Response content-types (best-effort): prefer 200, else first 2xx
    try:
        responses = opref.operation.get("responses") or {}
        chosen = None
        if "200" in responses:
            chosen = responses.get("200")
        else:
            for k, v in responses.items():
                if str(k).startswith("2"):
                    chosen = v
                    break
        if isinstance(chosen, dict):
            ct = chosen.get("content") or {}
            if ct:
                types = ", ".join(sorted(ct.keys()))
                lines.append(f"response content-types: {types}")
    except Exception:
        pass
    return "\n".join(lines)
