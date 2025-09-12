# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import contextlib
from typing import Optional

try:  # Prefer standard library importlib.resources
    from importlib import resources as importlib_resources
except Exception:  # pragma: no cover - fallback for very old Python
    import importlib_resources  # type: ignore

from zyra.visualization.styles import MAP_STYLES


def features_from_ns(ns) -> list[str] | None:
    """Build a features list from argparse namespace flags.

    Honors ``--features`` (CSV) and negation flags ``--no-coastline``,
    ``--no-borders``, and ``--no-gridlines``. Falls back to
    ``MAP_STYLES["features"]`` when not explicitly provided.
    """
    features = None
    if getattr(ns, "features", None):
        features = [f.strip() for f in (ns.features.split(",")) if f.strip()]
    else:
        features = list(MAP_STYLES.get("features", []) or [])
    if getattr(ns, "no_coastline", False) and "coastline" in features:
        features = [f for f in features if f != "coastline"]
    if getattr(ns, "no_borders", False) and "borders" in features:
        features = [f for f in features if f != "borders"]
    if getattr(ns, "no_gridlines", False) and "gridlines" in features:
        features = [f for f in features if f != "gridlines"]
    return features


def resolve_basemap_ref(
    ref: Optional[str],
) -> tuple[str | None, contextlib.ExitStack | None]:
    """Resolve a basemap reference to a filesystem path.

    Supports three forms:
      - Absolute/relative filesystem path (returned unchanged)
      - Bare filename under packaged assets/images (e.g., "earth_vegetation.jpg")
      - Packaged reference using ``pkg:`` scheme:
        - ``pkg:package/resource`` or ``pkg:package:resource``

    Returns a tuple of (path, guard). If a temporary path context is used, a
    contextlib.ExitStack is returned and must be kept alive until the path is
    no longer needed. Call ``guard.close()" when finished.
    """
    if not ref:
        return None, None
    s = str(ref).strip()
    # pkg: resolver
    if s.startswith("pkg:"):
        es = contextlib.ExitStack()
        try:
            spec = s[4:]
            if ":" in spec and "/" not in spec:
                pkg, res = spec.split(":", 1)
            else:
                parts = spec.split("/", 1)
                pkg = parts[0]
                res = parts[1] if len(parts) > 1 else ""
            if not res:
                es.close()
                return None, None
            path = importlib_resources.files(pkg).joinpath(res)
            p = es.enter_context(importlib_resources.as_file(path))
            return str(p), es
        except Exception:
            es.close()
            return None, None
    # Bare filename under packaged assets/images
    if "/" not in s and "\\" not in s:
        try:
            res = (
                importlib_resources.files("zyra.assets").joinpath("images").joinpath(s)
            )
            if getattr(res, "is_file", None) and res.is_file():  # type: ignore[attr-defined]
                es = contextlib.ExitStack()
                p = es.enter_context(importlib_resources.as_file(res))
                return str(p), es
        except Exception:
            pass
    # Relative resource path under packaged assets (e.g., 'images/earth_vegetation.jpg')
    if s.startswith("images/"):
        try:
            res = importlib_resources.files("zyra.assets").joinpath(s)
            if getattr(res, "is_file", None) and res.is_file():  # type: ignore[attr-defined]
                es = contextlib.ExitStack()
                p = es.enter_context(importlib_resources.as_file(res))
                return str(p), es
        except Exception:
            pass
    # Fallback: treat as filesystem path
    return s, None
