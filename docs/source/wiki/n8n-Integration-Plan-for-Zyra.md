## 1. Goal
- Build `n8n-nodes-zyra`, a custom n8n node package that:
  - Wraps Zyra FastAPI calls.
  - Exposes one node type per CLI module: **Acquire**, **Process**, **Visualize**, **Decimate**.
  - Dynamically loads available commands for each module from the API.
  - Returns execution logs and exit codes to the workflow.
  - Enables conditional branching and error handling in n8n.

---

## 2. Node Package Structure
```
n8n-nodes-zyra/
    package.json
    credentials/
        zyraApi.credentials.ts
    nodes/
        Acquire.node.ts
        Process.node.ts
        Visualize.node.ts
        Decimate.node.ts
    README.md
```

---

## 3. Credentials
**`zyraApi.credentials.ts`**
- Stores:
  - Base URL of the FastAPI service.
  - API key (if authentication enabled).
- Used in all node types.

---

## 4. Node Types

### 4.1 Acquire Node
- Dropdown: command list from `/cli/commands?stage=acquire`.
- Dynamic parameter fields based on selected command.
- Sends POST to `/cli/run` with `stage="acquire"`.

### 4.2 Process Node
- Dropdown: `/cli/commands?stage=process`.
- Conditional parameter UI.
- Sends POST with `stage="process"`.

### 4.3 Visualize Node
- Dropdown: `/cli/commands?stage=visualize`.
- Visualization-specific args shown dynamically.
- Sends POST with `stage="visualize"`.

### 4.4 Decimate Node
- Dropdown: `/cli/commands?stage=decimate`.
- Destination-specific args shown dynamically.
- Sends POST with `stage="decimate"`.

---

## 5. Execution Logic with Logs & Exit Code
Each node:
- Calls `/cli/run` (sync or async mode).
- Receives:
```json
{
  "status": "success",
  "stdout": "...",
  "stderr": "...",
  "exit_code": 0
}
```
- Returns this to n8n output as:
```json
{
  "stage": "process",
  "command": "decode-grib2",
  "args": {...},
  "exit_code": 0,
  "stdout": "...",
  "stderr": "...",
  "timestamp": "2025-08-12T15:32:10Z"
}
```

Example `execute()` snippet:
```ts
const creds = await this.getCredentials('zyraApi');
const response = await this.helpers.httpRequest({
    method: 'POST',
    url: `${creds.baseUrl}/cli/run`,
    headers: { Authorization: `Bearer ${creds.apiKey}` },
    body: {
        stage: 'process',
        command: this.getNodeParameter('command', 0),
        args: this.getNodeParameter('args', 0, {}),
        mode: 'sync'
    },
    json: true
});

return [this.helpers.returnJsonArray({
    stage: 'process',
    command: this.getNodeParameter('command', 0),
    args: this.getNodeParameter('args', 0, {}),
    exit_code: response.exit_code,
    stdout: response.stdout,
    stderr: response.stderr,
    timestamp: new Date().toISOString()
})];
```

---

## 6. Dynamic Command Loading
- API endpoint `/cli/commands`:
```json
{
  "acquire": ["http", "s3", "ftp", "vimeo"],
  "process": ["decode-grib2", "convert-format", "extract-variable"],
  "visualize": ["plot", "colormap"],
  "decimate": ["local", "s3", "ftp"]
}
```
- n8n node fetches commands for its stage when rendering parameter dropdown.

---

## 7. Debugging in n8n
- **Branch on Success/Failure**:
  - Use `If` node to check `exit_code`.
- **View Logs**:
  - `stdout` and `stderr` appear in n8n execution data.
- **Error Notifications**:
  - Connect failure branch to Slack, Email, etc.

---

## 8. Bonus Features
- **Async Job Mode**:
  - Node triggers `/cli/run` with `mode="async"`.
  - Poll `/jobs/{job_id}` until complete.
- **Upload Node**:
  - Wrap `/upload` endpoint for local file ingestion.
- **Pipeline Runner Node**:
  - Send entire pipeline YAML to `/run`.

---

## 9. Advantages of One Node Per Module
- Minimal number of nodes (4 core types).
- Easy to maintain — adding a CLI command only updates API output.
- Dynamic parameters keep UI relevant and avoid clutter.
- Clear mapping to Zyra CLI structure.

---

## 10. Future Extension
- Auto-generate "shortcut" nodes for high-use functions.
- Allow saving n8n workflows as Zyra pipeline configs.


### Visualization Node
**Purpose:** Render visual outputs from processed or raw data using the Zyra visualization module.

**CLI Stage:** `visualize`

**Supported Commands:** Dynamically fetched from `/cli/commands?stage=visualize`, e.g.:
- `heatmap`
- `contour`
- `timeseries`
- `wind-particles` (future)
- `animate` (future)

**Parameters:**
- Input file (`input`)
- Output path (`output`)
- Visualization type-specific parameters (`--var`, `--levels`, `--cmap`, `--map-type`, etc.)

**Example API Payload:**
```json
{
    "stage": "visualize",
    "command": "heatmap",
    "params": {
        "input": "processed.nc",
        "var": "temperature",
        "output": "heatmap.png",
        "cmap": "viridis"
    }
}
```

**Output:**
- Image or animation file path.
- Logs and exit code captured for debugging.
