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


def test_is_version_available_checks_simple_and_then_the_file(monkeypatch):
    """Availability now means listed *and* downloadable.

    It used to mean listed only, which let the guard pass while the
    file was still 404ing from the CDN pip fetches it from. The fake
    below has to answer both hops for this to return True.
    """
    mod = _load_wait_module()

    class Resp:
        def __init__(self, text: str = "", status: int = 200):
            self._b = text.encode("utf-8")
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self._b

    seen: list[str] = []

    def fake_urlopen(url, timeout=10.0):  # noqa: ARG001
        target = url if isinstance(url, str) else url.full_url
        seen.append(target)
        if target.endswith("/simple/zyra/"):
            return Resp('<a href="/packages/x/zyra-1.2.3.tar.gz">zyra-1.2.3.tar.gz</a>')
        return Resp(status=206)

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    assert mod.is_version_available("Zyra", "1.2.3") is True
    # Both hops, not just the index.
    assert any(u.endswith("/simple/zyra/") for u in seen)
    assert any("zyra-1.2.3.tar.gz" in u for u in seen)


# --- file-level availability -------------------------------------------
#
# The old check asked the simple index whether the version was *listed*.
# pip downloads from files.pythonhosted.org, a different host behind a
# different CDN, so "listed" and "downloadable" propagate independently:
# the guard went green and the very next `pip install` 404'd inside the
# Docker build. These cover the gap that closes.


def _index_html(*filenames: str) -> str:
    links = "".join(
        f'<a href="https://files.pythonhosted.org/packages/ab/cd/{f}#sha256=x">{f}</a>'
        for f in filenames
    )
    return f"<html><body>{links}</body></html>"


def _patch_index(mod, monkeypatch, html: str):
    class FakeResponse:
        def __enter__(self):
            import io

            return io.BytesIO(html.encode())

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod.urllib.request, "urlopen", lambda *a, **k: FakeResponse())


def test_file_urls_match_the_exact_version_not_a_prefix(monkeypatch):
    """`0.1.53` must not be satisfied by `0.1.53.1`.

    The previous substring check accepted it, so a *different* release
    could end the wait.
    """
    mod = _load_wait_module()
    _patch_index(mod, monkeypatch, _index_html("zyra-0.1.53.1.tar.gz"))
    assert mod.file_urls_for_version("zyra", "0.1.53") == []


def test_file_urls_find_wheel_and_sdist(monkeypatch):
    mod = _load_wait_module()
    _patch_index(
        mod,
        monkeypatch,
        _index_html("zyra-0.1.53-py3-none-any.whl", "zyra-0.1.53.tar.gz"),
    )
    urls = mod.file_urls_for_version("zyra", "0.1.53")
    assert len(urls) == 2
    # The fragment is stripped so the URL can be fetched directly.
    assert all("#" not in u for u in urls)


def test_listed_but_unfetchable_is_not_available(monkeypatch):
    """The exact race: the index lists it, the CDN does not serve it yet."""
    mod = _load_wait_module()
    monkeypatch.setattr(
        mod,
        "file_urls_for_version",
        lambda *a, **k: [
            "https://files.pythonhosted.org/packages/ab/cd/zyra-0.1.53.tar.gz"
        ],
    )

    def _404(*a, **k):
        raise urllib.error.HTTPError("u", 404, "Not Found", None, None)

    monkeypatch.setattr(mod.urllib.request, "urlopen", _404)
    with pytest.raises(urllib.error.HTTPError):
        mod.is_fetchable(
            "https://files.pythonhosted.org/packages/ab/cd/zyra-0.1.53.tar.gz"
        )


def test_is_fetchable_allows_the_files_host_but_not_others():
    """The file check has to follow the index's links off pypi.org."""
    mod = _load_wait_module()
    mod._require_allowed_url(
        "https://files.pythonhosted.org/packages/ab/cd/zyra-0.1.53.tar.gz",
        "files.pythonhosted.org",
    )
    with pytest.raises(ValueError):
        mod._require_allowed_url("https://evil.example/x.whl", "files.pythonhosted.org")
    with pytest.raises(ValueError):
        mod._require_allowed_url(
            "http://files.pythonhosted.org/x.whl", "files.pythonhosted.org"
        )


def test_no_files_means_not_available(monkeypatch):
    mod = _load_wait_module()
    monkeypatch.setattr(mod, "file_urls_for_version", lambda *a, **k: [])
    assert mod.is_version_available("zyra", "0.1.53") is False
