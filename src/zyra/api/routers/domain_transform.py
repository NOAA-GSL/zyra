from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks
from pydantic import ValidationError
from zyra.api.models.cli_request import CLIRunRequest
from zyra.api.models.domain_api import DomainRunRequest, DomainRunResponse
from zyra.api.routers.cli import get_cli_matrix, run_cli_endpoint
from zyra.api.schemas.domain_args import normalize_and_validate
from zyra.api.utils.errors import domain_error_response

router = APIRouter(tags=["transform"], prefix="")


@router.post("/transform", response_model=DomainRunResponse)
def transform_run(req: DomainRunRequest, bg: BackgroundTasks) -> DomainRunResponse:
    matrix = get_cli_matrix()
    stage = "transform"
    allowed = set(matrix.get(stage, {}).get("commands", []) or [])
    if req.tool not in allowed:
        return domain_error_response(
            status_code=400,
            err_type="invalid_tool",
            message="Invalid tool for transform domain",
            details={"allowed": sorted(list(allowed))},
        )

    mode = (req.options.mode if req.options else None) or "sync"
    try:
        args = normalize_and_validate(stage, req.tool, req.args)
    except ValidationError as ve:
        return domain_error_response(
            status_code=400,
            err_type="validation_error",
            message="Invalid arguments",
            details={"errors": ve.errors()},
        )
    resp = run_cli_endpoint(
        CLIRunRequest(stage=stage, command=req.tool, args=args, mode=mode), bg
    )
    if getattr(resp, "job_id", None):
        return DomainRunResponse(
            status="accepted",
            job_id=resp.job_id,
            poll=f"/jobs/{resp.job_id}",
            download=f"/jobs/{resp.job_id}/download",
            manifest=f"/jobs/{resp.job_id}/manifest",
        )
    return DomainRunResponse(
        status="ok" if (resp.exit_code or 1) == 0 else "error",
        stdout=getattr(resp, "stdout", None),
        stderr=getattr(resp, "stderr", None),
        exit_code=getattr(resp, "exit_code", None),
    )
