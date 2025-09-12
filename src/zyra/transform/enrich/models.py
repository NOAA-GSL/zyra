# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass, field

from zyra.connectors.discovery import DatasetMetadata


@dataclass
class DatasetVariable:
    name: str
    standard_name: str | None = None
    long_name: str | None = None
    units: str | None = None
    dims: list[str] | None = None
    shape: list[int] | None = None


@dataclass
class TimeInfo:
    start: str | None = None
    end: str | None = None
    cadence: str | None = None


@dataclass
class SpatialInfo:
    bbox: list[float] | None = None
    crs: str | None = None


@dataclass
class SizeInfo:
    approx_bytes: int | None = None
    n_features: int | None = None
    n_frames: int | None = None


@dataclass
class ProvenanceEntry:
    source: str
    method: str
    ts: str
    confidence: float | None = None


@dataclass
class DatasetEnrichment:
    variables: list[DatasetVariable] = field(default_factory=list)
    time: TimeInfo | None = None
    spatial: SpatialInfo | None = None
    size: SizeInfo | None = None
    format_detail: str | None = None
    license: str | None = None
    updated_at: str | None = None
    provenance: list[ProvenanceEntry] = field(default_factory=list)


@dataclass
class DatasetMetadataExtended(DatasetMetadata):
    enrichment: DatasetEnrichment | None = None
