# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import concurrent.futures as _fut
import contextlib
import re
from dataclasses import asdict
from typing import Any, Iterable, Protocol

from zyra.connectors.discovery import DatasetMetadata
from zyra.connectors.discovery.ogc import _findtext
from zyra.utils import simple_cache as cache

from .models import (
    DatasetEnrichment,
    DatasetMetadataExtended,
    DatasetVariable,
    ProvenanceEntry,
    SizeInfo,
    SpatialInfo,
    TimeInfo,
)

# Expanded, centralized units detection patterns for shallow extraction.
# Split into "word" units (matched with word boundaries) and symbol/compound units.
_UNIT_WORDS = [
    r"K",
    r"Kelvin",
    r"degC",
    r"Celsius",
    r"Pa",
    r"hPa",
    r"bar",
    r"mb",
    r"m",
    r"meter(?:s)?",
    r"cm",
    r"centimeter(?:s)?",
    r"mm",
    r"km",
    r"kilometer(?:s)?",
]
_UNIT_SYMBOLS = [
    r"%",
    r"°C",
    r"m/s",
    r"m s-1",
    r"kg/m\^?3",
    r"kg m-3",
    r"kg/m²",
    r"kg/m2",
    r"kg m-2",
]
_UNITS_PATTERN = (
    r"(?:\\b(?:"
    + r"|".join(_UNIT_WORDS)
    + r")\\b|(?:"
    + r"|".join(_UNIT_SYMBOLS)
    + r"))"
)
UNITS_REGEX = re.compile(_UNITS_PATTERN, re.I)


class BaseEnricher(Protocol):
    name: str

    def supports(self, item: DatasetMetadata) -> bool: ...

    def enrich(
        self, item: DatasetMetadata, level: str, ctx: dict[str, Any]
    ) -> DatasetEnrichment | None: ...


def _now_iso() -> str:
    import datetime as _dt

    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


class ShallowEnricher:
    name = "shallow"

    def supports(self, item: DatasetMetadata) -> bool:
        return True

    def enrich(
        self, item: DatasetMetadata, level: str, ctx: dict[str, Any]
    ) -> DatasetEnrichment:
        vars: list[DatasetVariable] = []
        text = f"{item.name}\n{item.description or ''}"
        unit_rx = UNITS_REGEX

        # Candidate variable names from free text
        cand = set()
        for m in re.finditer(r"\b([A-Za-z][A-Za-z0-9_]{2,})\b", text):
            s = m.group(1)
            if s.lower() in {"the", "and", "for", "with", "data", "dataset"}:
                continue
            cand.add(s)

        def _guess_unit_for_var(var: str) -> str | None:
            # Look for a unit mention near the variable in text (local window)
            try:
                for m in re.finditer(re.escape(var), text, flags=re.IGNORECASE):
                    i0, i1 = m.span()
                    window = text[max(0, i0 - 40) : min(len(text), i1 + 40)]
                    um = unit_rx.search(window)
                    if um:
                        return um.group(0)
            except Exception:
                pass
            # Fall back to None when no per-variable unit context is found
            return None

        for v in sorted(list(cand))[:3]:
            vars.append(
                DatasetVariable(
                    name=v,
                    long_name=None,
                    standard_name=None,
                    units=_guess_unit_for_var(v),
                    dims=None,
                    shape=None,
                )
            )
        tinfo = TimeInfo()
        y = re.findall(r"\b(19\d{2}|20\d{2})\b", text)
        if y:
            y_sorted = sorted(int(yy) for yy in y)
            tinfo.start = f"{y_sorted[0]}-01-01T00:00:00Z"
            tinfo.end = f"{y_sorted[-1]}-12-31T23:59:59Z"
        prov = [
            ProvenanceEntry(
                source=(item.source or "unknown"),
                method="shallow",
                ts=_now_iso(),
                confidence=0.2,
            )
        ]
        enr = DatasetEnrichment(
            variables=vars,
            time=tinfo if (tinfo.start or tinfo.end) else None,
            spatial=SpatialInfo(),
            size=SizeInfo(),
            format_detail=None,
            license=None,
            updated_at=_now_iso(),
            provenance=prov,
        )
        return enr


