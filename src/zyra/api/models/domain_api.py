# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from zyra.api.models.types import AssetRef, ErrorInfo, LogLine
from zyra.api.schemas import domain_args as da


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


# ---- Typed request variants to improve OpenAPI (discriminated by `tool`) ----


# Visualize
class VisualizeHeatmapRun(DomainRunRequest):
    tool: Literal["heatmap"]
    args: da.VisualizeHeatmapArgs  # type: ignore[assignment]


class VisualizeContourRun(DomainRunRequest):
    tool: Literal["contour"]
    args: da.VisualizeContourArgs  # type: ignore[assignment]


class VisualizeAnimateRun(DomainRunRequest):
    tool: Literal["animate"]
    args: da.VisualizeAnimateArgs  # type: ignore[assignment]


class VisualizeTimeSeriesRun(DomainRunRequest):
    tool: Literal["timeseries"]
    args: da.VisualizeTimeSeriesArgs  # type: ignore[assignment]


class VisualizeVectorRun(DomainRunRequest):
    tool: Literal["vector"]
    args: da.VisualizeVectorArgs  # type: ignore[assignment]


class VisualizeComposeVideoRun(DomainRunRequest):
    tool: Literal["compose-video"]
    args: da.VisualizeComposeVideoArgs  # type: ignore[assignment]


class VisualizeInteractiveRun(DomainRunRequest):
    tool: Literal["interactive"]
    args: da.VisualizeInteractiveArgs  # type: ignore[assignment]


# Process
class ProcessDecodeGrib2Run(DomainRunRequest):
    tool: Literal["decode-grib2"]
    args: da.ProcessDecodeGrib2Args  # type: ignore[assignment]


class ProcessExtractVariableRun(DomainRunRequest):
    tool: Literal["extract-variable"]
    args: da.ProcessExtractVariableArgs  # type: ignore[assignment]


class ProcessConvertFormatRun(DomainRunRequest):
    tool: Literal["convert-format"]
    args: da.ProcessConvertFormatArgs  # type: ignore[assignment]


# New process tools
class ProcessApiJsonRun(DomainRunRequest):
    tool: Literal["api-json"]
    args: da.ProcessApiJsonArgs  # type: ignore[assignment]


class ProcessAudioTranscodeRun(DomainRunRequest):
    tool: Literal["audio-transcode"]
    args: da.ProcessAudioTranscodeArgs  # type: ignore[assignment]


class ProcessAudioMetadataRun(DomainRunRequest):
    tool: Literal["audio-metadata"]
    args: da.ProcessAudioMetadataArgs  # type: ignore[assignment]


class ProcessVideoTranscodeRun(DomainRunRequest):
    tool: Literal["video-transcode"]
    args: da.ProcessVideoTranscodeArgs  # type: ignore[assignment]


# Decimate
class DecimateLocalRun(DomainRunRequest):
    tool: Literal["local"]
    args: da.DecimateLocalArgs  # type: ignore[assignment]


class DecimateS3Run(DomainRunRequest):
    tool: Literal["s3"]
    args: da.DecimateS3Args  # type: ignore[assignment]


class DecimatePostRun(DomainRunRequest):
    tool: Literal["post"]
    args: da.DecimatePostArgs  # type: ignore[assignment]


class DecimateFtpRun(DomainRunRequest):
    tool: Literal["ftp"]
    args: da.DecimateFtpArgs  # type: ignore[assignment]


# New skeleton domains for OpenAPI clarity (optional typed variants)
class SimulateSampleRun(DomainRunRequest):
    tool: Literal["sample"]
    args: da.SimulateSampleArgs  # type: ignore[assignment]


class DecideOptimizeRun(DomainRunRequest):
    tool: Literal["optimize"]
    args: da.DecideOptimizeArgs  # type: ignore[assignment]


class NarrateDescribeRun(DomainRunRequest):
    tool: Literal["describe"]
    args: da.NarrateDescribeArgs  # type: ignore[assignment]


class VerifyEvaluateRun(DomainRunRequest):
    tool: Literal["evaluate"]
    args: da.VerifyEvaluateArgs  # type: ignore[assignment]


# Acquire
class AcquireHttpRun(DomainRunRequest):
    tool: Literal["http"]
    args: da.AcquireHttpArgs  # type: ignore[assignment]


class AcquireS3Run(DomainRunRequest):
    tool: Literal["s3"]
    args: da.AcquireS3Args  # type: ignore[assignment]


class AcquireFtpRun(DomainRunRequest):
    tool: Literal["ftp"]
    args: da.AcquireFtpArgs  # type: ignore[assignment]


class AcquireApiRun(DomainRunRequest):
    tool: Literal["api"]
    args: da.AcquireApiArgs  # type: ignore[assignment]
