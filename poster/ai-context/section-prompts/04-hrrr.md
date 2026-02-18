# Section 4: Use Case -- HRRR Weather Model Processing

## Purpose
Demonstrate a concrete scientific workflow: acquiring, converting, and visualizing HRRR weather model data.

## Content

**Heading:** Use Case: HRRR Weather Model Processing

**Description:** Acquire the latest High-Resolution Rapid Refresh forecast, convert to NetCDF, and visualize temperature -- three commands, one pipeline.

**Code:**
```bash
zyra acquire http https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.20240101/conus/hrrr.t00z.wrfsfcf00.grib2 -o hrrr.grib2
zyra process convert-format hrrr.grib2 netcdf -o hrrr.nc
zyra visualize heatmap --input hrrr.nc --var TMP --colorbar --output hrrr_temp.png
```

**Image:** `poster/assets/generated/heatmap.png`
**Caption:** Heatmap rendered by `zyra visualize heatmap`

## Layout
- Half-column width
- Code block on top, heatmap image below
- Image should be prominent (at least 3-4 inches wide on poster)

## AI Design Prompt
> Create a use case card for a scientific poster. Heading "Use Case: HRRR Weather Model Processing" in Ocean Blue (#1A5A69), 20pt bold. A brief one-line description in Neutral 900. Below that, a code block with 3 bash commands on a Neutral 200 (#F7F5EE) background with monospace font. Below the code, display the heatmap.png image at roughly 4 inches wide with a caption "Heatmap rendered by zyra visualize heatmap" in italics. Use a thin Cable Blue (#00529E) left border or card frame. This occupies half the poster width.
