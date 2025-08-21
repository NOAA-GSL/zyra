from __future__ import annotations

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
