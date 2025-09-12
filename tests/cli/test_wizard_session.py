# SPDX-License-Identifier: Apache-2.0
from zyra.wizard import SessionState, _handle_prompt


def test_session_memory_in_context(monkeypatch, capsys):
    from zyra.wizard import llm_client

    calls = []

    def gen_first(system_prompt: str, user_prompt: str) -> str:
        calls.append(user_prompt)
        return (
            """
```bash
datavizhub process convert-format input.nc netcdf --output out1.nc
```
"""
        ).strip()

    def gen_second(system_prompt: str, user_prompt: str) -> str:
        calls.append(user_prompt)
        assert "Last file: out1.nc" in user_prompt
        return (
            """
```bash
datavizhub visualize heatmap --input out1.nc --var TMP --output plot.png
```
"""
        ).strip()

    # Both calls use MockClient; select generator via len(calls):
    # use gen_first when len(calls) == 0, else gen_second.
    def generate(system_prompt: str, user_prompt: str) -> str:
        return (
            gen_first(system_prompt, user_prompt)
            if len(calls) == 0
            else gen_second(system_prompt, user_prompt)
        )

    monkeypatch.setattr(llm_client.MockClient, "generate", staticmethod(generate))

    sess = SessionState()
    # Stub execution to avoid running real commands
    monkeypatch.setattr("zyra.wizard._run_one", lambda c: 0)
    # First prompt: execute (not dry-run) and auto-confirm to update session state
    rc1 = _handle_prompt(
        "subset HRRR",
        provider="mock",
        model=None,
        dry_run=False,
        assume_yes=True,
        max_commands=None,
        logfile=None,
        session=sess,
    )
    assert rc1 == 0
    assert sess.last_file == "out1.nc"
    # Second prompt should include session context in user prompt and produce commands using last file
    rc2 = _handle_prompt(
        "make a heatmap",
        provider="mock",
        model=None,
        dry_run=True,
        assume_yes=True,
        max_commands=None,
        logfile=None,
        session=sess,
    )
    assert rc2 == 0
    out = capsys.readouterr().out
    assert "datavizhub visualize heatmap --input out1.nc" in out
