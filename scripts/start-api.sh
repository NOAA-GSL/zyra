#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

# Start the Zyra FastAPI server (development convenience)
exec uvicorn zyra.api.server:app --reload --host 0.0.0.0 --port 8000

