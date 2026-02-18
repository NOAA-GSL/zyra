# Section 5: Use Case -- Drought Animation Pipeline

## Purpose
Show a real-world production pipeline that uses multi-agent swarm orchestration.

## Content

**Heading:** Use Case: Drought Animation Pipeline

**Description:** A production workflow syncs weekly drought risk frames from NOAA FTP, fills gaps with basemap placeholders, and composes an MP4 animation -- defined as a declarative YAML swarm manifest with provenance logging.

**DAG (from `poster/assets/diagrams/drought_dag.mmd`):**
download_frames (import/ftp-sync) -> scan_frames (transform/metadata) -> fill_missing (process/pad-missing) -> compose_animation (visualize/compose-video) -> save_local (export/local)

**Command:**
```bash
zyra swarm samples/swarm/drought_animation.yaml --parallel --memory provenance.sqlite
```

**Key point:** Each agent logs provenance (start time, duration, command, exit code) to a SQLite store for full reproducibility.

## Layout
- Half-column width
- DAG diagram at top (vertical flow, 5 boxes)
- Command in a small code block below
- Brief text description

## AI Design Prompt
> Create a use case card for a scientific poster. Heading "Use Case: Drought Animation Pipeline" in Ocean Blue (#1A5A69), 20pt bold. Include a vertical flowchart/DAG with 5 connected boxes: download_frames -> scan_frames -> fill_missing -> compose_animation -> save_local. Use Cable Blue (#00529E) for import/export stages and Leaf Green (#2C670C) for process/transform stages. Below the DAG, show a single bash command in a code block. Add a brief description mentioning NOAA FTP, gap filling, and provenance logging. Use a thin Cable Blue left border. Half-column width.
