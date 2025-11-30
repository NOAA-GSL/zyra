# SPDX-License-Identifier: Apache-2.0
def test_manifest_contains_core_groups():
    """Smoke-test the capabilities manifest builder for core groups.

    Narrow scope: Only asserts that at least one command path for each core
    group exists. This avoids coupling to optional/extras or specific
    subcommand names while still catching regressions.
    """
    from zyra.wizard.manifest import build_manifest

    mf = build_manifest()
    keys = list(mf.keys())

    has_acquire = any(k.startswith("acquire ") for k in keys)
    has_visualize = any(k.startswith("visualize ") for k in keys)

    assert has_acquire and has_visualize, (
        "manifest missing expected core commands: "
        f"acquire={has_acquire}, visualize={has_visualize}"
    )


def test_manifest_includes_impl_and_returns_hints():
    """Selected entries should carry impl metadata and return hints."""
    from zyra.wizard.manifest import build_manifest

    mf = build_manifest()
    sample = mf.get("acquire http") or {}
    assert isinstance(sample.get("impl"), dict)
    assert sample.get("impl", {}).get("module")
    assert sample.get("impl", {}).get("callable")
    assert isinstance(sample.get("returns"), str)
