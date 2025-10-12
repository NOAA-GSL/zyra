# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class AcquireHttpArgs(BaseModel):
    url: str | None = None
    output: str | None = None
    # Batch/listing options
    list_mode: bool | None = Field(default=None, alias="list")
    pattern: str | None = None
    since: str | None = None
    since_period: str | None = None
    until: str | None = None
    date_format: str | None = None
    inputs: list[str] | None = None
    manifest: str | None = None
    output_dir: str | None = None
    headers: dict[str, str] | None = None
    header: list[str] | None = None
    auth: str | None = None
    credentials: dict[str, str] | None = None
    credential: list[str] | None = None
    credential_file: str | None = None

    @model_validator(mode="after")
    def _require_source_or_listing(self):  # type: ignore[override]
        if not (self.url or self.inputs or self.manifest or self.list_mode):
            raise ValueError("Provide url or inputs/manifest, or set list=true")
        return self


class ProcessConvertFormatArgs(BaseModel):
    file_or_url: str | None = None
    format: str
    stdout: bool | None = None
    output: str | None = None
    # Batch
    inputs: list[str] | None = None
    output_dir: str | None = None
    # Advanced
    backend: str | None = None
    var: str | None = None
    pattern: str | None = None
    unsigned: bool | None = None


class ProcessDecodeGrib2Args(BaseModel):
    file_or_url: str
    pattern: str | None = None
    raw: bool | None = None
    backend: str | None = None
    unsigned: bool | None = None


class ProcessExtractVariableArgs(BaseModel):
    file_or_url: str
    pattern: str
    backend: str | None = None
    stdout: bool | None = None
    format: str | None = None


class VisualizeHeatmapArgs(BaseModel):
    input: str | None = None
    inputs: list[str] | None = None
    output: str | None = None
    output_dir: str | None = None
    var: str | None = None
    basemap: str | None = None
    extent: list[float] | None = Field(
        default=None, description="[west,east,south,north]"
    )
    width: int | None = None
    height: int | None = None
    dpi: int | None = None
    cmap: str | None = None
    colorbar: bool | None = None
    label: str | None = None
    units: str | None = None
    xarray_engine: str | None = None
    map_type: str | None = None
    tile_source: str | None = None
    tile_zoom: int | None = None
    timestamp: str | None = None
    crs: str | None = None
    reproject: bool | None = None

    @field_validator("extent")
    @classmethod
    def _extent_len(cls, v: list[float] | None):
        if v is not None and len(v) != 4:
            raise ValueError("extent must have 4 numbers: [west,east,south,north]")
        return v


class DecimateLocalArgs(BaseModel):
    input: str
    path: str


class DecimateS3Args(BaseModel):
    input: str | None = None
    url: str | None = None
    bucket: str | None = None
    key: str | None = None
    content_type: str | None = None

    @model_validator(mode="after")
    def _check_target(self):  # type: ignore[override]
        if not (self.url or self.bucket):
            raise ValueError("Provide either url or bucket (with optional key)")
        return self


class DecimateFtpArgs(BaseModel):
    input: str
    path: str
    user: str | None = None
    password: str | None = None
    credentials: dict[str, str] | None = None
    credential: list[str] | None = None
    credential_file: str | None = None


class AcquireS3Args(BaseModel):
    url: str | None = None
    bucket: str | None = None
    key: str | None = None
    unsigned: bool | None = None
    output: str | None = None
    # Listing/batch
    list_mode: bool | None = Field(default=None, alias="list")
    pattern: str | None = None
    since: str | None = None
    since_period: str | None = None
    until: str | None = None
    date_format: str | None = None
    inputs: list[str] | None = None
    manifest: str | None = None
    output_dir: str | None = None

    @model_validator(mode="after")
    def _check_target(self):  # type: ignore[override]
        if not (self.url or self.bucket):
            raise ValueError("Provide either url or bucket (with optional key)")
        return self


class AcquireFtpArgs(BaseModel):
    path: str | None = None
    output: str | None = None
    # Listing/batch
    list_mode: bool | None = Field(default=None, alias="list")
    pattern: str | None = None
    since: str | None = None
    since_period: str | None = None
    until: str | None = None
    date_format: str | None = None
    inputs: list[str] | None = None
    manifest: str | None = None
    output_dir: str | None = None
    user: str | None = None
    password: str | None = None
    credentials: dict[str, str] | None = None
    credential: list[str] | None = None
    credential_file: str | None = None

    @model_validator(mode="after")
    def _require_path_or_listing(self):  # type: ignore[override]
        if not (self.path or self.inputs or self.manifest or self.list_mode):
            raise ValueError("Provide path or inputs/manifest, or set list=true")
        return self


