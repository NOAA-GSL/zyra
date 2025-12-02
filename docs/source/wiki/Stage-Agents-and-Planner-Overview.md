# Stage Agents & Planner Overview

This page summarizes:

1. How stage agents map to the existing Zyra stages
2. The new `zyra plan` capabilities (reasoning trace, suggestions, clarifications)
3. Value Engine suggestions and how they influence the manifest
4. Running the generated plan with `zyra swarm`

## Stage Agents at a Glance

Each Zyra workflow stage now corresponds to a **stage agent** with a normalized spec:

| Stage      | Purpose                                         | Implementation Notes                               |
|------------|-------------------------------------------------|----------------------------------------------------|
| acquire    | Fetch/source data (HTTP, FTP, S3, etc.)         | CLI agent (`zyra acquire …`)                       |
| process    | Transform/clean data (scan-frames, pad-missing) | CLI agent                                          |
| simulate   | Skeleton mock (emits placeholder ensemble)      | Mock agent (ready for future simulation logic)     |
| decide     | Skeleton mock (scores/optimizes results)        | Mock agent (ensures DAG coverage)                  |
| visualize  | Render plots/animations                         | CLI agent (e.g., `compose-video`)                  |
| narrate    | Narration/summary                               | Proposal → CLI (LLM-backed)                        |
| verify     | Quality/completeness checks                     | CLI agent (`verify evaluate`)                      |
| export     | Save or disseminate artifacts                   | CLI agent (`decimate local`, `export s3`, etc.)    |

When you run `zyra swarm`, the orchestrator resolves each spec into an agent, honors `depends_on`, and executes the DAG with optional parallelism.

## Hybrid Design Workflow: Structured Tool Confirmation (The General Contractor Model)

Zyra includes the integration of the **ValueEngine** for proactive value suggestion, consistent with the architectural principles established in the sources.

**Analogy:** If the current implementation is like a factory floor manager (Orchestrator) specifying exactly which bolt (Tool) the worker (Stage Agent) must use, the hybrid design is like the manager telling the worker "Use the best high-strength fastener for this application" (Natural Language), and the worker replies, "I propose using a grade 8 titanium bolt with these specifications" (Structured Proposal). The manager then verifies that titanium is on the approved materials list (Validation) and logs the decision (Provenance) before allowing the work to proceed (Execution). This process is safer, more adaptable, and fully traceable.

The workflow is divided into three distinct phases, managing the transition from high-level user intent to validated, executable code.

### Phase 1: Planning, Value Augmentation, and Initial Validation (Central Control)

This phase establishes the complete, safe plan (DAG) and is primarily managed by the Orchestrator's LLM Reasoning, Planner, Validator, and ValueEngine components.

| Step | Component | Action / Description | Source Alignment |
| :--- | :--- | :--- | :--- |
| **1. User Intent and Interpretation** | LLM System Prompt / Reasoning Layer | Interprets the **natural-language user intent**, identifying verbs and objects, and maps them to high-level Zyra stages. Output is restricted to **Structured reasoning via JSON output**. | |
| **2. Base DAG Construction** | Planner (Python) | Verifies requested actions exist in the **capabilities registry**. Builds the initial Dependency Graph (DAG) based on canonical stages (e.g., `import → process → visualize → export`). | |
| **3. Proactive Value Suggestion** | **ValueEngine (LLM)** | Evaluates the initial DAG and provenance for potential low-cost, high-value augmentations (e.g., suggesting a `verify` or `narrate` stage). Returns structured suggestions (e.g., JSON containing stage, description, confidence). | |
| **4. Augmentation Validation & Acceptance** | Validator / User Interaction | Orchestrator presents suggestions to the user for **acceptance or dismissal**. The Validator ensures accepted additions are **safe and compatible**; accepted suggestions are recorded (stage, confidence, rationale) in Provenance and inserted via the template registry (`insert_node`). | |
| **5. Deterministic Stage Check** | Planner (Python) | Determines if the first executable stage is **deterministic** (e.g., `acquire ftp`, `process scan-frames`). Deterministic stages skip Phase 2 and proceed directly to execution (Step 9). **Ambiguous** stages (e.g., `visualize compose`, `narrate swarm`) enter Phase 2 for structured tool proposals. | |

---

### Phase 2: Specialized Reasoning and Proposal (Hybrid Loop – For Ambiguous Tasks Only)

This phase delegates specialized tool selection to the Stage Agent but retains central control via a structured contract and mandatory validation.

| Step | Component | Action / Description | Source Alignment |
| :--- | :--- | :--- | :--- |
| **6. Dispatch Natural Language Subtask** | Executor (Python) | Orchestrator dispatches the Stage Agent, providing a clear, high-level **natural language description** of the subtask. | |
| **7. Local Reasoning and Structured Proposal** | Stage Agent (LLM Reasoning + Tools) | The specialized Stage Agent uses its **domain-specific tools or skills** to select the optimal low-level method and returns a **structured JSON proposal** (the execution contract) to the Orchestrator, e.g.: `{"stage_id":"visualize_1","proposed_tool":"visualize heatmap","args":{"input":"...","output":"..."}}`. | |
| **Required Schema Contract** | JSON Payload | Must include: `stage_id`, **`proposed_tool`** (alias for capabilities lookup), mandatory **`args`**, optional `justification`, and structured outputs to match the capabilities registry. | |
| **8. Proposal Validation and Hook** | Validator (Guardrails / Pydantic) | Validator performs **schema enforcement and safety checks**. It uses the `proposed_tool` alias to verify the command against the **capabilities registry** and ensure the `args` confirm **proper inputs/outputs**. | |
| **8a. Validation Rejection Escalation** | Planner / User Interaction | If the proposal is rejected (e.g., safety failure, invalid schema): **1. Retry** with the same stage agent (keeping context) and request safer parameters. **2. Enter the Clarification Loop** if required inputs are missing. **3. Bubble an error** to the user if recovery is impossible (e.g., unsupported tool). | |

