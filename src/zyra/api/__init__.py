"""FastAPI service exposing the 4-stage Zyra CLI.

This package provides a lightweight web API to run CLI commands in-process
with captured stdout/stderr and exit codes, optionally as background jobs.
"""

__all__ = [
    "__version__",
]

try:  # pragma: no cover - best effort
    from importlib.metadata import version

    __version__ = version("zyra")
except Exception:  # pragma: no cover
    __version__ = "0.0.0"
