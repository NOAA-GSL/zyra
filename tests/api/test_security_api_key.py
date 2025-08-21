from __future__ import annotations

import pytest
from fastapi import HTTPException
from zyra.api.security import require_api_key


@pytest.mark.anyio
async def test_require_api_key_disabled_when_env_unset(monkeypatch) -> None:
    monkeypatch.delenv("DATAVIZHUB_API_KEY", raising=False)
    assert await require_api_key(None) is True
    assert await require_api_key("anything") is True


@pytest.mark.anyio
async def test_require_api_key_enforced(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "secret")
    # Missing
    with pytest.raises(HTTPException) as ei:
        await require_api_key(None)
    assert ei.value.status_code == 401
    # Wrong
    with pytest.raises(HTTPException):
        await require_api_key("wrong")
    # Correct
    assert await require_api_key("secret") is True
