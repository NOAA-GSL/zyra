# SPDX-License-Identifier: Apache-2.0
"""Keep notebook-session tests out of the working tree.

``NotebookRegistry`` writes ``notebook_capabilities_overlay.json`` and a
``provenance.sqlite`` under its workdir, and ``_resolve_workdir`` falls
back to :func:`Path.cwd` when neither an explicit ``workdir`` nor
``ZYRA_NOTEBOOK_DIR`` is set. A test that builds a session without a
workdir therefore drops both files into the repository root — so running
the suite left the tree dirty.

Pinning the env var per test fixes the whole package rather than one call
site, and keeps a future test from reintroducing it. Nothing here asserts
the CWD fallback itself, so overriding it costs no coverage.

The two ``setdefault`` calls in ``NotebookRegistry.__init__`` are why the
env vars are cleared as well: ``setdefault`` will not overwrite, so the
first session in a process would otherwise pin every later one to its own
temporary directory.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_notebook_workdir(tmp_path, monkeypatch):
    monkeypatch.setenv("ZYRA_NOTEBOOK_DIR", str(tmp_path))
    monkeypatch.delenv("ZYRA_NOTEBOOK_PROVENANCE", raising=False)
    monkeypatch.delenv("ZYRA_NOTEBOOK_OVERLAY", raising=False)
