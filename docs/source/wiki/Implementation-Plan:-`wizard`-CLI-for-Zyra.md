## 1. **Use Case & Goals**
- Provide an **interactive CLI assistant** that helps users build Zyra workflows and answer questions.  
- Use **LLMs (OpenAI, Ollama, etc.)** as backends, configurable via CLI flags or config file.  
- Enable natural-language driven workflows like:
  - "Fetch the latest HRRR 2m temperature for Colorado and make a heatmap."
  - "Convert this NetCDF file to GeoTIFF."
  - "Show me how to subset HRRR data using bbox."

This lowers the entry barrier for new users and accelerates power users.

---

## 2. **Placement in Pipeline**
- New CLI command: `zyra wizard`  
- Mode options:
  - **Interactive session** (conversational Q&A)  
  - **One-shot query** (single prompt → command output)  

Example:
```bash
zyra wizard
```
or
```bash
zyra wizard --prompt "Get me the latest HRRR 2m temperature for Colorado."
```

---

## 3. **Technical Approach**
### a. **LLM Provider Abstraction**
- Implement `src/zyra/wizard/llm_client.py` with pluggable backends:
  - **OpenAI API** (default, configurable with `OPENAI_API_KEY`).
  - **Ollama** (local models, configurable with host/port).
- Configurable via:
  - CLI flag: `--provider openai|ollama`
  - Env vars: `ZYRA_LLM_PROVIDER`, `ZYRA_LLM_MODEL`

### b. **Workflow Translation**
- User query → LLM → Suggested CLI command(s).
- Option to **auto-execute** or **preview first**.
- Example flow:
  1. User: "Subset HRRR to Colorado and make a heatmap."
  2. LLM: Generates:
     ```bash
     zyra acquire s3://... --pattern ":TMP:2 m" --output tmp.grib2
     zyra    process subset --input tmp.grib2 --bbox "-110,35,-100,45" --output co.grib2
     zyra visualize co.grib2 --type heatmap --output co.png
     ```
  3. User confirms execution.

### c. **Session State**
- Maintain context across turns (e.g., reuse last file name).  
- Store logs of conversations + executed commands.

### d. **Safety & Guardrails**
- Dry-run mode (`--dry-run`) shows commands but doesn’t execute.  
- Allow user approval before execution.  
- Handle errors gracefully (retry, fallback).  

---

## 4. **CLI Design**
Examples:

**Interactive mode:**
```bash
zyra wizard
```
Output:
```
Welcome to Zyra Wizard! How can I help?
> Subset HRRR to Colorado and make a heatmap.
I suggest:
  zyra acquire ...
  zyra process subset ...
  zyra visualize ...
Execute these? (y/n)
```

**One-shot mode:**
```bash
zyra wizard --prompt "Convert hrrr.grib2 to NetCDF."
```

**Custom model:**
```bash
zyra wizard --provider ollama --model mistral
```

---

## 5. **Implementation Steps**
1. Add `wizard` CLI command in `cli.py`.  
2. Implement `llm_client.py` with OpenAI + Ollama backends.  
3. Add parser for LLM → CLI command suggestions.  
4. Add interactive shell (loop) + one-shot query mode.  
5. Implement dry-run + confirm-before-execute.  
6. Add logging of conversations.  
7. Documentation + examples.

---

## 6. **Milestones**
- **MVP**: One-shot queries with OpenAI backend.  
- **Phase 2**: Interactive mode with context memory.  
- **Phase 3**: Ollama support for offline/local LLMs.  
- **Phase 4**: Config file (`~/.zyra_wizard.yaml`) for provider defaults.  
- **Phase 5**: Advanced features — autocomplete, explain commands, suggest optimizations.

---

**Summary**  
The `wizard` CLI will let users build and run Zyra workflows using natural language, powered by configurable LLMs (OpenAI/Ollama). MVP: generate CLI commands, confirm with user, execute. Future: richer interactions, config, offline/local models.
