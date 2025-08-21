"""Lightweight Vimeo client stub for optional dependency.

This module provides a minimal ``VimeoClient`` placeholder so that test suites
can patch ``vimeo.VimeoClient`` without requiring the third-party package.

If your application actually needs Vimeo API access, install the official
dependency and import it instead of this stub.
"""


class VimeoClient:  # pragma: no cover - runtime-patched in tests
    def __init__(self, *args, **kwargs):
        raise ImportError(
            "Vimeo client dependency is not installed. This is a test stub."
        )
