import json


def test_edit_commands_uses_wizard_session_id(monkeypatch, tmp_path):
    import datavizhub.wizard as wiz

    # Force prompt_toolkit path but stub the session
    monkeypatch.setattr(wiz, "PTK_AVAILABLE", True)

    class _FakePTKSession:
        def prompt(self, *args, **kwargs):
            # Return the default text unchanged
            return kwargs.get("default", "")

    monkeypatch.setattr(wiz, "PromptSession", _FakePTKSession)

    # Prepare inputs
    cmds = ["datavizhub visualize heatmap --input in.nc --var TMP  # trailing"]
    logfile = tmp_path / "wiz.log"
    sess = wiz.SessionState()

    out = wiz._edit_commands(cmds, logfile=logfile, session=sess)
    # Sanitized: comment removed and command retained
    assert out and out[0].startswith("datavizhub visualize heatmap")
    assert "#" not in out[0]

    # Validate log contains an edit event with session_id
    data = [json.loads(p) for p in logfile.read_text().splitlines() if p.strip()]
    assert any(e.get("type") == "edit" for e in data)
    assert any(e.get("session_id") == sess.session_id for e in data)


def test_edit_commands_handles_missing_session_id(monkeypatch, tmp_path):
    import datavizhub.wizard as wiz

    # Force prompt_toolkit path but stub the session
    monkeypatch.setattr(wiz, "PTK_AVAILABLE", True)

    class _FakePTKSession:
        def prompt(self, *args, **kwargs):
            return kwargs.get("default", "")

    monkeypatch.setattr(wiz, "PromptSession", _FakePTKSession)

    class DummySession:
        pass

    cmds = ["datavizhub --help"]
    logfile = tmp_path / "wiz2.log"

    # Should not raise even without session_id attribute
    out = wiz._edit_commands(cmds, logfile=logfile, session=DummySession())
    assert out and out[0] == "datavizhub --help"

    # Log should be written without a session_id key
    data = [json.loads(p) for p in logfile.read_text().splitlines() if p.strip()]
    assert any(e.get("type") == "edit" for e in data)
    assert all("session_id" not in e for e in data if e.get("type") == "edit")

