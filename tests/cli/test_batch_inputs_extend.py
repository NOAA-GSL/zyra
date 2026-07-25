# SPDX-License-Identifier: Apache-2.0
"""Batch ``--inputs`` must survive both arg-expansion styles.

Two callers expand a list arg differently:

- ``zyra run`` (the pipeline runner) emits ``--inputs a b c``
- the Domain API executor emits repeated ``--inputs a --inputs b``

With plain ``nargs="+"`` argparse overwrites the destination on each
occurrence, so the API path silently kept only the LAST input — an API
caller posting a frame sequence got a successful run that processed one
file, with nothing in the response to say so. ``action="extend"``
accepts both styles.
"""

from __future__ import annotations

import argparse

import pytest


def _registrar(domain):
    if domain == "visualize":
        from zyra.visualization import cli_register

        return cli_register.register_cli
    if domain == "sos":
        from zyra.visualization.cli_sos import register_sos_cli

        return register_sos_cli
    if domain == "process":
        from zyra.processing import register_cli

        return register_cli
    if domain == "acquire":
        from zyra.connectors.ingest import register_cli

        return register_cli
    raise AssertionError(f"unknown domain {domain}")


def _parse(domain, argv):
    parser = argparse.ArgumentParser()
    _registrar(domain)(parser.add_subparsers(dest="cmd"))
    return parser.parse_args(argv)


# (domain, argv prefix before --inputs, argv suffix after the inputs)
BATCH_COMMANDS = [
    # heatmap still declares --input required=True on this branch; passing
    # it keeps the case about --inputs expansion, not that requirement.
    ("visualize", ["heatmap", "--input", "x.tif"], ["--output-dir", "out"]),
    ("visualize", ["contour"], ["--output-dir", "out"]),
    ("visualize", ["vector"], []),
    ("visualize", ["animate"], []),
    ("sos", ["sos"], ["--output-dir", "out"]),
    ("process", ["convert-format", "geotiff"], ["--output-dir", "out"]),
    ("acquire", ["http", "https://example.org/x"], ["--output-dir", "out"]),
    ("acquire", ["s3", "--url", "s3://bucket/x"], ["--output-dir", "out"]),
    ("acquire", ["ftp", "ftp://example.org/x"], ["--output-dir", "out"]),
]

IDS = [f"{d}:{pre[0]}" for d, pre, _ in BATCH_COMMANDS]


@pytest.mark.parametrize(("domain", "prefix", "suffix"), BATCH_COMMANDS, ids=IDS)
def test_repeated_inputs_flags_accumulate(domain, prefix, suffix):
    # The Domain API executor's expansion style.
    ns = _parse(domain, [*prefix, "--inputs", "a", "--inputs", "b", *suffix])
    assert ns.inputs == ["a", "b"]


@pytest.mark.parametrize(("domain", "prefix", "suffix"), BATCH_COMMANDS, ids=IDS)
def test_multi_valued_inputs_flag_still_works(domain, prefix, suffix):
    # The pipeline runner's expansion style must be unaffected.
    ns = _parse(domain, [*prefix, "--inputs", "a", "b", *suffix])
    assert ns.inputs == ["a", "b"]


@pytest.mark.parametrize(("domain", "prefix", "suffix"), BATCH_COMMANDS, ids=IDS)
def test_inputs_defaults_to_none(domain, prefix, suffix):
    # action="extend" must not turn the unset default into [].
    ns = _parse(domain, [*prefix, *suffix])
    assert ns.inputs is None


def test_executor_expansion_round_trips_through_the_parser():
    # The actual bug path, end to end: the argv the Domain API builds for
    # a multi-item `inputs` array, parsed by the real CLI parser.
    from zyra.api.workers.executor import _args_dict_to_argv

    argv = _args_dict_to_argv(
        "visualize",
        "contour",
        {"inputs": ["f000.tif", "f006.tif", "f012.tif"], "output_dir": "out"},
    )
    assert argv.count("--inputs") == 3, argv
    ns = _parse("visualize", argv[1:])
    assert ns.inputs == ["f000.tif", "f006.tif", "f012.tif"]


def test_contour_batch_does_not_require_output():
    # --output was required=True even though this flag's own help says to
    # prefer --output-dir with --inputs, so the batch form was
    # unreachable without a dummy value.
    ns = _parse(
        "visualize", ["contour", "--inputs", "a.tif", "b.tif", "--output-dir", "out"]
    )
    assert ns.inputs == ["a.tif", "b.tif"]
    assert ns.output is None


