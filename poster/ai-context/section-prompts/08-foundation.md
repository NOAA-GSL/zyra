Section 8: Building Off the Foundation

**Purpose:** Showcase Zyra's three-layer architecture — CLI, Python API, and MCP/AI Agents — all built on the same 8-stage pipeline, emphasizing that every access layer shares a unified architecture with full provenance.

**Content:**

Three access tiers, presented as a 3D pyramid (bottom to top):

| Tier | Layer | Description |
|------|-------|-------------|
| 1 (base) | **CLI — The Foundation** | The CLI empowers researchers and developers to quickly build, test, and reproduce visualization pipelines with simple, scriptable commands. Every stage streams via `stdin/stdout` for Unix-style composition. CLI command: `zyra [command]` |
| 2 (middle) | **Python API** | Zyra's modular Python API extends the CLI with programmatic access — enabling custom processing modules, integration into existing data workflows, and automated dissemination pipelines via `import zyra`. |
| 3 (top) | **MCP + AI Agents** | Zyra exposes every pipeline stage as an MCP tool, letting LLM agents like Claude autonomously discover, compose, and execute scientific workflows. The AI layer transforms conversational intent into reproducible pipeline runs. CLI command: `tools/discover` |

Four highlight cards below the pyramid:

| Card | Description |
|------|-------------|
| **Streaming CLI Pipes** | Chain stages via `stdin/stdout` — acquire, process, and visualize in a single Unix pipeline with zero intermediate files. |
| **FastAPI Service Mode** | Run `zyra serve` to expose all pipeline stages as a REST API, enabling web dashboards and automated integrations. |
| **MCP Tool Discovery** | LLM agents discover available pipeline tools at runtime — no hardcoded prompts. Zyra's MCP server advertises capabilities dynamically. |
| **Same Pipeline, Every Layer** | Whether invoked from bash, Python, REST, or an AI agent — every execution follows the same 8-stage architecture with full provenance. |

**Layout:** Full poster width. Center: 3D pyramid SVG with three tiers (green/CLI at base, blue/API in middle, teal/MCP at top). Left column: three description cards aligned to pyramid tiers with dotted connector lines. Below pyramid: four horizontally-arranged highlight cards with color-coded top borders matching their respective tier.

**Color Mapping:**
- CLI tier: Leaf Green (`#2C670C`)
- API tier: Cable Blue (`#00529E`)
- MCP tier: Ocean Blue (`#1A5A69`)
- Cross-cutting highlight: Amber (`#FFC107`) accent with Soil (`#50452C`) text

**Background:** Subtle gradient from Neutral 50 to Neutral 200 with faint radial gradient accents.
