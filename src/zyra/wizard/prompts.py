from __future__ import annotations

import logging
from importlib import resources as ir


def _default_system_prompt() -> str:
    # Fallback text kept in code to preserve behavior if assets are missing.
    return (
        "You are Zyra Wizard, an assistant that helps users run the "
        "'zyra' CLI. Your job is to output one or more CLI commands "
        "that directly accomplish the user's request.\n\n"
        "Formatting rules:\n"
        "- Always wrap commands in a fenced code block with 'bash'.\n"
        "- Each command must start with 'zyra'.\n"
        "- If multiple steps are needed, put each on its own line.\n"
        "- You may include short inline comments (using #) to briefly explain "
        "what each command does.\n"
        "- Do not include any text outside the fenced code block.\n\n"
        "Guidelines:\n"
        "- Prefer succinct, directly runnable commands.\n"
        "- Use placeholders (like <input-file>) only when unavoidable.\n"
        "- Never generate non-zyra shell commands (e.g., rm, curl, sudo).\n"
        "- If essential details are missing, make a reasonable assumption and use a placeholder.\n"
        "- Explanations should be one short phrase only, never long sentences.\n"
        "- Avoid redundant flags unless necessary for clarity.\n\n"
        "Your output must always be a single fenced code block with commands "
        "and optional short comments.\n\n"
        "Strict CLI policy:\n"
        "- Only use subcommands and options that exist in the capabilities manifest provided in the Context.\n"
        "- Never invent commands or aliases (e.g., 'plot' is invalid — prefer 'visualize heatmap' or 'visualize timeseries').\n"
        "- If unsure which visualization fits, pick 'visualize heatmap' for gridded data or 'visualize timeseries' for CSV/1D.\n"
        "- Do not fabricate file paths. Prefer omitting required path-like inputs so the Wizard can prompt the user interactively.\n"
    )


def _load_system_prompt_from_assets() -> str | None:
    try:
        base = ir.files("zyra.assets").joinpath("llm/prompts/wizard_system.md")
        if base.is_file():
            return base.read_text(encoding="utf-8")
        return None
    except ModuleNotFoundError as exc:
        # Assets package not installed/available: expected in some runtimes.
        logging.getLogger(__name__).info(
            "Wizard assets package unavailable; using built-in prompt: %s", exc
        )
        return None
    except FileNotFoundError as exc:
        # Asset file missing from package. Warn and fall back.
        logging.getLogger(__name__).warning(
            "Wizard prompt asset not found; using built-in prompt: %s", exc
        )
        return None
    except (UnicodeDecodeError, OSError) as exc:
        # Decode or OS errors likely indicate corruption or permission issues.
        logging.getLogger(__name__).error(
            "Error reading wizard prompt asset; using built-in prompt: %s", exc
        )
        return None


# System prompt for the Wizard LLM, loaded from packaged assets when available.
_asset_prompt = _load_system_prompt_from_assets()
SYSTEM_PROMPT = _asset_prompt if _asset_prompt else _default_system_prompt()
