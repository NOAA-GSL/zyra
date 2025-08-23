## 1. Setup & Structure
- [ ] Create `src/zyra/visualization/` directory.
- [ ] Add `__init__.py` to mark as package.
- [ ] Create `base.py` with `VisualizationBase` class:
  - Handles loading xarray, pandas, numpy.
  - Common args: title, labels, cmap, output path.
  - Handles map projection if geospatial.

## 2. Basemap Enhancements
- [ ] Create `basemap.py`:
  - Implement `add_basemap_cartopy(ax, extent, features)`.
  - Implement `add_basemap_tile(ax, extent, tile_source, zoom)` using `contextily`.
  - Automatic CRS detection/reprojection.
  - Args: `map_type`, `tile_source`, `map_zoom`.

## 3. Visualization Types
- [ ] `plot_contour.py`:
  - Contour plots with optional basemap.
  - Args: var, levels, cmap.
- [ ] `plot_colormap.py`:
  - 2D heatmaps with optional basemap.
  - Args: var, cmap, vmin, vmax.
- [ ] `plot_timeseries.py`:
  - Time series from CSV or netCDF.
  - Args: x, y, style.
- [ ] `plot_wind_particles.py`:
  - Static: quiver/arrows.
  - Animated: particle advection over basemap.
  - Args: u-var, v-var, density, speed, color.
- [ ] `animate.py`:
  - Time-lapse of contour/heatmaps with basemap.
- [ ] `interactive.py`:
  - Plotly/Bokeh interactive maps with tile backgrounds.

## 4. CLI Preparation (Module-Only)
- [ ] Create `cli.py` inside visualization module.
- [ ] Implement argparse or click commands for each visualization type.
- [ ] Ensure each command calls its corresponding Python function.
- [ ] Test CLI entry by running visualization module directly:
```bash
python -m zyra.visualization.cli contour --input data.nc ...
```

## 5. API Preparation (Stub Functions)
- [ ] For each visualization type, create a function with clear parameters and return type.
- [ ] Return output file path or in-memory buffer (for future API use).
- [ ] No FastAPI server yet — just ensure functions are callable externally.

## 6. Styles
- [ ] Create `styles.py` with:
  - Default cmap, font sizes, grid style.
  - Default map styling.
  - Wind particle density defaults.

## 7. Testing
**Unit Tests**:
- [ ] Each visualization type outputs a file (PNG/JPEG/SVG/MP4).
- [ ] Basemap correctly overlays in cartopy mode.
- [ ] Tile-based basemap reprojects correctly.
- [ ] Wind particle rendering handles varying grid resolutions.

**Integration Tests (Module-Level)**:
- [ ] CLI entry calls correct functions and produces expected output.
- [ ] Projection matches between data and basemap.
- [ ] Tile map at multiple zoom levels works.
- [ ] Wind animation frames match static output for same timestep.

**Performance Tests**:
- [ ] Large dataset renders in under X seconds.
- [ ] Memory footprint stable.

## 8. Dependencies
- Required: matplotlib, numpy, pandas, xarray, cartopy.
- Optional: contextily, folium, plotly, bokeh.
- For wind particles: pyproj, matplotlib.animation, optional fastplotlib.
