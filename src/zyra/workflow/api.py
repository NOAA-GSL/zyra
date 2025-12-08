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

    @classmethod
    def load(
        cls, path: str, *, overrides: list[tuple[str, str]] | None = None
    ) -> Workflow:
        """Load a workflow config from YAML/JSON."""

        cfg = _load_config(path)
        _apply_overrides(cfg, overrides)
        cfg = _expand_env(cfg, strict=False)
        return cls(cfg, source_path=path)

    @classmethod
    def from_dict(
        cls, cfg: dict[str, Any], *, overrides: list[tuple[str, str]] | None = None
    ) -> Workflow:
        """Construct a workflow from an in-memory mapping."""

        data = copy.deepcopy(cfg)
        _apply_overrides(data, overrides)
        data = _expand_env(data, strict=False)
        return cls(data)

    def describe(self) -> dict[str, Any]:
        """Return a normalized view of stages."""

        stages = self._cfg.get("stages") or []
        summary = []
        for idx, st in enumerate(stages):
            stage_name = _stage_group_alias(str(st.get("stage", "")))
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

    def run(
        self,
        *,
        capture: bool = False,
        stream: bool = False,
        continue_on_error: bool = False,
    ) -> WorkflowRunResult:
        """Execute stages sequentially using the CLI subprocess."""

        stages = self._cfg.get("stages") or []
        results: list[StageResult] = []
        for st in stages:
            argv = _build_argv_for_stage(st)
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
                    with contextlib.suppress(
                        Exception
                    ):  # pragma: no cover - best effort
                        sys.stdout.write(stdout)
                if stream and stderr:
                    with contextlib.suppress(
                        Exception
                    ):  # pragma: no cover - best effort
                        sys.stderr.write(stderr)
                result = StageResult(
                    stage=_stage_group_alias(str(st.get("stage", ""))),
                    command=str(st.get("command", "")),
                    args=st.get("args") or {},
                    returncode=int(proc.returncode or 0),
                    stdout=stdout,
                    stderr=stderr,
                )
            else:
                proc = subprocess.run(cmd, check=False)
                result = StageResult(
                    stage=_stage_group_alias(str(st.get("stage", ""))),
                    command=str(st.get("command", "")),
                    args=st.get("args") or {},
                    returncode=int(proc.returncode or 0),
                    stdout=None,
                    stderr=None,
                )
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
        """Run a single stage by index or stage name."""

        stages = self._cfg.get("stages") or []
        target: dict[str, Any] | None = None
        if isinstance(name_or_index, int):
            if 0 <= name_or_index < len(stages):
                target = copy.deepcopy(stages[name_or_index])
        else:
            name_norm = _stage_group_alias(str(name_or_index))
            for st in stages:
                if _stage_group_alias(str(st.get("stage", ""))) == name_norm:
                    target = copy.deepcopy(st)
                    break
        if target is None:
            raise IndexError("Stage not found")
        target_args = target.get("args") or {}
        if args:
            target_args.update(args)
            target["args"] = target_args
        argv = _build_argv_for_stage(target)
        cmd = [sys.executable, "-m", "zyra.cli", *argv]
        LOG.debug("Running single stage: %s", " ".join(cmd))
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
                with contextlib.suppress(Exception):  # pragma: no cover
                    sys.stdout.write(stdout)
            if stream and stderr:
                with contextlib.suppress(Exception):  # pragma: no cover
                    sys.stderr.write(stderr)
            result = StageResult(
                stage=_stage_group_alias(str(target.get("stage", ""))),
                command=str(target.get("command", "")),
                args=target_args,
                returncode=int(proc.returncode or 0),
                stdout=stdout,
                stderr=stderr,
            )
        else:
            proc = subprocess.run(cmd, check=False)
            result = StageResult(
                stage=_stage_group_alias(str(target.get("stage", ""))),
                command=str(target.get("command", "")),
                args=target_args,
                returncode=int(proc.returncode or 0),
                stdout=None,
                stderr=None,
            )
        self._results = [result]
        return result

    @property
    def results(self) -> list[StageResult]:
        """Return results from the last run."""

        return self._results


__all__ = ["Workflow", "WorkflowRunResult", "StageResult"]
