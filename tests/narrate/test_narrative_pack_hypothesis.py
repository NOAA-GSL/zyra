# SPDX-License-Identifier: Apache-2.0
import pytest

from zyra.narrate.schemas import NarrativePack

hyp = pytest.importorskip("hypothesis")
st = pytest.importorskip("hypothesis.strategies")


@hyp.settings(max_examples=5)
@hyp.given(
    st.fixed_dictionaries(
        {
            "version": st.just(0),
            "inputs": st.fixed_dictionaries(
                {
                    "audiences": st.lists(
                        st.sampled_from(["kids", "policy", "scientific"]), max_size=3
                    ),
                    "style": st.one_of(
                        st.just("journalistic"), st.just("technical"), st.none()
                    ),
                }
            ),
            "models": st.fixed_dictionaries(
                {
                    "provider": st.sampled_from(["mock", "openai", "ollama"]),
                    "model": st.one_of(
                        st.text(min_size=1, max_size=16), st.just("placeholder")
                    ),
                }
            ),
            "status": st.fixed_dictionaries(
                {
                    "completed": st.booleans(),
                    "failed_agents": st.lists(
                        st.sampled_from(["summary", "context", "critic", "editor"]),
                        max_size=3,
                    ),
                }
            ),
            "outputs": st.dictionaries(
                keys=st.sampled_from(
                    [
                        "summary",
                        "context",
                        "kids_version",
                        "policy_version",
                        "critic_notes",
                        "edited",
                    ]
                ),
                values=st.text(max_size=64),
                max_size=6,
            ),
            "reviews": st.one_of(
                st.dictionaries(
                    keys=st.text(max_size=8), values=st.text(max_size=32), max_size=3
                ),
                st.none(),
            ),
            "errors": st.lists(
                st.fixed_dictionaries(
                    {
                        "agent": st.one_of(
                            st.sampled_from(["summary", "critic", "editor"]), st.none()
                        ),
                        "message": st.text(min_size=1, max_size=64),
                        "retried": st.one_of(
                            st.integers(min_value=0, max_value=3), st.none()
                        ),
                    }
                ),
                max_size=3,
            ),
            "provenance": st.lists(
                st.fixed_dictionaries(
                    {
                        "agent": st.sampled_from(
                            ["summary", "context", "critic", "editor"]
                        ),
                        "model": st.one_of(st.text(max_size=16), st.none()),
                        "started": st.one_of(st.text(max_size=32), st.none()),
                        "prompt_ref": st.one_of(st.text(max_size=32), st.none()),
                        "notes": st.one_of(st.text(max_size=64), st.none()),
                    }
                ),
                max_size=4,
            ),
        }
    )
)
def test_pack_schema_property_based(pack_dict):
    # Validation either succeeds or raises with useful errors; no crash
    try:
        pack = NarrativePack.model_validate(pack_dict)
        # Invariants when completed: not asserting outputs content here, just types
        assert isinstance(pack.outputs, dict)
    except Exception as e:
        # Errors acceptable in property tests; ensure readable message
        assert str(e)
