# Section 7: Use Case -- Reproducible Pipeline Configs

## Purpose
Show how YAML-driven pipelines make workflows declarative, shareable, and overridable.

## Content

**Heading:** Use Case: Reproducible Pipeline Configs

**Description:** Define multi-stage pipelines as YAML -- no scripting required. Override parameters at runtime, dry-run to preview commands, and share configs across teams.

**YAML Example:**
```yaml
name: FTP to Local Video
stages:
  - stage: acquire
    command: ftp
    args:
      path: ftp://ftp.nnvl.noaa.gov/SOS/DroughtRisk_Weekly
      sync_dir: ./frames
      since_period: "P1Y"
  - stage: visualize
    command: compose-video
    args:
      frames: ./frames
      output: video.mp4
      fps: 4
  - stage: export
    command: local
    args:
      input: video.mp4
      path: /output/video.mp4
```

**Commands:**
```bash
zyra run pipeline.yaml                          # execute
zyra run pipeline.yaml --dry-run                 # preview commands
zyra run pipeline.yaml --set visualize.fps=8     # override parameters
```

## Layout
- Half-column width
- YAML config block as the visual centerpiece
- Command examples in a smaller code block below

## AI Design Prompt
> Create a use case card for a scientific poster. Heading "Use Case: Reproducible Pipeline Configs" in Ocean Blue (#1A5A69), 20pt bold. Show a YAML code block as the main visual element -- use a Neutral 200 (#F7F5EE) background with syntax highlighting. The YAML defines a 3-stage pipeline (acquire, visualize, export). Below the YAML, show 3 bash commands demonstrating execute, dry-run, and parameter override. Brief description text mentioning declarative configs and team sharing. Use a thin Cable Blue (#00529E) left border. Half-column width.
