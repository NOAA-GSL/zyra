# SPDX-License-Identifier: Apache-2.0
from zyra.notebook import create_session


def test_to_pipeline_and_cli_export(tmp_path, monkeypatch):
    monkeypatch.setenv("ZYRA_NOTEBOOK_DIR", str(tmp_path))
    sess = create_session(workdir=tmp_path)

    def dummy(ns):
        return "ok"

    sess.process.register("dummy", dummy, returns="object")

    # Track a simple call
    result = sess.process.dummy()
    assert result == "ok"

    pipeline = sess.to_pipeline()
    cli_cmds = sess.to_cli()

    assert isinstance(pipeline, list)
    assert pipeline, "pipeline should include at least one stage"
    assert any("zyra" in cmd for cmd in cli_cmds)

    # Export pipeline to JSON for replay if needed
    out = tmp_path / "pipeline.json"
    import json

    out.write_text(json.dumps(pipeline, indent=2), encoding="utf-8")
    assert out.exists()
