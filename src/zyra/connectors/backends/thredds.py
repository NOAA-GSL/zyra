# SPDX-License-Identifier: Apache-2.0
"""THREDDS Data Server (TDS) connector backend.

Functional helpers to enumerate datasets from THREDDS ``catalog.xml`` documents
and map them to ``fileServer`` download URLs, with optional recursion into
nested ``catalogRef`` entries.

Design goals mirror the other connector backends (``http``/``ftp``/``s3``):

- Network access is optional so tests stay hermetic. Callers may inject a
  ``fetcher`` callable (or a single ``catalog_xml`` string) instead of hitting
  the network; otherwise the HTTP backend is used.
- Functions are small and dependency-light. Parsing relies on the stdlib
  ``xml.etree.ElementTree`` and is namespace-agnostic (THREDDS InvCatalog and
  xlink namespaces are matched by local tag name).

A THREDDS catalog declares one or more ``<service>`` entries (we use the
``HTTPServer`` service to build download URLs), a tree of ``<dataset>``
elements (downloadable ones carry a ``urlPath`` attribute), and
``<catalogRef>`` links to nested catalogs.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

from zyra.connectors.backends import ftp as ftp_backend
from zyra.connectors.backends import http as http_backend
from zyra.utils.date_manager import DateManager

# Re-export the shared sync option surface so callers can configure THREDDS
# sync behavior with the same vocabulary used by the FTP backend.
SyncOptions = ftp_backend.SyncOptions

logger = logging.getLogger(__name__)

#: Maximum recursion depth applied when ``recursive=True`` and the caller does
#: not specify ``max_depth``.
DEFAULT_MAX_DEPTH = 3


@dataclass(frozen=True)
class ThreddsDataset:
    """A single downloadable THREDDS dataset.

    Attributes
    - name: Human-readable dataset name (``name`` attribute).
    - url_path: The service-relative ``urlPath`` used to build the download URL.
    - download_url: Absolute HTTP(S) URL served by the ``fileServer`` service.
    - dataset_id: Optional THREDDS dataset ``ID`` attribute.
    - date: Optional ISO date string parsed from a ``<date>`` element, if any.
    """

    name: str
    url_path: str
    download_url: str
    dataset_id: str | None = None
    date: str | None = None


def _local(tag: str) -> str:
    """Return the local name of a possibly namespaced XML tag."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _attr(el: ET.Element, name: str) -> str | None:
    """Return an attribute by local name, ignoring any XML namespace prefix."""
    val = el.get(name)
    if val is not None:
        return val
    for key, value in el.attrib.items():
        if _local(key) == name:
            return value
    return None


def _iter_services(root: ET.Element) -> Iterable[ET.Element]:
    """Yield all ``<service>`` elements, including those nested in compounds."""
    for el in root.iter():
        if _local(el.tag) == "service":
            yield el


def _http_server_base(root: ET.Element) -> str:
    """Return the ``HTTPServer`` service base path (e.g. ``/thredds/fileServer/``).

    Falls back to the conventional default when no HTTPServer service is found.
    """
    for svc in _iter_services(root):
        stype = (_attr(svc, "serviceType") or "").lower()
        if stype == "httpserver":
            base = _attr(svc, "base") or ""
            if base:
                return base
    return "/thredds/fileServer/"


def _server_root(catalog_url: str) -> str:
    """Return ``scheme://netloc`` for the given catalog URL."""
    pr = urlparse(catalog_url)
    return f"{pr.scheme}://{pr.netloc}"


def _build_download_url(catalog_url: str, base: str, url_path: str) -> str:
    """Build an absolute fileServer download URL from a dataset ``urlPath``.

    ``base`` is the HTTPServer service base declared by the catalog. It may be
    relative (e.g. ``/thredds/fileServer/``), in which case it is resolved
    against the catalog's ``scheme://netloc``; or absolute (e.g.
    ``https://other.example/thredds/fileServer/``), in which case it is used as
    the root directly so the download points at the declared host.
    """
    base_parsed = urlparse(base)
    if base_parsed.scheme and base_parsed.netloc:
        base_url = base
    else:
        # Relative service base: resolve against the catalog host.
        rel = base if base.startswith("/") else "/" + base
        base_url = urljoin(_server_root(catalog_url), rel)
    if not base_url.endswith("/"):
        base_url += "/"
    return urljoin(base_url, url_path.lstrip("/"))


def _dataset_date(el: ET.Element) -> str | None:
    """Return the text of the first ``<date>`` child element, if present."""
    for child in el:
        if _local(child.tag) == "date" and (child.text or "").strip():
            return child.text.strip()
    return None


