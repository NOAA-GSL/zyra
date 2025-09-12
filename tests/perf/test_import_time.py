# SPDX-License-Identifier: Apache-2.0
import json
import subprocess
import sys


def test_import_time_report(capsys):
    """Report import times for lightweight entrypoints.

    This is a non-failing benchmark to monitor import cost over time. It
    intentionally does not assert thresholds to avoid flakes across environments.
    """
    code = r"""
import json
import time

def imp(name: str):
    t0 = time.perf_counter()
    err = None
    try:
        __import__(name)
    except Exception as e:
        err = repr(e)
    dt = time.perf_counter() - t0
    return {"module": name, "seconds": dt, "error": err}

mods = [
    'zyra.wizard',
    'zyra.visualization.cli_register',
]
print(json.dumps([imp(m) for m in mods]))
"""
    res = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stderr
    results = json.loads(res.stdout.strip() or "[]")
    # Emit a human-friendly summary in test output
    for row in results:
        mod = row.get("module")
        sec = float(row.get("seconds") or 0)
        err = row.get("error")
        if err:
            print(f"import {mod}: {sec:.3f}s (error: {err})")
        else:
            print(f"import {mod}: {sec:.3f}s")
    # Do not assert thresholds; this is informational only.
    captured = capsys.readouterr()
    # Keep at least one line to be visible in CI logs
    assert "import zyra.wizard:" in captured.out
