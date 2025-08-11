Tiny sample files (GRIB2 and NetCDF)

This repository prefers using very small, public‑domain sample files to enable fully offline tests and demos.

Network access is restricted in some environments, so samples are not embedded automatically. If you can fetch or generate them, place files in this directory as `demo.grib2` and `demo.nc` (≤ 200 KB each, ideally). Suitable sources:

- GRIB2: NOMADS/NCEP single‑message test files; NODD/GSL test artifacts
- NetCDF: Unidata sample datasets; xarray tutorial samples; or convert from the GRIB2 sample

Once added, tests and examples can reference:
- `tests/testdata/demo.grib2`
- `tests/testdata/demo.nc`

demo.grib2: A minimal GRIB2 sample used for offline CLI streaming tests. Generated with `nodd_fetch.py` from a single‑variable subset of a live NOMADS product. To regenerate, run:

    nodd_fetch.py rrfs_hr prs --path conus --vars 'TMP:2 m above ground' --start YYYY-MM-DD-HH -d tests/testdata

Then rename the output `.grib2` to `demo.grib2`. Use a current date/time for `--start` because NOMADS datasets expire quickly. Keep file size under 200 KB for fast test execution.

demo.nc: A tiny NetCDF counterpart. You can either download a small NetCDF from Unidata/xarray sample collections, or convert from `demo.grib2` if you have tools installed:

- Using wgrib2: `wgrib2 demo.grib2 -netcdf demo.nc`
- Using CDO: `cdo -f nc copy demo.grib2 demo.nc`

If needed, further subset variables or time steps to keep `demo.nc` small for fast tests.
