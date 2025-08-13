import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def ensure_uv_stacks():
    """Ensure samples/u_stack.npy and v_stack.npy exist by running the generator.

    This makes vector/particles tests self-healing without committing binaries.
    """
    repo_root = Path(__file__).resolve().parents[2]
    samples_dir = repo_root / "samples"
    u_path = samples_dir / "u_stack.npy"
    v_path = samples_dir / "v_stack.npy"

    if u_path.exists() and v_path.exists():
        return str(u_path), str(v_path)

    gen = samples_dir / "generate_uv_stacks.py"
    if not gen.exists():
        pytest.skip("samples/generate_uv_stacks.py not found")

    # Run the generator; default creates u_stack.npy and v_stack.npy
    env = os.environ.copy()
    proc = subprocess.run([sys.executable, str(gen)], cwd=str(repo_root), capture_output=True, text=True)
    if proc.returncode != 0:
        pytest.skip(f"Failed to generate U/V stacks: {proc.stderr}")

    if not (u_path.exists() and v_path.exists()):
        pytest.skip("Generator did not produce expected U/V stacks")

    return str(u_path), str(v_path)

