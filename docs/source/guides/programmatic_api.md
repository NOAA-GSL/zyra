# Programmatic API (Workflow, Manifest, Plugins)

- `Workflow`: load YAML/JSON pipelines and run them via the CLI for full parity.
- `Manifest`: inspect packaged CLI capabilities (with optional plugin merge).
- `plugins`: register local commands for discovery (CLI help epilog + manifest overlay).

## Examples

```python
from zyra.workflow.api import Workflow
from zyra.manifest import Manifest
from zyra import plugins

wf = Workflow.load("samples/workflows/minimal.yml")
print(wf.describe())
run_result = wf.run(capture=True, stream=False)
assert run_result.succeeded

plugins.register_command("process", "demo_plugin", description="Local demo")
manifest = Manifest.load(include_plugins=True)
print(manifest.list_commands(stage="process"))
```

Notes:
- Workflow execution uses subprocess calls to `zyra.cli` to mirror CLI behavior and logging.
- Plugin registry is discovery-only for now; execution dispatch remains unchanged.
- A companion notebook lives at `examples/api_and_programmatic_interface.ipynb` for interactive use.

## Notebook sessions

- `zyra.notebook.create_session()` builds stage namespaces from the same manifest used by `Manifest.load()`.
- Plugins registered via `zyra.plugins.register_command` are written to the overlay that notebook sessions read, so they show up in session namespaces and planner/help.
- Workflow APIs stay subprocess-based for parity, while notebook tools call callable wrappers; use whichever fits your notebook flow.
- Manifest/overlay loading is centralized in `zyra.manifest_utils.load_manifest_with_overlays` (honors `ZYRA_NOTEBOOK_OVERLAY` when set).

Example:

```python
from zyra.notebook import create_session

sess = create_session()
# Call a process tool directly from the manifest-driven namespace
sess.process.convert_format(file_or_url="/tmp/in.grib2", output="/tmp/out.tif")

# Plugins registered earlier are also discoverable
sess.process.demo_plugin()
```
