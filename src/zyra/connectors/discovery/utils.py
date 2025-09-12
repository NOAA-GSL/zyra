# SPDX-License-Identifier: Apache-2.0
"""Shared utilities for discovery backends.

Includes helpers shared by local/remote discovery paths to keep logic
consistent across CLI and API layers.
"""

from __future__ import annotations

import re


def slugify(s: str) -> str:
    """Return a lowercase, hyphenated slug for arbitrary text.

    Replaces non-word characters with ``-`` and trims leading/trailing hyphens.
    """
    return re.sub(r"\W+", "-", s).strip("-").lower()


def compute_inclusion(
    ogc_wms: object,
    ogc_records: object,
    prof_sources: dict | None,
    *,
    remote_only: bool,
    include_local_flag: bool,
    catalog_file_flag: str | None,
) -> tuple[bool, bool, str | None]:
    """Decide remote presence and whether to include local catalog.

    Parameters
    - ogc_wms: CLI or plan-provided WMS endpoint(s) (str/list/None)
    - ogc_records: CLI or plan-provided Records endpoint(s) (str/list/None)
    - prof_sources: profile sources mapping (may contain 'local', 'ogc_wms', 'ogc_records')
    - remote_only: if True, disable local catalog inclusion
    - include_local_flag: explicit request to include local alongside remote
    - catalog_file_flag: CLI or plan-provided catalog file path

    Returns
    - include_local (bool), any_remote (bool), catalog_path (str|None)
    """
    ps = prof_sources or {}
    # Determine any remote sources from CLI/plan flags or profile
    any_remote = bool(ogc_wms or ogc_records)
    if not any_remote:
        prof_has_remote = bool(
            (isinstance(ps.get("ogc_wms"), list) and ps.get("ogc_wms"))
            or (isinstance(ps.get("ogc_records"), list) and ps.get("ogc_records"))
        )
        any_remote = any_remote or prof_has_remote

    # Resolve catalog file: CLI/plan flag overrides profile local.catalog_file
    catalog_path = catalog_file_flag
    if not catalog_path:
        local = ps.get("local") if isinstance(ps.get("local"), dict) else None
        if isinstance(local, dict):
            catalog_path = local.get("catalog_file")
    local_explicit = bool(catalog_path)

    if remote_only:
        return False, any_remote, catalog_path

    # Include local unless (a) remote present and (b) not explicitly allowed and (c) no explicit local path
    include_local = include_local_flag or (not any_remote) or local_explicit
    return include_local, any_remote, catalog_path
