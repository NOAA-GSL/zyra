# Visualization

Commands
- `heatmap` — Render a 2D heatmap from NetCDF or NumPy arrays.
- `contour` — Render contour or filled-contour plots.
- `timeseries` — Plot time series.
- `vector` — Render vector/wind plots from U/V components.
- `animate` — Render animations from frames or datasets.
- `compose-video` — Compose image sequences into a video.
- `interactive` — Generate interactive maps.

Common options (subset)
- `--input` / `--inputs` — single or batch inputs
- `--output` / `--output-dir` — output path or directory for batches
- Dimensions & style: `--width`, `--height`, `--dpi`, `--cmap`, `--colorbar`
- Map features: `--basemap`, `--extent`, `--features coastline,borders,gridlines`
- CRS & reprojection: `--crs`, `--reproject`
- Tiles: `--map-type tile`, `--tile-source`, `--tile-zoom`

Examples
- Heatmap: `zyra visualize heatmap --input data.nc --var T --extent -180 180 -90 90 --output heatmap.png`
- Vector: `zyra visualize vector --input data.nc --u U --v V --output wind.png`
- Animation: `zyra visualize animate --inputs frames/*.png --fps 24 --output anim.mp4`
- Compose video: `zyra visualize compose-video --frames ./frames -o out.mp4`
- Science On a Sphere video: `zyra visualize compose-video --frames ./frames --preset sos -o dataset.mp4`

Presets (`compose-video`)
- `--preset sos` pins the NOAA Science On a Sphere spec: 4096x2048
  equirectangular (frames are scaled preserving aspect ratio and padded),
  30 fps, H.264 `yuv420p`, and `+faststart` for streaming playback.
- A preset supplies defaults, not a cage: explicit flags such as `--fps`
  or `--size WIDTHxHEIGHT` override individual preset values.
