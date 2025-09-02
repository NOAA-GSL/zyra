Zyra provides a flexible logging system for both **console output** and **file-based logs**, designed to help users debug workflows and preserve reproducible run histories.

---

## 🔍 Logging Overview

- Uses **Python's standard `logging` module**.
- Verbosity controlled by CLI flags (`-v/--verbose`, `--quiet`).
- Supports logging to **console** and/or **file(s)**.
- Errors are logged with helpful context for reruns.

---

## ⚙️ CLI Options

| Flag              | Description |
|-------------------|-------------|
| `-v`, `--verbose` | Enable debug-level logging (more details). |
| `--quiet`         | Suppress most output (errors only). |
| `--log-file PATH` | Write logs to the specified file. |
| `--log-dir DIR`   | Write structured logs under a directory (`workflow.log` by default). |
| `--log-file-mode` | File write mode: `append` (default) or `overwrite`. |

---

## 📊 Verbosity Levels

Logging levels are tied to environment variables:

- `ZYRA_VERBOSITY`, `DATAVIZHUB_VERBOSITY`
- Possible values:  
  - `debug` → `logging.DEBUG`  
  - `info` → `logging.INFO`  
  - `quiet` → `logging.ERROR`

These are automatically set when you pass `--verbose` or `--quiet` to the CLI.

---

## 🖥️ Console Logging

By default, Zyra prints logs to the console using the selected verbosity level.  
Examples:

```bash
zyra run pipeline.yaml --verbose
```

Will show **debug** logs for every stage.

```bash
zyra run pipeline.yaml --quiet
```

Will only display errors.

---

## 📂 File Logging

You can persist logs for reproducibility using:

```bash
zyra run pipeline.yaml --log-file run.log
```

Or use a log directory:

```bash
zyra run pipeline.yaml --log-dir ./logs/
```

This will generate `workflow.log` (or stage-specific logs) inside the directory.

To overwrite instead of append:

```bash
zyra run pipeline.yaml --log-file run.log --log-file-mode overwrite
```

---

## 🚨 Error Logging

If a pipeline stage fails, Zyra logs:

- The error message (`logging.error`)  
- Contextual hints (e.g., rerun with `--verbose`)  

Example output:

```
Stage 2 [process] failed with exit code 1.
Command: zyra convert-format --input file.csv --output file.nc
Hint: re-run with --verbose for details, or set ZYRA_VERBOSITY=debug.
```

---

## ✅ Summary

- **Console logging** for interactive runs.  
- **File logging** for reproducibility and debugging.  
- **Verbosity controlled** by CLI flags and env vars.  
- **Helpful error hints** provided automatically.

---
