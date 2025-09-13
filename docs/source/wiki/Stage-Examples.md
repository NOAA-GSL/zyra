# Stage Examples

Concise examples that demonstrate each of Zyra’s eight workflow stages. Replace URLs, paths, and variables for your data.

Notes
- Many commands accept `-` for stdin/stdout to enable streaming.
- Some examples require optional extras; see Install-Extras.md.

## 1) import (acquire/ingest)

- HTTP → file
```
zyra acquire http https://example.com/sample.grib2 -o sample.grib2
```

- S3 list and fetch one to stdout → file
```
zyra acquire s3 --url s3://bucket/prefix/ --list --pattern "\\.grib2$"
zyra acquire s3 --url s3://bucket/file.grib2 -o - > file.grib2
```

- FTP sync a directory (filtered by date pattern)
```
zyra acquire ftp ftp://host/path --sync-dir ./frames --pattern "image_(\\d{8})\\.png" --since 2024-08-01 --date-format %Y%m%d
```

## 2) process (transform)

- Decode GRIB2 subset to raw bytes → NetCDF
```
zyra process decode-grib2 s3://bucket/file.grib2 --pattern ":TMP:surface:" --raw > subset.grib2
zyra process convert-format subset.grib2 netcdf --stdout > out.nc
```

- Extract a variable from NetCDF and write NetCDF
```
zyra process extract-variable demo.nc T2M --stdout | zyra process convert-format - netcdf --stdout > t2m.nc
```

## 3) simulate (planned)

- Today: create synthetic inputs via notebooks/scripts (e.g., xarray to NetCDF), then feed to `process`/`visualize`.
```
# Pseudocode (Python/xarray):
# xr.DataArray(np.random.rand(10,10), coords=[('y', range(10)), ('x', range(10))]).to_dataset(name='VAR').to_netcdf('synthetic.nc')
zyra visualize heatmap --input synthetic.nc --var VAR --output synthetic.png
```

## 4) decide (optimize; planned)

- Today: run variants via config overrides; choose artifact manually or in orchestrator.
```
zyra run pipeline.yaml --set visualize.cmap=viridis
zyra run pipeline.yaml --set visualize.cmap=magma
# Compare outputs; select best (future: `zyra decide` automates this)
```

## 5) visualize (render)

- Heatmap from NetCDF
```
zyra visualize heatmap --input out.nc --var T2M --output heatmap.png
```

- Compose frames → MP4
```
zyra visualize animate --frames ./frames --output frames
zyra visualize compose-video --frames ./frames --output movie.mp4
```

## 6) narrate (planned)

- Today: generate captions/pages from metadata using templates; pair with outputs.
```
zyra transform metadata --frames ./frames --output frames_meta.json
# Use a template tool to render a report with frames_meta.json and plots
```

## 7) verify (planned)

- Today: validate with checksums and basic metadata checks.
```
sha256sum heatmap.png > heatmap.sha256
zyra transform enrich-metadata --dataset-id ds01 --vimeo-uri urn:vimeo:123 --input frames_meta.json --output frames_meta_enriched.json
```

## 8) export (disseminate/decimate)

- Local file from stdin
```
cat t2m.nc | zyra export local - -o out.nc
```

- HTTP POST JSON
```
echo '{"ok":true}' | zyra export post - https://example.com/ingest --content-type application/json
```

- S3: stdin → object
```
cat out.nc | zyra export s3 --url s3://bucket/out.nc -i -
```

---

See also
- Workflow-Stages.md — Stage definitions, aliases, and status
- Pipeline-Patterns.md — Chaining stages and pipeline configs
- Install-Extras.md — Install the right extras for each example
