from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field
from zyra.api.models.types import AssetRef, ErrorInfo, LogLine


class DomainRunOptions(BaseModel):
    mode: Literal["sync", "async"] | None = Field(default=None)
    sync: bool | None = Field(
        default=None,
        description="Convenience alias for mode; when true -> sync, false -> async",
    )
    timeout_ms: int | None = None
    dry_run: bool | None = None


class DomainRunRequest(BaseModel):
    tool: str = Field(..., description="Tool/command name within the domain")
    args: dict[str, Any] = Field(
        default_factory=dict, description="Command arguments as key/value pairs"
    )
    options: DomainRunOptions | None = None


class DomainRunResponse(BaseModel):
    status: Literal["ok", "error", "accepted"]
    # Extended envelope fields (non-breaking additions)
    result: Any | None = None
    assets: list[AssetRef] | None = None
    logs: list[LogLine] | None = None
    error: ErrorInfo | None = None
    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None
    job_id: str | None = None
    poll: str | None = None
    download: str | None = None
    manifest: str | None = None
