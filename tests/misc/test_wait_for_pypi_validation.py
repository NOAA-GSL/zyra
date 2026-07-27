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

    def fake_urlopen(url, *hosts, timeout=10.0):  # noqa: ARG001 - match signature
        return FakeResponse()

    monkeypatch.setattr(mod, "_urlopen", fake_urlopen)
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

    def fake_urlopen(url, *hosts, timeout=10.0):  # noqa: ARG001
        target = url if isinstance(url, str) else url.full_url
        seen.append(target)
        if target.endswith("/simple/zyra/"):
            return Resp('<a href="/packages/x/zyra-1.2.3.tar.gz">zyra-1.2.3.tar.gz</a>')
        return Resp(status=206)

    monkeypatch.setattr(mod, "_urlopen", fake_urlopen)
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

    monkeypatch.setattr(mod, "_urlopen", lambda *a, **k: FakeResponse())


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


def test_listed_but_unfetchable_never_ends_the_wait(monkeypatch):
    """The exact race: the index lists it, the CDN does not serve it yet.

    Driven through ``is_version_available`` and ``main``, not
    ``is_fetchable``. An earlier version of this test called the leaf
    directly while patching ``file_urls_for_version`` — setup for a call
    it never made — so it asserted nothing about the aggregate that the
    release job actually invokes, which is the only thing that decides
    whether a build starts.

    A 404 propagates rather than resolving to False: ``main`` classes it
    as transient and retries, which is what should happen while a CDN
    catches up. What must never happen is the wait ending green.
    """
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

    monkeypatch.setattr(mod, "_urlopen", _404)
    with pytest.raises(urllib.error.HTTPError):
        mod.is_version_available("zyra", "0.1.53")

    # End to end: retried, then gave up. Never exit 0.
    assert mod.main(["wait_for_pypi.py", "zyra", "0.1.53", "2", "0"]) == 1


def test_every_listed_file_must_be_fetchable(monkeypatch):
    """One file answering is not enough to end the wait.

    pip installs the wheel normally, but a source build reaches for the
    sdist, so going green on whichever responded first says nothing
    about the file pip will actually download. This pins the `all`, not
    `any`, that `is_version_available` is built on.
    """
    mod = _load_wait_module()
    wheel = "https://files.pythonhosted.org/packages/ab/cd/zyra-0.1.53-py3-none-any.whl"
    sdist = "https://files.pythonhosted.org/packages/ab/cd/zyra-0.1.53.tar.gz"
    monkeypatch.setattr(mod, "file_urls_for_version", lambda *a, **k: [wheel, sdist])

    # Wheel up, sdist still propagating — not available.
    monkeypatch.setattr(mod, "is_fetchable", lambda u, **k: u == wheel)
    assert mod.is_version_available("zyra", "0.1.53") is False

    # Only both serving is green.
    monkeypatch.setattr(mod, "is_fetchable", lambda u, **k: True)
    assert mod.is_version_available("zyra", "0.1.53") is True


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


# --- what counts as "the same host" ------------------------------------
#
# The guard compared `netloc`, which carries the port and any userinfo.
# That is over-strict in one direction (a default port spelled out loud
# is the same host) without being any safer in the other.


def test_allowlist_accepts_an_explicit_default_port():
    """`https://pypi.org:443/...` is pypi.org, not a stranger."""
    mod = _load_wait_module()
    mod._require_allowed_url("https://pypi.org:443/simple/zyra/", "pypi.org")


def test_allowlist_is_case_insensitive_on_the_host():
    """Hostnames are case-insensitive; the guard should be too."""
    mod = _load_wait_module()
    mod._require_allowed_url("https://PyPI.ORG/simple/zyra/", "pypi.org")
    # ...including when the allowlist itself is the odd one out.
    mod._require_allowed_url("https://pypi.org/simple/zyra/", "PyPI.org")


def test_allowlist_is_not_fooled_by_userinfo():
    """`https://pypi.org@evil.example/` is a request to evil.example."""
    mod = _load_wait_module()
    with pytest.raises(ValueError):
        mod._require_allowed_url("https://pypi.org@evil.example/x.whl", "pypi.org")
    with pytest.raises(ValueError):
        mod._require_allowed_url("https://pypi.org:443@evil.example/x.whl", "pypi.org")


# --- redirects ---------------------------------------------------------
#
# urllib follows redirects on its own. Validating only the URL we ask for
# checks the one hop that was never in doubt, and checking geturl() after
# the fact is too late: the request has already been issued. These pin
# the check at the point where it can still refuse.


def _redirect(mod, hosts, newurl):
    import urllib.request

    handler = mod._AllowlistRedirectHandler(hosts)
    req = urllib.request.Request("https://pypi.org/simple/zyra/")
    return handler.redirect_request(req, None, 302, "Found", {}, newurl)


def test_redirect_off_the_allowlist_is_refused_before_it_is_followed():
    mod = _load_wait_module()
    with pytest.raises(ValueError):
        _redirect(mod, ("pypi.org", mod.FILES_HOST), "https://evil.example/x.whl")


def test_redirect_within_the_allowlist_is_followed():
    """The index legitimately redirects to the files host — don't break that."""
    mod = _load_wait_module()
    out = _redirect(
        mod,
        ("pypi.org", mod.FILES_HOST),
        f"https://{mod.FILES_HOST}/packages/ab/cd/zyra-0.1.53.tar.gz",
    )
    assert out is not None
    assert out.full_url.startswith(f"https://{mod.FILES_HOST}/")


def test_downgrade_to_http_on_redirect_is_refused():
    """A redirect is also a way to drop out of TLS."""
    mod = _load_wait_module()
    with pytest.raises(ValueError):
        _redirect(
            mod, ("pypi.org", mod.FILES_HOST), f"http://{mod.FILES_HOST}/x.tar.gz"
        )
