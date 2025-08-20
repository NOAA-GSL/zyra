import json
import subprocess
import sys


def test_importing_wizard_does_not_import_heavy_visualization_modules():
    # Run in a fresh Python process to avoid pollution from other tests
    code = r"""
import sys
import json
mods_before = set(sys.modules.keys())
import datavizhub.wizard  # noqa: F401
heavy = [
    'datavizhub.visualization',
    'datavizhub.visualization.heatmap_manager',
    'datavizhub.visualization.contour_manager',
    'datavizhub.visualization.vector_field_manager',
]
present = [m for m in heavy if m in sys.modules]
print(json.dumps({'present': present}))
"""
    res = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip() or "{}")
    present = set(out.get("present", []))
    # Wizard should not import heavy viz modules during import
    assert "datavizhub.visualization" not in present
    assert "datavizhub.visualization.heatmap_manager" not in present
    assert "datavizhub.visualization.contour_manager" not in present
    assert "datavizhub.visualization.vector_field_manager" not in present
