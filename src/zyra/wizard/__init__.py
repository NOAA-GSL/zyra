from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shlex
import uuid
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from importlib.util import find_spec as _find_spec
from pathlib import Path
from pathlib import Path as _Path

from .llm_client import LLMClient
from .prompts import SYSTEM_PROMPT
from .resolver import MissingArgsError, MissingArgumentResolver

try:
    import yaml  # type: ignore
except Exception:
    yaml = None  # type: ignore[assignment]

# Optional prompt_toolkit for richer REPL
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion, PathCompleter

    PTK_AVAILABLE = True
except ImportError:  # pragma: no cover - may not be installed
    PromptSession = None  # type: ignore
    Completer = object  # type: ignore
    Completion = object  # type: ignore
    PathCompleter = object  # type: ignore
    PTK_AVAILABLE = False

# Best-effort: load environment variables from a local .env if present.
# This enables settings like OLLAMA_BASE_URL and ZYRA_LLM_*/DATAVIZHUB_LLM_* to be
# picked up when running the wizard in containers or dev shells.
try:  # pragma: no cover - environment dependent
    from dotenv import find_dotenv, load_dotenv

    _ENV_PATH = find_dotenv(usecwd=True)
    if _ENV_PATH:
        load_dotenv(_ENV_PATH, override=False)
        logging.getLogger(__name__).debug(
            "Loaded environment from .env at %s", _ENV_PATH
        )
    else:
        logging.getLogger(__name__).debug("No .env file found; skipping dotenv load.")
except (ImportError, ModuleNotFoundError) as exc:
    # Ignore if python-dotenv is unavailable; environment vars still work
    logging.getLogger(__name__).debug(
        "Skipping dotenv load (python-dotenv not installed): %s", exc
    )

MANIFEST_FILENAME = "zyra_capabilities.json"


@dataclass
class SessionState:
    last_file: str | None = None
    history: list[str] = field(default_factory=list)
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)


def _load_config() -> dict:
    """Load wizard config from ~/.zyra_wizard.yaml if present.

    Keys supported (both legacy root-level and nested under 'llm'):
    - provider: "openai" | "ollama" | "mock"
    - model: model name string
    - base_url: provider endpoint (e.g., Ollama base URL)
    """
    path = Path("~/.zyra_wizard.yaml").expanduser()
    try:
        if yaml is None:
            return {}
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            return {}
        cfg = {str(k): v for k, v in data.items()}
        # Normalize nested llm section if present
        llm = cfg.get("llm")
        if isinstance(llm, dict):
            for k in ("provider", "model", "base_url"):
                if k in llm and k not in cfg:
                    cfg[k] = llm[k]
        return cfg
    except Exception:
        return {}


def _select_provider(provider: str | None, model: str | None) -> LLMClient:
    cfg = _load_config()
    from zyra.utils.env import env

    prov = provider or env("LLM_PROVIDER") or cfg.get("provider") or "openai"
    prov = str(prov).lower()
    model_name = model or env("LLM_MODEL") or cfg.get("model") or None
    base_url = cfg.get("base_url")
    if prov == "openai":
        from .llm_client import MockClient, OpenAIClient

        try:
            return OpenAIClient(model=model_name, base_url=base_url)
        except (RuntimeError, ImportError, AttributeError) as exc:
            warnings.warn(
                f"OpenAI unavailable: {exc}. Falling back to mock.",
                category=UserWarning,
                stacklevel=2,
            )
            return MockClient()
    if prov == "ollama":
        from .llm_client import MockClient, OllamaClient

        try:
            return OllamaClient(model=model_name, base_url=base_url)
        except (ImportError, AttributeError) as exc:
            warnings.warn(
                f"Ollama unavailable: {exc}. Falling back to mock.",
                category=UserWarning,
                stacklevel=2,
            )
            return MockClient()
    if prov == "mock":
        from .llm_client import MockClient

        return MockClient()
    # Fallback to mock for unknown providers
    warnings.warn(
        f"Unknown LLM provider '{prov}'. Falling back to mock.",
        category=UserWarning,
        stacklevel=2,
    )
    from .llm_client import MockClient

    return MockClient()


