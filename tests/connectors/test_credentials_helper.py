# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass

import pytest

from zyra.connectors.credentials import (
    CredentialResolutionError,
    ResolvedCredentials,
    mask_secret,
    resolve_credentials,
)


@dataclass
class _StubManager:
    values: dict[str, str]

    def get_credential(self, key: str) -> str:
        if key not in self.values:
            raise KeyError(key)
        return self.values[key]


def test_resolve_credentials_literal_only():
    result = resolve_credentials(["user=alice", "password=secret"])
    assert isinstance(result, ResolvedCredentials)
    assert result.values == {"user": "alice", "password": "secret"}
    assert result.masked["password"].endswith("secret"[-4:])


def test_resolve_credentials_env_lookup(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "topsecret")
    result = resolve_credentials(["token=$API_TOKEN"])
    assert result.values["token"] == "topsecret"
    assert result.masked["token"].endswith("ret")


def test_resolve_credentials_manager_lookup():
    manager = _StubManager({"SERVICE_TOKEN": "abc123XYZ"})
    result = resolve_credentials(["token=@SERVICE_TOKEN"], manager=manager)  # type: ignore[arg-type]
    assert result.values["token"] == "abc123XYZ"
    assert result.masked["token"].endswith("3XYZ")


@pytest.mark.parametrize(
    "entry",
    ["missing_equals", "=value", "field=", "field=@UNKNOWN", "field=$MISSING"],
)
def test_resolve_credentials_invalid(entry, monkeypatch):
    if entry.endswith("$MISSING"):
        monkeypatch.delenv("MISSING", raising=False)
    with pytest.raises(CredentialResolutionError):
        resolve_credentials([entry], manager=_StubManager({}))  # type: ignore[arg-type]


def test_mask_secret_variants():
    assert mask_secret("abcdef") == "**cdef"
    assert mask_secret("ab") == "**"
    assert mask_secret("", visible=2) == "<empty>"
    assert mask_secret(None) == "<redacted>"
