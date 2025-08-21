"""Connectors package: ingest and egress submodules and shared backends.

Primary usage favors functional backends under ``zyra.connectors.backends``.
For flows that benefit from a light OO wrapper (e.g., persisting bucket/host
config), thin connector classes are available in ``zyra.connectors.clients``.
"""

from .base import (
    ByteRanged,
    Connector,
    Deletable,
    Existsable,
    Fetchable,
    Indexable,
    Listable,
    Statable,
    Uploadable,
)
from .clients import FTPConnector, S3Connector

__all__ = [
    # Base typing and optional abstract
    "Connector",
    "Fetchable",
    "Uploadable",
    "Listable",
    "Existsable",
    "Deletable",
    "Statable",
    "Indexable",
    "ByteRanged",
    # Light OO wrappers
    "FTPConnector",
    "S3Connector",
]
