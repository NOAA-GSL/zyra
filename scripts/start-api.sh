#!/usr/bin/env bash
set -euo pipefail

# Start the DataVizHub FastAPI server (development convenience)
exec uvicorn datavizhub.api.server:app --reload --host 0.0.0.0 --port 8000

