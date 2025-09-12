# SPDX-License-Identifier: Apache-2.0
import json
import subprocess
import sys


def test_importing_wizard_does_not_import_heavy_visualization_modules():
    # Run in a fresh Python process to avoid pollution from other tests
    code = r"""
import sys
import json
mods_before = set(sys.modules.keys())
import zyra.wizard  # noqa: F401
heavy = [
    'zyra.visualization',
    'zyra.visualization.heatmap_manager',
    'zyra.visualization.contour_manager',
    'zyra.visualization.vector_field_manager',
]
present = [m for m in heavy if m in sys.modules]
print(json.dumps({'present': present}))
"""
    res = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )
    out = json.loads(res.stdout.strip() or "{}")
    present = set(out.get("present", []))
    # Wizard should not import heavy viz modules during import
    assert "zyra.visualization" not in present
    assert "zyra.visualization.heatmap_manager" not in present
    assert "zyra.visualization.contour_manager" not in present
    assert "zyra.visualization.vector_field_manager" not in present
