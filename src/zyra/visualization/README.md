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
