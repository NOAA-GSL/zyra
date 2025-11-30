# SPDX-License-Identifier: Apache-2.0
import sqlite3

from zyra.notebook import create_session
from zyra.swarm import planner


def test_provenance_records_notebook_tool(tmp_path, monkeypatch):
    monkeypatch.setenv("ZYRA_NOTEBOOK_DIR", str(tmp_path))
    sess = create_session(workdir=tmp_path)
    store = sess.provenance_store()
    store.handle_event("run_started", {"started": "test"})

    def dummy(ns):  # pragma: no cover - minimal stub
        return "ok"

    sess.process.register("dummy", dummy, returns="object")
    sess.process.dummy()

    db_path = sess._provenance_path  # noqa: SLF001
    assert db_path.exists()
    conn = sqlite3.connect(db_path)
    try:
        events = conn.execute("SELECT event, payload FROM events").fetchall()
        assert events, "expected events recorded"
        assert any("dummy" in (row[1] or "") for row in events)
    finally:
        conn.close()


def test_overlay_drives_planner(tmp_path, monkeypatch):
    monkeypatch.setenv("ZYRA_NOTEBOOK_DIR", str(tmp_path))
    sess = create_session(workdir=tmp_path)

    def dummy(ns):  # pragma: no cover - minimal stub
        return "ok"

    sess.process.register(
        "dummy",
        dummy,
        returns="object",
        args_template={"input": "frames_padded"},
        outputs_template={"output": "analysis.json"},
    )
    overlay_path = tmp_path / "notebook_capabilities_overlay.json"
    assert overlay_path.exists()
    monkeypatch.setenv("ZYRA_NOTEBOOK_OVERLAY", str(overlay_path))
    planner.planner._caps = None  # reset cache
    caps = planner._load_capabilities()
    assert "process dummy" in caps["raw"]
    assert "dummy" in caps["stage_commands"].get("process", {})


def test_plan_replay_skip_inline_warning(monkeypatch, capsys):
    # Inline serialization should log a warning on load
    plan = {
        "agents": [
            {
                "id": "inline_demo",
                "stage": "process",
                "command": "inline",
                "serialization": {"kind": "inline", "replay": {"materialize": False}},
                "description": "inline test",
            }
        ]
    }
    monkeypatch.delenv("ZYRA_NOTEBOOK_OVERLAY", raising=False)
    from zyra.swarm import spec as spec_mod

    spec_mod.load_stage_agent_specs(plan)
    out = capsys.readouterr().err
    assert "inline agent" in out
