# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest

from zyra.swarm.guardrails import GuardrailsAdapter


def _make_dummy_agent(agent_id: str):
    class _Spec:
        id = agent_id

    class _Dummy:
        spec = _Spec()

    return _Dummy()


@pytest.mark.guardrails
def test_guardrails_adapter_validates(tmp_path):
    pytest.importorskip("guardrails")
    schema_path = tmp_path / "test_schema.rail"
    schema_path.write_text(
        """
<rail version="0.1">

<output>
    <string name="summary" description="summary text" />
</output>

<prompt>
    You must return a summary string.
    {{#block hidden=True}}
    {{input}}
    {{/block}}
</prompt>

</rail>
        """,
        encoding="utf-8",
    )
    adapter = GuardrailsAdapter(str(schema_path))
    agent = _make_dummy_agent("narrate")
    outputs = {"summary": '"Short summary"'}
    validated = adapter.validate(agent, outputs)
    assert validated["summary"] == "Short summary"