def parse_catalog(
    catalog_xml: str, catalog_url: str
) -> tuple[list[ThreddsDataset], list[str]]:
    """Parse a THREDDS catalog document.

    Parameters
    - catalog_xml: Raw catalog XML text.
    - catalog_url: URL the catalog was fetched from (used to resolve relative
      ``catalogRef`` hrefs and to build absolute download URLs).

    Returns a tuple ``(datasets, catalog_refs)`` where ``datasets`` are the
    downloadable datasets (those carrying a ``urlPath``) and ``catalog_refs``
    are absolute URLs of nested catalogs referenced via ``<catalogRef>``.
    """
    root = ET.fromstring(catalog_xml)
    base = _http_server_base(root)

    datasets: list[ThreddsDataset] = []
    catalog_refs: list[str] = []
    for el in root.iter():
        local = _local(el.tag)
        if local == "dataset":
            url_path = _attr(el, "urlPath")
            if not url_path:
                continue
            datasets.append(
                ThreddsDataset(
                    name=_attr(el, "name") or Path(url_path).name,
                    url_path=url_path,
                    download_url=_build_download_url(catalog_url, base, url_path),
                    dataset_id=_attr(el, "ID"),
                    date=_dataset_date(el),
                )
            )
        elif local == "catalogRef":
            href = _attr(el, "href")
            if href:
                catalog_refs.append(urljoin(catalog_url, href))
    return datasets, catalog_refs


def _default_fetcher(
    *, headers: dict[str, str] | None, timeout: int
) -> Callable[[str], str]:
    def _fetch(url: str) -> str:
        return http_backend.fetch_text(url, timeout=timeout, headers=headers)

    return _fetch


def enumerate_datasets(
    catalog_url: str,
    *,
    catalog_xml: str | None = None,
    recursive: bool = False,
    max_depth: int = DEFAULT_MAX_DEPTH,
    pattern: str | None = None,
    since: str | None = None,
    until: str | None = None,
    date_format: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
    fetcher: Callable[[str], str] | None = None,
) -> list[ThreddsDataset]:
    """Enumerate downloadable datasets from a THREDDS catalog.

    When ``recursive`` is True, nested ``catalogRef`` entries are followed up to
    ``max_depth`` levels (the root catalog is depth 0). A visited set guards
    against catalog reference cycles.

    Filtering mirrors the other connectors: ``pattern`` is a regex applied to
    the dataset ``urlPath``; ``since``/``until`` are ISO dates applied to dates
    parsed from the dataset basename via :class:`DateManager`.
    """
    fetch = fetcher or _default_fetcher(headers=headers, timeout=timeout)

    results: list[ThreddsDataset] = []
    seen_urls: set[str] = set()
    seen_downloads: set[str] = set()

    def _walk(url: str, xml: str | None, depth: int) -> None:
        if url in seen_urls:
            return
        seen_urls.add(url)
        try:
            text = xml if xml is not None else fetch(url)
        except Exception as exc:  # pragma: no cover - network/error path
            logger.warning("Failed to fetch THREDDS catalog %s: %s", url, exc)
            return
        try:
            datasets, refs = parse_catalog(text, url)
        except ET.ParseError as exc:
            # Servers may return an HTML error page or auth redirect instead of
            # XML; log and skip so a single bad catalog does not abort recursion.
            logger.warning("Failed to parse THREDDS catalog %s: %s", url, exc)
            return
        for ds in datasets:
            # De-duplicate on the fully-resolved download URL: recursion across
            # different hosts or HTTPServer bases can yield distinct datasets
            # that share a urlPath.
            if ds.download_url not in seen_downloads:
                seen_downloads.add(ds.download_url)
                results.append(ds)
        if recursive and depth < max_depth:
            for ref in refs:
                _walk(ref, None, depth + 1)

    _walk(catalog_url, catalog_xml, 0)

    if pattern:
        rx = re.compile(pattern)
        results = [ds for ds in results if rx.search(ds.url_path)]

    if since or until:
        dm = DateManager([date_format] if date_format else None)
        start = datetime.min if not since else datetime.fromisoformat(since)
        end = datetime.max if not until else datetime.fromisoformat(until)
        results = [
            ds
            for ds in results
            if dm.is_date_in_range(Path(ds.url_path).name, start, end)
        ]
    return results


