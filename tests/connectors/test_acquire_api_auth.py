# SPDX-License-Identifier: Apache-2.0
import os
import types

import pytest

from zyra.connectors.ingest import _cmd_api  # type: ignore


def _ns(**kw):
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
        auth=None,
        credential=[],
        credential_file=None,
    )
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


def test_auth_helper_bearer_env(monkeypatch):
    seen = {"headers": None}

    def fake_request_with_retries(method, url, **kwargs):  # noqa: ARG001
        seen["headers"] = kwargs.get("headers")
        return 200, {"Content-Type": "application/json"}, b"{}"

    from zyra.connectors.backends import api as api_backend

    monkeypatch.setattr(api_backend, "request_with_retries", fake_request_with_retries)
    os.environ["MYTOKEN"] = "abc123"
    ns = _ns(auth="bearer:$MYTOKEN")
    rc = _cmd_api(ns)
    assert rc == 0
    assert seen["headers"]["Authorization"] == "Bearer abc123"


def test_auth_helper_basic_env(monkeypatch):
    seen = {"headers": None}

    def fake_request_with_retries(method, url, **kwargs):  # noqa: ARG001
        seen["headers"] = kwargs.get("headers")
        return 200, {"Content-Type": "application/json"}, b"{}"

    from zyra.connectors.backends import api as api_backend

    monkeypatch.setattr(api_backend, "request_with_retries", fake_request_with_retries)
    os.environ["BASIC"] = "user:pass"
    ns = _ns(auth="basic:$BASIC")
    rc = _cmd_api(ns)
    assert rc == 0
    assert seen["headers"]["Authorization"].startswith("Basic ")


def test_auth_helper_basic_env_missing_colon(monkeypatch):
    seen = {"headers": None}

    def fake_request_with_retries(method, url, **kwargs):  # noqa: ARG001
        seen["headers"] = kwargs.get("headers")
        return 200, {"Content-Type": "application/json"}, b"{}"

    from zyra.connectors.backends import api as api_backend

    monkeypatch.setattr(api_backend, "request_with_retries", fake_request_with_retries)
    os.environ["BASIC_USER"] = "onlyuser"
    with pytest.warns(UserWarning, match="did not include ':'"):
        ns = _ns(auth="basic:$BASIC_USER")
        rc = _cmd_api(ns)
    assert rc == 0
    assert seen["headers"]["Authorization"].startswith("Basic ")


def test_auth_helper_custom_header_env(monkeypatch):
    seen = {"headers": None}

    def fake_request_with_retries(method, url, **kwargs):  # noqa: ARG001
        seen["headers"] = kwargs.get("headers")
        return 200, {"Content-Type": "application/json"}, b"{}"

    from zyra.connectors.backends import api as api_backend

    monkeypatch.setattr(api_backend, "request_with_retries", fake_request_with_retries)
    os.environ["APIKEY"] = "xyz"
    ns = _ns(auth="header:X-Api-Key:$APIKEY")
    rc = _cmd_api(ns)
    assert rc == 0
    assert seen["headers"]["X-Api-Key"] == "xyz"