def test_contour_argument_errors_exit_2():
    import subprocess
    import sys

    def run(extra):
        return subprocess.run(
            [sys.executable, "-m", "zyra.cli", "visualize", "contour", *extra],
            capture_output=True,
            text=True,
            check=False,
        )

    # Neither form given.
    proc = run([])
    assert proc.returncode == 2
    assert "--input is required" in proc.stderr
    assert "Traceback" not in proc.stderr

    # Single form without its output.
    proc = run(["--input", "x.npy"])
    assert proc.returncode == 2
    assert "--output is required" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_batch_missing_output_dir_exits_2_not_1():
    # The "--output-dir is required" guard used to raise SystemExit with
    # a string, which exits 1 and bypasses the ValueError -> exit-2
    # mapping every other argument error goes through.
    import subprocess
    import sys

    for cmd in ("heatmap", "contour"):
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "zyra.cli",
                "visualize",
                cmd,
                "--input",
                "x.npy",
                "--output",
                "o.png",
                "--inputs",
                "a.tif",
                "b.tif",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 2, f"{cmd}: {proc.returncode}\n{proc.stderr}"
        assert "--output-dir is required" in proc.stderr
        assert "Traceback" not in proc.stderr


def test_contour_schema_rejects_empty_inputs():
    import pytest as _pytest
    from pydantic import ValidationError

    from zyra.api.schemas.domain_args import VisualizeContourArgs

    # An explicit empty batch is malformed, not "no batch requested" —
    # otherwise it falls through to the single-output branch and a
    # payload that asked for zero frames validates as a single render.
    with _pytest.raises(ValidationError):
        VisualizeContourArgs(inputs=[], output_dir="out")
    with _pytest.raises(ValidationError):
        VisualizeContourArgs(inputs=[], output="o.png")
    # Both valid forms still validate.
    assert VisualizeContourArgs(inputs=["a.tif"], output_dir="out").output is None
    assert VisualizeContourArgs(output="o.png").output == "o.png"


# ---- Exit-code contract across the remaining batch handlers ---------------
# heatmap and contour got the ValueError -> logged exit 2 wrapper first;
# animate, vector, and sos still raised SystemExit with a string, which
# exits 1 and skips the logged-error path. Only ARGUMENT errors move:
# runtime failures and the --to-video path guards stay SystemExit.


def _run_visualize(cmd, extra):
    import subprocess
    import sys

    return subprocess.run(
        [sys.executable, "-m", "zyra.cli", "visualize", cmd, *extra],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("cmd", ["animate", "vector", "sos"])
def test_batch_missing_output_dir_exits_2_for_remaining_handlers(cmd):
    proc = _run_visualize(cmd, ["--inputs", "a.nc", "b.nc"])
    assert proc.returncode == 2, f"{cmd}: rc={proc.returncode}\n{proc.stderr}"
    assert "--output-dir is required" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_sos_single_mode_argument_errors_exit_2():
    proc = _run_visualize("sos", [])
    assert proc.returncode == 2, proc.stderr
    assert "--input or --inputs is required" in proc.stderr
    assert "Traceback" not in proc.stderr

    proc = _run_visualize("sos", ["--input", "x.nc"])
    assert proc.returncode == 2, proc.stderr
    assert "--output is required" in proc.stderr
    assert "Traceback" not in proc.stderr


def _raise_kinds(module):
    """Map each raised message fragment to the SET of exception classes
    raised with it.

    Parsed from the AST rather than matched against source text: a
    substring search picks up a neighbouring raise and passes even when
    the statement it names has changed type. A set rather than a single
    value because some messages are raised from more than one code path
    (``--to-video`` is guarded in both the batch and single paths), and a
    dict would let an unconverted duplicate mask a converted one.
    """
    import ast
    import inspect

    out = {}
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
            continue
        func = node.exc.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        for arg in node.exc.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                out.setdefault(arg.value, set()).add(name)
            elif isinstance(arg, ast.JoinedStr):
                lead = "".join(
                    v.value
                    for v in arg.values
                    if isinstance(v, ast.Constant) and isinstance(v.value, str)
                )
                if lead:
                    out.setdefault(lead, set()).add(name)
    return out


def test_guards_and_argument_errors_raise_the_right_types():
    # Regression guard for THIS change: the --to-video checks protect an
    # output-root escape and the render checks stop a pipeline treating an
    # empty render as success, so both must keep raising SystemExit rather
    # than being swept up as ordinary argument errors by the new wrapper.
    # The argument errors that DID move must be ValueError.
    from zyra.visualization import cli_animate, cli_sos, cli_vector

    animate = _raise_kinds(cli_animate)
    assert animate[
        "--to-video cannot start with '-' (may be interpreted as an option)"
    ] == {"SystemExit"}
    assert animate["--to-video is outside of allowed output root"] == {"SystemExit"}
    assert animate["ffmpeg grid composition failed"] == {"SystemExit"}

    sos = _raise_kinds(cli_sos)
    assert sos["Failed to render SOS frame from "] == {"SystemExit"}
    assert sos["Failed to render  SOS frame(s): "] == {"SystemExit"}

    for mod in (cli_animate, cli_vector, cli_sos):
        kinds = _raise_kinds(mod)
        assert kinds["--output-dir is required when using --inputs"] == {
            "ValueError"
        }, mod.__name__
    assert sos["--input or --inputs is required"] == {"ValueError"}
    assert sos["--output is required when using --input"] == {"ValueError"}