def list_files(
    catalog_url: str,
    *,
    catalog_xml: str | None = None,
    recursive: bool = False,
    max_depth: int = DEFAULT_MAX_DEPTH,
    pattern: str | None = None,
    since: str | None = None,
    until: str | None = None,
    date_format: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
    fetcher: Callable[[str], str] | None = None,
) -> list[str]:
    """Return absolute fileServer download URLs for matching datasets."""
    datasets = enumerate_datasets(
        catalog_url,
        catalog_xml=catalog_xml,
        recursive=recursive,
        max_depth=max_depth,
        pattern=pattern,
        since=since,
        until=until,
        date_format=date_format,
        headers=headers,
        timeout=timeout,
        fetcher=fetcher,
    )
    return [ds.download_url for ds in datasets]


def fetch_bytes(
    url: str, *, timeout: int = 60, headers: dict[str, str] | None = None
) -> bytes:
    """Fetch a single dataset over HTTP(S) (delegates to the HTTP backend)."""
    return http_backend.fetch_bytes(url, timeout=timeout, headers=headers)


def _has_done_marker(local_path: Path) -> bool:
    """Return True if a ``<filename>.done`` marker exists next to ``local_path``."""
    return (local_path.parent / (local_path.name + ".done")).exists()


def _parse_min_size(spec: int | str | None, local_size: int) -> int | None:
    """Parse a ``min_remote_size`` spec (absolute bytes or ``N%``) into bytes."""
    if spec is None:
        return None
    if isinstance(spec, int):
        return spec
    spec_str = str(spec).strip()
    if spec_str.endswith("%"):
        try:
            pct = float(spec_str[:-1])
        except ValueError:
            return None
        return round(local_size * (1 + pct / 100))
    try:
        return int(spec_str)
    except ValueError:
        return None


def _should_download(
    download_url: str,
    local_path: Path,
    options: SyncOptions,
    *,
    headers: dict[str, str] | None,
    timeout: int,
) -> bool:
    """Decide whether to (re)download a dataset to ``local_path``.

    Precedence mirrors the FTP backend for the options meaningful over HTTP:
    ``skip_if_local_done`` -> missing/zero-byte -> ``overwrite_existing`` /
    ``prefer_remote`` -> ``min_remote_size`` / ``recheck_existing`` (via the
    HTTP ``Content-Length`` header) -> default skip when a non-empty local copy
    already exists.
    """
    if options.skip_if_local_done and _has_done_marker(local_path):
        return False
    if not local_path.exists():
        return True
    local_size = local_path.stat().st_size
    if local_size == 0:
        return True
    if options.overwrite_existing or options.prefer_remote:
        return True
    if options.min_remote_size is not None or options.recheck_existing:
        remote_size = http_backend.get_size(
            download_url, headers=headers, timeout=timeout
        )
        if remote_size is None:
            return options.recheck_existing
        threshold = _parse_min_size(options.min_remote_size, local_size)
        if threshold is not None:
            return remote_size >= threshold
        if options.recheck_existing:
            return remote_size != local_size
    return False


def sync_directory(
    catalog_url: str,
    local_dir: str,
    *,
    catalog_xml: str | None = None,
    recursive: bool = False,
    max_depth: int = DEFAULT_MAX_DEPTH,
    pattern: str | None = None,
    since: str | None = None,
    until: str | None = None,
    date_format: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
    sync_options: SyncOptions | None = None,
    fetcher: Callable[[str], str] | None = None,
) -> list[str]:
    """Download matching THREDDS datasets into ``local_dir``.

    Returns the list of local file paths that were downloaded (skipped files are
    not included). Files are named by the dataset ``urlPath`` basename.

    Note: like the s3/ftp backends, local files are named by basename only, so
    datasets that share a basename across different catalog folders (or hosts,
    when ``recursive``) will collide and overwrite one another in ``local_dir``.
    """
    options = sync_options or SyncOptions()
    datasets = enumerate_datasets(
        catalog_url,
        catalog_xml=catalog_xml,
        recursive=recursive,
        max_depth=max_depth,
        pattern=pattern,
        since=since,
        until=until,
        date_format=date_format,
        headers=headers,
        timeout=timeout,
        fetcher=fetcher,
    )
    out_dir = Path(local_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    downloaded: list[str] = []
    for ds in datasets:
        name = Path(ds.url_path).name or "download.bin"
        local_path = out_dir / name
        if not _should_download(
            ds.download_url, local_path, options, headers=headers, timeout=timeout
        ):
            logger.debug("Skipping existing THREDDS dataset %s", name)
            continue
        data = fetch_bytes(ds.download_url, timeout=timeout, headers=headers)
        local_path.write_bytes(data)
        downloaded.append(str(local_path))
    return downloaded