def _test_llm_connectivity(provider: str | None, model: str | None) -> tuple[bool, str]:
    """Probe connectivity to the configured LLM provider.

    Returns (ok, message) where message is a human-friendly status line.
    """
    cfg = _load_config()
    from zyra.utils.env import env

    prov = (provider or env("LLM_PROVIDER") or cfg.get("provider") or "openai").lower()
    model_name = model or env("LLM_MODEL") or cfg.get("model") or ""
    base_url = cfg.get("base_url")
    try:
        import requests  # type: ignore
    except ImportError:
        return False, "requests library not available for connectivity test"

    if prov == "ollama":
        # Default resolution mirrors OllamaClient
        from .llm_client import OllamaClient

        oc = OllamaClient(model=model_name or None, base_url=base_url or None)
        url = f"{oc.base_url}/api/tags"
        try:
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            who = f"Ollama ({oc.model})"
            return True, f"✅ Connected to {who} at {oc.base_url}"
        except Exception:
            host_hint = ""
            if any(h in (oc.base_url or "") for h in ["localhost", "127.0.0.1"]):
                host_hint = (
                    "\n❓ Hint: If running in Docker, localhost refers to the container. "
                    "Use OLLAMA_BASE_URL=http://host.docker.internal:11434 (macOS/Windows) or add "
                    "--add-host=host.docker.internal:host-gateway (Linux)."
                )
            serve_hint = "\n🔧 Ensure: OLLAMA_HOST=0.0.0.0 ollama serve"
            return (
                False,
                "❌ Failed to reach Ollama endpoint." + host_hint + serve_hint,
            )

    if prov == "openai":
        from .llm_client import OpenAIClient

        try:
            oc = OpenAIClient(model=model_name or None, base_url=base_url or None)
        except RuntimeError:
            return False, "❌ OpenAI client not available; check API key configuration."
        try:
            # Hitting the models list is a lightweight way to check auth
            url = f"{oc.base_url}/models"
            headers = {"Authorization": f"Bearer {oc.api_key}"}
            r = requests.get(url, headers=headers, timeout=5)
            r.raise_for_status()
            who = f"OpenAI ({oc.model})"
            return True, f"✅ Connected to {who} at {oc.base_url}"
        except Exception:
            return False, "❌ Failed to query OpenAI; check API key and network access."

    # mock is always 'connected'
    return True, "✅ Using mock LLM provider"


_CAP_MANIFEST_CACHE: dict | None = None


def _load_capabilities_manifest() -> dict | None:
    global _CAP_MANIFEST_CACHE
    if _CAP_MANIFEST_CACHE is not None:
        return _CAP_MANIFEST_CACHE
    try:
        # Open manifest relative to this file to avoid issues with alias loaders
        spec = _find_spec("zyra.wizard")
        if (
            spec
            and getattr(spec, "origin", None)
            and not str(spec.origin).startswith("alias:")
        ):
            base = _Path(spec.origin).resolve().parent
        else:
            base = _Path(__file__).resolve().parent
        mpath = base / MANIFEST_FILENAME
        with mpath.open("r", encoding="utf-8") as f:
            _CAP_MANIFEST_CACHE = json.load(f)
            return _CAP_MANIFEST_CACHE
    except Exception:
        # Fallback: build manifest dynamically to ensure availability in tests
        try:
            from .manifest import build_manifest as _build_manifest

            _CAP_MANIFEST_CACHE = _build_manifest()
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


def _format_option_snippet(flag: str, val) -> str:
    if isinstance(val, dict):
        help_text = str(val.get("help") or "").strip()
        default_val = val.get("default")
        choices = val.get("choices") or []
        parts = [flag]
        if default_val is not None:
            parts.append(f"(default: {default_val})")
        if help_text:
            parts.append(f"— {help_text}")
        if choices:
            parts.append("[choices: " + ", ".join(map(str, choices)) + "]")
        return " ".join(parts)
    # Legacy string
    help_text = str(val or "").strip()
    return f"{flag} — {help_text}" if help_text else flag


def _select_relevant_details(prompt: str, cap: dict, limit: int = 6) -> list[str]:
    # Score commands as in _select_relevant_capabilities
    text = prompt.lower()
    scored: list[tuple[int, str, dict]] = []
    for cmd, meta in cap.items():
        desc = str(meta.get("description") or "").lower()
        opts_block = meta.get("options", {})
        opts = " ".join(opts_block.keys()) if isinstance(opts_block, dict) else ""
        hay = f"{cmd.lower()} {desc} {opts.lower()}"
        score = 0
        for token in set(text.replace("/", " ").replace(",", " ").split()):
            if token and token in hay:
                score += 1
        if score:
            scored.append((score, cmd, meta))
    scored.sort(key=lambda x: (-x[0], x[1]))
    result: list[str] = []
    for _, cmd, meta in scored[:limit]:
        lines = [f"- {cmd}: {meta.get('description', '')}".rstrip()]
        doc = str(meta.get("doc") or "").strip()
        epilog = str(meta.get("epilog") or "").strip()
        if doc:
            lines.append(f"  {doc}")
        if epilog:
            lines.append(f"  {epilog}")
        # Include up to 5 options
        opts_block = meta.get("options", {})
        if isinstance(opts_block, dict) and opts_block:
            count = 0
            for flag, val in list(opts_block.items()):
                lines.append("  - " + _format_option_snippet(str(flag), val))
                count += 1
                if count >= 5:
                    break
        result.append("\n".join(lines))
    return result