class WMSCapabilitiesEnricher:
    name = "wms-capabilities"

    def supports(self, item: DatasetMetadata) -> bool:
        if (item.source or "").lower() == "ogc-wms":
            return True
        if (item.format or "").upper() == "WMS":
            return True
        u = (item.uri or "").lower()
        return "service=wms" in u or u.endswith(".xml") or u.endswith("capabilities")

    def enrich(
        self, item: DatasetMetadata, level: str, ctx: dict[str, Any]
    ) -> DatasetEnrichment | None:
        offline = bool(ctx.get("offline")) if ctx else False
        https_only = bool(ctx.get("https_only")) if ctx else False
        allow = list(ctx.get("allow_hosts") or []) if ctx else []
        deny = list(ctx.get("deny_hosts") or []) if ctx else []
        req_timeout = float(ctx.get("timeout") or 3.0)
        import xml.etree.ElementTree as ET

        def _load_xml(uri: str) -> ET.Element | None:
            from pathlib import Path

            try:
                if uri.startswith("file:"):
                    path = Path(uri[5:])
                    with path.open(encoding="utf-8") as f:
                        return ET.fromstring(f.read())
                p = Path(uri)
                if p.exists():
                    with p.open(encoding="utf-8") as f:
                        return ET.fromstring(f.read())
            except Exception:
                return None
            if offline:
                return None
            url = uri
            if "service=wms" not in url.lower():
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}service=WMS&request=GetCapabilities"
            # Basic SSRF hardening: allowlist/denylist hosts and optional HTTPS-only
            try:
                if not _host_ok(url, https_only, allow, deny):
                    return None
            except Exception:
                return None
            try:
                import requests  # type: ignore

                # Use configured/request timeout instead of a hard-coded value
                r = requests.get(url, timeout=max(1.0, float(req_timeout or 3.0)))
                r.raise_for_status()
                return ET.fromstring(r.text)
            except Exception:
                return None

        try:
            root = _load_xml(item.uri)
            if root is None:
                return None
            target_layer = None
            for node in root.iter():
                if isinstance(node.tag, str) and node.tag.endswith("Layer"):
                    title = _findtext(node, "Title") or ""
                    name = _findtext(node, "Name") or ""
                    if item.name and (item.name == title or item.name == name):
                        target_layer = node
                        break
            variables: list[DatasetVariable] = []
            if target_layer is not None:
                title = _findtext(target_layer, "Title") or ""
                name = _findtext(target_layer, "Name") or ""
                vname = title or name or item.name
                if vname:
                    variables.append(DatasetVariable(name=vname))
                bbox = None
                for child in list(target_layer):
                    tag = getattr(child, "tag", "")
                    if isinstance(tag, str) and (
                        tag.endswith("EX_GeographicBoundingBox")
                        or tag.endswith("LatLonBoundingBox")
                    ):
                        try:
                            if tag.endswith("EX_GeographicBoundingBox"):
                                west = float(
                                    _findtext(child, "westBoundLongitude") or "nan"
                                )
                                east = float(
                                    _findtext(child, "eastBoundLongitude") or "nan"
                                )
                                south = float(
                                    _findtext(child, "southBoundLatitude") or "nan"
                                )
                                north = float(
                                    _findtext(child, "northBoundLatitude") or "nan"
                                )
                                bbox = [west, south, east, north]
                            else:
                                minx = float(child.get("minx"))
                                miny = float(child.get("miny"))
                                maxx = float(child.get("maxx"))
                                maxy = float(child.get("maxy"))
                                bbox = [minx, miny, maxx, maxy]
                        except Exception:
                            bbox = None
                        break
                spt = SpatialInfo(bbox=bbox, crs="EPSG:4326" if bbox else None)
            else:
                spt = SpatialInfo()
            prov = [
                ProvenanceEntry(
                    source=(item.source or "wms"),
                    method="capabilities",
                    ts=_now_iso(),
                    confidence=0.4,
                )
            ]
            return DatasetEnrichment(
                variables=variables,
                time=None,
                spatial=spt,
                size=None,
                format_detail="WMS",
                license=None,
                updated_at=_now_iso(),
                provenance=prov,
            )
        except Exception:
            return None


