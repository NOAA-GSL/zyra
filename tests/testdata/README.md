Tiny sample files (GRIB2 and NetCDF)

This repository prefers using very small, public‑domain sample files to enable fully offline tests and demos.

Network access is restricted in some environments, so samples are not embedded automatically. If you can fetch or generate them, place files in this directory as `demo.grib2` and `demo.nc` (≤ 200 KB each, ideally). Suitable sources:

- GRIB2: NOMADS/NCEP single‑message test files; NODD/GSL test artifacts
- NetCDF: Unidata sample datasets; xarray tutorial samples; or convert from the GRIB2 sample

Once added, tests and examples can reference:
- `tests/testdata/demo.grib2`
- `tests/testdata/demo.nc`

demo.grib2: A single GRIB2 message used for offline CLI streaming tests: NCEP GFS 0.5° analysis (f000), 2 m temperature (`TMP:2 m above ground:anl`), cycle 2025-08-10 00Z, 720 × 361 global lat/lon grid, 160,539 bytes. It is record 580 of the public NODD copy of `gfs.t00z.pgrb2.0p50.f000` on AWS. To fetch it again, look up the record's byte range in the `.idx` file and request just that range:

    BASE=https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.20250810/00/atmos/gfs.t00z.pgrb2.0p50.f000
    curl -s "$BASE.idx" | grep -A1 ':TMP:2 m above ground:anl:'
    # bytes = this record's offset .. next record's offset - 1
    curl -H 'Range: bytes=121590373-121750911' -o demo.grib2 "$BASE"

`zyra.utils.grib.idx_to_byteranges` computes the same range from the `.idx` lines. GFS data on NODD is retained long-term; if this cycle is ever removed, any GFS 0.5° `TMP:2 m above ground:anl` record works, though the tests assume the 720 × 361 grid.

demo.nc: A tiny NetCDF counterpart. You can either download a small NetCDF from Unidata/xarray sample collections, or convert from `demo.grib2` if you have tools installed:

- Using wgrib2: `wgrib2 demo.grib2 -netcdf demo.nc`
- Using CDO: `cdo -f nc copy demo.grib2 demo.nc`

If needed, further subset variables or time steps to keep `demo.nc` small for fast tests.

Binary fixtures and git: these files must be stored byte-for-byte. `.gitattributes` marks their formats as `binary`; without that, the repo-wide `* text eol=lf` rule rewrites CRLF byte pairs inside the data on commit and silently corrupts them. `tests/misc/test_testdata_integrity.py` checks that each fixture is structurally intact.
