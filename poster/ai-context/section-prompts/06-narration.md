# Section 6: Use Case -- AI/LLM Narration Swarm

## Purpose
Highlight Zyra's AI agent orchestration capabilities -- the multi-agent narration system.

## Content

**Heading:** Use Case: AI/LLM Narration Swarm

**Description:** Zyra orchestrates multi-agent workflows where LLM-powered agents generate, critique, and refine narrative outputs. The planning engine interprets natural language intent, the value engine suggests augmentations, and stage agents execute as a DAG.

**Diagram (from `poster/assets/diagrams/swarm_orchestration.mmd`):**
User Intent -> Planner (zyra plan) -> Value Engine -> Execution DAG -> Stage Agents (acquire, process, visualize, narrate) -> Provenance (SQLite)

**Narration swarm agents:** context -> summary -> critic -> editor

**Provider Table:**
| Provider | Usage |
|----------|-------|
| OpenAI | `--provider openai --model gpt-4` |
| Ollama | `--provider ollama --model gemma` |
| Gemini | `--provider gemini` |
| Mock | `--provider mock` (offline testing) |

**Key point:** Outputs validated against Pydantic schemas with optional guardrails (RAIL files).

## Layout
- Half-column width
- Orchestration diagram at top
- Provider table below
- Brief text description

## AI Design Prompt
> Create a use case card for a scientific poster. Heading "Use Case: AI/LLM Narration Swarm" in Ocean Blue (#1A5A69), 20pt bold. Include an orchestration flowchart: User Intent -> Planner -> Value Engine -> Execution DAG, which fans out to 4 Stage Agents, all flowing into Provenance. Use Soil (#50452C) for User Intent, Ocean Blue (#1A5A69) for Planner and LLM Agent, Amber (#FFC107) for Value Engine, Cable Blue (#00529E) for Execution DAG, Leaf Green (#2C670C) for CLI agents, Seafoam (#5F9DAE) for Provenance. Below the diagram, add a compact 4-row provider table. Brief text mentioning the narration swarm chains (context, summary, critic, editor agents). Half-column width.