class RecordsCapabilitiesEnricher:
    name = "records-capabilities"

    def supports(self, item: DatasetMetadata) -> bool:
        if (item.source or "").lower() == "ogc-records":
            return True
        if (item.format or "").upper() in {"OGC", "RECORDS"}:
            return True
        u = (item.uri or "").lower()
        return u.endswith("/items") or "/collections/" in u

    def enrich(
        self, item: DatasetMetadata, level: str, ctx: dict[str, Any]
    ) -> DatasetEnrichment | None:
        offline = bool(ctx.get("offline")) if ctx else False
        import json
        from pathlib import Path

        def _load_json(uri: str) -> dict[str, Any] | None:
            try:
                if uri.startswith("file:"):
                    p = Path(uri[5:])
                    return json.loads(p.read_text(encoding="utf-8"))
                p = Path(uri)
                if p.exists():
                    return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return None
            if offline:
                return None
            try:
                import requests  # type: ignore

                r = requests.get(uri, timeout=5)
                r.raise_for_status()
                return r.json()
            except Exception:
                return None

        data = _load_json(item.uri)
        if not data:
            return None
        time_info = None
        try:
            props = data.get("properties") or {}
            if not props:
                props = data
            start = props.get("start_datetime") or props.get("datetime:begin")
            end = props.get("end_datetime") or props.get("datetime:end")
            dt = props.get("datetime")
            if dt and not start and not end:
                start = end = dt
            if start or end:
                time_info = TimeInfo(start=start, end=end)
        except Exception:
            time_info = None
        bbox = None
        try:
            bbox = data.get("bbox")
            if not bbox and isinstance(data.get("extent"), dict):
                sp = data["extent"].get("spatial") or {}
                bbox = (sp.get("bbox") or [None])[0]
        except Exception:
            bbox = None
        variables: list[DatasetVariable] = []
        try:
            kws = []
            if isinstance(data.get("keywords"), list):
                kws = [str(k) for k in data.get("keywords")]
            bands = None
            if isinstance(data.get("summaries"), dict):
                bands = data["summaries"].get("eo:bands") or data["summaries"].get(
                    "raster:bands"
                )
            if isinstance(bands, list):
                for b in bands[:5]:
                    nm = b.get("name") or b.get("common_name")
                    if nm:
                        variables.append(DatasetVariable(name=str(nm)))
            for k in kws[:5]:
                variables.append(DatasetVariable(name=k))
        except Exception:
            pass
        prov = [
            ProvenanceEntry(
                source=(item.source or "records"),
                method="capabilities",
                ts=_now_iso(),
                confidence=0.5,
            )
        ]
        return DatasetEnrichment(
            variables=variables,
            time=time_info,
            spatial=SpatialInfo(bbox=bbox, crs="EPSG:4326" if bbox else None),
            size=None,
            format_detail="OGC Records",
            license=None,
            updated_at=_now_iso(),
            provenance=prov,
        )


