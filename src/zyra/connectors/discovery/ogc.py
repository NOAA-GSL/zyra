# SPDX-License-Identifier: Apache-2.0
"""OGC discovery backends (WMS capabilities search).

Lightweight parser that reads a WMS GetCapabilities XML document and returns
matching layers as DatasetMetadata results.

Notes
- Network fetching is optional to keep tests hermetic. When `capabilities_xml`
  is provided, no HTTP requests are made.
- If `capabilities_xml` is not provided, attempts to fetch via `requests`.
  `requests` is optional in this repo; raise a helpful error if missing.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable

from . import DatasetMetadata, DiscoveryBackend
from .utils import slugify


def _findtext(el: ET.Element, local_name: str) -> str | None:
    """Return text of the first immediate child whose tag ends with local_name.

    Handles XML with namespaces by matching on the local part only and avoids
    missing elements like Title/Abstract/Name in WMS 1.3.0 that use a default
    namespace.
    """
    for child in list(el):
        tag = getattr(child, "tag", None)
        if isinstance(tag, str) and tag.endswith(local_name):
            txt = child.text
            return txt.strip() if txt else None
    return None


def _slug(s: str) -> str:
    # Backward-compatibility wrapper; use shared utility
    return slugify(s)


@dataclass
class OGCWMSBackend(DiscoveryBackend):
    endpoint: str
    capabilities_xml: str | None = None
    weights: dict[str, int] | None = None

    def _load_xml(self) -> ET.Element:
        if self.capabilities_xml is not None:
            return ET.fromstring(self.capabilities_xml)
        # Fetch from endpoint (append service params if missing)
        url = self.endpoint
        # Offline/local file support
        try:
            from pathlib import Path

            if url.startswith("file:"):
                path = Path(url[5:])
                with path.open(encoding="utf-8") as f:
                    return ET.fromstring(f.read())
            p = Path(url)
            if p.exists():
                with p.open(encoding="utf-8") as f:
                    return ET.fromstring(f.read())
        except Exception:
            pass
        if "service=WMS" not in url.lower():
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}service=WMS&request=GetCapabilities"
        try:
            import requests  # type: ignore

            r = requests.get(url, timeout=10)
            r.raise_for_status()
            return ET.fromstring(r.text)
        except ImportError as e:  # pragma: no cover - env dependent
            raise RuntimeError(
                "requests is not installed; provide capabilities_xml or install connectors extras"
            ) from e

    def _get_getmap_base(self, root: ET.Element) -> str | None:
        # Try WMS 1.3.0 path first, then 1.1.1
        ns = {
            "xlink": "http://www.w3.org/1999/xlink",
        }
        paths = [
            "./Capability/Request/GetMap/DCPType/HTTP/Get/OnlineResource",
            "./Capability/Request/GetMap/DCPType/HTTP/Get/OnlineResource[@xlink:href]",
        ]
        for p in paths:
            el = root.find(p, ns)
            if el is not None:
                href = el.get("{http://www.w3.org/1999/xlink}href") or el.get("href")
                if href:
                    return href
        return None

    def _iter_layers(self, el: ET.Element) -> Iterable[ET.Element]:
        # Traverse all descendants and yield any element whose tag endswith 'Layer'
        for node in el.iter():
            if isinstance(node.tag, str) and node.tag.endswith("Layer"):
                yield node

    def search(self, query: str, *, limit: int = 10) -> list[DatasetMetadata]:
        root = self._load_xml()
        base = self._get_getmap_base(root) or self.endpoint
        # Token-aware matching: prefer multi-token scoring for long queries
        tokens = [t for t in re.split(r"\W+", query) if t]
        token_patterns = [
            re.compile(re.escape(t), re.IGNORECASE) for t in tokens if len(t) >= 3
        ]
        use_tokens = len(token_patterns) >= 2
        rx = re.compile(re.escape(query), re.IGNORECASE)
        results: list[tuple[int, DatasetMetadata]] = []
        w = self.weights or {}
        for layer in self._iter_layers(root):
            title = _findtext(layer, "Title") or ""
            abstract = _findtext(layer, "Abstract") or ""
            name = _findtext(layer, "Name") or title or "layer"
            score = 0
            if use_tokens:
                for pat in token_patterns:
                    if pat.search(title):
                        score += int(w.get("title", 3))
                    if pat.search(abstract):
                        score += int(w.get("abstract", 2))
                    if pat.search(name):
                        score += int(w.get("name", 1))
            else:
                if rx.search(title):
                    score += int(w.get("title", 3))
                if rx.search(abstract):
                    score += int(w.get("abstract", 2))
                if rx.search(name):
                    score += int(w.get("name", 1))
            # Keywords (WMS KeywordList)
            for kw in layer.iter():
                if (
                    isinstance(kw.tag, str)
                    and kw.tag.endswith("Keyword")
                    and kw.text
                    and rx.search(kw.text)
                ):
                    score += int(w.get("keywords", 1))
                    break
            if score > 0:
                results.append(
                    (
                        score,
                        DatasetMetadata(
                            id=_slug(name or title or "layer"),
                            name=title or name,
                            description=abstract or None,
                            source="ogc-wms",
                            format="WMS",
                            uri=base,
                        ),
                    )
                )
        results.sort(key=lambda t: (-t[0], t[1].name))
        return [d for _, d in results[: max(0, limit) or None]]
