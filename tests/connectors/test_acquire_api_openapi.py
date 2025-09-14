# SPDX-License-Identifier: Apache-2.0
import types

from zyra.connectors.ingest import _cmd_api  # type: ignore


def _ns(**kw):
    # Minimal Namespace-like object for _cmd_api
    ns = types.SimpleNamespace(
        verbose=False,
        quiet=False,
        trace=False,
        header=[],
        params=None,
        content_type=None,
        data=None,
        method="GET",
        paginate="none",
        timeout=30,
        max_retries=0,
        retry_backoff=0.1,
        allow_non_2xx=False,
        preset=None,
        stream=False,
        head_first=False,
        accept=None,
        expect_content_type=None,
        output="-",
        resume=False,
        newline_json=False,
        url="https://api.example/v1/items",
        detect_filename=False,
        openapi_help=False,
        openapi_validate=False,
        openapi_strict=False,
    )
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


def _spec_required_q():
    return {
        "openapi": "3.0.0",
        "paths": {
            "/v1/items": {
                "get": {
                    "parameters": [
                        {
                            "in": "query",
                            "name": "q",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                }
            }
        },
    }


def _spec_enum_and_type():
    return {
        "openapi": "3.0.0",
        "paths": {
            "/v1/items": {
                "get": {
                    "parameters": [
                        {
                            "in": "query",
                            "name": "mode",
                            "required": False,
                            "schema": {"type": "string", "enum": ["a", "b"]},
                        },
                        {
                            "in": "query",
                            "name": "limit",
                            "required": False,
                            "schema": {"type": "integer"},
                        },
                    ],
                }
            }
        },
    }


def test_openapi_help_prints(monkeypatch, capsys):
    from zyra.connectors.openapi import validate as _ov

    monkeypatch.setattr(_ov, "load_openapi", lambda base: _spec_required_q())
    ns = _ns(openapi_help=True)
    rc = _cmd_api(ns)
    assert rc == 0
    out = capsys.readouterr().out
    assert "OpenAPI operation: GET /v1/items" in out
    assert "Required: query:q" in out


def test_openapi_validate_strict_errors(monkeypatch):
    from zyra.connectors.openapi import validate as _ov

    monkeypatch.setattr(_ov, "load_openapi", lambda base: _spec_required_q())
    ns = _ns(openapi_validate=True, openapi_strict=True)
    try:
        _cmd_api(ns)
    except SystemExit as e:  # noqa: PT012
        assert int(getattr(e, "code", 0) or 0) == 2
    else:  # pragma: no cover
        assert False, "Expected strict validation to exit non-zero"


def test_openapi_validate_ok(monkeypatch, capsys):
    from zyra.connectors.openapi import validate as _ov

    monkeypatch.setattr(_ov, "load_openapi", lambda base: _spec_required_q())
    ns = _ns(openapi_validate=True)
    ns.params = "q=wind"
    rc = _cmd_api(ns)
    assert rc == 0
    out = capsys.readouterr().out
    assert "OpenAPI validation: OK" in out


def test_openapi_validate_enum_violation_strict(monkeypatch):
    from zyra.connectors.openapi import validate as _ov

    monkeypatch.setattr(_ov, "load_openapi", lambda base: _spec_enum_and_type())
    ns = _ns(openapi_validate=True, openapi_strict=True)
    ns.params = "mode=c"
    try:
        _cmd_api(ns)
    except SystemExit as e:  # noqa: PT012
        assert int(getattr(e, "code", 0) or 0) == 2
    else:  # pragma: no cover
        assert False


def test_openapi_validate_type_violation_strict(monkeypatch):
    from zyra.connectors.openapi import validate as _ov

    monkeypatch.setattr(_ov, "load_openapi", lambda base: _spec_enum_and_type())
    ns = _ns(openapi_validate=True, openapi_strict=True)
    ns.params = "limit=abc"
    try:
        _cmd_api(ns)
    except SystemExit as e:  # noqa: PT012
        assert int(getattr(e, "code", 0) or 0) == 2
    else:  # pragma: no cover
        assert False
