# SPDX-License-Identifier: Apache-2.0
"""Shared swarm orchestration primitives for Zyra."""

from .agents import (
    CliStageAgent,
    MockStageAgent,
    NoopStageAgent,
    StageAgent,
    build_stage_agent,
)
from .core import DEFAULT_MAX_WORKERS, StageContext, SwarmOrchestrator
from .guardrails import (
    BaseGuardrailsAdapter,
    GuardrailsAdapter,
    NullGuardrailsAdapter,
    build_guardrails_adapter,
)
from .memory import (
    NullProvenanceStore,
    ProvenanceStore,
    SQLiteProvenanceStore,
    open_provenance_store,
)
from .spec import StageAgentSpec, load_stage_agent_specs
from .value_engine import suggest as suggest_augmentations

__all__ = [
    "DEFAULT_MAX_WORKERS",
    "StageContext",
    "SwarmOrchestrator",
    "StageAgentSpec",
    "load_stage_agent_specs",
    "StageAgent",
    "CliStageAgent",
    "MockStageAgent",
    "NoopStageAgent",
    "build_stage_agent",
    "BaseGuardrailsAdapter",
    "GuardrailsAdapter",
    "NullGuardrailsAdapter",
    "build_guardrails_adapter",
    "ProvenanceStore",
    "SQLiteProvenanceStore",
    "NullProvenanceStore",
    "open_provenance_store",
    "suggest_augmentations",
]