def _tokenize_manifest(cap: dict) -> dict:
    """Tokenize commands and options from capabilities manifest.

    Returns a dict with:
    - commands: set of full command strings (e.g., 'process subset')
    - first_tokens: set of first words
    - sub_map: mapping[first] -> set of second tokens
    - options: set of all option flags across commands
    - opt_map: mapping[(first, second_or_None)] -> set of option flags for that command
    - path_like: set of option flags marked as path-like (manifest path_arg)
    - opt_choices: mapping[(first, second_or_None)] -> { option -> set(choices) }
    - choices_global: mapping[option] -> set(choices) across all commands
    - opt_meta: mapping[(first, second_or_None)] -> { option -> {help, default?} }
    - group_map: mapping[(first, second_or_None)] -> { option -> group_title }
    - group_order: mapping[(first, second_or_None)] -> { group_title -> index }
    """
    commands: set[str] = set()
    first_tokens: set[str] = set()
    sub_map: dict[str, set[str]] = {}
    options: set[str] = set()
    opt_map: dict[tuple[str, str | None], set[str]] = {}
    path_like: set[str] = set()
    opt_choices: dict[tuple[str, str | None], dict[str, set[str]]] = {}
    choices_global: dict[str, set[str]] = {}
    opt_meta: dict[tuple[str, str | None], dict[str, dict]] = {}
    group_map: dict[tuple[str, str | None], dict[str, str]] = {}
    group_order: dict[tuple[str, str | None], dict[str, int]] = {}
    for cmd, meta in cap.items():
        cmd = str(cmd).strip()
        if not cmd:
            continue
        commands.add(cmd)
        parts = cmd.split()
        if parts:
            first_tokens.add(parts[0])
            if len(parts) >= 2:
                sub_map.setdefault(parts[0], set()).add(parts[1])
        raw_opts = meta.get("options", {})
        cmd_opts: set[str] = set()
        if isinstance(raw_opts, dict):
            for opt, val in raw_opts.items():
                cmd_opts.add(str(opt))
                # Detect manifest-tagged path-like args
                if isinstance(val, dict) and val.get("path_arg"):
                    path_like.add(str(opt))
                # Extract enum choices if provided
                if isinstance(val, dict) and val.get("choices"):
                    ch = {str(x) for x in (val.get("choices") or [])}
                    if ch:
                        opt_choices.setdefault(
                            (parts[0], parts[1] if len(parts) >= 2 else None), {}
                        ).setdefault(str(opt), set()).update(ch)
                        choices_global.setdefault(str(opt), set()).update(ch)
                # Capture help/default metadata for tooltip display
                if isinstance(val, dict):
                    meta_entry = {}
                    if val.get("help") is not None:
                        meta_entry["help"] = str(val.get("help") or "")
                    if "default" in val:
                        meta_entry["default"] = val.get("default")
                    if meta_entry:
                        opt_meta.setdefault(
                            (parts[0], parts[1] if len(parts) >= 2 else None), {}
                        )[str(opt)] = meta_entry
        else:
            # Unexpected format; ignore gracefully
            pass
        options.update(cmd_opts)
        key = (parts[0], parts[1] if len(parts) >= 2 else None)
        opt_map[key] = cmd_opts
        # Groups mapping for display and ranking
        try:
            groups = meta.get("groups", []) or []
            if isinstance(groups, list):
                gmap: dict[str, str] = {}
                gorder: dict[str, int] = {}
                for idx, g in enumerate(groups):
                    title = str(g.get("title") or "").strip()
                    for opt in g.get("options", []) or []:
                        gmap[str(opt)] = title
                    gorder[title] = idx
                if gmap:
                    group_map[key] = gmap
                if gorder:
                    group_order[key] = gorder
        except Exception:
            pass
    return {
        "commands": commands,
        "first_tokens": first_tokens,
        "sub_map": sub_map,
        "options": options,
        "opt_map": opt_map,
        "path_like": path_like,
        "opt_choices": opt_choices,
        "choices_global": choices_global,
        "opt_meta": opt_meta,
        "group_map": group_map,
        "group_order": group_order,
    }


