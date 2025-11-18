# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from zyra.swarm.memory import SQLiteProvenanceStore


def test_sqlite_provenance_store_records_events(tmp_path) -> None:
    store = SQLiteProvenanceStore(tmp_path / "prov.db", metadata={"plan": "basic"})
    hook = store.as_event_hook()

    hook("run_started", {"started": "2025-01-01T00:00:00Z", "agent_count": 2})
    hook("agent_started", {"agent": "import", "role": "specialist"})
    hook("agent_completed", {"agent": "import", "duration_ms": 42})
    hook("run_completed", {"errors": [], "completed": "2025-01-01T00:00:01Z"})

    run = store.fetch_run()
    assert run
    assert run["run_id"] == store.run_id
    assert run["metadata"] == {"plan": "basic"}

    events = store.fetch_events()
    assert [e["event"] for e in events] == [
        "run_started",
        "agent_started",
        "agent_completed",
        "run_completed",
    ]
    assert events[1]["payload"]["agent"] == "import"
    store.close()