class STACCapabilitiesEnricher:
    name = "stac-capabilities"

    def supports(self, item: DatasetMetadata) -> bool:
        u = (item.uri or "").lower()
        return (
            "stac" in u
            or u.endswith("/items")
            or u.endswith("/collections")
            or "/collections/" in u
        )

    def enrich(
        self, item: DatasetMetadata, level: str, ctx: dict[str, Any]
    ) -> DatasetEnrichment | None:
        offline = bool(ctx.get("offline")) if ctx else False
        import json
        from pathlib import Path

        def _load_json(uri: str) -> dict[str, Any] | None:
            try:
                if uri.startswith("file:"):
                    p = Path(uri[5:])
                    return json.loads(p.read_text(encoding="utf-8"))
                p = Path(uri)
                if p.exists():
                    return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return None
            if offline:
                return None
            try:
                import requests  # type: ignore

                r = requests.get(uri, timeout=5)
                r.raise_for_status()
                return r.json()
            except Exception:
                return None

        data = _load_json(item.uri)
        if not isinstance(data, dict):
            return None
        if not (
            data.get("stac_version")
            or data.get("type") in {"Feature", "FeatureCollection"}
        ):
            return None
        time_info = None
        try:
            if data.get("type") == "Feature":
                props = data.get("properties") or {}
                start = props.get("start_datetime")
                end = props.get("end_datetime")
                dt = props.get("datetime")
                if dt and not start and not end:
                    start = end = dt
                if start or end:
                    time_info = TimeInfo(start=start, end=end)
            else:
                ext = (data.get("extent") or {}).get("temporal") or {}
                intervals = ext.get("interval") or []
                if intervals and isinstance(intervals[0], list):
                    start, end = intervals[0][0], intervals[0][1]
                    time_info = TimeInfo(start=start, end=end)
        except Exception:
            time_info = None
        bbox = None
        try:
            bbox = data.get("bbox")
            if not bbox and isinstance(data.get("extent"), dict):
                sp = data["extent"].get("spatial") or {}
                arr = sp.get("bbox") or []
                if arr and isinstance(arr[0], list):
                    bbox = arr[0]
        except Exception:
            bbox = None
        crs = None
        try:
            props = data.get("properties") or {}
            proj_epsg = props.get("proj:epsg") or data.get("proj:epsg")
            if isinstance(proj_epsg, int) or (
                isinstance(proj_epsg, str) and proj_epsg.isdigit()
            ):
                crs = f"EPSG:{proj_epsg}"
            elif isinstance(props.get("proj:code"), str):
                crs = props.get("proj:code")
        except Exception:
            pass
        variables: list[DatasetVariable] = []
        try:
            sums = data.get("summaries") or {}
            bands = sums.get("eo:bands") or sums.get("raster:bands")
            if isinstance(bands, list):
                for b in bands[:8]:
                    nm = b.get("name") or b.get("common_name")
                    units = b.get("unit") or b.get("units")
                    if nm:
                        variables.append(DatasetVariable(name=str(nm), units=units))
        except Exception:
            pass
        prov = [
            ProvenanceEntry(
                source=(item.source or "stac"),
                method="capabilities",
                ts=_now_iso(),
                confidence=0.6,
            )
        ]
        return DatasetEnrichment(
            variables=variables,
            time=time_info,
            spatial=SpatialInfo(bbox=bbox, crs=crs or ("EPSG:4326" if bbox else None)),
            size=None,
            format_detail="STAC",
            license=None,
            updated_at=_now_iso(),
            provenance=prov,
        )


def _is_local_uri(uri: str) -> bool:
    try:
        from pathlib import Path

        if uri.startswith("file:"):
            return True
        p = Path(uri)
        return p.exists()
    except Exception:
        return False


def _local_path(uri: str) -> str | None:
    from pathlib import Path

    if uri.startswith("file:"):
        return uri[5:]
    p = Path(uri)
    return str(p) if p.exists() else None


def _content_length(uri: str, *, offline: bool, timeout: float) -> int | None:
    try:
        lp = _local_path(uri)
        if lp is not None:
            from pathlib import Path

            return int(Path(lp).stat().st_size)
    except Exception:
        pass
    if offline:
        return None
    try:
        import requests  # type: ignore

        r = requests.head(
            uri, timeout=max(1.0, float(timeout or 3.0)), allow_redirects=False
        )
        r.raise_for_status()
        cl = r.headers.get("Content-Length") or r.headers.get("content-length")
        return int(cl) if cl and str(cl).isdigit() else None
    except Exception:
        return None


