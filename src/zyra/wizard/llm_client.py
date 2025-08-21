"""LLM client adapters used by the Wizard.

Network dependencies are optional. This module is designed to run in minimal
environments where `requests` may be unavailable. To keep exception handling
explicit without sprinkling type: ignores, we attempt to import
`requests.exceptions` and, if not present, define lightweight fallback classes
(`RequestException`, `HTTPError`) with the same names.

On network or parsing errors, each concrete client returns a helpful comment and
falls back to the in-memory `MockClient` so behavior remains deterministic in
tests and offline/dev environments.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Exception hierarchy for HTTP/network errors.
# requests may be unavailable in minimal environments; provide fallbacks so
# exception handling remains explicit without type: ignore noise.
try:  # pragma: no cover - environment dependent
    from requests.exceptions import HTTPError, RequestException  # type: ignore
except ImportError:  # pragma: no cover - requests missing

    class RequestException(Exception):  # type: ignore[no-redef]
        pass

    class HTTPError(RequestException):  # type: ignore[no-redef]
        pass


# Cache a single MockClient instance for fallback use to avoid re-instantiation
_mock_singleton: MockClient | None = None


def _get_mock_singleton() -> MockClient:
    global _mock_singleton
    if _mock_singleton is None:
        _mock_singleton = MockClient()
    return _mock_singleton


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

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        from zyra.utils.env import env

        resolved_model = model or env("LLM_MODEL") or "gpt-4o-mini"
        # Initialize dataclass fields explicitly
        super().__init__(name=self.name, model=resolved_model)
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.base_url = (
            base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        )
        self._session = None  # lazy-initialized requests.Session for connection pooling

        # Fail fast if credentials are missing for OpenAI provider
        if not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required for OpenAI provider. Set the env var or use provider='mock'."
            )

    def _get_session(self):  # pragma: no cover - trivial getter
        if self._session is None:
            try:
                import requests  # type: ignore
                from requests.adapters import HTTPAdapter  # type: ignore
            except ImportError:  # requests may be unavailable in minimal envs
                return None
            s = requests.Session()
            adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
            s.mount("https://", adapter)
            s.mount("http://", adapter)
            self._session = s
        return self._session

    def generate(
        self, system_prompt: str, user_prompt: str
    ) -> str:  # pragma: no cover - network optional
        import json
        from json import JSONDecodeError

        try:
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
            sess = self._get_session()
            if sess is None:
                import requests  # type: ignore

                resp = requests.post(
                    url, headers=headers, data=json.dumps(payload), timeout=60
                )
            else:
                resp = sess.post(
                    url, headers=headers, data=json.dumps(payload), timeout=60
                )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except (
            ImportError,
            JSONDecodeError,
            KeyError,
            IndexError,
            TypeError,
            RequestException,
            HTTPError,
        ) as exc:
            return f"# OpenAI error: {exc}\n" + _get_mock_singleton().generate(
                system_prompt, user_prompt
            )


class OllamaClient(LLMClient):
    name = "ollama"

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        from zyra.utils.env import env

        resolved_model = model or env("LLM_MODEL") or "mistral"
        # Initialize dataclass fields explicitly
        super().__init__(name=self.name, model=resolved_model)
        # Support both OLLAMA_BASE_URL (project conv.) and OLLAMA_HOST (common conv.)
        self.base_url = (
            base_url
            or os.environ.get("OLLAMA_BASE_URL")
            or os.environ.get("OLLAMA_HOST")
            or "http://localhost:11434"
        )
        self._session = None  # lazy-initialized requests.Session for connection pooling

    def _get_session(self):  # pragma: no cover - trivial getter
        if self._session is None:
            try:
                import requests  # type: ignore
                from requests.adapters import HTTPAdapter  # type: ignore
            except ImportError:  # requests may be unavailable in minimal envs
                return None
            s = requests.Session()
            adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
            s.mount("https://", adapter)
            s.mount("http://", adapter)
            self._session = s
        return self._session

    def generate(
        self, system_prompt: str, user_prompt: str
    ) -> str:  # pragma: no cover - network optional
        import json
        from json import JSONDecodeError

        try:
            url = f"{self.base_url}/api/chat"
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
            }
            sess = self._get_session()
            if sess is None:
                import requests  # type: ignore

                resp = requests.post(url, data=json.dumps(payload), timeout=60)
            else:
                resp = sess.post(url, data=json.dumps(payload), timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "").strip()
        except (
            ImportError,
            JSONDecodeError,
            KeyError,
            TypeError,
            RequestException,
            HTTPError,
        ) as exc:
            # Provide targeted hints for common connectivity issues
            err = str(exc)
            hints = []
            try:
                from urllib.parse import urlparse

                parsed = urlparse(self.base_url)
                host = parsed.hostname or ""
            except Exception:
                host = ""

            if (
                "Connection refused" in err
                or "Failed to establish a new connection" in err
            ):
                if host in {"localhost", "127.0.0.1"}:
                    hints.append(
                        "Ollama may not be listening on localhost inside your container."
                    )
                    hints.append(
                        "If using Docker on Linux, add --add-host=host.docker.internal:host-gateway and set OLLAMA_BASE_URL=http://host.docker.internal:11434."
                    )
                else:
                    hints.append(f"Verify OLLAMA_BASE_URL is correct: {self.base_url}")
                hints.append(
                    "Ensure the server is started with: OLLAMA_HOST=0.0.0.0 ollama serve"
                )
            hint_text = ("\n# " + "\n# ".join(hints)) if hints else ""
            return (
                f"# Ollama error: {exc}{hint_text}\n"
                + _get_mock_singleton().generate(system_prompt, user_prompt)
            )


class MockClient(LLMClient):
    name = "mock"

    def __init__(self) -> None:
        # Ensure dataclass field 'name' is initialized correctly
        super().__init__(name=self.name, model=None)

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        q = user_prompt.lower()
        # Very small heuristic to return plausible commands
        if "subset" in q and ("hrrr" in q or "colorado" in q):
            return (
                """Here are suggested commands:
```bash
zyra acquire https://example.com/hrrr.grib2 --output tmp.grib2
zyra process convert-format tmp.grib2 --format netcdf --output tmp.nc
zyra visualize heatmap --input tmp.nc --var TMP --output co.png
```
"""
            ).strip()
        if "convert" in q and ("netcdf" in q or "geotiff" in q or "grib" in q):
            return (
                """Try this:
```bash
zyra process convert-format input.nc --format geotiff --output output.tif
```
"""
            ).strip()
        # Generic default
        return (
            """Suggested command:
```bash
zyra --help
```
"""
        ).strip()
