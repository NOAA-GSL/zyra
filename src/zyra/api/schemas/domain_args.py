from __future__ import annotations

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

    @model_validator(mode="after")
    def _require_path_or_listing(self):  # type: ignore[override]
        if not (self.path or self.inputs or self.manifest or self.list_mode):
            raise ValueError("Provide path or inputs/manifest, or set list=true")
        return self


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
    return obj.model_dump(exclude_none=True)


# Additional high-value tool schemas
class VisualizeContourArgs(BaseModel):
    input: str | None = None
    inputs: list[str] | None = None
    output: str | None = None
    output_dir: str | None = None
    levels: int | str | None = None
    filled: bool | None = None


class DecimatePostArgs(BaseModel):
    input: str
    url: str
    content_type: str | None = None


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


def resolve_model(stage: str, tool: str) -> type[BaseModel] | None:
    key = (stage, tool)
    if key == ("acquire", "http"):
        return AcquireHttpArgs
    if key == ("process", "convert-format"):
        return ProcessConvertFormatArgs
    if key == ("process", "decode-grib2"):
        return ProcessDecodeGrib2Args
    if key == ("process", "extract-variable"):
        return ProcessExtractVariableArgs
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
    if key == ("acquire", "s3"):
        return AcquireS3Args
    if key == ("acquire", "ftp"):
        return AcquireFtpArgs
    if key == ("acquire", "http"):
        return AcquireHttpArgs
    return None
