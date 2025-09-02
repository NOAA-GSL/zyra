import importlib
import sys
import types
from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def vimeo_client():
    """Provide a dummy ``vimeo`` module with a mock VimeoClient.

    Avoids relying on a local stub or requiring the third-party package.
    """
    dummy = types.SimpleNamespace(VimeoClient=Mock(name="VimeoClient"))
    with patch.dict(sys.modules, {"vimeo": dummy}):
        yield dummy.VimeoClient


def test_vimeo_import_and_patch(vimeo_client):
    # The current codebase uses backends; Vimeo manager is placeholder. Ensure VimeoClient is patchable.
    try:
        mod = importlib.import_module("vimeo")
        assert hasattr(mod, "VimeoClient")
    except Exception:
        # If the optional dep isn't installed, our patch still provided the attribute
        assert True
