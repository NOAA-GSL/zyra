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
        # tokens include the whole command line split by shlex; first may be 'zyra'
        # identify command key as '<group> <sub>' if present in manifest
        if not tokens:
            return None
        start = 1 if tokens and tokens[0] in {"datavizhub", "zyra"} else 0
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

    def _present_positionals(self, tokens: list[str]) -> list[str]:
        # Return list of positional tokens found after removing flags and their values
        start = 1 if tokens and tokens[0] in {"datavizhub", "zyra"} else 0
        # Skip group/sub (1 or 2 tokens depending on manifest key)
        # Strategy: after 'zyra', next two tokens are group/sub for our commands
        i = start
        # Attempt to skip two tokens; if manifest keys include only one token, extra skip is harmless
        i += 2
        pos: list[str] = []
        # Build set of flags to detect values
        idx = i
        while idx < len(tokens):
            t = tokens[idx]
            if t.startswith("-"):
                # skip flag and its value if present
                if idx + 1 < len(tokens) and not tokens[idx + 1].startswith("-"):
                    idx += 2
                else:
                    idx += 1
                continue
            # positional
            pos.append(t)
            idx += 1
        return pos

    def _required_positionals(self, cmd_key: str) -> list[dict[str, Any]]:
        pos = self.manifest.get(cmd_key, {}).get("positionals", [])
        if not isinstance(pos, list):
            return []
        req: list[dict[str, Any]] = []
        for item in pos:
            if isinstance(item, dict) and item.get("required"):
                req.append(item)
        return req

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

        missing_flags = self._missing_required(tokens, key)
        # Determine missing positionals (those not yet present)
        req_pos = self._required_positionals(key)
        present_pos = self._present_positionals(tokens)
        pos_to_ask: list[dict[str, Any]] = []
        if len(present_pos) < len(req_pos):
            pos_to_ask = req_pos[len(present_pos) :]

        # Nothing to do: all required flags and positionals present
        if not missing_flags and not pos_to_ask:
            return command
        if not interactive:
            raise MissingArgsError(
                [f for f, _ in missing_flags] + [str(p.get("name")) for p in pos_to_ask]
            )

        # Default ask function uses input()
        def _default_ask(
            prompt: str, meta: dict[str, Any]
        ) -> str:  # pragma: no cover - trivial
            return input(prompt + ": ")

        ask: AskFn = ask_fn or _default_ask

        def _build_prompt_text(meta: dict[str, Any], fallback: str) -> str:
            prompt = meta.get("help") or fallback
            choices = meta.get("choices") or []
            if choices:
                prompt = f"{prompt} (choices: {', '.join(map(str, choices))})"
            return str(prompt)

        def _ask_and_validate(meta: dict[str, Any], fallback_label: str) -> str:
            # Returns a validated string value according to meta[type]/choices
            t = str(meta.get("type") or "str").lower()
            choices = [str(c) for c in (meta.get("choices") or [])]
            while True:
                raw = ask(_build_prompt_text(meta, fallback_label), meta)
                try:
                    if t == "int":
                        int(raw)  # validate
                    elif t == "float":
                        float(raw)
                    # Validate choices if provided
                    if choices and str(raw) not in choices:
                        raise ValueError("invalid choice")
                    return str(raw)
                except Exception:
                    # invalid; re-ask
                    continue

        # Prompt for each missing flag and append to tokens
        for flag, meta in missing_flags:
            value = _ask_and_validate(meta, f"Please provide {flag}")
            # Append to command (use long flag as given in manifest)
            tokens.extend([flag, value])
            if log_fn is not None:
                evt = {
                    "type": "arg_resolve",
                    "arg_name": flag,
                    "user_value": ("******" if meta.get("sensitive") else value),
                    "validated": True,
                }
                # Pass through meta fields that could be useful for analytics
                for k in ("type", "choices", "required"):
                    if k in meta:
                        evt[k] = meta[k]
                if meta.get("sensitive"):
                    evt["masked"] = True
                log_fn(evt)

        # Handle required positionals
        if pos_to_ask:
            for item in pos_to_ask:
                nm = item.get("name") or "arg"
                value = _ask_and_validate(item, f"Please provide {nm}")
                tokens.append(value)
                if log_fn is not None:
                    evt = {
                        "type": "arg_resolve",
                        "arg_name": nm,
                        "user_value": ("******" if item.get("sensitive") else value),
                        "validated": True,
                        "positional": True,
                    }
                    for k in ("type", "choices", "required"):
                        if k in item:
                            evt[k] = item[k]
                    if item.get("sensitive"):
                        evt["masked"] = True
                    log_fn(evt)

        # Recombine
        return " ".join(tokens)