def _host_ok(uri: str, https_only: bool, allow: list[str], deny: list[str]) -> bool:
    try:
        from urllib.parse import urlparse

        u = urlparse(uri)
        if u.scheme in {"", None}:
            return True
        if https_only and u.scheme != "https":
            return False
        host = (u.hostname or "").lower()
        if any(host.endswith(d.strip().lower()) for d in deny if d):
            return False
        if allow:
            return any(host.endswith(a.strip().lower()) for a in allow if a)
        return True
    except Exception:
        return False


class NetCDFProbeEnricher:
    name = "netcdf-probe"

    def supports(self, item: DatasetMetadata) -> bool:
        u = (item.uri or "").lower()
        return u.endswith(".nc") or (item.format or "").lower() in {
            "netcdf",
            "cdf",
            "opendap",
        }

    def enrich(
        self, item: DatasetMetadata, level: str, ctx: dict[str, Any]
    ) -> DatasetEnrichment | None:
        offline = bool(ctx.get("offline")) if ctx else False
        https_only = bool(ctx.get("https_only")) if ctx else False
        allow = list(ctx.get("allow_hosts") or [])
        deny = list(ctx.get("deny_hosts") or [])
        max_bytes = int(ctx.get("max_probe_bytes") or 50_000_000)
        timeout = float(ctx.get("timeout") or 3.0)
        uri = item.uri or ""
        if not uri:
            return None
        if not _is_local_uri(uri) and not _host_ok(uri, https_only, allow, deny):
            return None
        try:
            size = _content_length(uri, offline=offline, timeout=timeout)
            if size is not None and size > max_bytes:
                return None
        except Exception:
            size = None
        # If probing a remote resource with unknown size and a max cap is set, skip for safety
        try:
            if (not _is_local_uri(uri)) and (max_bytes is not None) and (size is None):
                return None
        except Exception:
            pass
        try:
            import xarray as xr  # type: ignore

            lp = _local_path(uri) or uri
            ds = xr.open_dataset(lp)
            variables: list[DatasetVariable] = []
            for name, da in list(ds.data_vars.items())[:32]:
                units = (
                    str(da.attrs.get("units"))
                    if isinstance(da.attrs.get("units"), (str, bytes))
                    else None
                )
                long_name = da.attrs.get("long_name") or None
                std_name = da.attrs.get("standard_name") or None
                dims = list(map(str, da.dims)) if getattr(da, "dims", None) else None
                shape = list(map(int, da.shape)) if getattr(da, "shape", None) else None
                variables.append(
                    DatasetVariable(
                        name=str(name),
                        standard_name=str(std_name)
                        if isinstance(std_name, str)
                        else None,
                        long_name=str(long_name)
                        if isinstance(long_name, str)
                        else None,
                        units=units,
                        dims=dims,
                        shape=shape,
                    )
                )
            time_info = None
            try:
                if "time" in ds.coords:
                    tc = ds.coords["time"]
                    if tc.size > 0:
                        t0 = tc.values[0]
                        t1 = tc.values[-1]

                        def _to_iso(v):
                            try:
                                import pandas as pd  # type: ignore

                                if hasattr(pd, "Timestamp"):
                                    return (
                                        pd.to_datetime(v).tz_localize(None).isoformat()
                                        + "Z"
                                    )
                            except Exception:
                                pass
                            return None

                        start = _to_iso(t0)
                        end = _to_iso(t1)
                        if start or end:
                            time_info = TimeInfo(start=start, end=end)
            except Exception:
                time_info = None
            prov = [
                ProvenanceEntry(
                    source=(item.source or "netcdf"),
                    method="probe",
                    ts=_now_iso(),
                    confidence=0.9,
                )
            ]
            return DatasetEnrichment(
                variables=variables,
                time=time_info,
                spatial=None,
                size=SizeInfo(approx_bytes=size),
                format_detail="NetCDF",
                license=None,
                updated_at=_now_iso(),
                provenance=prov,
            )
        except Exception:
            return None


