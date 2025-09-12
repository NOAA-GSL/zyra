# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AssetRef(BaseModel):
    uri: str = Field(..., description="zyra://asset/{id} or resolved path/URL")
    name: str | None = None
    media_type: str | None = None
    size: int | None = None


class Bounds(BaseModel):
    west: float
    south: float
    east: float
    north: float


class TimeRange(BaseModel):
    start: str
    end: str


class VariableSpec(BaseModel):
    name: str
    level: str | None = None
    pattern: str | None = None


class OutputSpec(BaseModel):
    path: str | None = None
    media_type: str | None = None


class LogLine(BaseModel):
    stream: Literal["stdout", "stderr", "progress"]
    text: str
    ts: float | None = None


class ErrorInfo(BaseModel):
    type: str
    message: str
    details: dict[str, Any] | None = None
    retriable: bool | None = None
