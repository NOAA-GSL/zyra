# SPDX-License-Identifier: Apache-2.0
"""FastAPI router exposing dataset search based on the local SOS catalog.

Reuses the connectors discovery backend so logic stays in one place.

Endpoint
- GET /search?q=<query>&limit=10

Response
- JSON array of DatasetMetadata-like dicts: id, name, description, source, format, uri
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

router = APIRouter(tags=["search"])


def _is_under_allowed(p: str, base_envs: list[str]) -> bool:
    """Syntactic containment check using normalized absolute paths (no FS resolve).

    Uses abspath/normpath/commonpath to avoid filesystem access that `Path.resolve()` may perform.
    """
    try:
        tgt = os.path.abspath(os.path.normpath(str(p)))  # noqa: PTH100
        for env in base_envs:
            base = os.getenv(env)
            if not base:
                continue
            try:
                base_abs = os.path.abspath(os.path.normpath(base))  # noqa: PTH100
                common = os.path.commonpath([tgt, base_abs])
                if common == base_abs:
                    return True
            except Exception:
                continue
        return False
    except Exception:
        return False


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
    enrich: str | None = Query(
        None,
        description=(
            "Optional metadata enrichment: shallow|capabilities|probe (bounded, cached)"
        ),
    ),
    enrich_timeout: float = Query(3.0, description="Per-item enrichment timeout (s)"),
    enrich_workers: int = Query(4, description="Enrichment concurrency (workers)"),
    cache_ttl: int = Query(86400, description="Enrichment cache TTL seconds"),
    offline: bool = Query(False, description="Disable network enrichment; local only"),
    https_only: bool = Query(False, description="Require HTTPS for any remote probing"),
    allow_hosts: str | None = Query(
        None, description="Comma-separated host suffixes to allow for probing"
    ),
    deny_hosts: str | None = Query(
        None, description="Comma-separated host suffixes to deny for probing"
    ),
    max_probe_bytes: int | None = Query(
        None, description="Max content length to probe (bytes)"
    ),
) -> list[dict[str, Any]]:
    """Search catalog(s) and return normalized results (JSON)."""
    try:
        from zyra.connectors.discovery import LocalCatalogBackend

        items: list[Any] = []
        # Profiles and file inputs: allow packaged refs or safe paths under allowlisted bases
        allowed_catalog_envs = ["ZYRA_CATALOG_DIR", "DATA_DIR"]
        allowed_profile_envs = ["ZYRA_PROFILE_DIR", "DATA_DIR"]

        prof_sources: dict[str, Any] = {}
        prof_weights: dict[str, int] = {}
        prof_defaults: dict[str, Any] = {}
        prof_license_policy: dict[str, Any] = {}
        defaults_sources: list[str] = []
        defaults_sources: list[str] = []
        prof_license_policy: dict[str, Any] = {}
        prof_license_policy: dict[str, Any] = {}
        prof_defaults: dict[str, Any] = {}
        prof_license_policy: dict[str, Any] = {}
        prof_license_policy: dict[str, Any] = {}
        prof_license_policy: dict[str, Any] = {}
        prof_license_policy: dict[str, Any] = {}
        prof_defaults: dict[str, Any] = {}
        prof_defaults: dict[str, Any] = {}
        prof_defaults: dict[str, Any] = {}
        prof_defaults: dict[str, Any] = {}
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
            enr = prof0.get("enrichment") or {}
            ed = enr.get("defaults") or {}
            if isinstance(ed, dict):
                prof_defaults.update(ed)
            lp = enr.get("license_policy") or {}
            if isinstance(lp, dict):
                prof_license_policy.update(lp)
            ed = (prof0.get("enrichment") or {}).get("defaults") or {}
            if isinstance(ed, dict):
                prof_defaults.update(ed)
            ed = (prof0.get("enrichment") or {}).get("defaults") or {}
            if isinstance(ed, dict):
                prof_defaults.update(ed)
            ed = (prof0.get("enrichment") or {}).get("defaults") or {}
            if isinstance(ed, dict):
                prof_defaults.update(ed)
            ed = (prof0.get("enrichment") or {}).get("defaults") or {}
            if isinstance(ed, dict):
                prof_defaults.update(ed)
        if profile_file:
            import json as _json
            from importlib import resources as importlib_resources

            if str(profile_file).startswith("pkg:"):
                ref = str(profile_file)[4:]
                try:
                    if ":" in ref and "/" not in ref:
                        pkg, res = ref.split(":", 1)
                    else:
                        parts = ref.split("/", 1)
                        pkg = parts[0]
                        res = parts[1] if len(parts) > 1 else None
                    if not pkg or not res:
                        raise ValueError("Invalid pkg reference")
                    path = importlib_resources.files(pkg).joinpath(res)
                    with importlib_resources.as_file(path) as p:
                        prof1 = _json.loads(p.read_text(encoding="utf-8"))
                except Exception as e:
                    raise HTTPException(
                        status_code=400, detail=f"Invalid profile_file: {e}"
                    ) from e
            else:
                # Normalize and validate against allowlisted base directories
                resolved = Path(os.path.abspath(os.path.normpath(str(profile_file))))  # noqa: PTH100
                if not _is_under_allowed(str(resolved), allowed_profile_envs):
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "profile_file not allowed; must be under ZYRA_PROFILE_DIR or DATA_DIR"
                        ),
                    )
                # Contained, normalized path under allowlisted base dirs
                prof1 = _json.loads(
                    resolved.read_text(encoding="utf-8")
                )  # lgtm [py/path-injection] [py/uncontrolled-data-in-path-expression]
            prof_sources.update(dict(prof1.get("sources") or {}))
            prof_weights.update(
                {k: int(v) for k, v in (prof1.get("weights") or {}).items()}
            )
            enr = prof1.get("enrichment") or {}
            ed = enr.get("defaults") or {}
            if isinstance(ed, dict):
                prof_defaults.update(ed)
            lp = enr.get("license_policy") or {}
            if isinstance(lp, dict):
                prof_license_policy.update(lp)
            ed = (prof1.get("enrichment") or {}).get("defaults") or {}
            if isinstance(ed, dict):
                prof_defaults.update(ed)
            ed = (prof1.get("enrichment") or {}).get("defaults") or {}
            if isinstance(ed, dict):
                prof_defaults.update(ed)
            ed = (prof1.get("enrichment") or {}).get("defaults") or {}
            if isinstance(ed, dict):
                prof_defaults.update(ed)
            ed = (prof1.get("enrichment") or {}).get("defaults") or {}
            if isinstance(ed, dict):
                prof_defaults.update(ed)

        # Local inclusion: consistent policy via shared helper
        from zyra.connectors.discovery.utils import (
            compute_inclusion as _compute_inclusion,
        )

        include_local_eff, _any_remote, cat = _compute_inclusion(
            ogc_wms,
            ogc_records,
            prof_sources,
            remote_only=bool(remote_only),
            include_local_flag=bool(include_local),
            catalog_file_flag=catalog_file,
        )
        if include_local_eff:
            # Validate/sanitize catalog path before passing to backend
            if cat and (
                not str(cat).startswith("pkg:")
                and not _is_under_allowed(str(cat), allowed_catalog_envs)
            ):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "catalog_file not allowed; must be under ZYRA_CATALOG_DIR or DATA_DIR"
                    ),
                )
            items.extend(
                LocalCatalogBackend(cat, weights=prof_weights).search(q, limit=limit)
            )
            # If no profile specified, auto-apply SOS defaults scoped to local items
            if not profile and not profile_file:
                try:
                    from importlib import resources as importlib_resources

                    pkg = "zyra.assets.profiles"
                    res = "sos.json"
                    path = importlib_resources.files(pkg).joinpath(res)
                    with importlib_resources.as_file(path) as p:
                        prof0 = __import__("json").loads(p.read_text(encoding="utf-8"))
                    enr = prof0.get("enrichment") or {}
                    ed = enr.get("defaults") or {}
                    if isinstance(ed, dict):
                        prof_defaults.update(ed)
                    lp = enr.get("license_policy") or {}
                    if isinstance(lp, dict):
                        prof_license_policy.update(lp)
                    defaults_sources = ["sos-catalog"]
                except Exception:
                    pass

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

        # Optional enrichment
        if enrich:
            try:
                from zyra.transform.enrich import enrich_items

                items = enrich_items(
                    items,
                    level=str(enrich),
                    timeout=float(enrich_timeout or 3.0),
                    workers=int(enrich_workers or 4),
                    cache_ttl=int(cache_ttl or 86400),
                    offline=bool(offline or False),
                    https_only=bool(https_only or False),
                    allow_hosts=[
                        s.strip() for s in (allow_hosts or "").split(",") if s.strip()
                    ],
                    deny_hosts=[
                        s.strip() for s in (deny_hosts or "").split(",") if s.strip()
                    ],
                    max_probe_bytes=max_probe_bytes,
                    profile_defaults=prof_defaults,
                    profile_license_policy=prof_license_policy,
                    defaults_sources=defaults_sources,
                )
            except Exception:
                # Do not fail the request if enrichment fails; return base items
                pass

    except HTTPException:
        # Propagate deliberate HTTP errors (e.g., allowlist violations)
        raise
    except Exception as e:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"Search failed: {e}") from e
    # Trim and return
    from zyra.utils.serialize import to_list

    items = items[: max(0, limit) or None]
    return to_list(items)


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

        allowed_catalog_envs = ["ZYRA_CATALOG_DIR", "DATA_DIR"]
        allowed_profile_envs = ["ZYRA_PROFILE_DIR", "DATA_DIR"]

        prof_sources: dict[str, Any] = {}
        prof_weights: dict[str, int] = {}
        prof_defaults: dict[str, Any] = {}
        prof_license_policy: dict[str, Any] = {}
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
            enr = prof0.get("enrichment") or {}
            ed = enr.get("defaults") or {}
            if isinstance(ed, dict):
                prof_defaults.update(ed)
            lp = enr.get("license_policy") or {}
            if isinstance(lp, dict):
                prof_license_policy.update(lp)
        if profile_file:
            import json as _json

            if str(profile_file).startswith("pkg:"):
                from importlib import resources as importlib_resources

                ref = str(profile_file)[4:]  # strip 'pkg:'
                try:
                    if ":" in ref and "/" not in ref:
                        pkg, res = ref.split(":", 1)
                    else:
                        parts = ref.split("/", 1)
                        pkg = parts[0]
                        res = parts[1] if len(parts) > 1 else None
                    if not pkg or not res:
                        raise ValueError("Invalid pkg reference")
                    path = importlib_resources.files(pkg).joinpath(res)
                    with importlib_resources.as_file(path) as p:
                        prof1 = _json.loads(p.read_text(encoding="utf-8"))
                except Exception as e:
                    raise HTTPException(
                        status_code=400, detail=f"Invalid profile_file: {e}"
                    ) from e
            else:
                # Normalize and validate against allowlisted base directories
                resolved = Path(os.path.abspath(os.path.normpath(str(profile_file))))  # noqa: PTH100
                if not _is_under_allowed(str(resolved), allowed_profile_envs):
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "profile_file not allowed; must be under ZYRA_PROFILE_DIR or DATA_DIR"
                        ),
                    )
                # Contained, normalized path under allowlisted base dirs
                prof1 = _json.loads(
                    resolved.read_text(encoding="utf-8")
                )  # lgtm [py/path-injection] [py/uncontrolled-data-in-path-expression]
            prof_sources.update(dict(prof1.get("sources") or {}))
            prof_weights.update(
                {k: int(v) for k, v in (prof1.get("weights") or {}).items()}
            )
            enr = prof1.get("enrichment") or {}
            ed = enr.get("defaults") or {}
            if isinstance(ed, dict):
                prof_defaults.update(ed)
            lp = enr.get("license_policy") or {}
            if isinstance(lp, dict):
                prof_license_policy.update(lp)

        # Local inclusion (POST body path)
        from zyra.connectors.discovery.utils import (
            compute_inclusion as _compute_inclusion,
        )

        include_local_eff, _any_remote, cat = _compute_inclusion(
            ogc_wms,
            ogc_records,
            prof_sources,
            remote_only=bool(remote_only),
            include_local_flag=bool(include_local),
            catalog_file_flag=catalog_file,
        )
        if include_local_eff:
            if cat and (
                not str(cat).startswith("pkg:")
                and not _is_under_allowed(str(cat), allowed_catalog_envs)
            ):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "catalog_file not allowed; must be under ZYRA_CATALOG_DIR or DATA_DIR"
                    ),
                )
            items.extend(
                LocalCatalogBackend(cat, weights=prof_weights).search(q, limit=limit)
            )
            if not profile and not profile_file:
                try:
                    import json as _json
                    from importlib import resources as importlib_resources

                    pkg = "zyra.assets.profiles"
                    res = "sos.json"
                    path = importlib_resources.files(pkg).joinpath(res)
                    with importlib_resources.as_file(path) as p:
                        prof0 = _json.loads(p.read_text(encoding="utf-8"))
                    enr = prof0.get("enrichment") or {}
                    ed = enr.get("defaults") or {}
                    if isinstance(ed, dict):
                        prof_defaults.update(ed)
                    lp = enr.get("license_policy") or {}
                    if isinstance(lp, dict):
                        prof_license_policy.update(lp)
                    defaults_sources = ["sos-catalog"]
                except Exception:
                    pass

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

        # Optional enrichment
        enrich = body.get("enrich")
        if enrich:
            try:
                from zyra.transform.enrich import enrich_items

                items = enrich_items(
                    items,
                    level=str(enrich),
                    timeout=float(body.get("enrich_timeout") or 3.0),
                    workers=int(body.get("enrich_workers") or 4),
                    cache_ttl=int(body.get("cache_ttl") or 86400),
                    offline=bool(body.get("offline") or False),
                    https_only=bool(body.get("https_only") or False),
                    allow_hosts=list(body.get("allow_hosts") or []),
                    deny_hosts=list(body.get("deny_hosts") or []),
                    max_probe_bytes=(body.get("max_probe_bytes")),
                    profile_defaults=prof_defaults,
                    profile_license_policy=prof_license_policy,
                    defaults_sources=defaults_sources,
                )
            except Exception:
                pass

        # If not analyzing, return like GET /search (serialize dataclasses safely)
        if not analyze:
            from zyra.utils.serialize import to_list

            return {"items": to_list(items[: max(0, limit) or None])}

        # Otherwise, perform analysis just like /semantic_search
        from zyra.utils.serialize import compact_dataset

        ctx_items = [
            compact_dataset(i, max_desc_len=240)
            for i in items[: max(1, int(body.get("analysis_limit") or 20))]
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


@router.post("/enrich")
def post_enrich(body: dict, bg: BackgroundTasks) -> dict[str, Any]:
    """POST /enrich: enrich provided items synchronously or as a background job.

    Body keys:
    - items: list of DatasetMetadata-like dicts (required)
    - enrich: level string (default: shallow)
    - enrich_timeout, enrich_workers, cache_ttl
    - async: boolean (if true, enqueue job and return job_id)
    """
    try:
        items = body.get("items")
        if not isinstance(items, list) or not items:
            raise HTTPException(status_code=400, detail="Missing 'items' array")
        do_async = bool(body.get("async") or False)
        if do_async:
            from zyra.api.workers import jobs as jobs_backend

            args = {
                "items": items,
                "enrich": body.get("enrich") or "shallow",
                "enrich_timeout": body.get("enrich_timeout") or 3.0,
                "enrich_workers": body.get("enrich_workers") or 4,
                "cache_ttl": body.get("cache_ttl") or 86400,
                "offline": bool(body.get("offline") or False),
                "https_only": bool(body.get("https_only") or False),
                "allow_hosts": list(body.get("allow_hosts") or []),
                "deny_hosts": list(body.get("deny_hosts") or []),
                "max_probe_bytes": body.get("max_probe_bytes"),
            }
            job_id = jobs_backend.submit_enrich_job(args)
            # In-memory mode: start immediately as a background task
            bg.add_task(jobs_backend.start_enrich_job, job_id, args)
            return {"job_id": job_id, "status": "queued"}
        # Sync path
        from zyra.connectors.discovery import DatasetMetadata
        from zyra.transform.enrich import enrich_items
        from zyra.utils.serialize import to_list

        items_in: list[DatasetMetadata] = []
        for d in items:
            try:
                items_in.append(
                    DatasetMetadata(
                        id=str(d.get("id")),
                        name=str(d.get("name")),
                        description=d.get("description"),
                        source=str(d.get("source")),
                        format=str(d.get("format")),
                        uri=str(d.get("uri")),
                    )
                )
            except Exception:
                continue
        out = enrich_items(
            items_in,
            level=str(body.get("enrich") or "shallow"),
            timeout=float(body.get("enrich_timeout") or 3.0),
            workers=int(body.get("enrich_workers") or 4),
            cache_ttl=int(body.get("cache_ttl") or 86400),
            offline=bool(body.get("offline") or False),
            https_only=bool(body.get("https_only") or False),
            allow_hosts=list(body.get("allow_hosts") or []),
            deny_hosts=list(body.get("deny_hosts") or []),
            max_probe_bytes=body.get("max_probe_bytes"),
        )
        return {"items": to_list(out)}
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"POST /enrich failed: {e}") from e
