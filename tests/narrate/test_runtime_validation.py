# SPDX-License-Identifier: Apache-2.0
from zyra.narrate import _runtime_validate_pack_dict


def test_runtime_validation_rfc3339_error():
    bad = {
        "version": 0,
        "status": {"completed": True, "failed_agents": []},
        "outputs": {},
        "provenance": [{"agent": "summary", "started": "2025/09/16 12:00:00"}],
    }
    try:
        _runtime_validate_pack_dict(bad)
        assert False, "expected ValueError"
    except ValueError as ve:
        assert "provenance[0].started" in str(ve)
