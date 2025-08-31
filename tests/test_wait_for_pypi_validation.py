import importlib.util
import pathlib
import urllib.error

import pytest


def _load_wait_module():
    path = pathlib.Path("scripts/wait_for_pypi.py").resolve()
    spec = importlib.util.spec_from_file_location("wait_for_pypi", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def test_fetch_json_rejects_non_https():
    mod = _load_wait_module()
    with pytest.raises(ValueError):
        mod.fetch_json("http://pypi.org/pypi/pkg/json")


def test_fetch_json_rejects_non_pypi_host():
    mod = _load_wait_module()
    with pytest.raises(ValueError):
        mod.fetch_json("https://example.com/foo.json")


def test_fetch_json_allows_pypi_https_and_reads(monkeypatch):
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
    mod = _load_wait_module()

    def raising_fetch(_url: str, timeout: float = 10.0):  # noqa: ARG001
        raise urllib.error.URLError("network down")

    monkeypatch.setattr(mod, "fetch_json", raising_fetch)
    # retries=1, delay=0 to keep test fast
    rc = mod.main(["wait_for_pypi.py", "zyra", "9.9.9", "1", "0"])
    assert rc == 1


def test_main_bubbles_unexpected_errors(monkeypatch):
    mod = _load_wait_module()

    def raising_fetch(_url: str, timeout: float = 10.0):  # noqa: ARG001
        raise RuntimeError("boom")

    monkeypatch.setattr(mod, "fetch_json", raising_fetch)
    with pytest.raises(RuntimeError):
        mod.main(["wait_for_pypi.py", "zyra", "9.9.9", "1", "0"])
