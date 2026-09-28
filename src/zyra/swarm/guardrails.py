# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import logging
import sys
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


def guardrails_install_hint() -> str:
    """Return an install hint for guardrails that fits the running Python.

    The ``zyra[guardrails]`` extra is limited to Python <3.15 because its
    litellm dependency has no patched release for newer interpreters.
    """
    if sys.version_info >= (3, 15):
        return (
            "guardrails is not supported on Python 3.15+ yet: the zyra[guardrails] "
            "extra is limited to Python <3.15 because its litellm dependency has "
            "no patched release for newer Pythons. Do not install guardrails-ai "
            "directly; use Python 3.10-3.14 to enable guardrails."
        )
    return 'guardrails library is not installed; pip install "zyra[guardrails]"'


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
            raise RuntimeError(guardrails_install_hint())
        self.schema_path = schema_path
        self.strict = strict
        self._guard = None

    def _load_guard(self):
        if self._guard:
            return self._guard
        path = Path(self.schema_path)
        self._guard = _guardrails.Guard.for_rail(str(path))  # type: ignore[attr-defined]
        return self._guard

    def validate(
        self, agent: SwarmAgentProtocol, outputs: dict[str, Any]
    ) -> dict[str, Any]:
        guard = self._load_guard()
        validated: dict[str, Any] = {}
        for key, value in outputs.items():
            raw = value if isinstance(value, str) else json.dumps(value)
            try:
                # guard.validate returns a ValidationOutcome with
                # .validation_passed (bool) and .validated_output
                result = guard.validate(raw)
            except Exception as exc:
                msg = f"guardrails validation failed for {agent.spec.id}:{key}: {exc}"
                if self.strict:
                    raise RuntimeError(msg) from exc
                LOG.warning("%s", msg)
                validated_value = value
            else:
                passed = getattr(result, "validation_passed", True)
                if not passed:
                    msg = (
                        f"guardrails validation did not pass for "
                        f"{agent.spec.id}:{key}"
                    )
                    if self.strict:
                        raise RuntimeError(msg)
                    LOG.warning("%s – falling back to original value", msg)
                    validated_value = value
                else:
                    validated_value = getattr(result, "validated_output", result)
            validated[key] = validated_value
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