class GeoTIFFProbeEnricher:
    name = "geotiff-probe"

    def supports(self, item: DatasetMetadata) -> bool:
        u = (item.uri or "").lower()
        return (
            u.endswith(".tif")
            or u.endswith(".tiff")
            or (item.format or "").lower() in {"geotiff", "tiff"}
        )

    def enrich(
        self, item: DatasetMetadata, level: str, ctx: dict[str, Any]
    ) -> DatasetEnrichment | None:
        offline = bool(ctx.get("offline")) if ctx else False
        https_only = bool(ctx.get("https_only")) if ctx else False
        allow = list(ctx.get("allow_hosts") or [])
        deny = list(ctx.get("deny_hosts") or [])
        max_bytes = int(ctx.get("max_probe_bytes") or 100_000_000)
        timeout = float(ctx.get("timeout") or 3.0)
        uri = item.uri or ""
        if not uri:
            return None
        if not _is_local_uri(uri) and not _host_ok(uri, https_only, allow, deny):
            return None
        try:
            size = _content_length(uri, offline=offline, timeout=timeout)
            if size is not None and size > max_bytes:
                return None
        except Exception:
            size = None
        # If probing a remote resource with unknown size and a max cap is set, skip for safety
        try:
            if (not _is_local_uri(uri)) and (max_bytes is not None) and (size is None):
                return None
        except Exception:
            pass
        try:
            import rasterio  # type: ignore

            lp = _local_path(uri) or uri
            with rasterio.open(lp) as src:  # type: ignore
                bounds = src.bounds
                crs = str(src.crs) if src.crs else None
                bbox = [bounds.left, bounds.bottom, bounds.right, bounds.top]
                variables: list[DatasetVariable] = []
                for i in range(1, (getattr(src, "count", 0) or 0) + 1):
                    variables.append(
                        DatasetVariable(
                            name=f"band_{i}",
                            dims=["y", "x"],
                            shape=[src.height, src.width],
                        )
                    )
                prov = [
                    ProvenanceEntry(
                        source=(item.source or "geotiff"),
                        method="probe",
                        ts=_now_iso(),
                        confidence=0.85,
                    )
                ]
                return DatasetEnrichment(
                    variables=variables,
                    time=None,
                    spatial=SpatialInfo(bbox=bbox, crs=crs),
                    size=SizeInfo(
                        approx_bytes=size, n_frames=getattr(src, "count", None)
                    ),
                    format_detail="GeoTIFF",
                    license=None,
                    updated_at=_now_iso(),
                    provenance=prov,
                )
        except Exception:
            return None


class ProfileDefaultsEnricher:
    name = "profile-defaults"

    def supports(self, item: DatasetMetadata) -> bool:
        return True

    def enrich(
        self, item: DatasetMetadata, level: str, ctx: dict[str, Any]
    ) -> DatasetEnrichment | None:
        pd = (ctx or {}).get("profile_defaults") or {}
        if not isinstance(pd, dict):
            return None
        # Optional source scoping: apply defaults only to specific sources when provided
        srcs = (ctx or {}).get("defaults_sources") or []
        if isinstance(srcs, list) and srcs:
            try:
                if (item.source or "") not in srcs:
                    return None
            except Exception:
                return None
        spatial = pd.get("spatial") or {}
        bbox = spatial.get("bbox") if isinstance(spatial, dict) else None
        crs = spatial.get("crs") if isinstance(spatial, dict) else None
        tdef = pd.get("time") or {}
        t_start = tdef.get("start") if isinstance(tdef, dict) else None
        t_end = tdef.get("end") if isinstance(tdef, dict) else None
        t_cadence = tdef.get("cadence") if isinstance(tdef, dict) else None
        lic = pd.get("license") if isinstance(pd.get("license"), str) else None
        fmt = (
            pd.get("format_detail")
            if isinstance(pd.get("format_detail"), str)
            else None
        )
        if not any([bbox, crs, t_start, t_end, t_cadence, lic, fmt]):
            return None
        prov = [
            ProvenanceEntry(
                source=(item.source or "profile"),
                method="profile-defaults",
                ts=_now_iso(),
                confidence=0.3,
            )
        ]
        return DatasetEnrichment(
            variables=[],
            time=(
                TimeInfo(start=t_start, end=t_end, cadence=t_cadence)
                if any([t_start, t_end, t_cadence])
                else None
            ),
            spatial=(SpatialInfo(bbox=bbox, crs=crs) if (bbox or crs) else None),
            size=None,
            format_detail=fmt,
            license=lic,
            updated_at=_now_iso(),
            provenance=prov,
        )


