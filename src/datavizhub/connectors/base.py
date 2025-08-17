"""Connector protocols and a minimal abstract base.

This module defines lightweight capability-oriented Protocols for connectors
and an optional minimal base ``Connector`` that offers a ``capabilities``
introspection helper and no-op context manager hooks. The goal is to keep the
primary connectors API functional and composable while enabling strong typing
and optional OO wrappers where persistent configuration/state is useful.
"""

from __future__ import annotations

from typing import Any, Iterable, Protocol, runtime_checkable


@runtime_checkable
class Fetchable(Protocol):
    def fetch_bytes(self, *args: Any, **kwargs: Any) -> bytes:
        ...


@runtime_checkable
class Uploadable(Protocol):
    def upload_bytes(self, data: bytes, *args: Any, **kwargs: Any) -> bool:
        ...


@runtime_checkable
class Listable(Protocol):
    def list_files(self, *args: Any, **kwargs: Any) -> Iterable[str] | None:
        ...


@runtime_checkable
class Existsable(Protocol):
    def exists(self, *args: Any, **kwargs: Any) -> bool:
        ...


@runtime_checkable
class Deletable(Protocol):
    def delete(self, *args: Any, **kwargs: Any) -> bool:
        ...


@runtime_checkable
class Statable(Protocol):
    def stat(self, *args: Any, **kwargs: Any) -> Any:
        ...


@runtime_checkable
class Indexable(Protocol):
    def get_idx_lines(self, *args: Any, **kwargs: Any) -> Iterable[str]:
        ...


@runtime_checkable
class ByteRanged(Protocol):
    def download_byteranges(self, *args: Any, **kwargs: Any) -> bytes:
        ...


class Connector:
    """Minimal abstract base for connector wrappers.

    Provides only introspection helpers and context manager convenience. It does
    not impose a lifecycle or specific methods on subclasses. Concrete wrapper
    classes are free to delegate to functional backends.
    """

    def __enter__(self):  # pragma: no cover - simple convenience
        return self

    def __exit__(self, exc_type, exc, tb):  # pragma: no cover - simple convenience
        return False

    @property
    def capabilities(self) -> set[str]:
        caps = getattr(type(self), "CAPABILITIES", None)
        return set(caps) if caps else set()
