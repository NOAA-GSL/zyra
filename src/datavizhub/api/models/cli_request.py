from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CLIRunRequest(BaseModel):
    stage: Literal["acquire", "process", "visualize", "decimate", "run"]
    command: str = Field(..., description="Subcommand within the selected stage")
    args: dict[str, Any] = Field(
        default_factory=dict, description="Command arguments as key/value pairs"
    )
    mode: Literal["sync", "async"] = Field(default="sync")


class CLIRunResponse(BaseModel):
    status: Literal["success", "accepted", "error"]
    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None
    job_id: str | None = None


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed", "canceled"]
    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None
    output_file: str | None = None
    resolved_input_paths: list[str] | None = None
