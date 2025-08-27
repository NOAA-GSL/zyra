from __future__ import annotations

import json
from importlib import resources as importlib_resources


def _load_profile(name: str) -> dict:
    pkg = "zyra.assets.profiles"
    path = importlib_resources.files(pkg).joinpath(f"{name}.json")
    with importlib_resources.as_file(path) as p:
        return json.loads(p.read_text(encoding="utf-8"))


def test_bundled_sos_profile_parses_and_points_to_pkg():
    prof = _load_profile("sos")
    assert "sources" in prof
    local = prof["sources"].get("local")
    assert isinstance(local, dict)
    cf = local.get("catalog_file")
    assert isinstance(cf, str) and cf.startswith("pkg:")


def test_bundled_gibs_and_pygeoapi_profiles_parse():
    gibs = _load_profile("gibs")
    pga = _load_profile("pygeoapi")
    assert isinstance(gibs.get("sources", {}).get("ogc_wms", []), list)
    assert isinstance(pga.get("sources", {}).get("ogc_records", []), list)
