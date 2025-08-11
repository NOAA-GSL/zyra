Tiny GRIB2 sample placeholder

This repository prefers shipping a very small, public‑domain GRIB2 file to enable fully offline tests and demos.

Network access is restricted in some environments, so the sample is not embedded here automatically. If you can fetch one, place it in this directory as `tiny.grib2` (≤ 200 KB ideally). Suitable sources:

- NOMADS/NCEP: small single‑message test files
- NODD/GSL test artifacts

Once added, tests and examples can reference `tests/testdata/tiny.grib2` without requiring internet access.

demo.grib2: A minimal GRIB2 sample used for offline CLI streaming tests. Generated with nodd_fetch.py from a single variable subset of a live NOMADS product. To regenerate, run nodd_fetch.py rrfs_hr prs --path conus --vars 'TMP:2 m above ground' --start YYYY-MM-DD-HH -d tests/testdata, then rename the output .grib2 to demo.grib2. Use a current date/time for --start because NOMADS datasets expire quickly. Keep file size under 200 KB for fast test execution.
