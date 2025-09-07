from __future__ import annotations

from pydantic import BaseModel, model_validator
from zyra.api.workers.executor import _normalize_args as _normalize_cli_like


class AcquireHttpArgs(BaseModel):
    url: str
    output: str | None = None


class ProcessConvertFormatArgs(BaseModel):
    file_or_url: str
    format: str
    stdout: bool | None = None


class ProcessDecodeGrib2Args(BaseModel):
    file_or_url: str
    pattern: str | None = None
    raw: bool | None = None


class ProcessExtractVariableArgs(BaseModel):
    file_or_url: str
    pattern: str


class VisualizeHeatmapArgs(BaseModel):
    input: str
    output: str
    width: int | None = None
    height: int | None = None
    dpi: int | None = None


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


class AcquireS3Args(BaseModel):
    url: str | None = None
    bucket: str | None = None
    key: str | None = None
    unsigned: bool | None = None
    output: str | None = None

    @model_validator(mode="after")
    def _check_target(self):  # type: ignore[override]
        if not (self.url or self.bucket):
            raise ValueError("Provide either url or bucket (with optional key)")
        return self


class AcquireFtpArgs(BaseModel):
    path: str
    output: str | None = None


def normalize_and_validate(stage: str, tool: str, args: dict) -> dict:
    """Validate known tool args via Pydantic models, else pass through as-is.

    Returns a new dict with validated/normalized keys. Unknown tools are not
    validated to preserve backward compatibility.
    """
    # Apply CLI-style normalization first so aliases are accepted (e.g., output->path)
    try:
        args = _normalize_cli_like(stage, tool, dict(args))
    except Exception:
        args = dict(args)
    model = resolve_model(stage, tool)

    if model is None:
        return dict(args)
    obj = model(**args)
    return obj.model_dump(exclude_none=True)


# Additional high-value tool schemas
class VisualizeContourArgs(BaseModel):
    input: str
    output: str
    levels: int | None = None
    filled: bool | None = None


class DecimatePostArgs(BaseModel):
    input: str
    url: str
    content_type: str | None = None


class VisualizeAnimateArgs(BaseModel):
    input: str
    output_dir: str
    mode: str | None = None
    fps: int | None = None
    to_video: str | None = None
    width: int | None = None
    height: int | None = None
    dpi: int | None = None


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
    if key == ("decimate", "local"):
        return DecimateLocalArgs
    if key == ("decimate", "s3"):
        return DecimateS3Args
    if key == ("decimate", "post"):
        return DecimatePostArgs
    if key == ("acquire", "s3"):
        return AcquireS3Args
    if key == ("acquire", "ftp"):
        return AcquireFtpArgs
    return None