---

### Phase 3: Central Execution and Provenance

This phase maintains the core principle that the Orchestrator, running Python code, is the sole executor, ensuring the workflow is **deterministic and auditable**.

| Step | Component | Action / Description | Source Alignment |
| :--- | :--- | :--- | :--- |
| **9. Centralized Execution** | Executor (Python) | If validated (or if the stage was deterministic), the Orchestrator’s Python Executor invokes the necessary internal runtime function (e.g., `_run_cli` or `_run_function`) using the approved command and parameters from the structured proposal. **The Stage Agent does not execute code remotely**. | |
| **10. Provenance Logging** | Provenance & Memory | The Executor ensures the stage **logs its artifacts, metadata, hash signatures, accepted/rejected suggestions, and tool proposals/validation results**. This achieves **full transparency and reproducibility**. | |
| **11. Workflow Advancement** | Planner / Executor | The Planner updates the DAG state and dispatches the next dependent Stage Agent or signals workflow completion. | |

## Planner Enhancements

`poetry run zyra plan --intent "<request>" --output plan.json --verbose` now:

- Emits a reasoning trace explaining why each stage was selected
- Prompts for missing arguments (e.g., FTP path, pad-missing fill mode)
- Invokes the **Value Engine** to suggest optional stages (narrate summaries, verification checks, retry logic). Suggestions can be accepted interactively.
- Automatically materializes verify stages when `scan-frames` detects missing or duplicate timestamps, wiring `verify evaluate --metric completeness --input <frames_meta>` into the manifest.

### Example Plan Intent

```bash
poetry run zyra plan \
  --intent "Download the last year of Weekly Drought Risk PNG frames from FTP, fill missing frames, compose an MP4 animation, and save to disk." \
  --output plan.json --verbose
```

**What to expect:**

- Verbose output logs the planner/LLM reasoning, clarification prompts, and suggestions.
- `plan.json` contains agents for `fetch_frames`, `scan_frames`, `pad_missing`, `compose_animation`, `save_local`, `verify_animation`, and `narrate_animation`.
- The Value Engine typically suggests adding narration and verification stages; accepting the narrate suggestion inserts a second proposal agent (e.g., `narrate_1`) with a specific intent like “Describe spatial patterns.”
- `plan_summary` now lists human-readable justifications for each agent (helpful downstream and for provenance).

## Value Engine Suggestions

The Value Engine inspects the manifest + semantic intent tags and offers low-cost augmentations (narration, verification, logging, etc.). Key upgrades in this branch:

- Suggestions include `intent_text` so accepted items append context back into the manifest intent.
- Verify suggestions can carry concrete `agent_template` payloads (e.g., `verify evaluate --metric completeness --input data/frames_meta.json`) so the planner inserts runnable agents rather than proposals.
- Accepted suggestions are recorded under `accepted_suggestions`; unaccepted ones remain in `suggestions` for reference.

## Running the Plan with `zyra swarm`

```
poetry run zyra swarm \
  --plan plan.json \
  --memory run.db \
  --log-events \
  --parallel \
  --provider ollama --model gemma --base-url http://host.docker.internal:11434
```

**Highlights:**

- `--memory run.db` records provenance (agent stats, verify/narrate results). Use `--dump-memory run.db` to inspect past runs.
- `--log-events` prints a stream like `[event agent_verify_result] agent=verify_animation stage=verify verdict=passed …`.
- `--parallel/--no-parallel` toggles concurrency (defaults to auto). `--agents simulate,decide,narrate` runs a subset if you need to focus on specific stages.
- `--provider/--model/--base-url` let you override the LLM client without editing `.env`; the planner and Value Engine honor the same settings.

### Sample Output (truncated)

```
[event run_started] {"agent_count": 8, ...}
[event agent_started] {"agent": "fetch_frames", "stage": "acquire"}
...
[event agent_verify_result] agent=verify_animation stage=verify verdict=passed metric=completeness message=verify evaluate: completeness PASSED - all frames present
[event agent_completed] {"agent": "narrate_animation", "role": "narrate", "duration_ms": 15957}
[event run_completed] agent_count=8 errors=0 failed=0 proposals=narrate_1:swarm, narrate_animation:swarm
```

The narrate stages receive enriched inputs (plan summary, frames metadata, verify results) so `narrative_summary.yaml` references missing weeks, sample frames, and completeness verdicts instead of just codec info.

## Sample Manifests

- `samples/swarm/mock_basic.yaml`: Minimal simulate → narrate DAG (mock outputs).
- `samples/swarm/drought_animation.yaml`: Full drought pipeline (FTP download, pad-missing, compose-video, narrate, verify, save).
- `samples/swarm/simulate_decide.yaml` *(new)*: Chains simulate → decide → narrate to exercise the skeleton stages without real data.

Use `poetry run zyra swarm --plan samples/swarm/simulate_decide.yaml --dry-run` to verify the mock pipeline works end-to-end.


