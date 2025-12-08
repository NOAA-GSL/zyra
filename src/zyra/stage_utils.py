# SPDX-License-Identifier: Apache-2.0
"""Stage normalization helpers shared across manifest and plugins."""

from __future__ import annotations

import contextlib
import logging

from zyra.wizard.manifest import DOMAIN_ALIAS_MAP


def normalize_stage_name(stage: str) -> str:
    """Normalize a stage name using CLI alias rules."""

    stage_norm = stage.strip().lower().replace("-", " ")
    stage_norm = " ".join(stage_norm.split())
    with contextlib.suppress(Exception):
        from zyra.pipeline_runner import _stage_group_alias

        return _stage_group_alias(stage_norm)
    with contextlib.suppress(Exception):
        logging.getLogger(__name__).debug(
            "stage normalization fallback applied for %s", stage_norm
        )
    return DOMAIN_ALIAS_MAP.get(stage_norm, stage_norm)


__all__ = ["normalize_stage_name"]
