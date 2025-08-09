import builtins
import importlib


def test_import_processing_package_without_viz(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        # Simulate absence of heavy viz dependencies
        if name.startswith("cartopy") or name.startswith("matplotlib"):
            raise ImportError("blocked for test")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    # Importing the base package and the processing namespace should not pull viz deps
    import datavizhub  # noqa: F401
    importlib.import_module("datavizhub.processing")

