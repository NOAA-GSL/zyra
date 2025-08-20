import json


def test_log_schema_and_correlation_fields(tmp_path, monkeypatch):
    from datavizhub.cli import main

    # Use a temp HOME so logs go to a known place
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    # Run wizard in dry-run with logging enabled to produce JSONL events
    rc = main(
        [
            "wizard",
            "--provider",
            "mock",
            "--prompt",
            "example",
            "--dry-run",
            "--log",
        ]
    )
    assert rc == 0

    logs_dir = home / ".datavizhub" / "wizard_logs"
    files = sorted(logs_dir.glob("*.jsonl"))
    assert files, "Expected a JSONL log file to be created"
    log_path = files[-1]
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1

    events = [json.loads(line) for line in lines]

    # schema_version always present and equals 1
    assert all(ev.get("schema_version") == 1 for ev in events)

    # session_id stable across events in a single run
    session_ids = {ev.get("session_id") for ev in events}
    assert len(session_ids) == 1
    assert next(iter(session_ids)), "session_id should be non-empty"

    # event_id unique per event
    event_ids = [ev.get("event_id") for ev in events]
    assert all(bool(eid) for eid in event_ids), "event_id should be present"
    assert len(set(event_ids)) == len(event_ids)


def test_log_includes_assistant_reply_when_enabled(tmp_path, monkeypatch):
    from datavizhub.cli import main

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    rc = main(
        [
            "wizard",
            "--provider",
            "mock",
            "--prompt",
            "example",
            "--dry-run",
            "--log",
            "--log-raw-llm",
        ]
    )
    assert rc == 0

    logs_dir = home / ".datavizhub" / "wizard_logs"
    files = sorted(logs_dir.glob("*.jsonl"))
    assert files, "Expected a JSONL log file"
    lines = files[-1].read_text(encoding="utf-8").strip().splitlines()
    events = [json.loads(line) for line in lines]

    replies = [ev for ev in events if ev.get("type") == "assistant_reply"]
    assert (
        replies
    ), "Expected at least one assistant_reply event when --log-raw-llm is set"
    assert any("raw" in ev and ev["raw"] for ev in replies)
