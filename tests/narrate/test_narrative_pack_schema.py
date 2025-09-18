# SPDX-License-Identifier: Apache-2.0
import pytest

from zyra.narrate.schemas import NarrativePack


def test_narrative_pack_valid_minimal():
    data = {
        "version": 0,
        "inputs": {"audiences": ["kids"], "style": "journalistic"},
        "models": {"provider": "mock", "model": "placeholder"},
        "status": {"completed": True, "failed_agents": []},
        "outputs": {"summary": "...", "kids_version": "..."},
        "reviews": {},
        "errors": [],
        "provenance": [],
    }
    pack = NarrativePack.model_validate(data)
    assert pack.status.completed is True
    assert pack.version == 0


def test_narrative_pack_critical_path_invariant():
    data = {
        "version": 0,
        "inputs": {},
        "models": {},
        "status": {"completed": False, "failed_agents": []},
        "outputs": {},
        "errors": [],
        "provenance": [],
    }
    with pytest.raises(Exception) as ei:
        NarrativePack.model_validate(data)
    msg = str(ei.value)
    assert "critical" in msg.lower()
