from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


class CLIRunRequest(BaseModel):
    stage: Literal["acquire", "process", "visualize", "decimate", "run"]
    command: str = Field(..., description="Subcommand within the selected stage")
    args: Dict[str, Any] = Field(default_factory=dict, description="Command arguments as key/value pairs")
    mode: Literal["sync", "async"] = Field(default="sync")


class CLIRunResponse(BaseModel):
    status: Literal["success", "accepted", "error"]
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    exit_code: Optional[int] = None
    job_id: Optional[str] = None


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed", "canceled"]
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    exit_code: Optional[int] = None
    output_file: Optional[str] = None
    resolved_input_paths: Optional[list[str]] = None
