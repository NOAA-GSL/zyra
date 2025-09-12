# SPDX-License-Identifier: Apache-2.0
"""OGC API - Records discovery backend.

Parses a Records "items" response (GeoJSON-like) and returns DatasetMetadata
entries for features whose title/description match the query.

Network fetching is optional; tests can pass a JSON payload via `items_json`.
If fetching is needed and `requests` is unavailable, raises a helpful error.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from . import DatasetMetadata, DiscoveryBackend
from .utils import slugify


def _slug(s: str) -> str:
    # Backward-compatibility wrapper; use shared utility
    return slugify(s)


@dataclass
class OGCRecordsBackend(DiscoveryBackend):
    endpoint: str
    items_json: str | None = None
    weights: dict[str, int] | None = None

    def _load_items(self) -> dict[str, Any]:
        if self.items_json is not None:
            return json.loads(self.items_json)
        url = self.endpoint
        # Offline/local file support
        try:
            from pathlib import Path

            if url.startswith("file:"):
                path = Path(url[5:])
                with path.open(encoding="utf-8") as f:
                    return json.loads(f.read())
            p = Path(url)
            if p.exists():
                with p.open(encoding="utf-8") as f:
                    return json.loads(f.read())
        except Exception:
            pass
        # Append basic query params if none are present
        if "?" not in url:
            url = f"{url}?limit=100"
        try:
            import requests  # type: ignore

            r = requests.get(url, timeout=10)
            r.raise_for_status()
            return r.json()
        except ImportError as e:  # pragma: no cover - env dependent
            raise RuntimeError(
                "requests is not installed; provide items_json or install connectors extras"
            ) from e

    def search(self, query: str, *, limit: int = 10) -> list[DatasetMetadata]:
        data = self._load_items()
        rx = re.compile(re.escape(query), re.IGNORECASE)
        feats = data.get("features") or []
        results: list[tuple[int, DatasetMetadata]] = []
        w = self.weights or {}
        for f in feats:
            props = f.get("properties") or {}
            title = str(props.get("title") or "")
            desc = str(props.get("description") or "")
            links = f.get("links") or props.get("links") or []
            # Score
            score = 0
            if rx.search(title):
                score += int(w.get("title", 3))
            if rx.search(desc):
                score += int(w.get("description", 2))
            # Fallback: scan link titles
            for ln in links:
                lt = str(ln.get("title") or "")
                if lt and rx.search(lt):
                    score += int(w.get("link_titles", 1))
                    break
            # Broader scan: feature id and generic properties (strings/lists of strings)
            fid = str(f.get("id") or "")
            if fid and rx.search(fid):
                score += int(w.get("id", 1))
            # Keywords array (commonly used)
            kws = props.get("keywords")
            if isinstance(kws, list) and any(
                isinstance(k, str) and rx.search(k) for k in kws
            ):
                score += int(w.get("keywords", 1))
            # Generic property values
            for k, v in props.items():
                if k in {"title", "description", "keywords", "links"}:
                    continue
                if isinstance(v, str) and rx.search(v):
                    score += int(w.get("generic_props", 1))
                    break
                if isinstance(v, list) and any(
                    isinstance(x, str) and rx.search(x) for x in v
                ):
                    score += int(w.get("generic_props", 1))
                    break
            if score <= 0:
                continue
            # Choose a representative URI: first self or data link
            uri = None
            for ln in links:
                rel = (ln.get("rel") or "").lower()
                href = ln.get("href")
                if rel in {"self", "data", "collection", "items"} and href:
                    uri = href
                    break
            if not uri:
                # Default to endpoint
                uri = self.endpoint
            results.append(
                (
                    score,
                    DatasetMetadata(
                        id=_slug(title or uri),
                        name=title or uri,
                        description=(desc or None),
                        source="ogc-records",
                        format="OGC",
                        uri=uri,
                    ),
                )
            )
        results.sort(key=lambda t: (-t[0], t[1].name))
        return [d for _, d in results[: max(0, limit) or None]]
