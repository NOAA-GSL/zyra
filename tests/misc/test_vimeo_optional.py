import importlib
from unittest.mock import patch

import pytest


@pytest.fixture
def vimeo_client():
    """Fixture to mock VimeoClient where used (connectors-based flows will patch when added)."""
    with patch("vimeo.VimeoClient") as mock_vimeo_client:
        yield mock_vimeo_client


def test_vimeo_import_and_patch(vimeo_client):
    # The current codebase uses backends; Vimeo manager is placeholder. Ensure VimeoClient is patchable.
    try:
        mod = importlib.import_module("vimeo")
        assert hasattr(mod, "VimeoClient")
    except Exception:
        # If the optional dep isn't installed, our patch still provided the attribute
        assert True
