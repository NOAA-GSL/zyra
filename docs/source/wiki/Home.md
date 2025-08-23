# 🌿 Welcome to Zyra

![Zyra Banner](https://repository-images.githubusercontent.com/854215643/22d02986-68b8-44cb-a510-17082384386e)

---

## What is Zyra?

**Zyra** (pronounced *Zy-rah*) is an open-source Python framework for **growing data into insight**.  

It helps scientists, educators, and developers build **modular, reproducible workflows** that transform raw data into clear visualizations and shareable knowledge.  

Think of Zyra as a **garden for data**:  
- You **plant seeds** of data (from the web, satellites, or experiments).  
- Zyra helps you **nurture and grow them** (through filtering, analysis, and processing).  
- Finally, you **harvest insights** (in the form of visualizations, reports, and interactive media).  

It’s designed to make science not just rigorous, but also **accessible, transparent, and beautiful**.

---

## A Framework for Everyone

Zyra is:  
- **Modular** → Swap out or extend any part of the workflow.  
- **Reproducible** → Every workflow can be re-run, shared, and verified.  
- **Interoperable** → Works with popular data formats, APIs, and visualization tools.  
- **Creative** → Supports animations, maps, and interactive visuals to make science engaging.  

Whether you’re a **researcher**, **educator**, or **curious learner**, Zyra gives you a toolkit to turn data into something meaningful.

---

## Technical Introduction

*(From the [Introduction wiki page](https://github.com/NOAA-GSL/zyra/wiki/Introduction))*  

### Kid Version
Imagine you have a big box of LEGO bricks mixed together — some from space sets, some from castles, some from race cars.  

**Zyra** is like a magical robot helper that:  
1. **Finds** the bricks you want (getting data from the internet or your computer).  
2. **Puts them in order** (sorting and cleaning the data).  
3. **Builds something amazing** (turning the data into pictures, videos, or maps you can show to friends).  

It makes science data less messy and more fun to look at.

---

### High School Version
Zyra is a Python tool that:  
- **Collects** data from many sources (like websites, cloud storage, and scientific file formats).  
- **Processes** it so it’s easier to work with (cutting, reshaping, converting formats).  
- **Visualizes** it in charts, maps, and animations.  

Think of it like a 3-step factory:  
1. **Input**: Raw data from the web, satellites, or experiments.  
2. **Processing**: Filtering, analyzing, or reformatting.  
3. **Output**: Graphs, weather maps, or animated videos you can share.  

It’s modular — you can swap out any step for your own custom tool.

---

### College Version
Zyra is an open-source, modular Python framework for reproducible scientific data workflows.  
It organizes work into **four layers**:  
1. **Acquisition Layer** → Connects to FTP, HTTP/S, S3, and local sources; supports GRIB, NetCDF, GeoTIFF, and streaming video.  
2. **Processing Layer** → Extracts subsets, applies transformations, and converts between scientific formats. Includes tools like `VideoProcessor` and `GRIBDataProcessor`.  
3. **Visualization Layer** → Uses Matplotlib and Basemap to produce static plots, animations, and composites with consistent color maps and overlays.  
4. **Utilities Layer** → Handles credentials, date parsing, file management, and small shared helpers.  

The system is designed for **flexibility**, **reproducibility**, and **interoperability**, making it suitable for research, teaching, and operational pipelines.

---

### White Paper Version
Zyra is a composable Python framework for end-to-end scientific data workflows, enabling acquisition, transformation, and visualization across diverse environmental and geospatial datasets.  

It is designed to address reproducibility, modularity, and interoperability challenges in modern data science.  

**Architecture:**  
- **Acquisition Managers**: standardized connectors to heterogeneous data sources (`FTPManager`, `HTTPManager`, `S3Manager`).  
- **Processing Managers**: domain-specific operations (video encoding/decoding, GRIB parsing, NetCDF extraction, geospatial transformations).  
- **Visualization Managers**: integration with Matplotlib and Basemap for consistent, publication-quality graphics.  
- **Utility Managers**: support for credentials, temporal range calculations, file path operations, and metadata management.  

**Supported Formats & Protocols:** GRIB2, NetCDF, GeoTIFF, MP4, PNG, JPEG; FTP, HTTP/S, AWS S3, local filesystem.  

**Use Cases:** operational forecasting pipelines, climate research, geospatial analysis, educational demonstrations, and public communication products.

---

## 📖 Explore More

Want to dive deeper? Here are some key wiki pages:

- [Introduction](https://github.com/NOAA-GSL/zyra/wiki/Introduction) – The full technical overview of Zyra.
- [Pipeline Patterns](https://github.com/NOAA-GSL/zyra/wiki/Pipeline-Patterns) – Common designs and reusable workflow templates.
- [Enhancing Zyra Through Insights from Similar Tools](https://github.com/NOAA-GSL/zyra/wiki/Enhancing-Zyra-Through-Insights-from-Similar-Tools) – Lessons from other open-source projects.
- [Privacy and Data Usage Best Practices](https://github.com/NOAA-GSL/zyra/wiki/Privacy-and-Data-Usage-Best-Practices-for-Zyra) – Ethical guidance for handling data.
- [Visualization Module Checklist](https://github.com/NOAA-GSL/zyra/wiki/Zyra-Visualization-Module-%E2%80%90-Implementation-Checklist) – Progress tracking for the visualization system.
- [CLI Expansion Plan](https://github.com/NOAA-GSL/zyra/wiki/Zyra-CLI-Expansion-Plan-with-Pipeline-Configs-and-Connectors-Refactor) – Roadmap for extending Zyra’s command-line interface.
- [Wizard Interactive Assistant](https://github.com/NOAA-GSL/zyra/wiki/Wizard-Interactive-Assistant) – Plans for a guided CLI workflow builder.
- [n8n Integration Plan](https://github.com/NOAA-GSL/zyra/wiki/n8n-Integration-Plan-for-Zyra) – Connecting Zyra with external automation tools.

---

## Get Involved

Zyra is open-source and community-driven. You can:  
- Explore the [GitHub repository](https://github.com/NOAA-GSL/zyra)  
- Join the [discussions](https://github.com/NOAA-GSL/zyra/discussions)  
- Contribute new workflows, ideas, or visualizations  

---

✨ *Zyra is where data grows into insight.*  
