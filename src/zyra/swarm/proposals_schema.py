# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from typing import Any

try:  # pragma: no cover - optional dependency
    from pydantic import BaseModel, Field
except Exception:  # pragma: no cover - fallback when pydantic missing
    BaseModel = object  # type: ignore
    Field = None  # type: ignore


class ProposalModel(BaseModel):  # type: ignore[misc]
    stage_id: str
    command: str
    args: dict[str, Any]
    justification: str | None = Field(default=None)


def validate_proposal(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(BaseModel, type):  # Pydantic not available
        return data
    model = ProposalModel(**data)
    return model.model_dump()


def schema() -> dict[str, Any]:
    if not isinstance(BaseModel, type):
        return {}
    return ProposalModel.model_json_schema()  # type: ignore[attr-defined]
