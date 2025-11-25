# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .core import SwarmAgentProtocol  # noqa: F401
else:  # pragma: no cover - runtime fallback
    SwarmAgentProtocol = Any

LOG = logging.getLogger("zyra.swarm.guardrails")

try:  # pragma: no cover - guardrails is optional
    import guardrails as _guardrails  # type: ignore
except Exception:  # pragma: no cover - guardrails missing
    _guardrails = None  # noqa: N816


class BaseGuardrailsAdapter:
    """Base class for guardrails adapters."""

    def validate(
        self, agent: SwarmAgentProtocol, outputs: dict[str, Any]
    ) -> dict[str, Any]:
        return outputs


class NullGuardrailsAdapter(BaseGuardrailsAdapter):
    """No-op adapter used when guardrails is disabled or unavailable."""

    pass


class GuardrailsAdapter(BaseGuardrailsAdapter):
    """Guardrails AI adapter backed by a .rail schema file."""

    def __init__(self, schema_path: str, *, strict: bool = False) -> None:
        if not _guardrails:
            raise RuntimeError(
                "guardrails library is not installed (pip install guardrails-ai)"
            )
        self.schema_path = schema_path
        self.strict = strict
        self._guard = None

    def _load_guard(self):
        if self._guard:
            return self._guard
        path = Path(self.schema_path)
        self._guard = _guardrails.Guard.from_rail(str(path))  # type: ignore[attr-defined]
        return self._guard

    def validate(
        self, agent: SwarmAgentProtocol, outputs: dict[str, Any]
    ) -> dict[str, Any]:
        guard = self._load_guard()
        validated: dict[str, Any] = {}
        for key, value in outputs.items():
            raw = value if isinstance(value, str) else json.dumps(value)
            try:
                # guard.parse returns the validated structure (string or dict)
                result = guard.parse(raw)
            except Exception as exc:
                msg = f"guardrails validation failed for {agent.spec.id}:{key}: {exc}"
                if self.strict:
                    raise RuntimeError(msg) from exc
                LOG.warning("%s", msg)
                result = value
            validated[key] = result
        return validated


def build_guardrails_adapter(
    schema_path: str | None, *, strict: bool = False
) -> BaseGuardrailsAdapter:
    """Factory returning the best-effort guardrails adapter."""
    if not schema_path:
        return NullGuardrailsAdapter()
    try:
        return GuardrailsAdapter(schema_path, strict=strict)
    except Exception as exc:
        if strict:
            raise
        LOG.warning("Guardrails disabled: %s", exc)
        return NullGuardrailsAdapter()
