# SPDX-License-Identifier: Apache-2.0
import pytest

from zyra.notebook.registry import create_session


def test_session_builds_stage_namespaces():
    sess = create_session()

    # Ensure core namespaces exist
    assert hasattr(sess, "acquire")
    assert hasattr(sess, "process")
    assert hasattr(sess, "visualize")
    assert hasattr(sess, "narrate")

    # Ensure known tool mapping is present
    assert "http" in dir(sess.acquire)
    assert "convert_format" in dir(sess.process)


def test_session_allows_custom_workdir(tmp_path):
    sess = create_session(workdir=tmp_path)
    assert sess.workspace() == tmp_path


def test_tool_wrapper_invokes_impl():
    manifest = {
        "process echo": {
            "impl": {
                "module": "zyra.notebook.registry",
                "callable": "_noop_tool",
            },
            "returns": "object",
        }
    }
    sess = create_session(manifest=manifest)
    out = sess.process.echo(value="ok", extra=1)
    assert out["value"] == "ok"
    assert out["extra"] == 1


def test_tool_wrapper_missing_impl_raises():
    manifest = {"process nope": {"returns": "object"}}
    sess = create_session(manifest=manifest)
    with pytest.raises(NotImplementedError):
        sess.process.nope()


def test_provenance_path_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("ZYRA_NOTEBOOK_DIR", str(tmp_path))
    sess = create_session()
    assert sess.provenance_store() is not None
    # default path under workdir
    assert (tmp_path / "provenance.sqlite") == sess._provenance_path  # noqa: SLF001


def test_inline_register_executes():
    sess = create_session(manifest={})

    def _adder(ns):
        return ns.a + ns.b

    sess.process.register("add", _adder, returns="object")
    assert sess.process.add(a=2, b=3) == 5


def test_provenance_logs_without_error(tmp_path, monkeypatch):
    monkeypatch.setenv("ZYRA_NOTEBOOK_DIR", str(tmp_path))
    sess = create_session(manifest={})

    def _echo(ns):
        return ns.value

    sess.process.register("echo", _echo, returns="object")
    # Should not raise even if store is null; placeholder ensures call path runs
    assert sess.process.echo(value="hi") == "hi"


def test_pipeline_and_cli_exports():
    sess = create_session(manifest={})

    def _adder(ns):
        return ns.a + ns.b

    sess.process.register("add", _adder, returns="object")
    sess.process.add(a=1, b=2)
    pipeline = sess.to_pipeline()
    assert pipeline == [
        {"stage": "process", "command": "add", "args": {"a": 1, "b": 2}}
    ]
    cli = sess.to_cli()
    assert cli[0].startswith("zyra process add")
    assert "--a 1" in cli[0]
    assert "--b 2" in cli[0]
