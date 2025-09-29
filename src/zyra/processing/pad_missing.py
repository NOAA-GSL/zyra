# SPDX-License-Identifier: Apache-2.0
"""Fill missing frame timestamps with synthetic images or copies.

This module powers the ``zyra process pad-missing`` CLI. It consumes the JSON
summary produced by ``zyra transform metadata``/``scan-frames`` to detect gaps
and produces placeholder frames so downstream animation steps receive a
contiguous chronology.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
from bisect import bisect_left
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    Image = ImageColor = ImageDraw = ImageFont = ImageOps = None  # type: ignore

    def _ensure_pillow() -> None:
        raise ModuleNotFoundError(
            "Pillow is required for 'zyra process pad-missing'. Install Pillow (e.g. 'pip install pillow') before running this command."
        )

else:  # pragma: no cover - simple guard

    def _ensure_pillow() -> None:
        return None


if TYPE_CHECKING:  # pragma: no cover - type checking only
    from PIL import Image as PILImage
else:  # pragma: no cover - runtime helper
    PILImage = Any  # type: ignore

from zyra.utils.date_manager import DateManager
from zyra.utils.io_utils import open_input

try:  # Optional dependency for basemap resolution reused from visualization
    from zyra.visualization.cli_utils import resolve_basemap_ref
except (
    ModuleNotFoundError
):  # pragma: no cover - keep CLI usable without visualization extras
    resolve_basemap_ref = None  # type: ignore[assignment]


SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".dds")
DEFAULT_SIZE = (1920, 1080)
DEFAULT_MODE = "RGBA"


@dataclass(frozen=True)
class FrameRecord:
    """Existing frame entry tracked by timestamp."""

    timestamp: datetime
    path: Path


class FramesCatalog:
    """Map timestamps to existing frame paths and derive naming conventions."""

    def __init__(
        self,
        frames_dir: str,
        *,
        pattern: str | None = None,
        datetime_format: str | None = None,
    ) -> None:
        self.frames_root = Path(frames_dir).expanduser()
        if not self.frames_root.exists() or not self.frames_root.is_dir():
            raise FileNotFoundError(f"Frames directory not found: {frames_dir}")
        self.pattern = pattern
        self.datetime_format = datetime_format
        self._records: list[FrameRecord] = []
        self._timestamp_to_path: dict[str, Path] = {}
        self._suffix_counter: Counter[str] = Counter()
        self._prefix = ""
        self._suffix = ""
        self._scan()

    # ------------------------------------------------------------------
    def _scan(self) -> None:
        names = [f for f in self.frames_root.iterdir() if f.is_file()]
        if self.pattern:
            rx = re.compile(self.pattern)
            names = [p for p in names if rx.search(p.name)]
        else:
            names = [p for p in names if p.suffix.lower() in SUPPORTED_EXTENSIONS]
        if not names:
            logging.warning("No frame images found in '%s'", self.frames_root)
        dm = DateManager([self.datetime_format] if self.datetime_format else None)
        fmt_regex = (
            dm.datetime_format_to_regex(self.datetime_format)
            if self.datetime_format
            else None
        )
        template_prefix = None
        template_suffix = None
        for path in sorted(names):
            name = path.name
            ts = None
            if self.datetime_format and fmt_regex:
                m = re.search(fmt_regex, name)
                if m:
                    try:
                        ts = datetime.strptime(m.group(), self.datetime_format)
                        if template_prefix is None:
                            template_prefix = name[: m.start()]
                            template_suffix = name[m.end() :]
                    except Exception:
                        ts = None
            if ts is None:
                iso = dm.extract_date_time(name)
                if iso:
                    try:
                        ts = datetime.fromisoformat(iso)
                    except ValueError:
                        ts = None
            if ts is None:
                continue
            rec = FrameRecord(timestamp=ts, path=path)
            key = ts.isoformat()
            self._records.append(rec)
            self._timestamp_to_path[key] = path
            self._suffix_counter[path.suffix.lower()] += 1
        self._records.sort(key=lambda r: r.timestamp)
        self._apply_template_bounds(template_prefix, template_suffix)

    def _apply_template_bounds(self, prefix: str | None, suffix: str | None) -> None:
        if prefix is not None:
            self._prefix = prefix
            self._suffix = suffix or ""
        else:
            self._prefix = ""
            self._suffix = ""

    # ------------------------------------------------------------------
    def has_timestamp(self, ts: datetime) -> bool:
        return ts.isoformat() in self._timestamp_to_path

    def get(self, ts: datetime) -> Path | None:
        return self._timestamp_to_path.get(ts.isoformat())

    def nearest(self, ts: datetime) -> Path | None:
        if not self._records:
            return None
        targets = [rec.timestamp for rec in self._records]
        pos = bisect_left(targets, ts)
        candidates: list[FrameRecord] = []
        if pos > 0:
            candidates.append(self._records[pos - 1])
        if pos < len(self._records):
            candidates.append(self._records[pos])
        if not candidates:
            return None
        best = min(candidates, key=lambda rec: abs(rec.timestamp - ts))
        return best.path

    @property
    def extension(self) -> str:
        if not self._suffix_counter:
            return ".png"
        return self._suffix_counter.most_common(1)[0][0]

    def filename_for(self, ts: datetime) -> str:
        if self.datetime_format:
            stamp = ts.strftime(self.datetime_format)
            return f"{self._prefix}{stamp}{self._suffix}"
        return f"{ts.isoformat()}{self.extension}"

    @property
    def sample_image_path(self) -> Path | None:
        return self._records[0].path if self._records else None

    @property
    def record_count(self) -> int:
        return len(self._records)


@dataclass
class IndicatorSpec:
    kind: str
    value: str | None = None


def parse_indicator(spec: str | None) -> IndicatorSpec | None:
    if not spec:
        return None
    token = spec.strip()
    if not token:
        return None
    if ":" not in token:
        raise ValueError("Indicator must use 'kind:value' form")
    kind, value = token.split(":", 1)
    kind = kind.strip().lower()
    value = value.strip()
    if kind not in {"watermark", "badge"}:
        raise ValueError(f"Unsupported indicator '{kind}'")
    if not value:
        raise ValueError("Indicator value cannot be empty")
    return IndicatorSpec(kind=kind, value=value)


def _load_metadata(path_or_stream: str, read_stdin: bool = False) -> dict:
    target = "-" if read_stdin else path_or_stream
    with open_input(target) as fp:
        raw = fp.read()
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:  # pragma: no cover - defensive decoding
        raise ValueError(f"Failed to decode frames metadata: {exc}") from exc


def _determine_canvas(catalog: FramesCatalog) -> tuple[tuple[int, int], str]:
    sample_path = catalog.sample_image_path
    if not sample_path or not sample_path.exists():
        return DEFAULT_SIZE, DEFAULT_MODE
    try:
        with Image.open(sample_path) as img:
            return img.size, img.mode
    except Exception:
        return DEFAULT_SIZE, DEFAULT_MODE


def _save_image(
    image: PILImage.Image, destination: Path, target_mode: str | None
) -> None:
    out = image
    converted = None
    if target_mode and out.mode != target_mode:
        converted = out.convert(target_mode)
        out = converted
    try:
        out.save(destination)
    finally:
        if converted is not None:
            with contextlib.suppress(Exception):
                converted.close()


def _build_blank(
    mode: str, size: tuple[int, int], color: str | None = None
) -> PILImage.Image:
    if mode == "P":
        mode = "RGBA"
    fill = (0, 0, 0, 0) if "A" in mode and not color else None
    if color:
        try:
            rgb = ImageColor.getcolor(color, mode if "A" not in mode else "RGBA")
            if len(rgb) == 3 and "A" in mode:
                rgb = (*rgb, 255)
            fill = rgb
        except ValueError as exc:
            raise ValueError(f"Invalid color '{color}' for solid fill: {exc}") from exc
    if fill is None:
        fill = (0, 0, 0, 255) if "A" in mode else 0
    return Image.new(mode if mode != "1" else "L", size, fill)


def _load_basemap(basemap: str, size: tuple[int, int]) -> PILImage.Image:
    if not basemap:
        raise ValueError("--basemap is required for basemap fill mode")
    path, guard = _resolve_basemap_reference(basemap)
    if not path:
        raise ValueError(f"Could not resolve basemap reference '{basemap}'")
    try:
        with Image.open(path) as img:
            img = img.convert("RGBA")
            return ImageOps.fit(img, size, method=Image.BILINEAR)
    finally:
        if guard is not None:
            close = getattr(guard, "close", None)
            if close:
                with contextlib.suppress(Exception):
                    close()


def _apply_indicator(img: PILImage.Image, spec: IndicatorSpec) -> PILImage.Image:
    if spec.kind == "watermark":
        return _apply_watermark(img, spec.value)
    if spec.kind == "badge":
        return _apply_badge(img, spec.value)
    return img


def _apply_watermark(img: PILImage.Image, text: str | None) -> PILImage.Image:
    if not text:
        return img
    out = img.copy()
    draw = ImageDraw.Draw(out)
    font = ImageFont.load_default()
    width, height = out.size
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
    except Exception:
        mask = font.getmask(text)
        text_width, text_height = mask.size
    margin = max(8, width // 100)
    x = width - text_width - margin
    y = height - text_height - margin
    if "A" in out.mode:
        box = Image.new(
            "RGBA", (text_width + margin, text_height + margin), (0, 0, 0, 128)
        )
        out.alpha_composite(box, dest=(x - margin // 2, y - margin // 2))
        draw = ImageDraw.Draw(out)
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))
    else:
        draw.rectangle(
            [
                (x - margin // 2, y - margin // 2),
                (x + text_width + margin // 2, y + text_height + margin // 2),
            ],
            fill="black",
        )
        draw.text((x, y), text, font=font, fill="white")
    return out


def _apply_badge(img: PILImage.Image, badge_path: str | None) -> PILImage.Image:
    if not badge_path:
        return img
    path = badge_path
    guard = None
    if resolve_basemap_ref:
        resolved, guard = resolve_basemap_ref(badge_path)
        if resolved:
            path = resolved
    out = img.copy()
    try:
        if not path:
            raise ValueError(f"Could not resolve badge '{badge_path}'")
        with Image.open(path) as badge:
            badge = badge.convert("RGBA")
            scale = 0.18  # badge covers ~18% of width
            max_width = int(out.size[0] * scale)
            if badge.size[0] > max_width:
                ratio = max_width / badge.size[0]
                new_size = (max_width, max(1, int(badge.size[1] * ratio)))
                badge = badge.resize(new_size, resample=Image.BILINEAR)
            pos = (
                out.size[0] - badge.size[0] - 12,
                out.size[1] - badge.size[1] - 12,
            )
            if "A" not in out.mode:
                out = out.convert("RGBA")
            out.alpha_composite(badge, dest=pos)
            if img.mode != out.mode:
                out = out.convert(img.mode)
            return out
    finally:
        if guard:
            with contextlib.suppress(Exception):
                guard.close()
    return out


def _write_json_report(path: str, payload: dict[str, Any]) -> None:
    report_path = Path(path)
    if report_path.parent:
        report_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2) + "\n"
    report_path.write_text(text, encoding="utf-8")


def _resolve_basemap_reference(
    ref: str,
) -> tuple[str | None, contextlib.AbstractContextManager | None]:
    if not resolve_basemap_ref:
        return ref, None
    try:
        result = resolve_basemap_ref(ref)
    except Exception as exc:  # pragma: no cover - defensive logging
        logging.warning("Failed to resolve basemap reference '%s': %s", ref, exc)
        return ref, None
    if isinstance(result, tuple) and len(result) == 2:
        return result
    if isinstance(result, str):
        return result, None
    logging.warning("Unexpected basemap resolver output for '%s': %r", ref, result)
    return ref, None


def _close_images(*images: PILImage.Image | None) -> None:
    """Best-effort helper to close Pillow image objects without duplicates."""
    seen_ids: set[int] = set()
    for image in images:
        if image is None or not hasattr(image, "close"):
            continue
        obj_id = id(image)
        if obj_id in seen_ids:
            continue
        seen_ids.add(obj_id)
        with contextlib.suppress(Exception):
            image.close()


def pad_missing_frames(
    metadata_path: str,
    *,
    output_dir: str,
    fill_mode: str,
    basemap: str | None = None,
    indicator: str | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
    json_report: str | None = None,
    read_stdin: bool = False,
) -> list[Path]:
    """Pad missing frame timestamps according to the requested strategy."""
    _ensure_pillow()
    meta = _load_metadata(metadata_path, read_stdin)
    frames_dir = meta.get("frames_dir")
    if not frames_dir:
        raise ValueError("Metadata must include 'frames_dir'")
    missing = meta.get("missing_timestamps") or []
    if not isinstance(missing, list):
        raise ValueError("Metadata 'missing_timestamps' must be a list")
    pattern = meta.get("pattern")
    datetime_format = meta.get("datetime_format")
    catalog = FramesCatalog(
        frames_dir, pattern=pattern, datetime_format=datetime_format
    )
    size, mode = _determine_canvas(catalog)
    indicator_spec = parse_indicator(indicator)
    out_root = Path(output_dir).expanduser()
    out_root.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    planned: list[str] = []
    skipped_existing: list[str] = []
    fill_mode = (fill_mode or "blank").lower()
    if fill_mode not in {"blank", "solid", "basemap", "nearest"}:
        raise ValueError(f"Unsupported fill mode '{fill_mode}'")
    # Pre-load reusable assets
    basemap_img = None
    if fill_mode == "solid":
        basemap_img = _build_blank(mode, size, basemap or "#000000")
    elif fill_mode == "basemap":
        basemap_img = _load_basemap(basemap or "", size)
    sorted_missing = sorted(
        datetime.fromisoformat(ts) for ts in missing if isinstance(ts, str)
    )
    if not sorted_missing:
        logging.info("No missing timestamps detected; nothing to do")
    target_mode = mode
    sample_name = catalog.filename_for(sorted_missing[0]) if sorted_missing else ""
    ext = Path(sample_name).suffix.lower() if sample_name else catalog.extension
    if ext in {".jpg", ".jpeg"}:
        target_mode = "RGB"
    elif not target_mode:
        target_mode = DEFAULT_MODE
    for ts in sorted_missing:
        filename = catalog.filename_for(ts)
        target = out_root / filename
        if target.exists() and not overwrite:
            logging.info(
                "Skipping existing frame '%s' (use --overwrite to replace)", target
            )
            skipped_existing.append(str(target))
            continue
        if dry_run:
            logging.info("[dry-run] would create '%s'", target)
            planned.append(str(target))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if fill_mode == "blank":
            img = _build_blank(mode, size)
            if indicator_spec:
                img = _apply_indicator(img, indicator_spec)
            _save_image(img, target, target_mode)
            _close_images(img)
        elif fill_mode == "solid":
            img = (
                basemap_img.copy() if basemap_img else _build_blank(mode, size, basemap)
            )
            if indicator_spec:
                img = _apply_indicator(img, indicator_spec)
            _save_image(img, target, target_mode)
            _close_images(img)
        elif fill_mode == "basemap":
            if basemap_img is None:
                raise ValueError("Failed to prepare basemap image")
            img = basemap_img.copy()
            if indicator_spec:
                img = _apply_indicator(img, indicator_spec)
            _save_image(img, target, target_mode)
            _close_images(img)
        elif fill_mode == "nearest":
            donor = catalog.nearest(ts)
            if not donor:
                logging.warning("No donor frame available for %s; using blank", ts)
                base = _build_blank(mode, size)
            else:
                with Image.open(donor) as donor_img:
                    base = donor_img.convert(target_mode or donor_img.mode).copy()
            img = base
            if indicator_spec:
                img = _apply_indicator(img, indicator_spec)
            _save_image(img, target, target_mode)
            _close_images(img, base)
        created.append(target)
        logging.debug("Created placeholder frame '%s'", target)
    if dry_run:
        logging.info(
            "Dry run complete; %d frame(s) would be created in '%s'",
            len(planned),
            out_root,
        )
    else:
        logging.info("Created %d placeholder frame(s) in '%s'", len(created), out_root)

    if json_report:
        try:
            report_payload: dict[str, Any] = {
                "status": "dry-run" if dry_run else "completed",
                "metadata_path": metadata_path if not read_stdin else "-",
                "frames_dir": str(frames_dir),
                "output_dir": str(out_root),
                "fill_mode": fill_mode,
                "basemap": basemap,
                "indicator": (
                    {"kind": indicator_spec.kind, "value": indicator_spec.value}
                    if indicator_spec
                    else None
                ),
                "missing_requested": [ts.isoformat() for ts in sorted_missing],
                "missing_count": len(sorted_missing),
                "created_count": len(created),
                "created_files": [str(p) for p in created],
                "planned_count": len(planned),
                "planned_files": planned,
                "skipped_existing_count": len(skipped_existing),
                "skipped_existing": skipped_existing,
                "dry_run": dry_run,
                "overwrite": overwrite,
                "frames_existing_count": catalog.record_count,
                "timestamp": datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
            }
            _write_json_report(json_report, report_payload)
            logging.info("Wrote pad-missing report to '%s'", json_report)
        except Exception as exc:  # pragma: no cover - best-effort reporting
            logging.error(
                "Failed to write pad-missing report '%s': %s", json_report, exc
            )
    return created
