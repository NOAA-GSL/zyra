## 1. **Use Case & Goals**
- Allow users to spatially subset large datasets (HRRR, GFS, etc.) by:
  - **Bounding box** (lat/lon extent)
  - **Point extraction** (single location timeseries)
  - (Future: polygon masks, shapefiles, etc.)

This reduces download size, speeds up visualization, and aligns with cloud-efficient workflows.

---

## 2. **Placement in Pipeline**
- New processor module: `src/zyra/processing/subset_processor.py`  
- Exposed in CLI as:
  ```bash
  zyra process subset \\
    --input file.grib2 \\
    --bbox "-110,35,-100,45" \\
    --output subset.grib2
  ```

---

## 3. **Technical Approach**
### a. **GRIB2 input**
- Use **wgrib2** (if available) for subsetting:  
  ```bash
  wgrib2 file.grib2 -small_grib lonW lonE latS latN subset.grib2
  ```
- Or use **cfgrib/xarray**:  
  ```python
  import xarray as xr
  ds = xr.open_dataset("file.grib2", engine="cfgrib")
  ds_sel = ds.sel(latitude=slice(latN, latS), longitude=slice(lonW, lonE))
  ds_sel.to_netcdf("subset.nc")
  ```

### b. **NetCDF/Zarr input**
- Directly use **xarray’s `.sel()`** with bounding box slices.  

### c. **Output**
- Keep format consistent with `--output` flag (GRIB2, NetCDF, GeoTIFF).  
- Reuse `convert-format` processor where possible.  

---

## 4. **CLI Design**
Proposed options:
```bash
zyra process subset \\
  --input hrrr.grib2 \\
  --bbox "-110,35,-100,45" \\   # lon_min, lat_min, lon_max, lat_max
  --output colorado.grib2
```

Extensions:
- `--point lon lat` → extract nearest grid point.  
- `--polygon shapefile.geojson` (future).  

---

## 5. **Integration with IDX (Future)**
- For HRRR in AWS S3, subsetting could be **done at download time**:
  - Parse `.idx` file.  
  - Filter only records that overlap bounding box.  
  - Fetch those byte ranges.  

This would be a **Phase 2 optimization** — start with local subsetting first.

---

## 6. **Implementation Steps**
1. **Prototype** `subset_processor.py` using xarray + cfgrib for NetCDF/GRIB inputs.  
2. **CLI wiring**: add `cmd_process_subset` in `cli.py`.  
3. **Output handling**: integrate with existing format converter.  
4. **Tests**:  
   - Full CONUS HRRR → subset Colorado  
   - Small NetCDF test file  
5. **Docs**: update CLI docs + examples.  

---

## 7. **Milestones**
- **MVP**: Support bounding-box subset for NetCDF & GRIB2 → NetCDF output.  
- **Phase 2**: Add GRIB2 → GRIB2 with `wgrib2` backend.  
- **Phase 3**: Add S3 IDX-aware subsetting (fetch only spatial subset from bucket).  
- **Phase 4**: Polygon masking & shapefile support.  
