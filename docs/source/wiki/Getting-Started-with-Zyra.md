Welcome to **Zyra**! 🌿 This page will help you install Zyra, explore its CLI, and run your first simple workflow.  

---

## 1. Install Zyra

Zyra is available on **PyPI**, so you can install it with:

```bash
pip install zyra
```

✅ Requires **Python 3.10+**.  
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

Here’s a simple example: fetching demo weather data and turning it into a plot.

```bash
# Step 1. Acquire example dataset
zyra acquire --source demo-weather

# Step 2. Process (filter last 24 hours)
zyra process --filter "last24h"

# Step 3. Visualize
zyra visualize --type line --output weather_plot.png
```

✨ Result: a **line chart** of weather data saved as `weather_plot.png`.

---

## 4. Next Steps

- 🌐 [Introduction](https://github.com/NOAA-GSL/zyra/wiki/Introduction) – Deeper context and design overview  
- 🧩 [Pipeline Patterns](https://github.com/NOAA-GSL/zyra/wiki/Pipeline-Patterns) – Reusable workflow templates  
- 🎨 [Visualization Module](https://noaa-gsl.github.io/zyra/api/zyra.visualization.html) – Plots, maps, and animations  
- 🔧 [Processing Module](https://noaa-gsl.github.io/zyra/api/zyra.processing.html) – GRIB, NetCDF, and data transformations  
- 🌐 [Acquisition Modules](https://noaa-gsl.github.io/zyra/api/zyra.connectors.html) – Fetching data from FTP, HTTP/S, S3, and more  
- 🛠️ [Utilities](https://noaa-gsl.github.io/zyra/api/zyra.utils.html) – File management, credentials, and helpers  

---

✨ *You just grew your first insight with Zyra!*  
