# SPDX-License-Identifier: Apache-2.0
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
from typing import Any, Callable

from zyra.utils.env import coalesce as _coalesce
from zyra.utils.env import env as _env
from zyra.utils.env import env_bool as _env_bool


def _content_blocks(txt: str, imgs: list[str] | None) -> list[dict[str, Any]]:
    """Build OpenAI-style multimodal content blocks for text + optional images."""
    blocks: list[dict[str, Any]] = [{"type": "text", "text": txt}]
    for b64 in imgs or []:
        blocks.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/*;base64,{b64}"},
            }
        )
    return blocks


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
_GEMINI_SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)
_DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
_DEFAULT_GEMINI_LOCATION = "us-central1"


def _get_mock_singleton() -> MockClient:
    global _mock_singleton
    if _mock_singleton is None:
        _mock_singleton = MockClient()
    return _mock_singleton


def _resolve_vertex_project(explicit: str | None) -> str | None:
    return _coalesce(
        explicit,
        _env("VERTEX_PROJECT"),
        os.environ.get("GOOGLE_PROJECT_ID"),
        os.environ.get("GOOGLE_CLOUD_PROJECT"),
    )


def _resolve_vertex_location(explicit: str | None) -> str:
    return (
        explicit
        or _env("VERTEX_LOCATION")
        or os.environ.get("GOOGLE_CLOUD_REGION")
        or _DEFAULT_GEMINI_LOCATION
    )


def _resolve_vertex_model(explicit: str | None) -> str:
    return (
        explicit or _env("VERTEX_MODEL") or _env("LLM_MODEL") or _DEFAULT_GEMINI_MODEL
    )


@dataclass
class LLMClient:
    name: str = "base"
    model: str | None = None

    def generate(
        self, system_prompt: str, user_prompt: str, images: list[str] | None = None
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
        self, system_prompt: str, user_prompt: str, images: list[str] | None = None
    ) -> str:  # pragma: no cover - network optional
        import json
        from json import JSONDecodeError

        try:
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": _content_blocks(user_prompt, images),
                },
            ]
            payload = {
                "model": self.model,
                "messages": messages,
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
        ) as _:
            # Avoid exposing exception details; provide generic hint and fallback to mock
            return (
                "# OpenAI error: fallback response used\n"
                + _get_mock_singleton().generate(system_prompt, user_prompt, images)
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
        self, system_prompt: str, user_prompt: str, images: list[str] | None = None
    ) -> str:  # pragma: no cover - network optional
        import json
        from json import JSONDecodeError

        try:
            url = f"{self.base_url}/api/chat"
            payload: dict = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
            }
            # Ollama multimodal: attach images as base64 strings when provided
            if images:
                payload["images"] = images
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
        ) as _:
            # Provide optional generic hints without leaking internal details
            include_hints = bool(_env_bool("LLM_ERROR_HINTS", False))
            hint_text = ""
            if include_hints:
                hints = [
                    "Verify OLLAMA_BASE_URL points to your Ollama server",
                    "Ensure the server is started with: OLLAMA_HOST=0.0.0.0 ollama serve",
                ]
                hint_text = "\n# " + "\n# ".join(hints)
            return (
                f"# Ollama error: fallback response used{hint_text}\n"
                + _get_mock_singleton().generate(system_prompt, user_prompt, images)
            )


class GeminiVertexClient(LLMClient):
    name = "gemini"

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        project: str | None = None,
        location: str | None = None,
    ) -> None:
        resolved_model = _resolve_vertex_model(model)
        super().__init__(name=self.name, model=resolved_model)
        self.api_key = os.environ.get("GOOGLE_API_KEY")
        self.project = _resolve_vertex_project(project)
        self.location = _resolve_vertex_location(location)
        self.publisher = os.environ.get("VERTEX_PUBLISHER", "google")
        self._session = None
        self._credentials = None
        self._google_request_factory: Callable[[], Any] | None = None

        if self.api_key:
            # Generative Language REST API mode
            base = (
                base_url
                or os.environ.get("GENLANG_BASE_URL")
                or os.environ.get("VERTEX_ENDPOINT")
                or "https://generativelanguage.googleapis.com"
            )
            self._mode = "api_key"
            self._endpoint_root = base.rstrip("/")
            self._endpoint = (
                f"{self._endpoint_root}/v1beta/models/{self.model}:generateContent"
            )
            self._models_endpoint = f"{self._endpoint_root}/v1beta/models"
            return

        # Otherwise require Workspace/Vertex credentials via ADC
        self._mode = "vertex"
        try:
            import google.auth  # type: ignore
            from google.auth.transport.requests import (
                Request as GoogleAuthRequest,  # type: ignore
            )
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ImportError(
                "Gemini provider requires google-auth. Install with `poetry install --with dev,llm`."
            ) from exc

        credentials, default_project = google.auth.default(scopes=_GEMINI_SCOPES)
        if not self.project:
            self.project = default_project
        if not self.project:
            raise RuntimeError(
                "Gemini provider requires VERTEX_PROJECT or GOOGLE_PROJECT_ID when GOOGLE_API_KEY is unset."
            )
        self._credentials = credentials
        self._google_request_factory = GoogleAuthRequest

        root = base_url or os.environ.get("VERTEX_ENDPOINT")
        if root:
            root = root.rstrip("/")
        else:
            root = f"https://{self.location}-aiplatform.googleapis.com"

        self._endpoint_root = root
        self._endpoint = (
            f"{root}/v1/projects/{self.project}/locations/{self.location}/publishers/"
            f"{self.publisher}/models/{self.model}:generateContent"
        )
        self._models_endpoint = (
            f"{root}/v1/projects/{self.project}/locations/{self.location}/publishers/"
            f"{self.publisher}/models"
        )

    def _get_session(self):  # pragma: no cover - trivial getter
        if self._session is None:
            try:
                import requests  # type: ignore
                from requests.adapters import HTTPAdapter  # type: ignore
            except ImportError:  # pragma: no cover - optional dependency missing
                return None
            s = requests.Session()
            adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
            s.mount("https://", adapter)
            s.mount("http://", adapter)
            self._session = s
        return self._session

    def _build_payload(
        self, system_prompt: str, user_prompt: str, images: list[str] | None
    ) -> dict[str, Any]:
        parts: list[dict[str, Any]] = [{"text": user_prompt}]
        for img in images or []:
            parts.append(
                {
                    "inlineData": {
                        "mimeType": "image/png",
                        "data": img,
                    }
                }
            )
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": parts}],
            "system_instruction": {
                "parts": [{"text": system_prompt}],
            },
        }
        return payload

    def _auth_headers(self) -> dict[str, str]:
        if self._mode == "api_key":
            return {}
        if not self._credentials or not self._google_request_factory:
            raise RuntimeError("Vertex credentials unavailable for Gemini provider.")
        if not self._credentials.valid:
            request = self._google_request_factory()
            self._credentials.refresh(request)
        token = getattr(self._credentials, "token", None)
        if not token:
            raise RuntimeError(
                "Failed to obtain Google auth token for Gemini provider."
            )
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        try:
            candidates = data.get("candidates") or []
            for cand in candidates:
                parts = (cand.get("content") or {}).get("parts") or cand.get("parts")
                if not parts:
                    continue
                texts = [
                    p.get("text") for p in parts if isinstance(p, dict) and "text" in p
                ]
                if texts:
                    return " ".join(
                        t.strip() for t in texts if isinstance(t, str)
                    ).strip()
        except Exception:
            pass
        return ""

    def generate(
        self, system_prompt: str, user_prompt: str, images: list[str] | None = None
    ) -> str:
        import json
        from json import JSONDecodeError

        payload = self._build_payload(system_prompt, user_prompt, images)
        try:
            headers = {"Content-Type": "application/json"}
            headers.update(self._auth_headers())
            url = self._endpoint
            if self.api_key:
                url = f"{url}?key={self.api_key}"
            sess = self._get_session()
            if sess is None:
                import requests  # type: ignore

                resp = requests.post(
                    url, data=json.dumps(payload), headers=headers, timeout=60
                )
            else:
                resp = sess.post(
                    url, data=json.dumps(payload), headers=headers, timeout=60
                )
            resp.raise_for_status()
            data = resp.json()
            text = self._extract_text(data)
            if text:
                return text
            return "# Gemini error: empty response\n" + _get_mock_singleton().generate(
                system_prompt, user_prompt, images
            )
        except (
            ImportError,
            JSONDecodeError,
            KeyError,
            TypeError,
            RequestException,
            HTTPError,
            Exception,
        ) as _:
            hint_text = ""
            if _env_bool("LLM_ERROR_HINTS", False):
                hints = [
                    "Ensure GOOGLE_API_KEY is set for Generative Language API usage "
                    "or VERTEX_PROJECT/GOOGLE_APPLICATION_CREDENTIALS for Vertex AI.",
                    "Install google-auth (poetry install --with llm) for Vertex-managed access.",
                ]
                hint_text = "\n# " + "\n# ".join(hints)
            return (
                f"# Gemini error: fallback response used{hint_text}\n"
                + _get_mock_singleton().generate(system_prompt, user_prompt, images)
            )

    def test_connection(self) -> tuple[bool, str]:
        try:
            headers = {}
            url = self._models_endpoint
            if self.api_key:
                url = f"{url}?key={self.api_key}"
            else:
                headers.update(self._auth_headers())
            sess = self._get_session()
            if sess is None:
                import requests  # type: ignore

                resp = requests.get(url, headers=headers, timeout=10)
            else:
                resp = sess.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            return True, f"✅ Connected to Gemini ({self.model})"
        except Exception:
            hint = ""
            if _env_bool("LLM_ERROR_HINTS", False):
                hint = (
                    "\n# Provide GOOGLE_API_KEY for REST access or configure Vertex "
                    "project/location credentials."
                )
            return False, f"❌ Failed to reach Gemini endpoint.{hint}"


class MockClient(LLMClient):
    name = "mock"

    def __init__(self) -> None:
        # Ensure dataclass field 'name' is initialized correctly
        super().__init__(name=self.name, model=None)

    def generate(
        self, system_prompt: str, user_prompt: str, images: list[str] | None = None
    ) -> str:
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
