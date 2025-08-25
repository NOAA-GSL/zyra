"""FastAPI router exposing dataset search based on the local SOS catalog.

Reuses the connectors discovery backend so logic stays in one place.

Endpoint
- GET /search?q=<query>&limit=10

Response
- JSON array of DatasetMetadata-like dicts: id, name, description, source, format, uri
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(tags=["search"])


@router.get("/search")
def search(
    q: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=100, description="Max number of results"),
    catalog_file: str | None = Query(
        None, description="Local catalog JSON path or pkg:module/resource"
    ),
    profile: str | None = Query(
        None, description="Bundled profile name under zyra.assets.profiles"
    ),
    profile_file: str | None = Query(None, description="External profile JSON path"),
    ogc_wms: str | None = Query(
        None, description="WMS capabilities URL(s), comma-separated"
    ),
    ogc_records: str | None = Query(
        None, description="OGC API - Records items URL(s), comma-separated"
    ),
    remote_only: bool = Query(False, description="If true, skip local catalog"),
    include_local: bool = Query(
        False,
        description=(
            "When remote sources are provided, also include local catalog results"
        ),
    ),
) -> list[dict[str, Any]]:
    """Search catalog(s) and return normalized results (JSON)."""
    try:
        from zyra.connectors.discovery import LocalCatalogBackend

        items: list[Any] = []
        # Profiles
        prof_sources: dict[str, Any] = {}
        prof_weights: dict[str, int] = {}
        if profile:
            from importlib import resources as importlib_resources

            pkg = "zyra.assets.profiles"
            res = f"{profile}.json"
            path = importlib_resources.files(pkg).joinpath(res)
            with importlib_resources.as_file(path) as p:
                prof0 = __import__("json").loads(p.read_text(encoding="utf-8"))
            prof_sources.update(dict(prof0.get("sources") or {}))
            prof_weights.update(
                {k: int(v) for k, v in (prof0.get("weights") or {}).items()}
            )
        if profile_file:
            import json as _json
            from pathlib import Path

            prof1 = _json.loads(Path(profile_file).read_text(encoding="utf-8"))
            prof_sources.update(dict(prof1.get("sources") or {}))
            prof_weights.update(
                {k: int(v) for k, v in (prof1.get("weights") or {}).items()}
            )

        # Local inclusion: default to remote-only when any remote provided unless include_local
        include_local_eff = not remote_only
        if include_local:
            include_local_eff = True
        # Local
        if include_local_eff:
            cat = catalog_file
            if not cat:
                local = (
                    prof_sources.get("local")
                    if isinstance(prof_sources.get("local"), dict)
                    else None
                )
                if isinstance(local, dict):
                    cat = local.get("catalog_file")
            # If any remote present and no explicit local path or profile-local and not include_local, drop local
            any_remote = bool(ogc_wms or ogc_records)
            if not any_remote:
                any_remote = bool(
                    (
                        isinstance(prof_sources.get("ogc_wms"), list)
                        and prof_sources.get("ogc_wms")
                    )
                    or (
                        isinstance(prof_sources.get("ogc_records"), list)
                        and prof_sources.get("ogc_records")
                    )
                )
            local_explicit = bool(cat)
            if any_remote and not local_explicit and not include_local:
                include_local_eff = False
            if include_local_eff:
                items.extend(
                    LocalCatalogBackend(cat, weights=prof_weights).search(
                        q, limit=limit
                    )
                )

        # WMS
        wms_urls: list[str] = []
        if ogc_wms:
            wms_urls.extend([u.strip() for u in ogc_wms.split(",") if u.strip()])
        prof_wms = prof_sources.get("ogc_wms") or []
        if isinstance(prof_wms, list):
            wms_urls.extend([u for u in prof_wms if isinstance(u, str)])
        if wms_urls:
            from zyra.connectors.discovery.ogc import OGCWMSBackend

            for url in wms_urls:
                items.extend(
                    OGCWMSBackend(url, weights=prof_weights).search(q, limit=limit)
                )

        # Records
        rec_urls: list[str] = []
        if ogc_records:
            rec_urls.extend([u.strip() for u in ogc_records.split(",") if u.strip()])
        prof_rec = prof_sources.get("ogc_records") or []
        if isinstance(prof_rec, list):
            rec_urls.extend([u for u in prof_rec if isinstance(u, str)])
        if rec_urls:
            from zyra.connectors.discovery.ogc_records import OGCRecordsBackend

            for url in rec_urls:
                items.extend(
                    OGCRecordsBackend(url, weights=prof_weights).search(q, limit=limit)
                )

    except Exception as e:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"Search failed: {e}") from e
    # Trim and return
    items = items[: max(0, limit) or None]
    return [d.__dict__ for d in items]


@router.get("/search/profiles")
def list_profiles() -> dict[str, Any]:
    """Return bundled search profiles with metadata for discovery guidance.

    Response includes a flat `profiles` list for backward compatibility and an
    `entries` array of objects with `id`, `name`, `description`, and `keywords`.
    """
    try:
        import json as _json
        from importlib import resources as importlib_resources

        pkg = "zyra.assets.profiles"
        names: list[str] = []
        entries: list[dict[str, Any]] = []
        for p in importlib_resources.files(pkg).iterdir():  # type: ignore[attr-defined]
            try:
                n = str(getattr(p, "name", ""))
            except Exception:
                n = ""
            if n.endswith(".json"):
                pid = n[:-5]
                names.append(pid)
                # Load metadata fields if present
                try:
                    with importlib_resources.as_file(p) as fp:
                        data = _json.loads(fp.read_text(encoding="utf-8"))
                    entries.append(
                        {
                            "id": pid,
                            "name": data.get("name") or pid,
                            "description": data.get("description") or None,
                            "keywords": data.get("keywords") or [],
                        }
                    )
                except Exception:
                    entries.append(
                        {"id": pid, "name": pid, "description": None, "keywords": []}
                    )
        names.sort()
        entries.sort(key=lambda e: e.get("id") or "")
        return {"profiles": names, "entries": entries}
    except Exception as e:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=500, detail=f"Failed to list profiles: {e}"
        ) from e


@router.post("/search")
def post_search(body: dict) -> dict[str, Any]:
    """POST /search: accept JSON body; optional analysis via `analyze: true`.

    Body keys mirror `/semantic_search` with an additional `analyze` boolean.
    When `analyze` is false or omitted, returns items like GET /search.
    When `analyze` is true, also includes an `analysis` block.
    """
    analyze = bool(body.get("analyze") or False)
    # Delegate to the same internals used by GET /search and /semantic_search
    # Gather items first
    try:
        q = str(body.get("query") or "").strip()
        if not q:
            raise HTTPException(status_code=400, detail="Missing 'query'")
        limit = int(body.get("limit") or 10)
        # Reuse the gather portion from semantic_search by inlining minimal logic
        include_local = bool(body.get("include_local") or False)
        remote_only = bool(body.get("remote_only") or False)
        profile = body.get("profile")
        profile_file = body.get("profile_file")
        catalog_file = body.get("catalog_file")
        ogc_wms = body.get("ogc_wms")
        ogc_records = body.get("ogc_records")
        if isinstance(ogc_wms, list):
            ogc_wms = ",".join(map(str, ogc_wms))
        if isinstance(ogc_records, list):
            ogc_records = ",".join(map(str, ogc_records))

        items: list[Any] = []
        from zyra.connectors.discovery import LocalCatalogBackend

        prof_sources: dict[str, Any] = {}
        prof_weights: dict[str, int] = {}
        if profile:
            import json as _json
            from importlib import resources as importlib_resources

            pkg = "zyra.assets.profiles"
            res = f"{profile}.json"
            path = importlib_resources.files(pkg).joinpath(res)
            with importlib_resources.as_file(path) as p:
                prof0 = _json.loads(p.read_text(encoding="utf-8"))
            prof_sources.update(dict(prof0.get("sources") or {}))
            prof_weights.update(
                {k: int(v) for k, v in (prof0.get("weights") or {}).items()}
            )
        if profile_file:
            import json as _json
            from pathlib import Path

            prof1 = _json.loads(Path(profile_file).read_text(encoding="utf-8"))
            prof_sources.update(dict(prof1.get("sources") or {}))
            prof_weights.update(
                {k: int(v) for k, v in (prof1.get("weights") or {}).items()}
            )

        # Local inclusion
        if not remote_only:
            cat = catalog_file
            if not cat:
                local = (
                    prof_sources.get("local")
                    if isinstance(prof_sources.get("local"), dict)
                    else None
                )
                if isinstance(local, dict):
                    cat = local.get("catalog_file")
            any_remote = bool(
                ogc_wms
                or ogc_records
                or (
                    isinstance(prof_sources.get("ogc_wms"), list)
                    and prof_sources.get("ogc_wms")
                )
                or (
                    isinstance(prof_sources.get("ogc_records"), list)
                    and prof_sources.get("ogc_records")
                )
            )
            local_explicit = bool(cat)
            if not (any_remote and not local_explicit and not include_local):
                items.extend(
                    LocalCatalogBackend(cat, weights=prof_weights).search(
                        q, limit=limit
                    )
                )

        # WMS
        wms_urls: list[str] = []
        if ogc_wms:
            wms_urls.extend([u.strip() for u in str(ogc_wms).split(",") if u.strip()])
        prof_wms = prof_sources.get("ogc_wms") or []
        if isinstance(prof_wms, list):
            wms_urls.extend([u for u in prof_wms if isinstance(u, str)])
        if wms_urls:
            from contextlib import suppress

            from zyra.connectors.discovery.ogc import OGCWMSBackend

            for url in wms_urls:
                with suppress(Exception):
                    items.extend(
                        OGCWMSBackend(url, weights=prof_weights).search(q, limit=limit)
                    )

        # Records
        rec_urls: list[str] = []
        if ogc_records:
            rec_urls.extend(
                [u.strip() for u in str(ogc_records).split(",") if u.strip()]
            )
        prof_rec = prof_sources.get("ogc_records") or []
        if isinstance(prof_rec, list):
            rec_urls.extend([u for u in prof_rec if isinstance(u, str)])
        if rec_urls:
            from contextlib import suppress

            from zyra.connectors.discovery.ogc_records import OGCRecordsBackend

            for url in rec_urls:
                with suppress(Exception):
                    items.extend(
                        OGCRecordsBackend(url, weights=prof_weights).search(
                            q, limit=limit
                        )
                    )

        # If not analyzing, return like GET /search (serialize dataclasses safely)
        if not analyze:
            from zyra.utils.serialize import to_list

            return {"items": to_list(items[: max(0, limit) or None])}

        # Otherwise, perform analysis just like /semantic_search
        def compact(d: Any) -> dict[str, Any]:
            desc = getattr(d, "description", None) or ""
            if len(desc) > 240:
                desc = desc[:239] + "…"
            return {
                "id": getattr(d, "id", None),
                "name": getattr(d, "name", None),
                "description": desc,
                "source": getattr(d, "source", None),
                "format": getattr(d, "format", None),
                "uri": getattr(d, "uri", None),
            }

        ctx_items = [
            compact(i) for i in items[: max(1, int(body.get("analysis_limit") or 20))]
        ]
        import json as _json

        from zyra.wizard import _select_provider  # type: ignore[attr-defined]
        from zyra.wizard.prompts import load_semantic_analysis_prompt

        client = _select_provider(None, None)
        sys_prompt = load_semantic_analysis_prompt()
        user = _json.dumps({"query": q, "results": ctx_items})
        analysis_raw = client.generate(sys_prompt, user)
        try:
            analysis = _json.loads(analysis_raw.strip())
        except Exception:
            analysis = {"summary": analysis_raw.strip(), "picks": []}

        return {"query": q, "limit": limit, "items": ctx_items, "analysis": analysis}
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"POST /search failed: {e}") from e