class SOSLicenseEnricher:
    name = "sos-license"

    def supports(self, item: DatasetMetadata) -> bool:
        return (item.source or "").lower() == "sos-catalog"

    # Use the shared slug logic from LocalCatalogBackend to avoid duplication

    def _load_catalog(self) -> list[dict[str, Any]] | None:
        try:
            from importlib import resources as importlib_resources

            pkg = "zyra.assets.metadata"
            path = importlib_resources.files(pkg).joinpath("sos_dataset_metadata.json")
            with importlib_resources.as_file(path) as p:
                import json as _json

                return _json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def enrich(
        self, item: DatasetMetadata, level: str, ctx: dict[str, Any]
    ) -> DatasetEnrichment | None:
        pol = (ctx or {}).get("profile_license_policy") or {}
        if not isinstance(pol, dict):
            return None
        data = self._load_catalog() or []
        if not data:
            return None
        try:
            entry = None
            for d in data:
                url = d.get("url") or ""
                if not isinstance(url, str):
                    continue
                from zyra.connectors.discovery import LocalCatalogBackend

                if LocalCatalogBackend._slug_from_url(url) == (item.id or ""):
                    entry = d
                    break
            if not entry:
                return None
            dev = entry.get("dataset_developer") or {}
            vis = entry.get("vis_developer") or {}
            dev_name = str(dev.get("name") or "")
            vis_name = str(vis.get("name") or "")
            dev_aff = str(dev.get("affiliation_url") or "")
            vis_aff = str(vis.get("affiliation_url") or "")
            noaa_domains = [str(s).lower() for s in pol.get("noaa_domains") or []]
            noaa_keywords = [str(s).lower() for s in pol.get("noaa_keywords") or []]
            text = " ".join([dev_name, vis_name, dev_aff, vis_aff]).lower()
            is_noaa = any(k in text for k in noaa_keywords) or any(
                (aff and any(aff.lower().endswith(d) for d in noaa_domains))
                for aff in [dev_aff, vis_aff]
            )
            if is_noaa:
                lic = pol.get("noaa_license") or "Public domain (U.S. Government work)"
            else:
                lic = pol.get("non_noaa_note") or (
                    "Ownership per contributing organization; see dataset page."
                )
            prov = [
                ProvenanceEntry(
                    source="sos-catalog",
                    method="license-policy",
                    ts=_now_iso(),
                    confidence=0.7,
                )
            ]
            return DatasetEnrichment(
                variables=[],
                time=None,
                spatial=None,
                size=None,
                format_detail=None,
                license=str(lic) if lic else None,
                updated_at=_now_iso(),
                provenance=prov,
            )
        except Exception:
            return None


_REGISTRY: dict[str, list[BaseEnricher]] = {
    "shallow": [ShallowEnricher(), ProfileDefaultsEnricher(), SOSLicenseEnricher()],
    "capabilities": [
        ProfileDefaultsEnricher(),
        STACCapabilitiesEnricher(),
        RecordsCapabilitiesEnricher(),
        WMSCapabilitiesEnricher(),
    ],
    "probe": [
        ProfileDefaultsEnricher(),
        SOSLicenseEnricher(),
        NetCDFProbeEnricher(),
        GeoTIFFProbeEnricher(),
    ],
}


def register(level: str, enricher: BaseEnricher) -> None:
    _REGISTRY.setdefault(level, []).append(enricher)


def _cache_key(item: DatasetMetadata, level: str, plugin: str) -> str:
    uri = item.uri or ""
    src = item.source or ""
    fmt = item.format or ""
    return f"{uri}|{src}|{fmt}|{level}|{plugin}"


