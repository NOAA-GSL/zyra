"""Dataset discovery backends and CLI for `zyra search`.

Implements a lightweight local backend that searches the packaged
SOS dataset catalog at `zyra.assets.metadata/sos_dataset_metadata.json`.

Usage examples:
  - zyra search "tsunami"
  - zyra search "GFS" --json
  - Use the selected URI with the matching connector, e.g.:
      zyra acquire ftp "$(zyra search 'earthquake' --select 1)" -o out.bin
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

try:  # Prefer standard library importlib.resources
    from importlib import resources as importlib_resources
except Exception:  # pragma: no cover - fallback for very old Python
    import importlib_resources  # type: ignore


@dataclass
class DatasetMetadata:
    id: str
    name: str
    description: str | None
    source: str
    format: str
    uri: str


class DiscoveryBackend:
    """Interface for dataset discovery backends."""

    def search(self, query: str, *, limit: int = 10) -> list[DatasetMetadata]:
        raise NotImplementedError


class LocalCatalogBackend(DiscoveryBackend):
    """Local backend backed by the packaged SOS catalog JSON.

    File: `zyra.assets.metadata/sos_dataset_metadata.json`
    Schema (subset of fields used here):
      - url (str): public catalog URL
      - title (str): dataset title
      - description (str): dataset description
      - keywords (list[str]): search tags
      - ftp_download (str|None): FTP base path to assets (preferred URI)
    """

    _cache: list[dict[str, Any]] | None = None

    def __init__(
        self, catalog_path: str | None = None, *, weights: dict[str, int] | None = None
    ) -> None:
        self._catalog_path = catalog_path
        self._weights = weights or {}

    def _load(self) -> list[dict[str, Any]]:
        if self._cache is not None:
            return self._cache
        data: list[dict[str, Any]]
        if self._catalog_path:
            from pathlib import Path

            # Support packaged resource references: pkg:package/resource or pkg:package:resource
            cp = str(self._catalog_path)
            if cp.startswith("pkg:"):
                ref = cp[4:]
                if ":" in ref and "/" not in ref:
                    pkg, res = ref.split(":", 1)
                else:
                    parts = ref.split("/", 1)
                    pkg = parts[0]
                    res = parts[1] if len(parts) > 1 else "sos_dataset_metadata.json"
                path = importlib_resources.files(pkg).joinpath(res)
                with importlib_resources.as_file(path) as p:
                    data = json.loads(p.read_text(encoding="utf-8"))
            else:
                data = json.loads(Path(cp).read_text(encoding="utf-8"))
        else:
            pkg = "zyra.assets.metadata"
            path = importlib_resources.files(pkg).joinpath("sos_dataset_metadata.json")
            with importlib_resources.as_file(path) as p:
                data = json.loads(p.read_text(encoding="utf-8"))
        # Store as-is; we'll normalize per-result on demand
        self._cache = data
        return data

    def _match_score(self, item: dict[str, Any], rx: re.Pattern[str]) -> int:
        title = str(item.get("title") or "")
        desc = str(item.get("description") or "")
        keywords = item.get("keywords") or []
        score = 0
        if rx.search(title):
            score += int(self._weights.get("title", 3))
        if rx.search(desc):
            score += int(self._weights.get("description", 2))
        for kw in keywords:
            if isinstance(kw, str) and rx.search(kw):
                score += int(self._weights.get("keywords", 1))
        return score

    @staticmethod
    def _slug_from_url(url: str) -> str:
        # e.g., https://sos.noaa.gov/catalog/datasets/tsunami-history/ -> tsunami-history
        m = re.search(r"/datasets/([^/]+)/?", url)
        return m.group(1) if m else re.sub(r"\W+", "-", url).strip("-")

    def _normalize(self, item: dict[str, Any]) -> DatasetMetadata:
        url = str(item.get("url") or "")
        title = str(item.get("title") or "")
        desc = str(item.get("description") or "") or None
        ftp = item.get("ftp_download")
        uri = str(ftp or url)
        fmt = "FTP" if ftp else "HTML"
        return DatasetMetadata(
            id=self._slug_from_url(url) if url else title.lower().replace(" ", "-"),
            name=title or (url or uri),
            description=desc,
            source="sos-catalog",
            format=fmt,
            uri=uri,
        )

    def search(self, query: str, *, limit: int = 10) -> list[DatasetMetadata]:
        data = self._load()
        # Token-aware matching: break the query into words and score per-token
        tokens = [t for t in re.split(r"\W+", query) if t]
        token_patterns = [re.compile(re.escape(t), re.IGNORECASE) for t in tokens if len(t) >= 3]
        scored: list[tuple[int, dict[str, Any]]] = []
        if token_patterns:
            for it in data:
                s = 0
                for pat in token_patterns:
                    s += self._match_score(it, pat)
                if s > 0:
                    scored.append((s, it))
        else:
            # Fallback to phrase search when no meaningful tokens extracted
            rx = re.compile(re.escape(query), re.IGNORECASE)
            for it in data:
                s = self._match_score(it, rx)
                if s > 0:
                    scored.append((s, it))
        # Sort by score desc, then title asc for stability
        scored.sort(key=lambda t: (-t[0], str(t[1].get("title") or "")))
        results = [self._normalize(it) for _, it in scored[: max(0, limit) or None]]
        return results


def _print_table(items: Iterable[DatasetMetadata]) -> None:
    rows = [("ID", "Name", "Format", "URI")]
    for d in items:
        rows.append((d.id, d.name, d.format, d.uri))
    # Compute simple column widths with caps
    caps = (32, 40, 10, 60)
    widths = [
        min(max(len(str(r[i])) for r in rows), caps[i]) for i in range(len(rows[0]))
    ]

    def _fit(s: str, w: int) -> str:
        if len(s) <= w:
            return s.ljust(w)
        return s[: max(0, w - 1)] + "\u2026"

    for i, r in enumerate(rows):
        line = "  ".join(_fit(str(r[j]), widths[j]) for j in range(len(r)))
        print(line)
        if i == 0:
            print("  ".join("-" * w for w in widths))


def register_cli(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "query",
        nargs="?",
        help="Search query (matches title/keywords/description)",
    )
    p.add_argument(
        "--query",
        "-q",
        dest="q",
        help="Search query (alternative to positional)",
    )
    p.add_argument(
        "-l",
        "--limit",
        type=int,
        default=10,
        help="Maximum number of results (default: 10)",
    )
    p.add_argument(
        "--catalog-file",
        help=("Path to a local catalog JSON file (overrides packaged SOS catalog)"),
    )
    p.add_argument(
        "--include-local",
        action="store_true",
        help=("When remote sources are provided, also include local catalog results"),
    )
    p.add_argument(
        "--profile",
        help=("Name of a bundled profile under zyra.assets.profiles (e.g., sos)"),
    )
    p.add_argument(
        "--profile-file",
        help=(
            "Path to a JSON profile describing sources (local/ogc) and optional scoring weights"
        ),
    )
    p.add_argument(
        "--semantic-analyze",
        action="store_true",
        help=(
            "Perform general search and send results to LLM for analysis/ranking (prints summary and picks)"
        ),
    )
    p.add_argument(
        "--analysis-limit",
        type=int,
        default=20,
        help="Max number of results to include in LLM analysis (default: 20)",
    )
    p.add_argument(
        "--semantic",
        help=(
            "Natural-language semantic search; plans sources via LLM and executes backends"
        ),
    )
    p.add_argument(
        "--show-plan",
        action="store_true",
        help="Print the generated semantic search plan (JSON)",
    )
    # Optional remote discovery: OGC WMS capabilities
    p.add_argument(
        "--ogc-wms",
        help=(
            "WMS GetCapabilities URL to search (remote). If provided, results"
            " include remote matches; use --remote-only to skip local catalog."
        ),
    )
    p.add_argument(
        "--remote-only",
        action="store_true",
        help="When used with --ogc-wms, only show remote results",
    )
    p.add_argument(
        "--ogc-records",
        help=(
            "OGC API - Records items URL to search (remote). Often ends with /collections/{id}/items"
        ),
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format",
    )
    p.add_argument(
        "--yaml",
        action="store_true",
        help="Output results in YAML format",
    )
    p.add_argument(
        "--select",
        type=int,
        help=("Select a single result by 1-based index and print its URI only"),
    )

    def _cmd(ns: argparse.Namespace) -> int:
        items: list[DatasetMetadata] = []
        # Semantic search (LLM-planned)
        if getattr(ns, "semantic", None):
            try:
                items = _semantic_search(ns)
            except Exception as e:
                print(f"Semantic search failed: {e}", file=__import__("sys").stderr)
                return 2
            return _emit_results(ns, items)
        # Semantic analysis: general search then LLM analysis over results
        if getattr(ns, "semantic_analyze", None):
            try:
                return _semantic_analyze(ns)
            except Exception as e:
                print(f"Semantic analysis failed: {e}", file=__import__("sys").stderr)
                return 2
        # Non-semantic path requires a query
        effective_query = getattr(ns, "query", None) or getattr(ns, "q", None)
        if not effective_query:
            print(
                "error: the following arguments are required: query",
                file=__import__("sys").stderr,
            )
            return 2
        # Optional profile(s)
        prof_sources: dict[str, Any] = {}
        prof_weights: dict[str, int] = {}
        # Bundled profile by name
        if getattr(ns, "profile", None):
            try:
                pkg = "zyra.assets.profiles"
                res = f"{ns.profile}.json"
                path = importlib_resources.files(pkg).joinpath(res)
                with importlib_resources.as_file(path) as p:
                    prof0 = json.loads(p.read_text(encoding="utf-8"))
                prof_sources.update(dict(prof0.get("sources") or {}))
                prof_weights.update(
                    {k: int(v) for k, v in (prof0.get("weights") or {}).items()}
                )
            except Exception as e:
                print(
                    f"Failed to load bundled profile '{ns.profile}': {e}",
                    file=__import__("sys").stderr,
                )
                return 2
        # External profile file (overrides bundled)
        if getattr(ns, "profile_file", None):
            try:
                from pathlib import Path

                prof = json.loads(Path(ns.profile_file).read_text(encoding="utf-8"))
                prof_sources.update(dict(prof.get("sources") or {}))
                prof_weights.update(
                    {k: int(v) for k, v in (prof.get("weights") or {}).items()}
                )
            except Exception as e:
                print(f"Failed to load profile: {e}", file=__import__("sys").stderr)
                return 2

        # Decide whether to include local: default to remote-only when any remote
        # sources are provided, unless explicitly including local.
        include_local = not ns.remote_only
        # Determine remote presence from CLI flags and profile
        any_remote = bool(
            getattr(ns, "ogc_wms", None) or getattr(ns, "ogc_records", None)
        )
        # profile-based remote (set later) also counts; we'll recompute after loading profile
        if not ns.remote_only and include_local:
            # After profile load, we can refine below
            pass

        if not ns.remote_only:
            # CLI override takes precedence, else use profile's local.catalog_file
            cat_path = getattr(ns, "catalog_file", None)
            if not cat_path:
                local = (
                    prof_sources.get("local")
                    if isinstance(prof_sources.get("local"), dict)
                    else None
                )
                if isinstance(local, dict):
                    cat_path = local.get("catalog_file")
            # If remote requested and no local explicitly configured and not include-local, skip local
            # Recompute any_remote including profile sources
            prof_has_remote = bool(
                (
                    isinstance(prof_sources.get("ogc_wms"), list)
                    and prof_sources.get("ogc_wms")
                )
                or (
                    isinstance(prof_sources.get("ogc_records"), list)
                    and prof_sources.get("ogc_records")
                )
            )
            any_remote = any_remote or prof_has_remote
            local_explicit = bool(cat_path)
            if (not ns.include_local) and any_remote and not local_explicit:
                include_local = False
            if include_local:
                items.extend(
                    LocalCatalogBackend(cat_path, weights=prof_weights).search(
                        effective_query, limit=ns.limit
                    )
                )
        # Optional remote OGC WMS
        # Remote WMS: combine CLI flag and profile list
        wms_urls = []
        if getattr(ns, "ogc_wms", None):
            wms_urls.append(ns.ogc_wms)
        prof_wms = prof_sources.get("ogc_wms") or []
        if isinstance(prof_wms, list):
            wms_urls.extend([u for u in prof_wms if isinstance(u, str)])
        for wurl in wms_urls:
            try:
                from .ogc import OGCWMSBackend

                rem = OGCWMSBackend(wurl, weights=prof_weights).search(
                    effective_query, limit=ns.limit
                )
                items.extend(rem)
            except Exception as e:
                print(
                    f"Remote OGC WMS search failed: {e}",
                    file=__import__("sys").stderr,
                )
        # Remote OGC API - Records: combine CLI flag and profile list
        rec_urls = []
        if getattr(ns, "ogc_records", None):
            rec_urls.append(ns.ogc_records)
        prof_rec = prof_sources.get("ogc_records") or []
        if isinstance(prof_rec, list):
            rec_urls.extend([u for u in prof_rec if isinstance(u, str)])
        for rurl in rec_urls:
            try:
                from .ogc_records import OGCRecordsBackend

                rec = OGCRecordsBackend(rurl, weights=prof_weights).search(
                    effective_query, limit=ns.limit
                )
                items.extend(rec)
            except Exception as e:
                print(
                    f"Remote OGC Records search failed: {e}",
                    file=__import__("sys").stderr,
                )
        return _emit_results(ns, items)

    p.set_defaults(func=_cmd)


def _emit_results(ns: argparse.Namespace, items: list[DatasetMetadata]) -> int:
    # Respect overall limit
    items = items[: max(0, ns.limit) or None]
    if ns.select is not None:
        idx = ns.select
        if idx < 1 or idx > len(items):
            print(
                f"--select index out of range (1..{len(items)})",
                file=__import__("sys").stderr,
            )
            return 2
        print(items[idx - 1].uri)
        return 0
    if ns.json and ns.yaml:
        print("Choose one of --json or --yaml", file=__import__("sys").stderr)
        return 2
    if ns.json:
        out = [d.__dict__ for d in items]
        print(json.dumps(out, indent=2))
        return 0
    if ns.yaml:
        try:
            import yaml  # type: ignore

            out = [d.__dict__ for d in items]
            print(yaml.safe_dump(out, sort_keys=False))
            return 0
        except Exception:
            print(
                "PyYAML is not installed. Use --json or install PyYAML.",
                file=__import__("sys").stderr,
            )
            return 2
    _print_table(items)
    return 0


def _semantic_search(ns: argparse.Namespace) -> list[DatasetMetadata]:
    # Plan with the same LLM provider/model as Wizard
    from zyra.wizard import _select_provider  # type: ignore[attr-defined]
    from zyra.wizard.prompts import load_semantic_search_prompt

    client = _select_provider(None, None)
    sys_prompt = load_semantic_search_prompt()
    user = (
        "Given a user's dataset request, produce a minimal JSON search plan.\n"
        f"User request: {ns.semantic}\n"
        "If unsure about endpoints, prefer profile 'sos'. Keep keys minimal."
    )
    plan_raw = client.generate(sys_prompt, user)
    try:
        plan = json.loads(plan_raw.strip())
    except Exception:
        plan = {"query": ns.semantic, "profile": "sos"}
    # Apply CLI overrides
    if getattr(ns, "limit", None):
        plan["limit"] = ns.limit
    # Heuristic: switch from 'sos' when SST/NASA or pygeoapi terms detected
    q = str(plan.get("query") or ns.semantic)
    wms_urls = plan.get("ogc_wms") or []
    rec_urls = plan.get("ogc_records") or []
    profile = plan.get("profile")
    if (not profile or profile == "sos") and not wms_urls and not rec_urls:
        ql = q.lower()
        if "sea surface temperature" in ql or "sst" in ql or "nasa" in ql:
            plan["profile"] = "gibs"
        elif "lake" in ql or "pygeoapi" in ql:
            plan["profile"] = "pygeoapi"

    # Execute using the same backends as normal search
    from zyra.connectors.discovery.ogc import OGCWMSBackend
    from zyra.connectors.discovery.ogc_records import OGCRecordsBackend

    q = str(plan.get("query") or ns.semantic)
    limit = int(plan.get("limit", ns.limit or 10))
    include_local = bool(plan.get("include_local", False))
    remote_only = bool(plan.get("remote_only", False))
    profile = plan.get("profile")
    catalog_file = plan.get("catalog_file")
    wms_urls = plan.get("ogc_wms") or []
    rec_urls = plan.get("ogc_records") or []

    prof_sources: dict[str, Any] = {}
    prof_weights: dict[str, int] = {}
    if isinstance(profile, str) and profile:
        from contextlib import suppress
        from importlib import resources as ir

        with suppress(Exception):
            base = ir.files("zyra.assets.profiles").joinpath(profile + ".json")
            with ir.as_file(base) as p:
                pr = json.loads(p.read_text(encoding="utf-8"))
            prof_sources = dict(pr.get("sources") or {})
            prof_weights = {k: int(v) for k, v in (pr.get("weights") or {}).items()}

    results: list[DatasetMetadata] = []
    # Local inclusion: mirror default behavior (remote-only when remote present unless include_local)
    any_remote = bool(
        wms_urls or rec_urls or (isinstance(prof_sources.get("ogc_wms"), list) and prof_sources.get("ogc_wms")) or (isinstance(prof_sources.get("ogc_records"), list) and prof_sources.get("ogc_records"))
    )
    if not remote_only:
        cat = catalog_file
        if not cat:
            local = prof_sources.get("local") if isinstance(prof_sources.get("local"), dict) else None
            if isinstance(local, dict):
                cat = local.get("catalog_file")
        local_explicit = bool(cat)
        include_local_eff = include_local or (not any_remote)
        if include_local_eff or local_explicit:
            results.extend(LocalCatalogBackend(cat, weights=prof_weights).search(q, limit=limit))

    # Remote WMS
    prof_wms = prof_sources.get("ogc_wms") or []
    if isinstance(prof_wms, list):
        wms_urls = list(wms_urls) + [u for u in prof_wms if isinstance(u, str)]
    from contextlib import suppress
    for u in wms_urls:
        with suppress(Exception):
            results.extend(OGCWMSBackend(u, weights=prof_weights).search(q, limit=limit))
    # Remote Records
    prof_rec = prof_sources.get("ogc_records") or []
    if isinstance(prof_rec, list):
        rec_urls = list(rec_urls) + [u for u in prof_rec if isinstance(u, str)]
    for u in rec_urls:
        with suppress(Exception):
            results.extend(OGCRecordsBackend(u, weights=prof_weights).search(q, limit=limit))

    # Optional show-plan
    if getattr(ns, "show_plan", False):
        try:
            effective = {
                "query": q,
                "limit": limit,
                "profile": profile,
                "catalog_file": catalog_file,
                "include_local": include_local,
                "remote_only": remote_only,
                "ogc_wms": wms_urls or None,
                "ogc_records": rec_urls or None,
            }
            print(json.dumps(plan, indent=2))
            print(json.dumps({k: v for k, v in effective.items() if v}, indent=2))
        except Exception:
            pass

    return results


def _semantic_analyze(ns: argparse.Namespace) -> int:
    # 1) Perform a broad search using provided flags (reuse normal path)
    # We'll emulate non-semantic search execution path to collect items
    from types import SimpleNamespace

    temp_ns = SimpleNamespace(**vars(ns))
    temp_ns.semantic = None
    # Build up items using the same code paths
    items: list[DatasetMetadata] = []
    # Local
    eff_query = getattr(ns, "query", None) or getattr(ns, "q", None) or ""
    if not getattr(ns, "remote_only", False):
        items.extend(
            LocalCatalogBackend(getattr(ns, "catalog_file", None)).search(
                eff_query, limit=ns.limit
            )
        )
    # WMS
    if getattr(ns, "ogc_wms", None):
        from .ogc import OGCWMSBackend

        items.extend(OGCWMSBackend(ns.ogc_wms).search(eff_query, limit=ns.limit))
    # Records
    if getattr(ns, "ogc_records", None):
        from .ogc_records import OGCRecordsBackend

        items.extend(OGCRecordsBackend(ns.ogc_records).search(eff_query, limit=ns.limit))
    # 2) Analyze via LLM
    import json as _json

    from zyra.wizard import _select_provider  # type: ignore[attr-defined]
    from zyra.wizard.prompts import load_semantic_analysis_prompt

    def compact(d: DatasetMetadata) -> dict[str, Any]:
        desc = d.description or ""
        if len(desc) > 240:
            desc = desc[: 239] + "…"
        return {
            "id": d.id,
            "name": d.name,
            "description": desc,
            "source": d.source,
            "format": d.format,
            "uri": d.uri,
        }

    ctx_items = [compact(i) for i in items[: max(1, getattr(ns, "analysis_limit", 20))]]
    client = _select_provider(None, None)
    sys_prompt = load_semantic_analysis_prompt()
    user = _json.dumps({"query": eff_query, "results": ctx_items})
    raw = client.generate(sys_prompt, user)
    try:
        analysis = _json.loads(raw.strip())
    except Exception:
        analysis = {"summary": raw.strip(), "picks": []}
    # Emit analysis; respect --json
    out = {
        "query": eff_query,
        "items": ctx_items,
        "analysis": analysis,
    }
    if getattr(ns, "json", False):
        print(_json.dumps(out, indent=2))
    else:
        print(analysis.get("summary", ""))
        picks = analysis.get("picks", []) or []
        if picks:
            print("")
            print("Top picks:")
            for p in picks:
                print(f"- {p.get('id')}: {p.get('reason')}")
    return 0
