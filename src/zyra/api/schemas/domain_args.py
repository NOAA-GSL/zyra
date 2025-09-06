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
    key = (stage, tool)
    model: type[BaseModel] | None = None
    if key == ("acquire", "http"):
        model = AcquireHttpArgs
    elif key == ("process", "convert-format"):
        model = ProcessConvertFormatArgs
    elif key == ("process", "decode-grib2"):
        model = ProcessDecodeGrib2Args
    elif key == ("visualize", "heatmap"):
        model = VisualizeHeatmapArgs
    elif key == ("decimate", "local"):
        model = DecimateLocalArgs
    elif key == ("decimate", "s3"):
        model = DecimateS3Args

    if model is None:
        return dict(args)
    obj = model(**args)
    return obj.model_dump(exclude_none=True)
