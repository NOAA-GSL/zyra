from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from zyra.api.services import manifest as svc

router = APIRouter(tags=["commands"])


@router.get("/commands")
def commands(
    format: str = Query("json", pattern="^(json|list|summary)$"),
    command_name: str | None = None,
    details: str | None = Query(None, pattern="^(options|example)$"),
    stage: str | None = Query(
        None, pattern="^(acquire|process|visualize|transform|decimate|run)$"
    ),
    q: str | None = None,
    fuzzy_cutoff: float | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Unified commands endpoint with list/summary/json and per-command details.

    - format: json (default), list, or summary
    - command_name: fuzzy-matched command key (e.g., "visualize heatmap")
    - details: when command_name given, return only options or an example
    - stage: filter by stage for list/summary views
    - q: substring filter across names/descriptions for list/summary views
    - fuzzy_cutoff: 0..1 similarity cutoff (default 0.5)
    - refresh: force cache rebuild
    """
    if command_name:
        return svc.get_command(
            command_name=command_name,
            details=details,
            fuzzy_cutoff=fuzzy_cutoff,
            refresh=refresh,
        )
    return svc.list_commands(format=format, stage=stage, q=q, refresh=refresh)
