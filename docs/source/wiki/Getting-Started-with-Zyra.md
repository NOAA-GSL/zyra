Welcome to **Zyra**! 🌿 This page will help you install Zyra, explore its CLI, and run your first simple workflow.  

---

## 1. Install Zyra

Zyra is available on **PyPI**, so you can install it with:

```bash
pip install zyra
```

✅ Requires **Python 3.11.5+**.  
For developer setup, see the [Contributing Guide](https://github.com/NOAA-GSL/zyra/wiki/Contributing).

---

## 2. Explore the CLI

Zyra comes with a **command-line interface (CLI)** for building workflows quickly.  
Check available commands:

```bash
zyra --help
```

You’ll see options for:  
- Data acquisition  
- Processing and transformations  
- Visualization (plots, maps, animations)  
- Export  

📖 [Read the CLI reference →](https://noaa-gsl.github.io/zyra/api/zyra.cli.html)

---

## 3. Your First Workflow

Here’s a simple, realistic flow using the CLI’s groups:

```bash
# Step 1. Acquire a file (HTTP → local path)
zyra acquire http https://example.com/sample.grib2 -o sample.grib2

# Step 2. Convert GRIB2 → NetCDF (streams stdout to file)
zyra process convert-format sample.grib2 netcdf --stdout > sample.nc

# Step 3. Visualize (choose a variable present in the file)
zyra visualize heatmap --input sample.nc --var VAR --output weather_plot.png
```

Notes
- Replace the URL with your data source.
- Use a variable that exists in your file for `--var` (e.g., `T2M`).
- Many subcommands support stdin/stdout for piping (`-` as input/output).

---

## 4. Next Steps

- 🌐 [Introduction](https://github.com/NOAA-GSL/zyra/wiki/Introduction) – Deeper context and design overview  
- 🧩 [Pipeline Patterns](https://github.com/NOAA-GSL/zyra/wiki/Pipeline-Patterns) – Reusable workflow templates  
- 🎨 [Visualization Module](https://noaa-gsl.github.io/zyra/api/zyra.visualization.html) – Plots, maps, and animations  
- 🔧 [Processing Module](https://noaa-gsl.github.io/zyra/api/zyra.processing.html) – GRIB, NetCDF, and data transformations  
- 🔌 [Connectors](https://noaa-gsl.github.io/zyra/api/zyra.connectors.html) – HTTP/FTP/S3/Vimeo transfer helpers  
- 🛠️ [Utilities](https://noaa-gsl.github.io/zyra/api/zyra.utils.html) – File management, credentials, and helpers  

---

✨ *You just grew your first insight with Zyra!*  
