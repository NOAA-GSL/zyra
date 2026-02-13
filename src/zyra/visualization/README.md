# Visualization

Commands
- `heatmap` — Render a 2D heatmap from NetCDF or NumPy arrays.
- `contour` — Render contour or filled-contour plots.
- `timeseries` — Plot time series.
- `vector` — Render vector/wind plots from U/V components.
- `animate` — Render animations from frames or datasets.
- `compose-video` — Compose image sequences into a video.
- `interactive` — Generate interactive maps.
- `globe` — Build interactive WebGL or Cesium globe bundles.

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
- Globe (WebGL): ``zyra visualize globe --target webgl-sphere --texture earth.jpg --legend legend.png --output webgl_globe``
- Globe (Cesium): ``zyra visualize globe --target cesium-globe --tile-url https://tiledimageservices.arcgis.com/P3ePLMYs2RVChkJx/ArcGIS/rest/services/Seafloor_Age_02_WM/ImageServer --legend https://d3sik7mbbzunjo.cloudfront.net/land/sea_floor_age/colorbar_contour_en.png --output cesium_globe``

Globe bundles accept shared flags such as ``--title``/``--description`` for overlay copy, ``--legend`` for a title legend image, and ``--probe-gradient`` / ``--probe-lut`` / ``--probe-data`` so probe readouts can return color-decoded or dataset-backed values. Reusable color tables can be registered with ``--shared-gradient name=path`` when multiple layers or frame stacks should point at the same resource. Provide ``--video-source`` (local file, HTTP URL, or ``vimeo:ID``) together with ``--video-start`` and ``--video-fps`` to sample frames directly from video content—each extracted frame records an absolute timestamp based on the playback position. Textures and legends may reference local files, ``pkg:`` assets, or remote HTTP(S) URLs. Drag to rotate and use the mouse wheel or a touch pinch to zoom; ``--auto-rotate`` restores the legacy spin when desired. Use ``--lighting`` to opt back into shaded rendering—the viewer defaults to an unlit texture for clarity. The command writes an ``index.html`` alongside ``assets/`` that can be opened locally or published as static content.