class _WizardCompleter(Completer):  # type: ignore[misc]
    def __init__(self, cap: dict | None) -> None:
        if not PTK_AVAILABLE or not cap:
            self.enabled = False
            return
        self.enabled = True
        toks = _tokenize_manifest(cap)
        self.first_tokens: set[str] = toks["first_tokens"]
        self.sub_map: dict[str, set[str]] = toks["sub_map"]
        self.options: set[str] = toks["options"]
        self.opt_map: dict[tuple[str, str | None], set[str]] = toks["opt_map"]
        self.path_like: set[str] = toks.get("path_like", set())
        self.opt_choices: dict[tuple[str, str | None], dict[str, set[str]]] = toks.get(
            "opt_choices", {}
        )
        self.choices_global: dict[str, set[str]] = toks.get("choices_global", {})
        self.opt_meta: dict[tuple[str, str | None], dict[str, dict]] = toks.get(
            "opt_meta", {}
        )
        self.group_map: dict[tuple[str, str | None], dict[str, str]] = toks.get(
            "group_map", {}
        )
        self.group_order: dict[tuple[str, str | None], dict[str, int]] = toks.get(
            "group_order", {}
        )
        self.path_completer = PathCompleter(expanduser=True)  # type: ignore

    def _iter_basic(self, last: str, word: str):
        prefix = word.lower()
        for w in sorted(last):
            if w.lower().startswith(prefix):
                yield w

    def get_completions(self, document, complete_event):  # type: ignore[override]
        if not self.enabled:
            return
        text = document.text_before_cursor
        parts = [p for p in text.strip().split() if p]
        current = document.get_word_before_cursor(WORD=False)
        if len(parts) == 0:
            for w in self._iter_basic(self.first_tokens, current):
                yield Completion(w, start_position=-len(current))  # type: ignore
            return
        # Determine context
        first = parts[0]
        if len(parts) == 1:
            # Complete first token
            for w in self._iter_basic(self.first_tokens, current):
                yield Completion(w, start_position=-len(current))  # type: ignore
            return

        # After first token, try subcommands and options
        # If typing an option, complete from options
        def _meta_for_option(opt_name: str) -> dict:
            second = parts[1] if len(parts) >= 2 else None
            meta = {}
            if (first, second) in self.opt_meta:
                meta.update(self.opt_meta[(first, second)].get(opt_name, {}))
            if not meta and (first, None) in self.opt_meta:
                meta.update(self.opt_meta[(first, None)].get(opt_name, {}))
            if not meta and first in self.sub_map:
                for s in self.sub_map[first]:
                    if opt_name in self.opt_meta.get((first, s), {}):
                        meta.update(self.opt_meta[(first, s)][opt_name])
                        break
            return meta

        def _group_for_option(opt_name: str) -> tuple[str | None, int | None]:
            second = parts[1] if len(parts) >= 2 else None
            key = (first, second)
            title = None
            order = None
            if key in self.group_map and opt_name in self.group_map[key]:
                title = self.group_map[key][opt_name]
                order = self.group_order.get(key, {}).get(title)
                return title, order
            # Try single-token command
            key2 = (first, None)
            if key2 in self.group_map and opt_name in self.group_map[key2]:
                title = self.group_map[key2][opt_name]
                order = self.group_order.get(key2, {}).get(title)
                return title, order
            # Aggregate across subs
            if first in self.sub_map:
                for s in self.sub_map[first]:
                    key3 = (first, s)
                    if key3 in self.group_map and opt_name in self.group_map[key3]:
                        title = self.group_map[key3][opt_name]
                        order = self.group_order.get(key3, {}).get(title)
                        return title, order
            return None, None

        def _rank_options(cands: set[str]) -> list[str]:
            # Prefer options in earlier groups; then by recent usage; then alphabetical
            scored = []
            for opt in cands:
                gtitle, gidx = _group_for_option(opt)
                gp = gidx if gidx is not None else 9999
                recent = 0
                if hasattr(self, "recent_opts"):
                    recent = getattr(self, "recent_opts", {}).get(opt, 0)
                scored.append((gp, -recent, opt))
            scored.sort()
            return [x[2] for x in scored]

        if current.startswith("-"):
            # Scope options to known command when possible
            second = parts[1] if len(parts) >= 2 else None
            scoped: set[str] = set()
            if second and (first, second) in self.opt_map:
                scoped = self.opt_map[(first, second)]
            elif (first, None) in self.opt_map:
                # Single-token command like 'run'
                scoped = self.opt_map[(first, None)]
            elif first in self.sub_map:
                # Aggregate options for all subcommands under this first token
                for s in self.sub_map[first]:
                    scoped.update(self.opt_map.get((first, s), set()))
            else:
                scoped = self.options
            # Rank by group and usage
            ordered = _rank_options(scoped)
            for w in ordered:
                if not w.lower().startswith(current.lower()):
                    continue
                meta = _meta_for_option(w)
                tip = None
                if meta:
                    default_val = meta.get("default")
                    help_text = meta.get("help") or ""
                    gtitle, _ = _group_for_option(w)
                    pieces = []
                    if gtitle:
                        pieces.append(f"({gtitle})")
                    if help_text:
                        pieces.append(str(help_text))
                    if default_val is not None:
                        pieces.append(f"default: {default_val}")
                    tip = " — ".join(pieces) if pieces else None
                yield Completion(w, start_position=-len(current), display_meta=tip)  # type: ignore
            return
        # If previous token is an option that likely expects a path, use PathCompleter
        prev = parts[-2] if len(parts) >= 2 else ""
        # Use manifest-tagged path-like flags when available; fall back to heuristics
        path_flags = self.path_like or {
            "--input",
            "-i",
            "--output",
            "-o",
            "--output-dir",
            "--frames",
            "--frames-dir",
            "--input-file",
            "--manifest",
        }
        if prev in path_flags:
            # Delegate to PathCompleter
            yield from self.path_completer.get_completions(document, complete_event)  # type: ignore
            return

        # If previous token is an option with choices, suggest its choices
        def _choices_for_option(opt_name: str) -> set[str]:
            second = parts[1] if len(parts) >= 2 else None
            # Exact command
            ch = set()
            if (first, second) in self.opt_choices:
                ch.update(self.opt_choices[(first, second)].get(opt_name, set()))
            # Single-token command
            if not ch and (first, None) in self.opt_choices:
                ch.update(self.opt_choices[(first, None)].get(opt_name, set()))
            # Aggregate across subcommands
            if not ch and first in self.sub_map:
                for s in self.sub_map[first]:
                    ch.update(self.opt_choices.get((first, s), {}).get(opt_name, set()))
            # Global fallback
            if not ch:
                ch.update(self.choices_global.get(opt_name, set()))
            return ch

        if prev.startswith("-"):
            choices = _choices_for_option(prev)
            if choices:
                for w in self._iter_basic(choices, current):
                    yield Completion(w, start_position=-len(current))  # type: ignore
                return

        subs = self.sub_map.get(first, set())
        for w in self._iter_basic(subs, current):
            yield Completion(w, start_position=-len(current))  # type: ignore


