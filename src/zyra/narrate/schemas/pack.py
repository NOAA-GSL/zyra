# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)


class Status(BaseModel):
    completed: bool = Field(..., description="True if critical path succeeded")
    failed_agents: list[str] = Field(
        default_factory=list, description="Agent IDs that failed or were skipped"
    )


class ErrorEntry(BaseModel):
    agent: str | None = Field(None, description="Agent ID that produced the error")
    message: str
    retried: int | None = Field(None, ge=0)


class ProvenanceEntry(BaseModel):
    agent: str
    model: str | None = None
    started: str | None = Field(
        None, description="RFC3339 timestamp when the agent started"
    )
    prompt_ref: str | None = None
    notes: str | None = None
    duration_ms: int | None = Field(
        None, ge=0, description="Execution duration in milliseconds"
    )

    @field_validator("started")
    @classmethod
    def _started_rfc3339(cls, v: str | None) -> str | None:  # noqa: D401
        """Validate RFC3339 timestamp (basic check using fromisoformat)."""
        if v is None:
            return v
        s = v.strip()
        if "T" not in s:
            raise ValueError("must contain 'T' date/time separator")
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            datetime.fromisoformat(s)
        except Exception as exc:  # pragma: no cover - exercised via higher-level tests
            raise ValueError("invalid RFC3339 timestamp") from exc
        return v


class NarrativePack(BaseModel):
    version: int = Field(0, description="Schema version (integer for v0)")
    inputs: dict[str, Any] = Field(default_factory=dict)
    models: dict[str, Any] = Field(default_factory=dict)
    status: Status
    outputs: dict[str, Any] = Field(default_factory=dict)
    reviews: dict[str, Any] | None = None
    errors: list[ErrorEntry] = Field(default_factory=list)
    provenance: list[ProvenanceEntry] = Field(default_factory=list)

    @field_validator("version")
    @classmethod
    def _version_supported(cls, v: int) -> int:
        if v != 0:
            raise ValueError("unsupported version; expected 0")
        return v

    @model_validator(mode="after")
    def _invariants(self) -> NarrativePack:
        # If status.completed is False, enforce at least one critical agent failed
        if not self.status.completed:
            critical = {"summary", "critic", "editor"}
            if not any(a in critical for a in self.status.failed_agents):
                raise ValueError(
                    "status.completed is false but no critical agent in failed_agents"
                )
        # Monotonic timestamps per agent in provenance (non-decreasing)
        try:
            by_agent: dict[str, list[str]] = {}
            for _i, p in enumerate(self.provenance or []):
                if not isinstance(p, ProvenanceEntry):
                    continue
                if p.started:
                    by_agent.setdefault(p.agent, []).append(p.started)
            for agent, seq in by_agent.items():

                def _to_dt(s: str) -> datetime:
                    s2 = s[:-1] + "+00:00" if s.endswith("Z") else s
                    return datetime.fromisoformat(s2)

                seq_dt = [_to_dt(s) for s in seq]
                if any(seq_dt[i] > seq_dt[i + 1] for i in range(len(seq_dt) - 1)):
                    raise ValueError(
                        f"provenance timestamps not monotonic for agent '{agent}'"
                    )
        except Exception as exc:
            raise ValueError(str(exc)) from exc
        return self


def validate_or_raise(data: Any) -> NarrativePack:
    """Validate data as NarrativePack, raising ValidationError with field paths.

    This helper formats errors to include the failing field `loc` so callers
    can surface actionable messages.
    """
    try:
        return NarrativePack.model_validate(data)
    except ValidationError:
        # Let callers format/handle; API/CLI can map to exit code 2
        raise
