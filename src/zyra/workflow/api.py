# SPDX-License-Identifier: Apache-2.0
"""Programmatic workflow runner."""

from __future__ import annotations

import contextlib
import copy
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from zyra.pipeline_runner import (
    _apply_overrides,
    _build_argv_for_stage,
    _expand_env,
    _load_config,
    _stage_group_alias,
)

LOG = logging.getLogger(__name__)


@dataclass
class StageResult:
    """Result of a single stage execution."""

    stage: str
    command: str
    args: dict[str, Any]
    returncode: int
    stdout: str | None = None
    stderr: str | None = None


@dataclass
class WorkflowRunResult:
    """Aggregate result for a workflow run."""

    stages: list[StageResult] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return all(s.returncode == 0 for s in self.stages)


class Workflow:
    """Workflow loader/runner with CLI parity."""

    def __init__(self, cfg: dict[str, Any], *, source_path: str | None = None) -> None:
        self._cfg = cfg
        self._source_path = Path(source_path) if source_path else None
        self._results: list[StageResult] = []

    @staticmethod
    def _normalized_stage(stage: dict[str, Any]) -> str:
        return _stage_group_alias(str(stage.get("stage", "")))

    @classmethod
    def load(
        cls, path: str, *, overrides: list[tuple[str, str]] | None = None
    ) -> Workflow:
        """Load a workflow config from YAML/JSON.

        Args:
            path: File path to a YAML or JSON workflow configuration file.
            overrides: Optional list of (key, value) tuples to override
                configuration values. Follows the same format as the ``--set``
                CLI flag (e.g., ``[("stage.key", "value")]``).

        Returns:
            Workflow instance with the loaded and processed configuration.

        Raises:
            FileNotFoundError: If the workflow file does not exist.
            ValueError: If the file cannot be parsed as YAML or JSON.
        """

        cfg = _load_config(path)
        _apply_overrides(cfg, overrides)
        cfg = _expand_env(cfg, strict=False)
        return cls(cfg, source_path=path)

    @classmethod
    def from_dict(
        cls, cfg: dict[str, Any], *, overrides: list[tuple[str, str]] | None = None
    ) -> Workflow:
        """Construct a workflow from an in-memory mapping.

        Args:
            cfg: Dictionary containing workflow configuration with a ``stages``
                key. Each stage should include ``stage``, ``command``, and
                optional ``args`` keys.
            overrides: Optional list of (key, value) tuples to override
                configuration values, following the same format as the
                ``--set`` CLI flag.

        Returns:
            Workflow instance with the processed configuration.
        """

        data = copy.deepcopy(cfg)
        _apply_overrides(data, overrides)
        data = _expand_env(data, strict=False)
        return cls(data)

    def describe(self) -> dict[str, Any]:
        """Return a normalized view of workflow stages.

        Returns:
            Dict with:
            - ``source``: path to the source file if loaded from disk, else None.
            - ``stages``: list of stage dicts containing:
                - ``index``: 0-based stage index
                - ``stage``: normalized stage name (e.g., ``process``)
                - ``command``: command name within the stage
                - ``args``: argument mapping for the stage

        Example:
            ``{'source': 'workflow.yml', 'stages': [{'index': 0, 'stage': 'process', ...}]}``
        """

        stages = self._cfg.get("stages") or []
        summary = []
        for idx, st in enumerate(stages):
            stage_name = self._normalized_stage(st)
            summary.append(
                {
                    "index": idx,
                    "stage": stage_name,
                    "command": st.get("command"),
                    "args": st.get("args") or {},
                }
            )
        return {
            "source": str(self._source_path) if self._source_path else None,
            "stages": summary,
        }

    def _execute_stage(
        self, stage: dict[str, Any], *, capture: bool, stream: bool
    ) -> StageResult:
        argv = _build_argv_for_stage(stage)
        cmd = [sys.executable, "-m", "zyra.cli", *argv]
        LOG.debug("Running workflow stage: %s", " ".join(cmd))
        if capture or stream:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            if stream and stdout:
                with contextlib.suppress(Exception):  # pragma: no cover - best effort
                    sys.stdout.write(stdout)
            if stream and stderr:
                with contextlib.suppress(Exception):  # pragma: no cover - best effort
                    sys.stderr.write(stderr)
            return StageResult(
                stage=self._normalized_stage(stage),
                command=str(stage.get("command", "")),
                args=stage.get("args") or {},
                returncode=int(proc.returncode or 0),
                stdout=stdout,
                stderr=stderr,
            )
        proc = subprocess.run(cmd, check=False)
        return StageResult(
            stage=self._normalized_stage(stage),
            command=str(stage.get("command", "")),
            args=stage.get("args") or {},
            returncode=int(proc.returncode or 0),
            stdout=None,
            stderr=None,
        )

    def run(
        self,
        *,
        capture: bool = False,
        stream: bool = False,
        continue_on_error: bool = False,
    ) -> WorkflowRunResult:
        """Execute stages sequentially using the CLI subprocess.

        Args:
            capture: If True, capture stdout/stderr from each stage.
            stream: If True and ``capture`` is True, write captured output to
                stdout/stderr while also returning it.
            continue_on_error: If True, continue executing remaining stages even
                when a stage fails. If False (default), stop at the first failure.

        Returns:
            WorkflowRunResult containing results for all executed stages.
        """

        stages = self._cfg.get("stages") or []
        results: list[StageResult] = []
        for st in stages:
            result = self._execute_stage(st, capture=capture, stream=stream)
            results.append(result)
            if result.returncode != 0 and not continue_on_error:
                break
        self._results = results
        return WorkflowRunResult(stages=results)

    def run_stage(
        self,
        name_or_index: str | int,
        *,
        args: dict[str, Any] | None = None,
        capture: bool = False,
        stream: bool = False,
    ) -> StageResult:
        """Run a single stage by index or stage name.

        Args:
            name_or_index: Stage index (0-based) or stage name to execute.
            args: Optional dict of arguments to override or add to the stage's args.
            capture: If True, capture stdout/stderr from the stage execution.
            stream: If True and ``capture`` is True, write captured output to
                stdout/stderr while also returning it.

        Returns:
            StageResult for the requested stage.

        Raises:
            IndexError: If the stage name or index is not found.
        """

        stages = self._cfg.get("stages") or []
        target: dict[str, Any] | None = None
        if isinstance(name_or_index, int):
            if 0 <= name_or_index < len(stages):
                target = copy.deepcopy(stages[name_or_index])
        else:
            name_norm = _stage_group_alias(str(name_or_index))
            for st in stages:
                if self._normalized_stage(st) == name_norm:
                    target = copy.deepcopy(st)
                    break
        if target is None:
            raise IndexError(f"Stage not found: {name_or_index!r}")
        target_args = target.get("args") or {}
        if args:
            target_args.update(args)
            target["args"] = target_args
        result = self._execute_stage(target, capture=capture, stream=stream)
        self._results = [result]
        return result

    @property
    def results(self) -> list[StageResult]:
        """Return results from the last run."""

        return self._results


__all__ = ["Workflow", "WorkflowRunResult", "StageResult"]
