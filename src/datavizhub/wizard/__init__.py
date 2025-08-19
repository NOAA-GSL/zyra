from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from importlib import resources
from pathlib import Path

from .llm_client import LLMClient, MockClient, OllamaClient, OpenAIClient

try:
    import yaml  # type: ignore
except Exception:
    yaml = None  # type: ignore[assignment]


@dataclass
class SessionState:
    last_file: str | None = None
    history: list[str] = field(default_factory=list)
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)


def _load_config() -> dict:
    """Load wizard config from ~/.datavizhub_wizard.yaml if present.

    Keys supported:
    - provider: "openai" | "ollama" | "mock"
    - model: model name string
    """
    path = Path("~/.datavizhub_wizard.yaml").expanduser()
    try:
        if yaml is None:
            return {}
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            return {}
        return {str(k): v for k, v in data.items()}
    except Exception:
        return {}


def _select_provider(provider: str | None, model: str | None) -> LLMClient:
    cfg = _load_config()
    prov = (
        provider
        or os.environ.get("DATAVIZHUB_LLM_PROVIDER")
        or cfg.get("provider")
        or "openai"
    )
    prov = str(prov).lower()
    model_name = (
        model or os.environ.get("DATAVIZHUB_LLM_MODEL") or cfg.get("model") or None
    )
    if prov == "openai":
        return OpenAIClient(model=model_name)
    if prov == "ollama":
        return OllamaClient(model=model_name)
    if prov == "mock":
        return MockClient()
    # Fallback to mock for unknown providers
    return MockClient()


SYSTEM_PROMPT = (
    "You are DataVizHub Wizard, an assistant that helps users run the "
    "'datavizhub' CLI. Your job is to output one or more CLI commands "
    "that directly accomplish the user's request.\n\n"
    "Formatting rules:\n"
    "- Always wrap commands in a fenced code block with 'bash'.\n"
    "- Each command must start with 'datavizhub'.\n"
    "- If multiple steps are needed, put each on its own line.\n"
    "- You may include short inline comments (using #) to briefly explain "
    "what each command does.\n"
    "- Do not include any text outside the fenced code block.\n\n"
    "Guidelines:\n"
    "- Prefer succinct, directly runnable commands.\n"
    "- Use placeholders (like <input-file>) only when unavoidable.\n"
    "- Never generate non-datavizhub shell commands (e.g., rm, curl, sudo).\n"
    "- If essential details are missing, make a reasonable assumption and use a placeholder.\n"
    "- Explanations should be one short phrase only, never long sentences.\n"
    "- Avoid redundant flags unless necessary for clarity.\n\n"
    "Your output must always be a single fenced code block with commands "
    "and optional short comments."
)

_CAP_MANIFEST_CACHE: dict | None = None


def _load_capabilities_manifest() -> dict | None:
    global _CAP_MANIFEST_CACHE
    if _CAP_MANIFEST_CACHE is not None:
        return _CAP_MANIFEST_CACHE
    try:
        with resources.files(__package__).joinpath("datavizhub_capabilities.json").open(
            "r", encoding="utf-8"
        ) as f:
            _CAP_MANIFEST_CACHE = json.load(f)
            return _CAP_MANIFEST_CACHE
    except Exception:
        _CAP_MANIFEST_CACHE = None
        return None


def _select_relevant_capabilities(prompt: str, cap: dict, limit: int = 6) -> list[str]:
    text = prompt.lower()
    scored: list[tuple[int, str, dict]] = []
    for cmd, meta in cap.items():
        desc = str(meta.get("description") or "").lower()
        opts = " ".join(meta.get("options", {}).keys()).lower()
        hay = f"{cmd.lower()} {desc} {opts}"
        score = 0
        for token in set(text.replace("/", " ").replace(",", " ").split()):
            if token and token in hay:
                score += 1
        if score:
            scored.append((score, cmd, meta))
    scored.sort(key=lambda x: (-x[0], x[1]))
    out = []
    for _, cmd, meta in scored[:limit]:
        opts = ", ".join(meta.get("options", {}).keys())
        desc = meta.get("description", "")
        out.append(f"- {cmd}: {desc} Options: {opts}".strip())
    return out


def _strip_inline_comment(s: str) -> str:
    """Strip inline '#' comments that are outside quotes.

    Keeps content inside single or double quotes intact; stops at the first
    unquoted '#'. This is a best-effort sanitizer for LLM explanations.
    """
    out = []
    in_single = False
    in_double = False
    escape = False
    for ch in s:
        if escape:
            out.append(ch)
            escape = False
            continue
        if ch == "\\":
            out.append(ch)
            escape = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
            out.append(ch)
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
            continue
        if ch == "#" and not in_single and not in_double:
            break  # start of comment
        out.append(ch)
    return "".join(out).rstrip()


