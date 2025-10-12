# SPDX-License-Identifier: Apache-2.0
"""Credential resolution helpers for Zyra connectors.

This module centralizes the parsing and resolution of credential arguments
supplied via the CLI or programmatic interfaces. It supports the unified
`--credential field=value` UX described in Issue #75 by handling:

* ``@NAME`` lookup through :class:`~zyra.utils.credential_manager.CredentialManager`
* ``$ENV`` expansion via process environment variables
* literal values (default)

The helpers return both the resolved secret material (for functional use) and a
masked representation that can be safely logged for debugging.
"""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass
from typing import Iterable, Mapping

from zyra.utils.credential_manager import CredentialManager

_MASK_PLACEHOLDER = "<redacted>"


@dataclass(frozen=True)
class ResolvedCredentials:
    """Container for resolved credential slots.

    Parameters
    ----------
    values:
        Mapping of credential slot name to the resolved secret string.
    masked:
        Mapping with the same keys as ``values`` but each value masked for
        logging (e.g., ``****abcd``). The masked form should be used for any
        telemetry or debug output.
    """

    values: dict[str, str]
    masked: dict[str, str]

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return the resolved credential value for ``key``."""

        return self.values.get(key, default)

    def masked_get(self, key: str, default: str | None = None) -> str | None:
        """Return the masked credential representation for ``key``."""

        return self.masked.get(key, default)


class CredentialResolutionError(RuntimeError):
    """Raised when credential parsing or resolution fails."""


def resolve_basic_auth_credentials(
    credentials: Mapping[str, str],
) -> tuple[str | None, str | None]:
    """Return the best-effort username/password pair from credential aliases."""

    username = (
        credentials.get("basic_user")
        or credentials.get("user")
        or credentials.get("username")
    )
    password = credentials.get("basic_password") or credentials.get("password")
    return username, password


def mask_secret(value: str | None, *, visible: int = 4) -> str:
    """Return a masked representation of ``value`` suitable for logs."""

    if value is None:
        return _MASK_PLACEHOLDER
    if not value:
        return "<empty>"
    if len(value) <= visible:
        return "*" * len(value)
    return f"{'*' * (len(value) - visible)}{value[-visible:]}"


def resolve_credentials(
    entries: Iterable[str] | None,
    *,
    credential_file: str | None = None,
    namespace: str | None = None,
    manager: CredentialManager | None = None,
) -> ResolvedCredentials:
    """Resolve credential entries into usable values.

    Parameters
    ----------
    entries:
        Iterable of ``field=value`` strings supplied by the user. ``None`` or an
        empty iterable results in an empty mapping.
    credential_file:
        Optional path to a dotenv file. When provided, a
        :class:`CredentialManager` is instantiated with this file when resolving
        ``@NAME`` references.
    namespace:
        Optional namespace prefix applied when the helper instantiates a
        :class:`CredentialManager` internally.
    manager:
        Optional pre-configured :class:`CredentialManager`. When supplied the
        helper will use it instead of creating a new instance.

    Returns
    -------
    ResolvedCredentials
        Container with resolved and masked credential mappings.

    Raises
    ------
    CredentialResolutionError
        If an entry is malformed (missing ``=``) or a referenced credential is
        unavailable.
    """

    if not entries:
        return ResolvedCredentials(values={}, masked={})

    resolved: dict[str, str] = {}
    masked: dict[str, str] = {}

    cm: CredentialManager | None = manager

    def _ensure_manager() -> CredentialManager:
        nonlocal cm
        if cm is not None:
            return cm
        cm = CredentialManager(credential_file, namespace=namespace)
        cm.read_credentials()
        return cm

    for raw in entries:
        if "=" not in raw:
            raise CredentialResolutionError(
                f"Credential entry '{raw}' must use the form field=value"
            )
        field, value = raw.split("=", 1)
        field = field.strip()
        token = value.strip()
        if not field:
            raise CredentialResolutionError(
                f"Credential entry '{raw}' has an empty field name"
            )
        if token.startswith("@"):
            key = token[1:]
            try:
                cm_inst = _ensure_manager()
            except (
                ImportError,
                RuntimeError,
            ) as exc:  # pragma: no cover - env dependent
                raise CredentialResolutionError(str(exc)) from exc
            try:
                secret = cm_inst.get_credential(key)
            except KeyError as exc:
                raise CredentialResolutionError(
                    f"Credential '{key}' not found in credential manager"
                ) from exc
        elif token.startswith("$"):
            env_key = token[1:]
            secret = os.environ.get(env_key)
            if secret is None:
                raise CredentialResolutionError(
                    f"Environment variable '{env_key}' not set for credential '{field}'"
                )
        else:
            secret = token
        if secret == "":
            raise CredentialResolutionError(
                f"Credential '{field}' resolved to an empty value"
            )
        resolved[field] = secret
        masked[field] = mask_secret(secret)
    return ResolvedCredentials(values=resolved, masked=masked)


__all__ = [
    "CredentialResolutionError",
    "ResolvedCredentials",
    "mask_secret",
    "resolve_credentials",
    "resolve_basic_auth_credentials",
    "parse_header_strings",
    "apply_auth_header",
    "apply_http_credentials",
]


def parse_header_strings(values: Iterable[str] | None) -> dict[str, str]:
    """Parse repeated ``Name: Value`` header strings into a dict."""

    headers: dict[str, str] = {}
    for item in values or []:
        if ":" not in item:
            continue
        name, value = item.split(":", 1)
        headers[name.strip()] = value.lstrip()
    return headers


def apply_auth_header(headers: dict[str, str], auth_value: str | None) -> None:
    """Apply convenience ``--auth`` helpers onto ``headers`` in-place."""

    if not auth_value:
        return
    try:
        scheme, val = auth_value.split(":", 1)
    except ValueError:
        return
    scheme_l = scheme.strip().lower()
    value = val.strip()
    if value.startswith("$"):
        value = os.environ.get(value[1:], "")
    if scheme_l == "bearer" and value:
        headers.setdefault("Authorization", f"Bearer {value}")
    elif scheme_l == "basic" and value:
        import base64 as _b64

        if ":" not in value:
            warnings.warn(
                "Basic auth value did not include ':'; using entire value as username",
                UserWarning,
                stacklevel=2,
            )
            user = value
            pwd = ""
        else:
            user, pwd = value.split(":", 1)
        token = _b64.b64encode(f"{user}:{pwd}".encode()).decode("ascii")
        headers.setdefault("Authorization", f"Basic {token}")
    elif scheme_l == "header" and value and ":" in value:
        name, v = value.split(":", 1)
        name = name.strip()
        v = v.strip()
        if v.startswith("$"):
            v = os.environ.get(v[1:], "")
        if name and v and name not in headers:
            headers[name] = v


def apply_http_credentials(
    headers: dict[str, str], credentials: Mapping[str, str]
) -> None:
    """Map resolved credential slots onto HTTP headers in-place."""

    import base64 as _b64

    bearer = credentials.get("token") or credentials.get("bearer")
    basic_user, basic_pwd = resolve_basic_auth_credentials(credentials)
    if bearer and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {bearer}"
    if basic_user and basic_pwd and "Authorization" not in headers:
        token = _b64.b64encode(f"{basic_user}:{basic_pwd}".encode()).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    for key, value in credentials.items():
        lower = key.lower()
        if lower in {
            "token",
            "bearer",
            "user",
            "username",
            "password",
            "basic_user",
            "basic_password",
        }:
            continue
        header_name: str | None = None
        if lower.startswith("header."):
            header_name = key.removeprefix("header.")
        elif lower.startswith("header:"):
            header_name = key.removeprefix("header:")
        elif lower.startswith("header_"):
            header_name = key.removeprefix("header_")
        else:
            continue
        header_name = header_name.strip() if header_name is not None else ""
        if header_name and header_name not in headers:
            headers[header_name] = value
