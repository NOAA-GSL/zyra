Samples for Visualization CLI

This folder contains small demonstration inputs for the visualization CLI.

Files
- `demo.npy`: 10x10 float array saved in NumPy `.npy` format (random values 0–20).
- `demo.nc`: Copied from `tests/testdata/demo.nc` for consistency across tests and samples.
- `timeseries.csv`: Tiny CSV with columns `time,value` for timeseries demo.
- `generate_uv_stacks.py`: Script to create tiny U/V stacks (`u_stack.npy`, `v_stack.npy`, and `uv_stack.nc`).

Prerequisites
- Install the visualization extras; this includes Matplotlib, Cartopy, Xarray, and SciPy:
  - Poetry: `poetry install --with dev -E visualization`
  - Pip (editable): `pip install -e .[visualization]`

Usage
- Heatmap from `.npy`:
  - `python -m datavizhub.cli heatmap --input samples/demo.npy --output heatmap.png`
  - Optional: add `--width 256 --height 128` for a smaller image.
- Contour from `.nc` (variable `T2M`):
  - `python -m datavizhub.cli contour --input samples/demo.nc --var T2M --output contour.png --levels 5,10,15 --filled`
- Timeseries from `.csv`:
  - `python -m datavizhub.cli timeseries --input samples/timeseries.csv --x time --y value --output timeseries.png`
- Vector field (U/V) from `.npy` (e.g., wind or currents):
  - First, generate tiny stacks (default uniform flow): `python samples/generate_uv_stacks.py`
  - Then render: `python -m datavizhub.cli vector --u samples/u_stack.npy --v samples/v_stack.npy --output vector.png`
  - Note: `wind` is a deprecated alias for `vector` and still works.
- Animation (frames only):
  - Generate a small 3D stack: `python - << 'PY'\nimport numpy as np, os\nos.makedirs('samples', exist_ok=True)\nstack = np.random.rand(3, 16, 32).astype('float32')\nnp.save('samples/stack.npy', stack)\nprint('Wrote samples/stack.npy with shape', stack.shape)\nPY`
  - Render frames: `python -m datavizhub.cli animate --mode heatmap --input samples/stack.npy --output-dir frames --width 320 --height 160`
  - Optional: compose directly after rendering frames with a custom FPS:
    - `python -m datavizhub.cli animate --mode heatmap --input samples/stack.npy --output-dir frames --to-video out.mp4 --fps 12`
  - Inspect `frames/` for `frame_0000.png`, `frame_0001.png`, `frame_0002.png` and an optional `manifest.json` if `--manifest` was provided.
  - Vector fields: generate U/V stacks and render
    - Generate U/V stacks: `python samples/generate_uv_stacks.py --pattern uniform --t 3 --ny 12 --nx 24`
    - Render vector frames: `python -m datavizhub.cli animate --mode vector --u samples/u_stack.npy --v samples/v_stack.npy --output-dir frames_vec --width 320 --height 160`
  - Particle advection over vector fields
    - Render particle frames: `python -m datavizhub.cli animate --mode particles --u samples/u_stack.npy --v samples/v_stack.npy --output-dir frames_particles --width 320 --height 160 --particles 80`
  - Compose frames to video (requires ffmpeg):
    - `python -m datavizhub.cli compose-video --frames frames --output out.mp4 --fps 12`

Interactive HTML
- Heatmap (Folium engine):
  - `python -m datavizhub.cli interactive --input samples/demo.npy --output interactive.html --engine folium --mode heatmap`
- Heatmap (Plotly engine):
  - `python -m datavizhub.cli interactive --input samples/demo.npy --output interactive_plotly.html --engine plotly --mode heatmap --width 600 --height 400`
- Points from CSV:
  - Provided `samples/points.csv` includes columns `lat,lon,popup`.
  - Run: `python -m datavizhub.cli interactive --input samples/points.csv --output points.html --engine folium --mode points`
  - Click markers to see the popup labels.

- Points TimeDimension (animated points):
  - Provided `samples/points_time.csv` includes columns `lat,lon,time,popup`.
  - Run:
    - `python -m datavizhub.cli interactive \
      --input samples/points_time.csv \
      --output points_time.html \
      --engine folium --mode points \
      --time-column time --period P1D --transition-ms 300`

### Interactive Vector Overlays

Generate U/V stacks if missing:

```
python samples/generate_uv_stacks.py --pattern rotation --t 5 --ny 10 --nx 10
```

Quiver:

```
python -m datavizhub.cli interactive --mode vector \
  --u samples/u_stack.npy --v samples/v_stack.npy \
  --output vector_quiver.html --engine folium
```

Streamlines:

```
python -m datavizhub.cli interactive --mode vector \
  --u samples/u_stack.npy --v samples/v_stack.npy \
  --output vector_streamlines.html --engine folium --streamlines
```

Requires:

```
pip install -e .[interactive]
```

Notebook Quickstart
- A minimal notebook is provided at `samples/Visualization_Quickstart.ipynb` covering heatmap, contour, vector, particles, frames, and an interactive example. Open it in Jupyter or VS Code and run cells top-to-bottom.
    - Inspect `frames_vec/` for `frame_0000.png`, `frame_0001.png`, `frame_0002.png` and `manifest.json` if `--manifest` was provided.

Notes
- The `.nc` file is a small sample duplicated from `tests/testdata`.
- Outputs are static PNG images in PlateCarree projection. Add a basemap with `--basemap path/to/image.jpg` if desired (see packaged images under `datavizhub.assets.images`).
- Stages can be run independently by installing only their extras (e.g., visualization) without acquisition or processing extras.

Overlays and Features
- Colorbar and labels (heatmap/contour):
  - `python -m datavizhub.cli heatmap --input samples/demo.npy --output heatmap_cb.png --colorbar --label "Temperature" --units K`
- Map features and quick negations:
  - Start from defaults and remove borders: `--no-borders`
  - Or specify explicitly: `--features coastline,borders --no-borders`
  - Example: `python -m datavizhub.cli contour --input samples/demo.nc --var T2M --output contour_feat.png --filled --features coastline,gridlines --no-gridlines`
- Timestamp overlay and placement:
  - Static: `--timestamp "2024-01-01 00Z" --timestamp-loc upper_right`
  - Animated: `--show-timestamp --timestamps-csv samples/timestamps.csv --timestamp-loc lower_left`
