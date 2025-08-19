from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class LLMClient:
    name: str = "base"
    model: str | None = None

    def generate(
        self, system_prompt: str, user_prompt: str
    ) -> str:  # pragma: no cover - thin wrapper
        raise NotImplementedError


class OpenAIClient(LLMClient):
    name = "openai"

    def __init__(self, model: str | None = None) -> None:
        super().__init__(
            model=model or os.environ.get("DATAVIZHUB_LLM_MODEL") or "gpt-4o-mini"
        )
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

    def generate(
        self, system_prompt: str, user_prompt: str
    ) -> str:  # pragma: no cover - network optional
        if not self.api_key:
            # Soft-fail with guidance
            return (
                "# Missing OPENAI_API_KEY. Falling back to mock suggestion.\n"
                + MockClient().generate(system_prompt, user_prompt)
            )
        import json

        try:
            import requests

            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
            }
            resp = requests.post(
                url, headers=headers, data=json.dumps(payload), timeout=60
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            return f"# OpenAI error: {exc}\n" + MockClient().generate(
                system_prompt, user_prompt
            )


class OllamaClient(LLMClient):
    name = "ollama"

    def __init__(self, model: str | None = None) -> None:
        super().__init__(
            model=model or os.environ.get("DATAVIZHUB_LLM_MODEL") or "mistral"
        )
        self.base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

    def generate(
        self, system_prompt: str, user_prompt: str
    ) -> str:  # pragma: no cover - network optional
        import json

        try:
            import requests

            url = f"{self.base_url}/api/chat"
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
            }
            resp = requests.post(url, data=json.dumps(payload), timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "").strip()
        except Exception as exc:
            return f"# Ollama error: {exc}\n" + MockClient().generate(
                system_prompt, user_prompt
            )


class MockClient(LLMClient):
    name = "mock"

    def __init__(self) -> None:
        super().__init__(model=None)

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        q = user_prompt.lower()
        # Very small heuristic to return plausible commands
        if "subset" in q and ("hrrr" in q or "colorado" in q):
            return (
                """Here are suggested commands:
```bash
datavizhub acquire https://example.com/hrrr.grib2 --output tmp.grib2
datavizhub process convert-format tmp.grib2 --format netcdf --output tmp.nc
datavizhub visualize heatmap --input tmp.nc --var TMP --output co.png
```
"""
            ).strip()
        if "convert" in q and ("netcdf" in q or "geotiff" in q or "grib" in q):
            return (
                """Try this:
```bash
datavizhub process convert-format input.nc --format geotiff --output output.tif
```
"""
            ).strip()
        # Generic default
        return (
            """Suggested command:
```bash
datavizhub --help
```
"""
        ).strip()
