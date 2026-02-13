# SPDX-License-Identifier: Apache-2.0
"""Base interfaces for interactive visualization renderers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence


@dataclass(slots=True)
class InteractiveBundle:
    """Describes the output artifacts produced by an interactive renderer."""

    output_dir: Path
    index_html: Path
    assets: Sequence[Path] = field(default_factory=tuple)


class InteractiveRenderer(ABC):
    """Contract for interactive renderers that emit self-contained bundles."""

    slug: str = "interactive"
    description: str = ""

    def __init__(self, **options: Any) -> None:
        self._options: dict[str, Any] = dict(options)

    def configure(self, **options: Any) -> None:
        """Update renderer options prior to bundle generation."""

        self._options.update(options)

    @abstractmethod
    def build(self, *, output_dir: Path) -> InteractiveBundle:
        """Generate the interactive bundle inside ``output_dir``."""

    def describe(self) -> dict[str, Any]:
        """Return metadata about the renderer for CLI help text."""

        return {"slug": self.slug, "description": self.description}