# New: acquire api (generic REST)
class AcquireApiArgs(BaseModel):
    url: str | None = None
    method: str | None = None
    output: str | None = None
    # Use dicts for API convenience
    headers: dict[str, str] | None = None
    params: dict[str, str] | None = None
    data: str | dict | None = None
    content_type: str | None = None
    # Pagination
    paginate: str | None = None
    page_param: str | None = None
    page_start: int | None = None
    page_size_param: str | None = None
    page_size: int | None = None
    empty_json_path: str | None = None
    cursor_param: str | None = None
    next_cursor_json_path: str | None = None
    # Link-based pagination
    link_rel: str | None = None
    # Streaming/binary
    stream: bool | None = None
    detect_filename: bool | None = None
    accept: str | None = None
    expect_content_type: str | None = None
    head_first: bool | None = None
    resume: bool | None = None
    progress: bool | None = None
    # OpenAPI validation
    openapi_validate: bool | None = None
    openapi_strict: bool | None = None
    # Convenience auth helper
    auth: str | None = None
    # NDJSON option for paginated responses
    newline_json: bool | None = None
    # Preset helpers
    preset: str | None = None
    since: str | None = None
    start: str | None = None
    end: str | None = None
    duration: str | None = None
    audio_source: str | None = None

    @model_validator(mode="after")
    def _require_url_or_preset(self):  # type: ignore[override]
        if not (self.url or self.preset):
            raise ValueError("Provide url or preset")
        return self