def _extract_annotated_commands(text: str) -> list[str]:
    """Extract datavizhub command lines from LLM text.

    Strategy:
    - Prefer fenced code blocks; support both `datavizhub ...` and `$ datavizhub ...` forms.
    - If none found in fences, scan whole text for the same patterns.
    - Return each command line as a separate string without shell prompts.
    """

    def _normalize_cmd(line: str) -> str | None:
        s = line.strip()
        if not s or s.startswith("#"):
            return None
        # Strip common shell prompt prefixes like `$ ` or `> `
        if s.startswith("$"):
            s = s[1:].lstrip()
        if s.startswith(">"):
            s = s[1:].lstrip()
        return s if s.startswith("datavizhub ") else None

    cmds: list[str] = []
    # Find fenced code blocks first
    code_blocks = re.findall(r"```[a-zA-Z0-9_-]*\n(.*?)```", text, flags=re.S)
    for block in code_blocks:
        for line in block.splitlines():
            s = _normalize_cmd(line)
            if s:
                cmds.append(s)
    # Fallback: scan lines outside of code fences
    if not cmds:
        for line in text.splitlines():
            s = _normalize_cmd(line)
            if s:
                cmds.append(s)
    return cmds


def _confirm(prompt: str, assume_yes: bool = False) -> bool:
    if assume_yes:
        return True
    try:
        ans = input(prompt + " [y/N]: ").strip().lower()
        return ans in ("y", "yes")
    except EOFError:
        return False


def _run_one(cmd: str) -> int:
    """Execute a single datavizhub command by calling the internal CLI."""
    from datavizhub.cli import main as cli_main

    # Strip leading program name if present
    parts = shlex.split(cmd)
    if parts and parts[0] == "datavizhub":
        parts = parts[1:]
    try:
        return int(cli_main(parts))
    except SystemExit as exc:  # if cli_main raises SystemExit
        return int(getattr(exc, "code", 1) or 0)


def _ensure_log_dir() -> Path:
    root = Path("~/.datavizhub/wizard_logs").expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _log_event(
    logfile: Path | None, event: dict, *, session_id: str | None = None
) -> None:
    if logfile is None:
        return
    try:
        # Enrich with schema + correlation IDs
        event = dict(event)
        event.setdefault("schema_version", 1)
        if session_id:
            event.setdefault("session_id", session_id)
        event.setdefault("event_id", uuid.uuid4().hex)
        with logfile.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _handle_prompt(
    prompt: str,
    *,
    provider: str | None,
    model: str | None,
    dry_run: bool,
    assume_yes: bool,
    max_commands: int | None,
    logfile: Path | None,
    log_raw_llm: bool = False,
    show_raw: bool = False,
    explain: bool = False,
    session: SessionState | None = None,
) -> int:
    client = _select_provider(provider, model)
    # Build contextual user prompt for LLM if session is provided
    user_prompt = prompt
    if session is not None and (session.last_file or session.history):
        ctx_lines = ["Context:"]
        if session.last_file:
            ctx_lines.append(f"- Last file: {session.last_file}")
        if session.history:
            recent = session.history[-5:]
            ctx_lines.append("- Recent commands:")
            for c in recent:
                ctx_lines.append(f"  - {c}")
        # Capabilities: prepend relevant commands from manifest
        cap = _load_capabilities_manifest()
        if cap:
            rel = _select_relevant_capabilities(prompt, cap)
            if rel:
                ctx_lines.append("- Relevant commands:")
                ctx_lines.extend(f"  {line}" for line in rel)
        ctx_lines.append("")
        ctx_lines.append("Task:")
        ctx_lines.append(prompt)
        user_prompt = "\n".join(ctx_lines)
    provider_name = getattr(client, "name", client.__class__.__name__)
    model_name = getattr(client, "model", None)
    _log_event(
        logfile,
        {
            "ts": datetime.utcnow().isoformat() + "Z",
            "type": "user_prompt",
            "prompt": prompt,
            "provider": provider_name,
            "model": model_name,
        },
        session_id=(session.session_id if session else None),
    )

    reply = client.generate(SYSTEM_PROMPT, user_prompt)
    if log_raw_llm:
        _log_event(
            logfile,
            {
                "ts": datetime.utcnow().isoformat() + "Z",
                "type": "assistant_reply",
                "text": reply,
                "raw": reply,
                "provider": provider_name,
                "model": model_name,
            },
            session_id=(session.session_id if session else None),
        )

    annotated_cmds = _extract_annotated_commands(reply)
    # Normalize by stripping comments while keeping only datavizhub lines
    cmds = []
    for a in annotated_cmds:
        s = _strip_inline_comment(a)
        if s.startswith("datavizhub "):
            cmds.append(s)
    # Strict safety: drop any lines that don't start with datavizhub
    safe_cmds = [c for c in cmds if c.startswith("datavizhub ")]
    dropped = len(cmds) - len(safe_cmds)
    if dropped > 0:
        print(f"[safe] Ignored {dropped} non-datavizhub line(s).")
    cmds = safe_cmds
    if max_commands is not None:
        cmds = cmds[: max(0, int(max_commands))]

    if not cmds:
        print("No datavizhub commands were suggested.")
        return 1

    # Show raw LLM output if requested (debug aid before parsing)
    if show_raw:
        print("Raw model output:\n" + reply)
    # Suggested commands: optionally include inline comments via annotated lines
    if explain:
        shown = [a for a in annotated_cmds if a.startswith("datavizhub ")]
        print(
            "Suggested commands (with explanations):\n"
            + "\n".join(f"  {c}" for c in shown)
        )
    else:
        print("Suggested commands:\n" + "\n".join(f"  {c}" for c in cmds))
    # Update session context immediately so dry-runs can influence follow-up prompts
    if session is not None:
        session.history.extend(cmds if not explain else shown)
        last_out = None
        for c in cmds:
            m = re.findall(r"(?:--output|-o)\s+(\S+)", c)
            if m:
                last_out = m[-1]
        if last_out:
            session.last_file = last_out
    if dry_run:
        _log_event(
            logfile,
            {
                "ts": datetime.utcnow().isoformat() + "Z",
                "type": "dry_run",
                "commands": cmds,
                "provider": provider_name,
                "model": model_name,
            },
            session_id=(session.session_id if session else None),
        )
        return 0
    if not _confirm("Execute these commands?", assume_yes):
        return 0

    status = 0
    for c in cmds:
        print(f"\n$ {c}")
        rc = _run_one(c)
        _log_event(
            logfile,
            {
                "ts": datetime.utcnow().isoformat() + "Z",
                "type": "exec",
                "cmd": c,
                "returncode": rc,
                "ok": (rc == 0),
                "provider": provider_name,
                "model": model_name,
            },
            session_id=(session.session_id if session else None),
        )
        if rc != 0:
            print(f"Command failed with exit code {rc}")
            status = rc
            break
    _log_event(
        logfile,
        {
            "ts": datetime.utcnow().isoformat() + "Z",
            "type": "result",
            "returncode": status,
            "ok": (status == 0),
            "commands": cmds,
            "provider": provider_name,
            "model": model_name,
        },
        session_id=(session.session_id if session else None),
    )
    # Session was already updated above; nothing further needed here.
    return status


