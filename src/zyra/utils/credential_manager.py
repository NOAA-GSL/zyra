"""Credential storage and retrieval utilities.

This module provides `CredentialManager`, a small helper class to securely
load, access, and manage credentials from a `.env`-style file without leaking
them into the global process environment.

Examples
--------
Load and access values::

    from zyra.utils.credential_manager import CredentialManager

    cm = CredentialManager("./.env")
    cm.read_credentials(expected_keys=["API_KEY"])
    token = cm.get_credential("API_KEY")

Use as a context manager::

    with CredentialManager("./.env") as cm:
        cm.read_credentials()
        do_work(cm.get_credential("ACCESS_TOKEN"))
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

# Defer optional dependency import to method calls to avoid crashing
# modules that import CredentialManager when python-dotenv is unavailable.


class CredentialManager:
    """Manage app credentials from a dotenv file.

    Parameters
    ----------
    filename : str, optional
        Path to a dotenv file containing key=value pairs.
    namespace : str, optional
        Optional prefix to apply to all keys when stored/retrieved.

    Examples
    --------
    Namespaced keys::

        cm = CredentialManager(".env", namespace="MYAPP_")
        cm.read_credentials(expected_keys=["API_KEY"])  # expects MYAPP_API_KEY
    """

    def __init__(self, filename: str | None = None, namespace: str | None = None):
        self.filename = filename
        self.namespace = namespace or ""
        self.credentials: dict[str, str] = {}

    def __enter__(self):
        """Load credentials when entering a context manager block.

        Returns
        -------
        CredentialManager
            The manager instance.
        """
        if self.filename:
            self.read_credentials()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clear credentials on exit and propagate exceptions if any.

        Returns
        -------
        bool
            ``False`` to propagate exceptions.
        """
        self.clear_credentials()
        if exc_type is not None:
            logging.error(f"Exception occurred: {exc_val}")
        return False

    def _namespaced_key(self, key: str) -> str:
        """Return namespaced key when a namespace is configured."""
        return f"{self.namespace}{key}" if self.namespace else key

    def read_credentials(self, expected_keys: Iterable[str] | None = None) -> None:
        """Read credentials from the dotenv file into memory.

        Parameters
        ----------
        expected_keys : Iterable[str], optional
            Keys that must be present; raises if any are missing.

        Raises
        ------
        FileNotFoundError
            If the dotenv path cannot be resolved.
        KeyError
            If any expected keys are missing after reading.
        """
        try:
            from dotenv import dotenv_values, find_dotenv  # type: ignore
        except (
            ImportError,
            ModuleNotFoundError,
        ) as exc:  # pragma: no cover - optional dependency path
            raise ImportError(
                "python-dotenv is required to read credentials; install the 'dev' extra or add python-dotenv"
            ) from exc

        dotenv_path = Path(self.filename) if self.filename else Path(find_dotenv())
        if dotenv_path and dotenv_path.exists():
            env_vars = dotenv_values(dotenv_path)
            for key, value in env_vars.items():
                namespaced_key = self._namespaced_key(key)
                self.credentials[namespaced_key] = value  # type: ignore[assignment]
                logging.debug(f"Added credential key: {namespaced_key}")
            missing = set(expected_keys or []) - set(self.credentials.keys())
            if missing:
                raise KeyError(f"Missing expected keys: {', '.join(missing)}")
        else:
            raise FileNotFoundError(f"The file {self.filename} was not found.")

    @property
    def tracked_keys(self) -> set[str]:
        """Return the set of keys currently tracked in memory."""
        return set(self.credentials.keys())

    def list_credentials(self, expected_keys: Iterable[str] | None = None) -> list[str]:
        """List tracked credential keys, checking for expected ones when provided.

        Parameters
        ----------
        expected_keys : Iterable[str], optional
            Keys to verify are present.

        Returns
        -------
        list of str
            Keys currently stored in memory.

        Raises
        ------
        KeyError
            If any expected keys are missing.
        """
        if expected_keys is not None:
            missing_keys = set(expected_keys) - self.tracked_keys
            if missing_keys:
                raise KeyError(f"Missing expected keys: {', '.join(missing_keys)}")
        return list(self.credentials.keys())

    def get_credential(self, key: str) -> str:
        """Retrieve a credential value by key (with namespace applied).

        Parameters
        ----------
        key : str
            Base key name (namespace is applied automatically).

        Returns
        -------
        str
            Stored value for the namespaced key.

        Raises
        ------
        KeyError
            If the key is not present in memory.
        """
        namespaced_key = self._namespaced_key(key)
        if namespaced_key not in self.credentials:
            raise KeyError(
                f"Credential key '{namespaced_key}' not found in credentials."
            )
        return self.credentials[namespaced_key]

    def add_credential(self, key: str, value: str) -> None:
        """Add or update a credential value in memory.

        Parameters
        ----------
        key : str
            Base key name (namespace is applied automatically).
        value : str
            Credential value to store.
        """
        namespaced_key = self._namespaced_key(key)
        self.credentials[namespaced_key] = value
        logging.debug(f"Added/Updated credential key: {namespaced_key}")

    def delete_credential(self, key: str) -> None:
        """Delete a credential by key if present.

        Parameters
        ----------
        key : str
            Base key name (namespace is applied automatically).
        """
        namespaced_key = self._namespaced_key(key)
        if namespaced_key in self.credentials:
            del self.credentials[namespaced_key]

    def clear_credentials(self) -> None:
        """Remove all tracked credentials from memory."""
        self.credentials.clear()