def _prompt_line(prompt: str, *, session: SessionState | None = None) -> str:
    """Read a line from user, with optional prompt_toolkit support."""
    if PTK_AVAILABLE:
        cap = _load_capabilities_manifest() or {}
        session_obj = PromptSession()
        comp = _WizardCompleter(cap)
        # Attach recent option usage from session history for ranking
        if session is not None:
            import re as _re

            recent = {}
            for line in session.history[-20:]:
                for m in _re.findall(r"\s(--[a-zA-Z0-9-]+|-[a-zA-Z])\b", line):
                    recent[m] = recent.get(m, 0) + 1
            # Stash recent options on the completer for ranking
            import contextlib as _ctx

            with _ctx.suppress(Exception):
                comp.recent_opts = recent  # type: ignore[attr-defined]
        try:
            return session_obj.prompt(prompt, completer=comp)  # type: ignore[arg-type]
        except (EOFError, KeyboardInterrupt):  # pragma: no cover - handled by caller
            raise
    return input(prompt)


def _edit_commands(
    cmds: list[str], *, logfile: Path | None, session: SessionState | None
) -> list[str]:
    """Allow the user to edit commands; return sanitized list.

    Logs an 'edit' event with pre_edit and post_edit.
    """
    pre = list(cmds)
    text = "\n".join(pre) + "\n"
    edited = text
    used = "none"
    # Prefer prompt_toolkit multiline buffer when available
    if PTK_AVAILABLE:
        try:
            ptk_session = PromptSession()
            edited = ptk_session.prompt(
                "Edit commands (finish with Esc+Enter):\n",
                multiline=True,
                default=text,
            )
            used = "prompt_toolkit"
        except Exception:
            edited = text
    else:
        # Try $VISUAL/$EDITOR; fallback to plain stdin editing
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
        if editor:
            import subprocess
            import tempfile

            with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".sh") as tf:
                tf.write(text)
                tf.flush()
                path = tf.name
            try:
                subprocess.run([editor, path], check=False)
                from pathlib import Path as _P

                edited = _P(path).read_text(encoding="utf-8")
                used = editor
            finally:
                import contextlib
                from pathlib import Path as _P

                with contextlib.suppress(Exception):
                    _P(path).unlink()
        else:
            print("Enter edited commands. End with an empty line:")
            lines: list[str] = []
            while True:
                try:
                    line = input()
                except EOFError:
                    break
                if line.strip() == "":
                    break
                lines.append(line)
            edited = "\n".join(lines)
            used = "stdin"
    # Sanitize: keep only zyra/datavizhub lines and strip inline comments
    post: list[str] = []
    for line in edited.splitlines():
        s = _strip_inline_comment(line.strip())
        if s.startswith("zyra ") or s.startswith("datavizhub "):
            post.append(s)
    # Derive a safe session_id if available
    sess_id = None
    try:
        sess_id = (
            session.session_id if session and hasattr(session, "session_id") else None
        )
    except Exception:
        sess_id = None
    _log_event(
        logfile,
        {
            "ts": datetime.utcnow().isoformat() + "Z",
            "type": "edit",
            "pre_edit": pre,
            "post_edit": post,
            "editor": used,
        },
        session_id=sess_id,
    )
    return post


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
    """Extract zyra/datavizhub command lines from LLM text.

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
        return s if (s.startswith("zyra ") or s.startswith("datavizhub ")) else None

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


def _extract_safe_commands_from_reply(reply: str) -> tuple[list[str], list[str], int]:
    """Parse LLM reply and return sanitized, safe commands.

    Returns a tuple of:
    - cmds: sanitized commands safe to execute (inline comments stripped)
    - shown: commands for display with explanations preserved
    - dropped: count of non-datavizhub lines ignored
    """
    annotated_cmds = _extract_annotated_commands(reply)
    # Keep shown commands as-is to preserve any inline explanations
    shown = [a for a in annotated_cmds if a.startswith(("zyra ", "datavizhub "))]
    # Sanitize for execution by stripping inline comments
    cmds: list[str] = []
    dropped = 0
    for a in annotated_cmds:
        s = _strip_inline_comment(a)
        if s.startswith("zyra ") or s.startswith("datavizhub "):
            cmds.append(s)
        else:
            dropped += 1
    return cmds, shown, dropped


def _confirm(prompt: str, assume_yes: bool = False) -> bool:
    if assume_yes:
        return True
    try:
        ans = input(prompt + " [y/N]: ").strip().lower()
        return ans in ("y", "yes")
    except EOFError:
        return False


def _run_one(cmd: str) -> int:
    """Execute a single zyra/datavizhub command by calling the internal CLI.

    Safety notes:
    - No shell is invoked; arguments are parsed with shlex and passed directly
      to the CLI entrypoint function, which prevents shell command injection.
    - Upstream validation ensures only `zyra` (or legacy `datavizhub`) commands are constructed.
      This function strips the leading program name if present and forwards the
      remaining arguments to the CLI.
    """
    from zyra.cli import main as cli_main

    # Strip leading program name if present
    if "\x00" in cmd or "\n" in cmd:
        # Reject NUL/newline to avoid multi-line inputs
        raise ValueError("Invalid command: contains disallowed control characters")
    parts = shlex.split(cmd)
    if parts and parts[0] in {"zyra", "datavizhub"}:
        parts = parts[1:]
    try:
        return int(cli_main(parts))
    except SystemExit as exc:  # if cli_main raises SystemExit
        return int(getattr(exc, "code", 1) or 0)


def _resolve_missing_args(
    cmd: str,
    *,
    interactive: bool,
    logfile: Path | None,
    session: SessionState | None,
) -> str:
    """Use capabilities manifest to prompt for missing required args.

    When non-interactive and required args are missing, raises MissingArgsError.
    """
    cap = _load_capabilities_manifest()
    if not cap:
        return cmd

    def _log_evt(evt: dict) -> None:
        _log_event(
            logfile,
            {"ts": datetime.utcnow().isoformat() + "Z", **evt},
            session_id=(session.session_id if session else None),
        )

    resolver = MissingArgumentResolver(cap)
    updated = resolver.resolve(
        cmd,
        interactive=interactive,
        ask_fn=lambda q, meta: _prompt_line(q, session=session),
        log_fn=lambda e: _log_evt({"type": "arg_resolve", **e}),
    )
    if updated != cmd:
        print(f"✅ Command ready: {updated}")
    return updated


def _ensure_log_dir() -> Path:
    root = Path("~/.datavizhub/wizard_logs").expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _history_file_path() -> Path:
    root = Path("~/.datavizhub").expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root / "wizard_history"


def _append_history(cmd: str) -> None:
    """Append a JSONL record for a successfully executed command.

    Writes: {"ts": ISO8601Z, "cmd": "zyra ..."}
    Silently ignores non-zyra/datavizhub lines.
    """
    try:
        s = _strip_inline_comment(cmd.strip())
        if not (s.startswith("zyra ") or s.startswith("datavizhub ")):
            return
        rec = {"ts": datetime.utcnow().isoformat() + "Z", "cmd": s}
        p = _history_file_path()
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        # Best-effort; do not fail the REPL if persistence breaks
        pass


def _fallback_commands_for_prompt(prompt: str) -> list[str]:
    """Generate safe default commands when the model suggests none.

    Heuristic: if the prompt mentions CSV/columns/time series, suggest a
    timeseries visualization with placeholder axes; otherwise suggest a
    heatmap with a placeholder variable.

    The aim is to trigger interactive argument resolution without inventing
    file paths.
    """
    ql = prompt.lower()
    if any(w in ql for w in ["csv", "column", "time series", "timeseries"]):
        return ["zyra visualize timeseries --x time --y value --output timeseries.png"]
    return ["zyra visualize heatmap --var temperature --output heatmap.png"]


def _load_persisted_history() -> list[str]:
    """Load persisted history JSONL; return sanitized zyra/datavizhub commands.

    - Skips corrupted lines with a brief warning.
    - Deduplicates consecutive duplicates.
    """
    p = _history_file_path()
    if not p.exists():
        return []
    out: list[str] = []
    last: str | None = None
    try:
        with p.open("r", encoding="utf-8") as f:
            for ln, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    print(f"[history] Skipped corrupted JSON at line {ln}")
                    continue
                cmd = str(obj.get("cmd") or "").strip()
                s = _strip_inline_comment(cmd)
                if not (s.startswith("zyra ") or s.startswith("datavizhub ")):
                    continue
                if last is not None and s == last:
                    continue
                out.append(s)
                last = s
    except Exception:
        # If loading fails, return what we have
        pass
    return out


def _clear_history_file() -> None:
    """Delete history file if present."""
    try:
        p = _history_file_path()
        if p.exists():
            p.unlink()
    except Exception:
        pass


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
    edit_mode: str | None = None,  # 'always' | 'never' | 'prompt'
    interactive_args: bool = False,
) -> int:
    client = _select_provider(provider, model)
    # Build contextual user prompt for LLM if session is provided
    user_prompt = prompt
    if session is not None:
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
            rel = _select_relevant_details(prompt, cap)
            if rel:
                ctx_lines.append("- Relevant commands:")
                for block in rel:
                    for i, line in enumerate(block.splitlines()):
                        if i == 0:
                            ctx_lines.append(f"  {line}")
                        else:
                            ctx_lines.append(f"    {line}")
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

    cmds, shown, dropped = _extract_safe_commands_from_reply(reply)
    if dropped > 0:
        print(f"[safe] Ignored {dropped} non-datavizhub line(s).")
    # If model suggested nothing usable, provide a safe default that triggers interactive prompts
    if not cmds:
        cmds = _fallback_commands_for_prompt(prompt)
    # In dry-run, print suggestions as-is without manifest filtering/remapping
    if dry_run:
        if max_commands is not None:
            cmds = cmds[: max(0, int(max_commands))]
        if not cmds:
            print("No datavizhub commands were suggested.")
            return 1
        if show_raw:
            print("Raw model output:\n" + reply)
        if explain:
            print(
                "Suggested commands (with explanations):\n"
                + "\n".join(f"  {cmd}" for cmd in shown)
            )
        else:
            print("Suggested commands:\n" + "\n".join(f"  {cmd}" for cmd in cmds))
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
    # For interactive runs, keep suggested datavizhub lines as-is here so
    # users can edit unknown commands into valid ones. We will sanitize/resolve
    # just before execution.
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
        print(
            "Suggested commands (with explanations):\n"
            + "\n".join(f"  {cmd}" for cmd in shown)
        )
    else:
        print("Suggested commands:\n" + "\n".join(f"  {cmd}" for cmd in cmds))
    # Update session context immediately so dry-runs can influence follow-up prompts
    if session is not None:
        session.history.extend(cmds if not explain else shown)
        last_out = None
        for cmd in cmds:
            m = re.findall(r"(?:--output|-o)\s+(\S+)", cmd)
            if m:
                last_out = m[-1]
        if last_out:
            session.last_file = last_out
    # Decide whether to run, edit, or cancel
    choice = "r"
    from zyra.utils.env import env

    mode = (edit_mode or (env("WIZARD_EDITOR_MODE") or "prompt")).lower()
    if mode not in {"always", "never", "prompt"}:
        mode = "prompt"
    if mode == "always":
        choice = "e"
    elif mode == "never":
        choice = (
            "r" if (assume_yes or _confirm("Execute these commands?", False)) else "c"
        )
    else:
        if assume_yes:
            choice = "r"
        else:
            try:
                ans = _prompt_line("[r]un / [e]dit / [c]ancel? ").strip().lower()
            except EOFError:
                ans = "c"
            choice = ans[:1] if ans else "r"
            if choice not in {"r", "e", "c"}:
                choice = "r"

    if choice == "c":
        return 0
    if choice == "e":
        edited = _edit_commands(cmds, logfile=logfile, session=session)
        # Re-apply strict safety filter after edit
        cmds = []
        for line in edited or []:
            s = _strip_inline_comment(line)
            if s.startswith("datavizhub "):
                cmds.append(s)
        if not cmds:
            print("No commands to run after edit. Cancelled.")
            return 0

    status = 0
    for cmd in cmds:
        print(f"\n$ {cmd}")
        # Resolve missing required args
        try:
            cmd = _resolve_missing_args(
                cmd,
                interactive=interactive_args,
                logfile=logfile,
                session=session,
            )
        except MissingArgsError:
            status = 2
            break
        rc = _run_one(cmd)
        _log_event(
            logfile,
            {
                "ts": datetime.utcnow().isoformat() + "Z",
                "type": "exec",
                "cmd": cmd,
                "returncode": rc,
                "ok": (rc == 0),
                "provider": provider_name,
                "model": model_name,
            },
            session_id=(session.session_id if session else None),
        )
        if rc == 0:
            _append_history(cmd)
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
    print("Welcome to Zyra Wizard! Type 'exit' to quit.")
    session = SessionState()
    logfile = None
    if args.log:
        logdir = _ensure_log_dir()
        logfile = logdir / (datetime.utcnow().strftime("%Y%m%dT%H%M%SZ") + ".jsonl")
    # Resolve editor mode once for the session
    from zyra.utils.env import env

    env_mode = (env("WIZARD_EDITOR_MODE") or "prompt").lower()
    if getattr(args, "edit", False):
        editor_mode = "always"
    elif getattr(args, "no_edit", False):
        editor_mode = "never"
    elif env_mode in {"always", "never", "prompt"}:
        editor_mode = env_mode
    else:
        editor_mode = "prompt"

    # Preload persisted history into session (deduped)
    try:
        persisted = _load_persisted_history()
        if persisted:
            session.history.extend(persisted)
    except Exception:
        pass

    # Helper: get sanitized history commands (only datavizhub lines, comments stripped)
    def _history_commands() -> list[str]:
        out: list[str] = []
        for line in session.history:
            s = _strip_inline_comment(str(line).strip())
            if s.startswith("datavizhub "):
                out.append(s)
        return out

    while True:
        try:
            q = _prompt_line("> ").strip()
        except EOFError:
            print()
            return 0
        if not q:
            continue
        if q.lower() in {"exit", "quit"}:
            return 0

        # Built-in REPL helpers: :history, !N / :retry N, :edit N
        # Show history: optional limit e.g., :history 20
        m_hist = re.match(r"^:?history(?:\s+(\d+))?$", q.strip(), flags=re.I)
        if m_hist:
            limit = int(m_hist.group(1)) if m_hist.group(1) else None
            cmds = _history_commands()
            if limit is not None:
                cmds = cmds[-limit:]
            if not cmds:
                print("No history yet.")
            else:
                print("History:")
                # Number from 1..N in chronological order
                for i, cmd in enumerate(cmds, start=1):
                    print(f"[{i}] {cmd}")
            continue

        # Clear history: both in-memory and file
        if re.match(r"^:clear-history$", q.strip(), flags=re.I):
            _clear_history_file()
            session.history.clear()
            print("History cleared.")
            _log_event(
                logfile,
                {
                    "ts": datetime.utcnow().isoformat() + "Z",
                    "type": "history_clear",
                },
                session_id=session.session_id,
            )
            continue

        # Save history to a file path: :save-history <file>
        m_save = re.match(r"^:save-history\s+(.+)$", q.strip(), flags=re.I)
        if m_save:
            dest_raw = m_save.group(1).strip()
            try:
                dest = Path(dest_raw).expanduser()
                dest.parent.mkdir(parents=True, exist_ok=True)
                cmds = _history_commands()
                with dest.open("w", encoding="utf-8") as f:
                    for c in cmds:
                        f.write(c + "\n")
                print(f"Saved {len(cmds)} command(s) to {str(dest)}")
                _log_event(
                    logfile,
                    {
                        "ts": datetime.utcnow().isoformat() + "Z",
                        "type": "history_save",
                        "path": str(dest),
                        "count": len(cmds),
                    },
                    session_id=session.session_id,
                )
            except Exception as exc:
                print(f"Failed to save history: {exc}")
            continue

        # Recall as-is: !N or :retry N
        m_retry = re.match(r"^(?:!(\d+)|:?retry\s+(\d+))$", q.strip(), flags=re.I)
        if m_retry:
            idx_s = m_retry.group(1) or m_retry.group(2)
            try:
                idx = int(idx_s)
            except Exception:
                print("Invalid index.")
                continue
            cmds = _history_commands()
            if not cmds:
                print("No history yet.")
                continue
            if idx < 1 or idx > len(cmds):
                print("Index out of range. Use :history to list.")
                continue
            cmd = cmds[idx - 1]
            print(f"\n$ {cmd}")
            _log_event(
                logfile,
                {
                    "ts": datetime.utcnow().isoformat() + "Z",
                    "type": "history_exec",
                    "action": "retry",
                    "index": idx,
                    "cmd": cmd,
                },
                session_id=session.session_id,
            )
            rc = _run_one(cmd)
            _log_event(
                logfile,
                {
                    "ts": datetime.utcnow().isoformat() + "Z",
                    "type": "exec",
                    "cmd": cmd,
                    "returncode": rc,
                    "ok": (rc == 0),
                },
                session_id=session.session_id,
            )
            if rc == 0:
                _append_history(cmd)
            # Update session context
            session.history.append(cmd)
            m_out = re.findall(r"(?:--output|-o)\s+(\S+)\b", cmd)
            if m_out:
                session.last_file = m_out[-1]
            if rc != 0:
                print(f"Command failed with exit code {rc}")
                print(f"Last command set exited with {rc}")
            continue

        # Edit selected history entry then run: :edit N
        m_edit = re.match(r"^:edit\s+(\d+)$", q.strip(), flags=re.I)
        if m_edit:
            idx = int(m_edit.group(1))
            cmds = _history_commands()
            if not cmds:
                print("No history yet.")
                continue
            if idx < 1 or idx > len(cmds):
                print("Index out of range. Use :history to list.")
                continue
            original = cmds[idx - 1]
            edited = _edit_commands([original], logfile=logfile, session=session)
            # Re-apply strict safety filter after edit
            to_run: list[str] = []
            for line in edited or []:
                s = _strip_inline_comment(line)
                if s.startswith("datavizhub "):
                    to_run.append(s)
            if not to_run:
                print("No commands to run after edit. Cancelled.")
                continue
            status = 0
            for c in to_run:
                print(f"\n$ {c}")
                _log_event(
                    logfile,
                    {
                        "ts": datetime.utcnow().isoformat() + "Z",
                        "type": "history_exec",
                        "action": "edit",
                        "index": idx,
                        "cmd": c,
                    },
                    session_id=session.session_id,
                )
                rc = _run_one(c)
                _log_event(
                    logfile,
                    {
                        "ts": datetime.utcnow().isoformat() + "Z",
                        "type": "exec",
                        "cmd": c,
                        "returncode": rc,
                        "ok": (rc == 0),
                    },
                    session_id=session.session_id,
                )
                if rc == 0:
                    _append_history(c)
                session.history.append(c)
                m_out = re.findall(r"(?:--output|-o)\s+(\S+)", c)
                if m_out:
                    session.last_file = m_out[-1]
                if rc != 0:
                    print(f"Command failed with exit code {rc}")
                    status = rc
                    break
            if status != 0:
                print(f"Last command set exited with {status}")
            continue
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
            edit_mode=editor_mode,
            interactive_args=True,
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
    p.add_argument(
        "--test-llm",
        action="store_true",
        help="Probe connectivity to configured LLM provider and exit",
    )
    p.add_argument(
        "--edit",
        action="store_true",
        help="Open an editor to modify commands before run",
    )
    p.add_argument(
        "--no-edit",
        action="store_true",
        help="Do not offer edit prompt; run/cancel only",
    )
    p.add_argument(
        "--interactive",
        action="store_true",
        help="Ask for missing required arguments in one-shot mode",
    )

    def _cmd(ns: argparse.Namespace) -> int:
        if ns.test_llm:
            ok, msg = _test_llm_connectivity(ns.provider, ns.model)
            print(msg)
            return 0 if ok else 2
        if ns.prompt:
            logfile = None
            if ns.log:
                logdir = _ensure_log_dir()
                logfile = logdir / (
                    datetime.utcnow().strftime("%Y%m%dT%H%M%SZ") + ".jsonl"
                )
            # One-shot: create a transient session for correlation IDs
            the_session = SessionState()
            # Resolve editor mode (one-shot)
            from zyra.utils.env import env

            env_mode = (env("WIZARD_EDITOR_MODE") or "prompt").lower()
            if ns.edit:
                editor_mode = "always"
            elif ns.no_edit:
                editor_mode = "never"
            elif env_mode in {"always", "never", "prompt"}:
                editor_mode = env_mode
            else:
                editor_mode = "prompt"
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
                edit_mode=editor_mode,
                interactive_args=bool(getattr(ns, "interactive", False)),
            )
        return _interactive_loop(ns)

    p.set_defaults(func=_cmd)
