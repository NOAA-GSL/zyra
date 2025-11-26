# Task Decomposition and Planning Summary

This summary captures **how Zyra’s orchestrator should decompose user requests into structured, executable stage plans.** It describes a hybrid architecture combining LLM-based reasoning with deterministic orchestration logic, Guardrails validation, and provenance tracking.

## Overview

Zyra’s orchestrator shouldn’t be a “black box” that hides logic in LLM prompts. Instead, it should operate as a **planning and coordination layer** where the LLM interprets user intent and structured Python code builds, validates, and executes a dependency graph.

### Key Insight
> The orchestrator should be a **planner**, not a **magician**.  
> The LLM reasons about *what to do*, while the orchestration layer determines *how and when to do it*.

---

## Architecture Breakdown

| Layer | Responsibility | Implementation |
|-------|----------------|----------------|
| **LLM System Prompt** | Interpret natural-language user intent. Identify relevant Zyra stages. Suggest clarifications. | Structured reasoning via JSON output. |
| **Planner (Python)** | Build dependency graph based on stage relationships. | Deterministic DAG creation. |
| **Validator (Guardrails / Pydantic)** | Validate LLM-generated plans. Ensure supported stages and proper inputs/outputs. | Schema enforcement and safety checks. |
| **Executor (Python)** | Dispatch stage agents, manage retries and concurrency. | Code-based orchestration logic. |
| **Provenance & Memory** | Persist state, track user clarifications, record reproducibility. | Provenance database + session memory. |

---

## Task Decomposition Flow

1. **User Request → Orchestrator (LLM Reasoning Layer)**  
   The LLM parses user intent, identifies verbs and objects, and maps them to Zyra stages.

2. **Capability Validation (Python)**  
   The orchestrator verifies that requested actions exist in the capabilities registry.

3. **DAG Construction (Planner)**  
   Build a dependency graph based on supported stages and Zyra’s canonical order:  
   `import → process → simulate → decide → visualize → narrate → verify → export`

4. **Interactive Clarification Loop**  
   If information is missing (e.g., FTP path, dataset ID), the orchestrator pauses, prompts the user, validates input with Guardrails, and resumes execution.

5. **Execution & Provenance Logging**  
   Each stage logs its artifacts, metadata, and hash signatures to the Provenance Store.

---

## Real-Time DAG Modification

When a stage fails or new information becomes available, the orchestrator can modify the active DAG:

- **Recoverable Error:** Retry or skip a failed node.  
- **Missing Input:** Insert a temporary *clarification node* to gather user input before resuming.  
- **Validation Failure:** Replace or re-run a stage using safer parameters.  

Example modification:
```json
{
  "dag_modification": {
    "action": "insert_node",
    "new_node": {
      "name": "clarify_input_source",
      "type": "user_interaction",
      "upstream": ["import"],
      "downstream": ["process"]
    }
  }
}
```

All DAG changes are logged to the Provenance Store for full transparency and reproducibility.

---

## Proactive Orchestration and Value Suggestion

Beyond reactive task handling, Zyra’s orchestrator can serve as a **proactive research assistant**, suggesting low-effort, high-value enhancements to user workflows.

### Example:  
**User Request:** “Generate a temperature anomaly map for 2020.”  
**Base Plan:** `import → process → visualize → export`  
**Proactive Suggestions:**
- Add `verify` stage → “Check data coverage consistency before plotting.”  
- Add `narrate` stage → “Generate a short summary for documentation.”  
- Add quick diagnostics → “Create a QC scatter plot for raw vs processed data.”  

### Implementation Outline

| Component | Role |
|------------|------|
| **ValueEngine (new)** | Evaluates DAG and provenance for potential low-cost augmentations. |
| **Planner** | Accepts optional “suggested nodes” from ValueEngine. |
| **Validator** | Ensures additions are safe and compatible. |
| **User Interaction** | Presents suggestions to user for acceptance or dismissal. |
| **Provenance** | Logs which suggestions were made, accepted, or rejected. |

**Example JSON Output:**
```json
{
  "augmentations": [
    {
      "stage": "verify",
      "description": "Add statistical verification of processed data",
      "confidence": 0.92
    },
    {
      "stage": "narrate",
      "description": "Generate a summary paragraph explaining the map",
      "confidence": 0.88
    }
  ]
}
```

This transforms the orchestrator into an **active collaborator** that enhances scientific value without user burden.

---

## Recommended System Prompt Structure

The LLM system prompt focuses solely on reasoning, not execution:

```json
{
  "intent": "<summary of user goal>",
  "stages": [
    {"name": "<zyra_stage_name>", "description": "<purpose>", "inputs": [], "outputs": []}
  ],
  "dependencies": {"stage": ["upstream_stage"]},
  "clarifications_needed": ["<missing_info>"]
}
```

- **Always returns JSON.**
- **No unstructured text or code.**
- **Clarifications trigger user feedback loops.**

---

## Best Practices

- Keep orchestration **deterministic** and **auditable**.  
- Restrict the LLM to **interpretation**, not execution.  
- Validate all plans before execution.  
- Support human-in-the-loop recovery for incomplete or ambiguous requests.  
- Use provenance and Guardrails to maintain safety and reproducibility.  
- Enable proactive, context-aware suggestions to add scientific value.
