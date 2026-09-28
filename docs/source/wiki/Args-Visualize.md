Render frames, plots, animations, or composed video.

Aliases accepted for `stage:` — `visualization`, `render`.

Generated from Zyra **0.1.54**. See [Pipeline Schema](Pipeline-Schema) for how `args` keys become CLI flags.

**Commands:** [`animate`](#visualize-animate) · [`compose-video`](#visualize-compose-video) · [`contour`](#visualize-contour) · [`heatmap`](#visualize-heatmap) · [`interactive`](#visualize-interactive) · [`sos`](#visualize-sos) · [`timeseries`](#visualize-timeseries) · [`vector`](#visualize-vector)

---
### `visualize animate`

zyra visualize animate

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `input` | `--input` | path |  |  |
| `inputs` | `--inputs` | path |  |  |
| `output` | `--output` | path |  |  |
| `output_dir` | `--output-dir` | path |  |  |
| `mode` | `--mode` | str | `heatmap` | Choices: `heatmap`, `contour`, `vector`, `particles` |
| `var` | `--var` | str |  |  |
| `uvar` | `--uvar` | str |  |  |
| `vvar` | `--vvar` | str |  |  |
| `u` | `--u` | str |  |  |
| `v` | `--v` | str |  |  |
| `density` | `--density` | float | `0.2` |  |
| `scale` | `--scale` | str |  |  |
| `color` | `--color` | str | `#333333` |  |
| `basemap` | `--basemap` | str |  | Basemap (path, bare image name, or pkg:ref) |
| `extent` | `--extent` | float |  | west east south north (default: -180 180 -90 90) (note: `process reproject --dst-bounds` uses west south east north) |
| `width` | `--width` | int | `1024` |  |
| `height` | `--height` | int | `512` |  |
| `dpi` | `--dpi` | int | `96` |  |
| `cmap` | `--cmap` | str | `YlOrBr` |  |
| `levels` | `--levels` | str |  |  |
| `vmin` | `--vmin` | str |  |  |
| `vmax` | `--vmax` | str |  |  |
| `colorbar` | `--colorbar` | bool | `False` |  |
| `label` | `--label` | str |  |  |
| `units` | `--units` | str |  |  |
| `show_timestamp` | `--show-timestamp` | bool | `False` |  |
| `timestamps_csv` | `--timestamps-csv` | str |  |  |
| `timestamp_loc` | `--timestamp-loc` | str | `lower_right` | Choices: `upper_left`, `upper_right`, `lower_left`, `lower_right` |
| `map_type` | `--map-type` | str | `image` | Choices: `image`, `tile` |
| `tile_source` | `--tile-source` | str |  |  |
| `tile_zoom` | `--tile-zoom` | int | `3` |  |
| `xarray_engine` | `--xarray-engine` | str |  |  |
| `crs` | `--crs` | str |  |  |
| `reproject` | `--reproject` | bool | `False` |  |
| `to_video` | `--to-video` | str |  |  |
| `fps` | `--fps` | int | `30` |  |
| `grid_mode` | `--grid-mode` | str | `grid` | Choices: `grid`, `hstack`, `vstack` |
| `grid_cols` | `--grid-cols` | int | `2` |  |
| `combine_to` | `--combine-to` | str |  |  |
| `seed` | `--seed` | int | `0` |  |
| `particles` | `--particles` | int | `2000` |  |
| `custom_seed` | `--custom-seed` | bool | `False` |  |
| `dt` | `--dt` | float | `0.5` |  |
| `steps_per_frame` | `--steps-per-frame` | int | `1` |  |
| `method` | `--method` | str | `RK4-SPH` | Choices: `RK4-SPH`, `RK4-Grid` |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

**Chaining:** writes via `--output`.

### `visualize compose-video`

zyra visualize compose-video

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `frames` | `--frames` | path |  | Frames directory |
| `output` | `--output` | path |  | Output MP4 path |
| `glob` | `--glob` | str |  | Filename glob within frames dir (e.g., '*.png'); defaults to first extension found |
| `fps` | `--fps` | int |  | Frames per second (default: 30) |
| `basemap` | `--basemap` | str |  | Basemap (path, bare image name, or pkg:ref) |
| `preset` | `--preset` | str |  | Named output preset. 'sos' pins the Science On a Sphere spec: 4096x2048, 30 fps, H.264 yuv420p, faststart. Explicit flags override individual preset values. Choices: `sos` |
| `size` | `--size` | str |  | Output size as WIDTHxHEIGHT (e.g., 4096x2048); frames are scaled preserving aspect ratio and padded to fit |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

**Chaining:** writes via `--output`.

### `visualize contour`

zyra visualize contour

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `input` | `--input` | path |  | Path to .nc/.nc4, .npy, or .tif/.tiff input |
| `inputs` | `--inputs` | path |  | Multiple inputs for batch rendering |
| `output_dir` | `--output-dir` | path |  | Directory to write outputs for --inputs |
| `output_names` | `--output-names` | path |  | Destination filenames for --inputs, one per input, in order (default: the source stem + .png) |
| `var` | `--var` | str |  | Variable name for NetCDF inputs |
| `band` | `--band` | int | `1` | Band to read for GeoTIFF (.tif/.tiff) inputs (1-based; nodata renders transparent) |
| `basemap` | `--basemap` | str |  | Basemap (path, bare image name, or pkg:ref) |
| `extent` | `--extent` | float |  | west east south north (default: -180 180 -90 90) (note: `process reproject --dst-bounds` uses west south east north) |
| `output` | `--output` | path |  | Output PNG path (required for single --input; when using --inputs, prefer --output-dir) |
| `width` | `--width` | int | `1024` |  |
| `height` | `--height` | int | `512` |  |
| `dpi` | `--dpi` | int | `96` |  |
| `cmap` | `--cmap` | str | `YlOrBr` |  |
| `cmap_file` | `--cmap-file` | str |  | Palette JSON (classified bands or continuous spec); path, '-', or an http(s)/s3 URL |
| `legend_file` | `--legend-file` | str |  | Write a standalone colorbar legend image (transparent background) |
| `legend_orientation` | `--legend-orientation` | str | `horizontal` | Orientation for --legend-file Choices: `horizontal`, `vertical` |
| `filled` | `--filled` | bool | `False` | Use filled contours |
| `levels` | `--levels` | str |  | Count or comma-separated levels (default: 10; with a classified --cmap-file the palette bounds are used unless set) |
| `colorbar` | `--colorbar` | bool | `False` |  |
| `label` | `--label` | str |  |  |
| `units` | `--units` | str |  |  |
| `features` | `--features` | str |  | Comma-separated features: coastline,borders,gridlines |
| `xarray_engine` | `--xarray-engine` | str |  | xarray engine for NetCDF inputs (e.g., netcdf4, h5netcdf, scipy) |
| `map_type` | `--map-type` | str | `image` | Choices: `image`, `tile` |
| `tile_source` | `--tile-source` | str |  | Contextily tile source (when --map-type=tile) |
| `tile_zoom` | `--tile-zoom` | int | `3` |  |
| `timestamp` | `--timestamp` | str |  | Overlay timestamp string |
| `crs` | `--crs` | str |  | Force input CRS (e.g., EPSG:3857) |
| `reproject` | `--reproject` | bool | `False` |  |
| `timestamp_loc` | `--timestamp-loc` | str | `lower_right` | Timestamp placement (axes-relative) Choices: `upper_left`, `upper_right`, `lower_left`, `lower_right` |
| `no_coastline` | `--no-coastline` | bool | `False` |  |
| `no_borders` | `--no-borders` | bool | `False` |  |
| `no_gridlines` | `--no-gridlines` | bool | `False` |  |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

**Chaining:** writes via `--output`.

### `visualize heatmap`

zyra visualize heatmap

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `input` | `--input` | path |  | Path to .nc/.nc4, .npy, or .tif/.tiff input |
| `var` | `--var` | str |  | Variable name for NetCDF inputs |
| `band` | `--band` | int | `1` | Band to read for GeoTIFF (.tif/.tiff) inputs (1-based; nodata renders transparent) |
| `basemap` | `--basemap` | str |  | Basemap (path, bare image name, or pkg:ref) |
| `extent` | `--extent` | float |  | west east south north (default: -180 180 -90 90) (note: `process reproject --dst-bounds` uses west south east north) |
| `output` | `--output` | path |  | Output PNG path (required when using --input; for --inputs use --output-dir) |
| `inputs` | `--inputs` | path |  | Multiple input paths for batch rendering |
| `output_dir` | `--output-dir` | path |  | Directory to write outputs for --inputs |
| `output_names` | `--output-names` | path |  | Destination filenames for --inputs, one per input, in order (default: the source stem + .png) |
| `width` | `--width` | int | `1024` |  |
| `height` | `--height` | int | `512` |  |
| `dpi` | `--dpi` | int | `96` |  |
| `cmap` | `--cmap` | str | `YlOrBr` |  |
| `cmap_file` | `--cmap-file` | str |  | Palette JSON (classified bands or continuous spec); path, '-', or an http(s)/s3 URL |
| `legend_file` | `--legend-file` | str |  | Write a standalone colorbar legend image (transparent background) |
| `legend_orientation` | `--legend-orientation` | str | `horizontal` | Orientation for --legend-file Choices: `horizontal`, `vertical` |
| `vmin` | `--vmin` | float |  | Fixed minimum data value for color scaling (use across frame sequences to avoid flicker) |
| `vmax` | `--vmax` | float |  | Fixed maximum data value for color scaling (use across frame sequences to avoid flicker) |
| `data_encoded` | `--data-encoded` | bool | `False` | Write value-exact 8-bit grayscale instead of a picture: luma is the value normalised against --vmin/--vmax, and a palette sidecar colours it at display time. Requires --vmin/--vmax; never autoscales per frame. Bypasses the basemap and the figure pipeline entirely |
| `color_scale_file` | `--color-scale-file` | str |  | Write the palette + scale sidecar JSON for --data-encoded (stops, vmin, vmax, units, transparentRange) |
| `colorbar` | `--colorbar` | bool | `False` |  |
| `label` | `--label` | str |  |  |
| `units` | `--units` | str |  |  |
| `features` | `--features` | str |  | Comma-separated features: coastline,borders,gridlines |
| `xarray_engine` | `--xarray-engine` | str |  | xarray engine for NetCDF inputs (e.g., netcdf4, h5netcdf, scipy) |
| `map_type` | `--map-type` | str | `image` | Basemap type: image (default) or tile Choices: `image`, `tile` |
| `tile_source` | `--tile-source` | str |  | Contextily tile source name or URL (when --map-type=tile) |
| `tile_zoom` | `--tile-zoom` | int | `3` | Tile source zoom level |
| `timestamp` | `--timestamp` | str |  | Overlay timestamp string |
| `crs` | `--crs` | str |  | Force input CRS (e.g., EPSG:3857) |
| `reproject` | `--reproject` | bool | `False` | Attempt reprojection to EPSG:4326 (limited support) |
| `timestamp_loc` | `--timestamp-loc` | str | `lower_right` | Timestamp placement (axes-relative) Choices: `upper_left`, `upper_right`, `lower_left`, `lower_right` |
| `no_coastline` | `--no-coastline` | bool | `False` |  |
| `no_borders` | `--no-borders` | bool | `False` |  |
| `no_gridlines` | `--no-gridlines` | bool | `False` |  |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

**Chaining:** writes via `--output`.

**Example stage**

```yaml
- stage: visualize
  command: heatmap
  args:
    input: "samples/demo.npy"
    output: "/tmp/heatmap.png"
```

### `visualize interactive`

zyra visualize interactive

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `input` | `--input` | path |  |  |
| `var` | `--var` | str |  |  |
| `mode` | `--mode` | str | `heatmap` | Choices: `heatmap`, `vector`, `points` |
| `engine` | `--engine` | str | `plotly` | Choices: `plotly`, `folium` |
| `cmap` | `--cmap` | str | `YlOrBr` |  |
| `colorbar` | `--colorbar` | bool | `False` |  |
| `label` | `--label` | str |  |  |
| `units` | `--units` | str |  |  |
| `timestamp` | `--timestamp` | str |  |  |
| `timestamp_loc` | `--timestamp-loc` | str | `lower_right` |  |
| `tiles` | `--tiles` | str | `OpenStreetMap` |  |
| `zoom` | `--zoom` | int | `3` |  |
| `extent` | `--extent` | float |  | west east south north (default: -180 180 -90 90) (note: `process reproject --dst-bounds` uses west south east north) |
| `width` | `--width` | int | `1024` |  |
| `height` | `--height` | int | `512` |  |
| `output` | `--output` | path |  |  |
| `uvar` | `--uvar` | str |  |  |
| `vvar` | `--vvar` | str |  |  |
| `u` | `--u` | str |  |  |
| `v` | `--v` | str |  |  |
| `density` | `--density` | float | `0.2` |  |
| `scale` | `--scale` | float | `1.0` |  |
| `color` | `--color` | str | `#333333` |  |
| `streamlines` | `--streamlines` | bool | `False` |  |
| `features` | `--features` | str |  |  |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

**Chaining:** writes via `--output`.

### `visualize sos`

Render gridded data as Science On a Sphere (SOS) frames: full-globe, PlateCarree, 2:1, edge-to-edge PNGs. Use a fixed --vmin/--vmax range to keep color scaling identical across a frame sequence (flicker-free). Supports single (--input/--output) and batch (--inputs/--output-dir) modes.

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `input` | `--input` | path |  | Path to .nc or .npy input |
| `inputs` | `--inputs` | path |  | Multiple input paths for batch rendering |
| `var` | `--var` | str |  | Variable name for NetCDF inputs |
| `output` | `--output` | path |  | Output PNG path (required when using --input) |
| `output_dir` | `--output-dir` | path |  | Directory to write outputs (required when using --inputs) |
| `basemap` | `--basemap` | str |  | Optional basemap (path, bare image name, or pkg:ref) drawn under the data |
| `extent` | `--extent` | float |  | west east south north (default: global -180 180 -90 90) (note: `process reproject --dst-bounds` uses west south east north) |
| `width` | `--width` | int | `4096` | Output width (px) |
| `height` | `--height` | int | `2048` | Output height (px) |
| `dpi` | `--dpi` | int | `96` |  |
| `cmap` | `--cmap` | str | `YlOrBr` | Colormap name |
| `vmin` | `--vmin` | float |  | Fixed minimum data value for color scaling (recommended for sequences) |
| `vmax` | `--vmax` | float |  | Fixed maximum data value for color scaling (recommended for sequences) |
| `flip` | `--flip` | bool | `False` | Flip data vertically before rendering (for north-up grids) |
| `xarray_engine` | `--xarray-engine` | str |  | xarray engine for NetCDF inputs (e.g., netcdf4, h5netcdf, scipy) |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

### `visualize timeseries`

zyra visualize timeseries

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `input` | `--input` | path |  |  |
| `x` | `--x` | str |  |  |
| `y` | `--y` | str |  |  |
| `var` | `--var` | str |  |  |
| `output` | `--output` | path |  |  |
| `title` | `--title` | str |  |  |
| `xlabel` | `--xlabel` | str |  |  |
| `ylabel` | `--ylabel` | str |  |  |
| `style` | `--style` | str | `line` | Choices: `line`, `scatter` |
| `width` | `--width` | int | `1024` |  |
| `height` | `--height` | int | `512` |  |
| `dpi` | `--dpi` | int | `96` |  |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

**Chaining:** writes via `--output`.

### `visualize vector`

zyra visualize vector

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `input` | `--input` | path |  |  |
| `inputs` | `--inputs` | path |  |  |
| `output` | `--output` | path |  |  |
| `output_dir` | `--output-dir` | path |  |  |
| `uvar` | `--uvar` | str |  |  |
| `vvar` | `--vvar` | str |  |  |
| `u` | `--u` | str |  |  |
| `v` | `--v` | str |  |  |
| `basemap` | `--basemap` | str |  | Basemap (path, bare image name, or pkg:ref) |
| `extent` | `--extent` | float |  | west east south north (default: -180 180 -90 90) (note: `process reproject --dst-bounds` uses west south east north) |
| `width` | `--width` | int | `1024` |  |
| `height` | `--height` | int | `512` |  |
| `dpi` | `--dpi` | int | `96` |  |
| `crs` | `--crs` | str |  |  |
| `reproject` | `--reproject` | bool | `False` |  |
| `map_type` | `--map-type` | str | `image` | Choices: `image`, `tile` |
| `tile_source` | `--tile-source` | str |  |  |
| `tile_zoom` | `--tile-zoom` | int | `3` |  |
| `density` | `--density` | float | `0.2` |  |
| `scale` | `--scale` | float |  |  |
| `color` | `--color` | str | `#333333` |  |
| `streamlines` | `--streamlines` | bool | `False` |  |
| `features` | `--features` | str |  |  |
| `no_coastline` | `--no-coastline` | bool | `False` |  |
| `no_borders` | `--no-borders` | bool | `False` |  |
| `no_gridlines` | `--no-gridlines` | bool | `False` |  |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

**Chaining:** writes via `--output`.
