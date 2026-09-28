Generate text/narrative products.

Generated from Zyra **0.1.54**. See [Pipeline Schema](Pipeline-Schema) for how `args` keys become CLI flags.

**Commands:** [`describe`](#narrate-describe) · [`swarm`](#narrate-swarm)

---
### `narrate describe`

zyra narrate describe

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `topic` | `--topic` | str |  | Topic to narrate (placeholder) |

### `narrate swarm`

Run a lightweight narration swarm with presets and YAML merging. When audiences are provided, an internal audience_adapter agent emits <aud>_version outputs. Provenance is recorded per agent with started/model/prompt_ref/duration_ms and included in the Narrative Pack.

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `preset` | `--preset` | str |  | Preset template name (use '-P help' to list presets) |
| `list_presets` | `--list-presets` | bool | `False` | List available presets and exit |
| `swarm_config` | `--swarm-config` | str |  | YAML config with agents/graph/settings |
| `agents` | `--agents` | str |  | Comma-separated agent IDs (e.g., summary,critic) |
| `audiences` | `--audiences` | str |  | Comma-separated audiences (e.g., kids,policy) |
| `style` | `--style` | str |  | Target writing style (e.g., journalistic) |
| `provider` | `--provider` | str |  | LLM provider (mock\|openai\|ollama\|gemini\|vertex). Gemini accepts GOOGLE_API_KEY or Vertex creds. |
| `model` | `--model` | str |  | Model name (provider-specific) |
| `base_url` | `--base-url` | str |  | Provider base URL override |
| `max_workers` | `--max-workers` | int |  | Max concurrent agents (optional) |
| `max_rounds` | `--max-rounds` | int |  | Review rounds (0 disables critic/editor loop) |
| `pack` | `--pack` | str |  | Output file for Narrative Pack (yaml or json); '-' for stdout |
| `rubric` | `--rubric` | str |  | Path to critic rubric YAML (defaults to packaged critic rubric) |
| `verbose` | `--verbose` | bool | `False` | Verbose logging (shows per-agent dialog) |
| `quiet` | `--quiet` | bool | `False` | Quiet logging (errors only) |
| `input` | `--input` | path |  | Optional input file path or '-' for stdin (JSON/YAML autodetect; falls back to text) |
| `critic_structured` | `--critic-structured` | bool | `False` | Emit structured critic output (critic_notes as {notes: ...}) |
| `attach_images` | `--attach-images` | bool | `False` | Attach images from input_data.images to LLM calls (multimodal models only) |
| `strict_grounding` | `--strict-grounding` | bool | `False` | Fail the run if critic flags ungrounded content |
| `guardrails` | `--guardrails` | str |  | Guardrails (.rail) schema applied to stage outputs (optional) |
| `strict_guardrails` | `--strict-guardrails` | bool | `False` | Fail the run if guardrails validation fails |
| `memory` | `--memory` | str |  | Provenance store path (SQLite). Use '-' for in-memory/no file. |
