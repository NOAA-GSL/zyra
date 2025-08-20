from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Any, Callable


class MissingArgsError(Exception):
    def __init__(self, missing: list[str]) -> None:
        super().__init__(", ".join(missing))
        self.missing = missing


AskFn = Callable[[str, dict[str, Any]], str]
LogFn = Callable[[dict[str, Any]], None]


@dataclass
class MissingArgumentResolver:
    manifest: dict

    def _find_cmd_key(self, tokens: list[str]) -> str | None:
        # tokens include the whole command line split by shlex; first may be 'datavizhub'
        # identify command key as '<group> <sub>' if present in manifest
        if not tokens:
            return None
        start = 1 if tokens and tokens[0] == "datavizhub" else 0
        if len(tokens) - start >= 2:
            key = f"{tokens[start]} {tokens[start+1]}"
            if key in self.manifest:
                return key
        # Fallback: exact first token command if present
        if len(tokens) - start >= 1:
            key = tokens[start]
            if key in self.manifest:
                return key
        return None

    def _present_flags(self, tokens: list[str]) -> set[str]:
        present: set[str] = set()
        for t in tokens:
            if t.startswith("-"):
                present.add(t)
        return present

    def _required_flags(self, cmd_key: str) -> list[tuple[str, dict[str, Any]]]:
        opts = self.manifest.get(cmd_key, {}).get("options", {})
        if not isinstance(opts, dict):
            return []
        out: list[tuple[str, dict[str, Any]]] = []
        for flag, meta in opts.items():
            if isinstance(meta, dict) and meta.get("required"):
                out.append((flag, meta))
        return out

    def _flag_has_value(self, tokens: list[str], idx: int) -> bool:
        # A flag is considered provided if it appears with a following value (non-flag)
        if idx < 0 or idx >= len(tokens):
            return False
        if idx + 1 >= len(tokens):
            return False
        nxt = tokens[idx + 1]
        return not nxt.startswith("-")

    def _missing_required(
        self, tokens: list[str], cmd_key: str
    ) -> list[tuple[str, dict[str, Any]]]:
        reqs = self._required_flags(cmd_key)
        missing: list[tuple[str, dict[str, Any]]] = []
        # Build map of positions for quick lookup
        for flag, meta in reqs:
            present = False
            for i, t in enumerate(tokens):
                if t == flag:
                    # Must have a value token next
                    present = self._flag_has_value(tokens, i)
                    break
            if not present:
                missing.append((flag, meta))
        return missing

    def resolve(
        self,
        command: str,
        *,
        interactive: bool = False,
        ask_fn: AskFn | None = None,
        log_fn: LogFn | None = None,
    ) -> str:
        """Ensure required arguments are present; optionally prompt interactively.

        - Returns updated command string when all required arguments are present.
        - Raises MissingArgsError when non-interactive and required args are missing.
        """
        tokens = shlex.split(command)
        key = self._find_cmd_key(tokens)
        if not key:
            return command  # unknown command; do not modify

        missing = self._missing_required(tokens, key)
        if not missing:
            return command
        if not interactive:
            raise MissingArgsError([f for f, _ in missing])

        # Default ask function uses input()
        def _default_ask(
            prompt: str, meta: dict[str, Any]
        ) -> str:  # pragma: no cover - trivial
            return input(prompt + ": ")

        ask: AskFn = ask_fn or _default_ask

        # Prompt for each missing flag and append to tokens
        for flag, meta in missing:
            q = meta.get("help") or f"Please provide {flag}"
            t = (meta.get("type") or "str").lower()
            choices = meta.get("choices") or []
            if choices:
                q += f" (choices: {', '.join(map(str, choices))})"
            value: str
            while True:
                raw = ask(q, meta)
                try:
                    if t == "int":
                        int(raw)  # validate
                    elif t == "float":
                        float(raw)
                    # for str/path or others, accept as-is
                    if choices and str(raw) not in [str(c) for c in choices]:
                        raise ValueError("invalid choice")
                    value = str(raw)
                    break
                except Exception:
                    # invalid; re-ask
                    continue
            # Append to command (use long flag as given in manifest)
            tokens.extend([flag, value])
            if log_fn is not None:
                evt = {
                    "type": "arg_resolve",
                    "arg_name": flag,
                    "user_value": value,
                    "validated": True,
                }
                # Pass through meta fields that could be useful for analytics
                for k in ("type", "choices", "required"):
                    if k in meta:
                        evt[k] = meta[k]
                log_fn(evt)

        # Recombine
        return " ".join(tokens)