def enrich_items(
    items: Iterable[DatasetMetadata],
    *,
    level: str,
    timeout: float = 3.0,
    workers: int = 4,
    cache_ttl: int = 86400,
    offline: bool | None = None,
    https_only: bool | None = None,
    allow_hosts: list[str] | None = None,
    deny_hosts: list[str] | None = None,
    max_probe_bytes: int | None = None,
    profile_defaults: dict[str, Any] | None = None,
    profile_license_policy: dict[str, Any] | None = None,
    defaults_sources: list[str] | None = None,
    max_total_timeout: float | None = None,
) -> list[DatasetMetadataExtended]:
    enrs = _REGISTRY.get(level, [])
    if not enrs:
        return [DatasetMetadataExtended(**asdict(i)) for i in items]

    items_list = list(items)
    out: list[DatasetMetadataExtended] = [
        DatasetMetadataExtended(**asdict(i)) for i in items_list
    ]

    def _do_one(ix: int) -> None:
        item = items_list[ix]
        for e in enrs:
            if not e.supports(item):
                continue
            key = _cache_key(item, level, e.name)
            cached = cache.get(key)
            if cached is not None:
                try:
                    d = cached
                    enr = DatasetEnrichment(
                        variables=[
                            DatasetVariable(**v) for v in d.get("variables", [])
                        ],
                        time=(TimeInfo(**d["time"]) if d.get("time") else None),
                        spatial=(
                            SpatialInfo(**d["spatial"]) if d.get("spatial") else None
                        ),
                        size=(SizeInfo(**d["size"]) if d.get("size") else None),
                        format_detail=d.get("format_detail"),
                        license=d.get("license"),
                        updated_at=d.get("updated_at"),
                        provenance=[
                            ProvenanceEntry(**p) for p in d.get("provenance", [])
                        ],
                    )
                except Exception:
                    enr = None
                if enr:
                    cur = out[ix].enrichment or DatasetEnrichment()
                    out[ix].enrichment = _merge_enrichment(cur, enr)
                    continue
            try:
                enr = e.enrich(
                    item,
                    level,
                    {
                        "offline": offline,
                        "https_only": bool(https_only or False),
                        "allow_hosts": list(allow_hosts or []),
                        "deny_hosts": list(deny_hosts or []),
                        "max_probe_bytes": max_probe_bytes,
                        "timeout": timeout,
                        "profile_defaults": dict(profile_defaults or {}),
                        "profile_license_policy": dict(profile_license_policy or {}),
                        "defaults_sources": list(defaults_sources or []),
                    },
                )
            except Exception:
                enr = None
            if enr:
                cur = out[ix].enrichment or DatasetEnrichment()
                out[ix].enrichment = _merge_enrichment(cur, enr)
                with contextlib.suppress(Exception):
                    cache.set(key, asdict(enr), cache_ttl)

    with _fut.ThreadPoolExecutor(max_workers=max(1, int(workers))) as ex:
        futs = [ex.submit(_do_one, i) for i in range(len(items_list))]
        # Base total timeout scales with item count; apply optional ceiling to avoid excessive waits
        base_total = max(1.0, float(timeout or 0.0)) * max(1, len(items_list)) * 1.5
        total = (
            min(base_total, float(max_total_timeout))
            if max_total_timeout is not None
            else base_total
        )
        _fut.wait(futs, timeout=total)

    return out


def _merge_enrichment(a: DatasetEnrichment, b: DatasetEnrichment) -> DatasetEnrichment:
    out = DatasetEnrichment(
        variables=(list(a.variables) + list(b.variables)),
        time=b.time or a.time,
        spatial=b.spatial or a.spatial,
        size=b.size or a.size,
        format_detail=b.format_detail or a.format_detail,
        license=b.license or a.license,
        updated_at=b.updated_at or a.updated_at,
        provenance=(list(a.provenance) + list(b.provenance)),
    )
    return out
