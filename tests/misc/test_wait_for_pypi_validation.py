# SPDX-License-Identifier: Apache-2.0
import importlib.util
import pathlib
import urllib.error

import pytest


def _load_wait_module():
    """Dynamically load the wait_for_pypi module from the scripts directory."""
    path = pathlib.Path("scripts/wait_for_pypi.py").resolve()
    spec = importlib.util.spec_from_file_location("wait_for_pypi", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def test_fetch_json_rejects_non_https():
    """fetch_json should reject non-HTTPS URLs for security."""
    mod = _load_wait_module()
    with pytest.raises(ValueError):
        mod.fetch_json("http://pypi.org/pypi/pkg/json")


def test_fetch_json_rejects_non_pypi_host():
    """fetch_json should reject URLs not hosted on pypi.org."""
    mod = _load_wait_module()
    with pytest.raises(ValueError):
        mod.fetch_json("https://example.com/foo.json")


def test_fetch_json_allows_pypi_https_and_reads(monkeypatch):
    """fetch_json should accept a valid PyPI URL and return parsed JSON."""
    mod = _load_wait_module()

    class FakeResponse:
        def __enter__(self):
            # Provide a minimal JSON body; json.load reads from file-like
            import io

            self._buf = io.BytesIO(b'{\n  "releases": {\n    "1.0.0": [1]\n  }\n}')
            return self._buf

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(url, timeout=10.0):  # noqa: ARG001 - match signature
        return FakeResponse()

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    data = mod.fetch_json("https://pypi.org/pypi/pkg/json")
    assert isinstance(data, dict)
    assert "releases" in data


def test_main_retries_on_urlerror_and_times_out(monkeypatch):
    """main should retry on transient URLError and exit 1 after retries."""
    mod = _load_wait_module()

    def raising_simple(_pkg: str, _ver: str, timeout: float = 10.0):  # noqa: ARG001
        raise urllib.error.URLError("network down")

    monkeypatch.setattr(mod, "is_version_available", raising_simple)
    # retries=1, delay=0 to keep test fast
    rc = mod.main(["wait_for_pypi.py", "zyra", "9.9.9", "1", "0"])
    assert rc == 1


def test_main_bubbles_unexpected_errors(monkeypatch):
    """main should propagate unexpected exceptions for visibility in CI."""
    mod = _load_wait_module()

    def raising_fetch(_pkg: str, _ver: str, timeout: float = 10.0):  # noqa: ARG001
        raise RuntimeError("boom")

    monkeypatch.setattr(mod, "is_version_available", raising_fetch)
    with pytest.raises(RuntimeError):
        mod.main(["wait_for_pypi.py", "zyra", "9.9.9", "1", "0"])


def test_is_version_available_checks_simple(monkeypatch):
    """is_version_available should check the PyPI simple index for the version."""
    mod = _load_wait_module()

    class Resp:
        def __init__(self, text: str):
            self._b = text.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self._b

    def fake_urlopen(url, timeout=10.0):  # noqa: ARG001
        assert url.endswith("/simple/zyra/")
        # Include the normalized filename pattern with version
        return Resp('<a href="/packages/.../zyra-1.2.3.tar.gz">zyra-1.2.3.tar.gz</a>')

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    assert mod.is_version_available("Zyra", "1.2.3") is True