def _interactive_loop(args: argparse.Namespace) -> int:
    print("Welcome to DataVizHub Wizard! Type 'exit' to quit.")
    session = SessionState()
    logfile = None
    if args.log:
        logdir = _ensure_log_dir()
        logfile = logdir / (datetime.utcnow().strftime("%Y%m%dT%H%M%SZ") + ".jsonl")
    while True:
        try:
            q = input("> ").strip()
        except EOFError:
            print()
            return 0
        if not q:
            continue
        if q.lower() in {"exit", "quit"}:
            return 0
        rc = _handle_prompt(
            q,
            provider=args.provider,
            model=args.model,
            dry_run=args.dry_run,
            assume_yes=args.yes,
            max_commands=args.max_commands,
            logfile=logfile,
            log_raw_llm=getattr(args, "log_raw_llm", False),
            show_raw=getattr(args, "show_raw", False),
            explain=getattr(args, "explain", False),
            session=session,
        )
        if rc != 0:
            print(f"Last command set exited with {rc}")


def register_cli(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--prompt",
        help="One-shot query to generate CLI commands; start interactive mode if omitted",
    )
    p.add_argument(
        "--provider",
        choices=["openai", "ollama", "mock"],
        help="LLM provider (default: openai)",
    )
    p.add_argument("--model", help="Model name override for the selected provider")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show suggested commands but do not execute",
    )
    p.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Auto-confirm execution without prompting",
    )
    p.add_argument(
        "--max-commands",
        type=int,
        help="Limit number of suggested commands to run",
    )
    p.add_argument(
        "--log",
        action="store_true",
        help="Log prompts, replies, and executions to ~/.datavizhub/wizard_logs",
    )
    p.add_argument(
        "--log-raw-llm",
        action="store_true",
        help="Include full raw LLM responses in logs (assistant_reply events)",
    )
    p.add_argument(
        "--show-raw",
        action="store_true",
        help="Print the full raw LLM output before parsing",
    )
    p.add_argument(
        "--explain",
        action="store_true",
        help="Show inline # comments in suggested commands (preview only)",
    )

    def _cmd(ns: argparse.Namespace) -> int:
        if ns.prompt:
            logfile = None
            if ns.log:
                logdir = _ensure_log_dir()
                logfile = logdir / (
                    datetime.utcnow().strftime("%Y%m%dT%H%M%SZ") + ".jsonl"
                )
            # One-shot: create a transient session for correlation IDs
            the_session = SessionState()
            return _handle_prompt(
                ns.prompt,
                provider=ns.provider,
                model=ns.model,
                dry_run=ns.dry_run,
                assume_yes=ns.yes,
                max_commands=ns.max_commands,
                logfile=logfile,
                log_raw_llm=ns.log_raw_llm,
                show_raw=ns.show_raw,
                explain=ns.explain,
                session=the_session,
            )
        return _interactive_loop(ns)

    p.set_defaults(func=_cmd)