def _normalize_headers(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``payload`` with header aliases flattened."""

    header_items: list[str] = []
    existing_headers = payload.get("header")
    if isinstance(existing_headers, list):
        header_items.extend(existing_headers)
    headers_map = payload.get("headers")
    if isinstance(headers_map, dict):
        header_items.extend(f"{k}: {v}" for k, v in headers_map.items())
    result = payload.copy()
    result.pop("header", None)
    result.pop("headers", None)
    if header_items:
        result["header"] = header_items
    return result


def _normalize_credentials(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``payload`` with credential aliases flattened."""

    credential_items: list[str] = []
    existing_credentials = payload.get("credential")
    if isinstance(existing_credentials, list):
        credential_items.extend(existing_credentials)
    credentials_map = payload.get("credentials")
    if isinstance(credentials_map, dict):
        credential_items.extend(f"{k}={v}" for k, v in credentials_map.items())
    result = payload.copy()
    result.pop("credential", None)
    result.pop("credentials", None)
    if credential_items:
        result["credential"] = credential_items
    return result


def normalize_and_validate(stage: str, tool: str, args: dict) -> dict:
    """Validate known tool args via Pydantic models, else pass through as-is.

    Returns a new dict with validated/normalized keys. Unknown tools are not
    validated to preserve backward compatibility.
    """
    # Apply CLI-style normalization first so aliases are accepted (e.g., output->path)
    # Defer import to avoid heavy dependencies during OpenAPI schema generation
    try:
        from zyra.api.workers.executor import _normalize_args as _normalize_cli_like

        try:
            args = _normalize_cli_like(stage, tool, dict(args))
        except Exception:
            args = dict(args)
    except Exception:
        # Fallback when executor is unavailable
        args = dict(args)
    model = resolve_model(stage, tool)

    if model is None:
        return dict(args)
    obj = model(**args)
    out = obj.model_dump(exclude_none=True)

    if stage == "acquire" and tool == "http":
        out = _normalize_headers(out)
        out = _normalize_credentials(out)
    elif stage == "acquire" and tool == "ftp":
        out = _normalize_credentials(out)
    elif stage == "decimate" and tool == "post":
        out = _normalize_headers(out)
        out = _normalize_credentials(out)
    elif stage == "decimate" and tool == "ftp":
        out = _normalize_credentials(out)

    return out


# Additional high-value tool schemas
class VisualizeContourArgs(BaseModel):
    input: str | None = None
    inputs: list[str] | None = None
    output: str
    output_dir: str | None = None
    levels: int | str | None = None
    filled: bool | None = None


class DecimatePostArgs(BaseModel):
    input: str
    url: str
    content_type: str | None = None
    headers: dict[str, str] | None = None
    header: list[str] | None = None
    auth: str | None = None
    credentials: dict[str, str] | None = None
    credential: list[str] | None = None
    credential_file: str | None = None


class VisualizeAnimateArgs(BaseModel):
    input: str | None = None
    inputs: list[str] | None = None
    output_dir: str
    mode: str | None = None
    fps: int | None = None
    to_video: str | None = None
    width: int | None = None
    height: int | None = None
    dpi: int | None = None
    cmap: str | None = None
    levels: int | str | None = None
    vmin: float | None = None
    vmax: float | None = None
    basemap: str | None = None
    extent: list[float] | None = None
    uvar: str | None = None
    vvar: str | None = None
    u: str | None = None
    v: str | None = None

    @field_validator("extent")
    @classmethod
    def _extent_len2(cls, v: list[float] | None):
        if v is not None and len(v) != 4:
            raise ValueError("extent must have 4 numbers: [west,east,south,north]")
        return v


class VisualizeTimeSeriesArgs(BaseModel):
    input: str
    output: str
    x: str | None = None
    y: str | None = None
    var: str | None = None
    width: int | None = None
    height: int | None = None
    dpi: int | None = None
    title: str | None = None
    xlabel: str | None = None
    ylabel: str | None = None
    style: str | None = None


class VisualizeVectorArgs(BaseModel):
    input: str | None = None
    inputs: list[str] | None = None
    uvar: str | None = None
    vvar: str | None = None
    u: str | None = None
    v: str | None = None
    basemap: str | None = None
    extent: list[float] | None = None
    output: str | None = None
    output_dir: str | None = None
    width: int | None = None
    height: int | None = None
    dpi: int | None = None
    density: float | None = None
    scale: float | None = None
    color: str | None = None
    xarray_engine: str | None = None
    map_type: str | None = None
    tile_source: str | None = None
    tile_zoom: int | None = None
    streamlines: bool | None = None
    crs: str | None = None
    reproject: bool | None = None

    @field_validator("extent")
    @classmethod
    def _extent_len3(cls, v: list[float] | None):
        if v is not None and len(v) != 4:
            raise ValueError("extent must have 4 numbers: [west,east,south,north]")
        return v

    @field_validator("density")
    @classmethod
    def _density_range(cls, v: float | None):
        if v is not None and not (0 < v <= 1):
            raise ValueError("density must be in (0,1]")
        return v


class VisualizeComposeVideoArgs(BaseModel):
    frames: str
    output: str
    basemap: str | None = None
    fps: int | None = None


class VisualizeInteractiveArgs(BaseModel):
    input: str
    output: str
    var: str | None = None
    mode: str | None = None
    engine: str | None = None
    extent: list[float] | None = None
    cmap: str | None = None
    features: str | None = None
    no_coastline: bool | None = None
    no_borders: bool | None = None
    no_gridlines: bool | None = None
    colorbar: bool | None = None
    label: str | None = None
    units: str | None = None
    timestamp: str | None = None
    timestamp_loc: str | None = None
    tiles: str | None = None
    zoom: int | None = None
    attribution: str | None = None
    wms_url: str | None = None
    wms_layers: str | None = None
    wms_format: str | None = None
    wms_transparent: bool | None = None
    layer_control: bool | None = None
    width: int | None = None
    height: int | None = None
    crs: str | None = None
    reproject: bool | None = None
    time_column: str | None = None
    period: str | None = None
    transition_ms: int | None = None
    uvar: str | None = None
    vvar: str | None = None
    u: str | None = None
    v: str | None = None
    density: float | None = None
    scale: float | None = None
    color: str | None = None
    streamlines: bool | None = None


class SimulateSampleArgs(BaseModel):
    """Arguments for ``simulate sample``.

    Provides simple placeholders to facilitate early integration and testing
    of the simulate stage.
    """

    seed: int | None = Field(default=None, description="Random seed")
    trials: int | None = Field(default=None, description="Number of trials")


class DecideOptimizeArgs(BaseModel):
    """Arguments for ``decide optimize`` (skeleton)."""

    strategy: str | None = Field(
        default=None,
        description="Optimization strategy (e.g., 'greedy', 'random', 'grid')",
    )


class NarrateDescribeArgs(BaseModel):
    """Arguments for ``narrate describe`` (skeleton)."""

    topic: str | None = Field(default=None, description="Narration topic")


class NarrateSwarmArgs(BaseModel):
    """Arguments for ``narrate swarm``.

    Mirrors the CLI flags; types favor strings to align with CLI parsing.
    """

    preset: str | None = Field(default=None, description="Preset name (-P/--preset)")
    swarm_config: str | None = Field(
        default=None, description="YAML config path for swarm orchestrator"
    )
    agents: str | None = Field(
        default=None, description="Comma-separated agent IDs (e.g., summary,critic)"
    )
    audiences: str | None = Field(
        default=None, description="Comma-separated audiences (e.g., kids,policy)"
    )
    style: str | None = Field(default=None, description="Target writing style")
    provider: str | None = Field(
        default=None, description="LLM provider (mock|openai|ollama)"
    )
    model: str | None = Field(default=None, description="Model name")
    base_url: str | None = Field(default=None, description="Provider base URL")
    max_workers: int | None = Field(
        default=None, description="Max concurrent agents (auto-scales if omitted)"
    )
    max_rounds: int | None = Field(default=None, description="Critic/editor rounds")
    pack: str | None = Field(
        default=None, description="Output pack path ('-' for stdout)"
    )


class VerifyEvaluateArgs(BaseModel):
    """Arguments for ``verify evaluate`` (skeleton)."""

    metric: str | None = Field(default=None, description="Metric name")


# New: process tools
class ProcessApiJsonArgs(BaseModel):
    file_or_url: str
    records_path: str | None = None
    fields: str | None = None
    flatten: bool | None = None
    explode: list[str] | None = None
    derived: str | None = None
    format: str | None = None
    output: str | None = None
    preset: str | None = None


class ProcessAudioTranscodeArgs(BaseModel):
    input: str
    output: str
    to: str | None = None
    sample_rate: int | None = None
    mono: bool | None = None
    stereo: bool | None = None


class ProcessAudioMetadataArgs(BaseModel):
    input: str
    output: str | None = None


class ProcessVideoTranscodeArgs(BaseModel):
    """Arguments for ``process video-transcode``."""

    input: str
    output: str | None = None
    container: str | None = None
    codec: str | None = None
    audio_codec: str | None = None
    audio_bitrate: str | None = None
    scale: str | None = None
    fps: float | None = None
    bitrate: str | None = None
    pix_fmt: str | None = None
    preset: str | None = None
    crf: int | None = None
    gop: int | None = None
    extra_args: list[str] | None = None
    metadata_out: str | None = None
    write_metadata: bool | None = None
    sos_legacy: bool | None = None
    no_overwrite: bool | None = None


class PresetLimitlessAudioArgs(BaseModel):
    """Args for preset endpoint: /v1/presets/limitless/audio.

    Provide either (start & end) or (since & duration). Optionally specify
    audio_source (e.g., "pendant" or "app").
    """

    start: str | None = None
    end: str | None = None
    since: str | None = None
    duration: str | None = None
    audio_source: str | None = None

    @model_validator(mode="after")
    def _check_time_args(self):  # type: ignore[override]
        use_range = bool(self.start and self.end)
        use_since = bool(self.since and self.duration)
        if not (use_range or use_since):
            raise ValueError("Provide start+end or since+duration")
        return self


def resolve_model(stage: str, tool: str) -> type[BaseModel] | None:
    key = (stage, tool)
    if key == ("acquire", "http"):
        return AcquireHttpArgs
    if key == ("acquire", "api"):
        return AcquireApiArgs
    # Aliases for acquire
    if key == ("import", "http"):
        return AcquireHttpArgs
    if key == ("import", "api"):
        return AcquireApiArgs
    if key == ("process", "convert-format"):
        return ProcessConvertFormatArgs
    if key == ("process", "decode-grib2"):
        return ProcessDecodeGrib2Args
    if key == ("process", "extract-variable"):
        return ProcessExtractVariableArgs
    if key == ("process", "api-json"):
        return ProcessApiJsonArgs
    if key == ("process", "audio-transcode"):
        return ProcessAudioTranscodeArgs
    if key == ("process", "audio-metadata"):
        return ProcessAudioMetadataArgs
    if key == ("process", "video-transcode"):
        return ProcessVideoTranscodeArgs
    if key == ("visualize", "heatmap"):
        return VisualizeHeatmapArgs
    if key == ("visualize", "contour"):
        return VisualizeContourArgs
    if key == ("visualize", "animate"):
        return VisualizeAnimateArgs
    if key == ("visualize", "timeseries"):
        return VisualizeTimeSeriesArgs
    if key == ("visualize", "vector"):
        return VisualizeVectorArgs
    if key == ("visualize", "compose-video"):
        return VisualizeComposeVideoArgs
    if key == ("visualize", "interactive"):
        return VisualizeInteractiveArgs
    if key == ("decimate", "local"):
        return DecimateLocalArgs
    if key == ("decimate", "s3"):
        return DecimateS3Args
    if key == ("decimate", "post"):
        return DecimatePostArgs
    if key == ("decimate", "ftp"):
        return DecimateFtpArgs
    # Alias for disseminate/export mapping to decimate schemas
    if key == ("disseminate", "local"):
        return DecimateLocalArgs
    if key == ("disseminate", "s3"):
        return DecimateS3Args
    if key == ("disseminate", "post"):
        return DecimatePostArgs
    if key == ("disseminate", "ftp"):
        return DecimateFtpArgs
    if key == ("acquire", "s3"):
        return AcquireS3Args
    if key == ("acquire", "ftp"):
        return AcquireFtpArgs
    if key == ("acquire", "http"):
        return AcquireHttpArgs
    # New skeleton domains
    if key == ("simulate", "sample"):
        return SimulateSampleArgs
    if key == ("decide", "optimize"):
        return DecideOptimizeArgs
    if key == ("narrate", "describe"):
        return NarrateDescribeArgs
    if key == ("narrate", "swarm"):
        return NarrateSwarmArgs
    if key == ("verify", "evaluate"):
        return VerifyEvaluateArgs
    return None
