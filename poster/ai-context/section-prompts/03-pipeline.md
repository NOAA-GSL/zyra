# Section 3: The Pipeline -- 8 Composable Stages

## Purpose
Central visual of the poster. Shows Zyra's 8-stage architecture as a flow diagram with supporting table.

## Content

### Pipeline Stages

| # | Stage | Purpose | CLI | Status |
|---|-------|---------|-----|--------|
| 1 | Import (acquire) | Fetch from HTTP/S, S3, FTP, REST API | `zyra acquire` | Implemented |
| 2 | Process (transform) | Decode, subset, convert (GRIB2, NetCDF, GeoTIFF) | `zyra process` | Implemented |
| 3 | Simulate | Generate synthetic/test data | -- | Planned |
| 4 | Decide (optimize) | Parameter optimization and selection | -- | Planned |
| 5 | Visualize (render) | Static maps, plots, animations, interactive | `zyra visualize` | Implemented |
| 6 | Narrate | AI-driven captions, summaries, reports | `zyra narrate` | Implemented |
| 7 | Verify | Quality checks and metadata validation | `zyra verify` | Partial |
| 8 | Export (disseminate) | Push to S3, FTP, Vimeo, local, HTTP POST | `zyra export` | Implemented |

### Streaming Example
```
zyra acquire http $URL -o - | zyra process convert-format - netcdf --stdout | zyra visualize heatmap --input - --var TMP -o plot.png
```

### Diagram
Render from `poster/assets/diagrams/pipeline_architecture.mmd` or recreate as:
1 Import -> 2 Process -> 3 Simulate -> 4 Decide -> 5 Visualize -> 6 Narrate -> 7 Verify -> 8 Export

Color coding:
- Implemented stages: solid colored boxes (Cable Blue, Leaf Green, Olive, Ocean Blue, Seafoam)
- Planned stages (Simulate, Decide): dashed border, Neutral 700 (#8B8985) fill

## Layout
- Full poster width, prominent position (center or just below the challenge)
- Pipeline diagram as the hero visual -- large and eye-catching
- Compact table below or beside the diagram
- Streaming code example in a small code block

## AI Design Prompt
> Create the central section of a scientific poster showing an 8-stage data pipeline. Draw a horizontal flow diagram with 8 connected boxes: Import -> Process -> Simulate -> Decide -> Visualize -> Narrate -> Verify -> Export. Use Cable Blue (#00529E) for Import and Export, Leaf Green (#2C670C) for Process, Olive (#576216) for Visualize, Ocean Blue (#1A5A69) for Narrate, Seafoam (#5F9DAE) for Verify. Make Simulate and Decide boxes dashed with Neutral 700 (#8B8985) fill to indicate "planned." White text on colored boxes. Below the diagram, place a compact 8-row table showing stage name, purpose, and CLI command. Add a small code block showing the Unix pipe chaining example. Section heading "The Pipeline: 8 Composable Stages" in Navy (#00172D). This is the most important visual on the poster -- make it large and prominent.
