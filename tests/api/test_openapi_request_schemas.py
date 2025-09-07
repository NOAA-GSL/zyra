from __future__ import annotations

from zyra.api.server import app


def test_openapi_visualize_request_discriminator() -> None:
    spec = app.openapi()
    v = spec["paths"]["/visualize"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    # Expect oneOf with discriminator on 'tool'
    assert "oneOf" in v and isinstance(v["oneOf"], list) and len(v["oneOf"]) >= 3
    disc = v.get("discriminator") or {}
    assert disc.get("propertyName") == "tool"


def test_openapi_process_request_oneof() -> None:
    spec = app.openapi()
    v = spec["paths"]["/process"]["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ]
    assert "oneOf" in v and isinstance(v["oneOf"], list)
