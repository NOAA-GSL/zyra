from __future__ import annotations

from pathlib import Path


def project_root(start: Path | None = None) -> Path:
    """Return the repository root by walking up to find pyproject.toml.

    Falls back to the topmost parent if no anchor is found. This avoids using
    hard-coded parent indices that can break when test layout changes.
    """
    here = (start or Path(__file__)).resolve()
    for anc in [here, *here.parents]:
        if (anc / "pyproject.toml").exists():
            return anc
    # Fallback: the highest parent available, or `here` if none
    return here.parents[-1] if here.parents else here
