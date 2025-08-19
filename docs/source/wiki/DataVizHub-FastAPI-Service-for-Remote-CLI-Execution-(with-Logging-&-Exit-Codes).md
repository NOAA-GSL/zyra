## Goal
Expose the full 4-stage DataVizHub CLI as a FastAPI web service with:
- Sync and async execution modes.
- File uploads and result downloads.
- Real-time progress streaming via WebSockets.
- Full logging and exit code capture for each command (for debugging & workflow tools like n8n).
- Automatic startup in the development container.

---

## 1. Project Structure

```
src/datavizhub/api/
    __init__.py
    server.py           # FastAPI app entrypoint
    routers/
        cli.py          # Endpoints for CLI execution
        jobs.py         # Endpoints for async job management
        files.py        # Endpoints for uploads/downloads
    workers/
        executor.py     # Runs CLI commands safely
    models/
        cli_request.py  # Pydantic models for request/response
```

---

## 2. FastAPI Endpoints

### 2.1 Run CLI Command (Sync or Async)
**POST /cli/run**  
Request:
```json
{
  "stage": "process",
  "command": "decode-grib2",
  "args": { "input": "s3://bucket/file.grib2", "output": "-" },
  "mode": "sync"
}
```
Response (sync):
```json
{
  "status": "success",
  "stdout": "...",
  "stderr": "",
  "exit_code": 0
}
```
Response (async):
```json
{
  "status": "accepted",
  "job_id": "abc123"
}
```

> **Enhancement**: All responses now include `exit_code` (for sync runs) or will include it when async job is complete.

### 2.2 Upload Data
**POST /upload** (multipart form)  
- Accepts file upload, stores in `/tmp/datavizhub_uploads/`, returns `file_id`.

### 2.3 Download Results
**GET /jobs/{job_id}/download**  
- Returns output file from completed job.

### 2.4 WebSocket Progress
**/ws/jobs/{job_id}**  
- Streams logs/progress in real time.

### 2.5 Job Management
- **GET /jobs/{job_id}** → status, `stdout`, `stderr`, and `exit_code`.
- **DELETE /jobs/{job_id}** → cancel a job.

---

## 3. Internal Execution Model

### 3.1 Command Registry
```python
CLI_REGISTRY = {
    "visualize": visualization.command_map
}  # Visualization-first; other stages to be added later
```

### 3.2 Synchronous Execution with Logging & Exit Code
```python
from io import StringIO
import sys

def run_cli(stage, command, args):
    func = CLI_REGISTRY[stage][command]
    sys_stdout, sys_stderr = StringIO(), StringIO()
    sys_stdout_backup, sys_stderr_backup = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = sys_stdout, sys_stderr
    exit_code = 0
    try:
        func(**args)
    except Exception as e:
        exit_code = 1
        print(str(e), file=sys.stderr)
    finally:
        sys.stdout, sys.stderr = sys_stdout_backup, sys_stderr_backup
    return {
        "stdout": sys_stdout.getvalue(),
        "stderr": sys_stderr.getvalue(),
        "exit_code": exit_code
    }
```

### 3.3 Asynchronous Execution
- Use Celery or RQ with Redis.
- Job record stores:
  - `status`
  - `stdout`
  - `stderr`
  - `exit_code`
  - `output_file_path`

---

## 4. Bonus Features Implementation

### 4.1 File Upload Handling
- Save uploaded files to `/tmp/datavizhub_uploads/` with UUID names.
- Allow CLI args to reference `file_id`.

### 4.2 Result Download
- Store output in `/tmp/datavizhub_results/{job_id}`.
- Direct file download endpoint.

### 4.3 WebSocket Streaming
- Workers push logs and progress updates to Redis pub/sub.
- WebSocket subscribers stream updates to clients.

> Enhancement: WebSocket messages now include `{ "stdout": "...", "stderr": "...", "exit_code": 0, "progress": 0.5 }`

---

## 5. Security
- No raw shell exec — only mapped callables.
- Pydantic validation on all requests.
- API keys or OAuth2.
- Rate limiting.

---

## 6. Deployment

### 6.1 Local Dev
```bash
uvicorn datavizhub.api.server:app --reload --host 0.0.0.0 --port 8000
```

### 6.2 Production
- Gunicorn + Uvicorn workers.
- HTTPS via Nginx or Caddy.
- Redis for async jobs.

---

## 7. Dev Container Auto-Startup

### 7.1 Startup Script
`scripts/start-api.sh`:
```bash
#!/usr/bin/env bash
set -e
cd /workspace/datavizhub
uvicorn datavizhub.api.server:app --reload --host 0.0.0.0 --port 8000
```
Make executable:
```bash
chmod +x scripts/start-api.sh
```

### 7.2 Devcontainer Hook
`.devcontainer/devcontainer.json`:
```json
{
  "name": "DataVizHub Dev",
  "dockerFile": "Dockerfile",
  "postCreateCommand": "pip install -e .",
  "postStartCommand": "./scripts/start-api.sh",
  "forwardPorts": [8000]
}
```

### 7.3 Background Mode (optional)
```json
"postStartCommand": "nohup ./scripts/start-api.sh > /workspace/datavizhub/api.log 2>&1 &"
```

---

## 8. Testing
- Unit tests for endpoints and CLI execution mapping.
- Integration tests for pipelines via API.
- WebSocket tests for live progress.
- Tests for correct `exit_code`, `stdout`, and `stderr` capture.

---

## 9. Documentation
- API reference in `/docs` (FastAPI auto-docs).
- Examples for:
  - Submitting sync/async jobs.
  - Uploading files and referencing them in CLI.
  - Downloading results.
  - Streaming progress with logs and exit codes.
