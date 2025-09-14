# SPDX-License-Identifier: Apache-2.0
from zyra.connectors.openapi import validate as ov


def _spec_template_and_literal():
    return {
        "openapi": "3.0.0",
        "paths": {
            "/v1/items": {"get": {"responses": {"200": {}}}},
            "/v1/items/{id}": {"get": {"responses": {"200": {}}}},
            "/v1/items/search": {"get": {"responses": {"200": {}}}},
        },
    }


def test_find_operation_prefers_template_for_id_path():
    spec = _spec_template_and_literal()
    op = ov.find_operation(spec, "https://api.example/v1/items/123", "GET")
    assert op is not None
    assert op.path == "/v1/items/{id}"


def test_find_operation_prefers_literal_when_exact():
    spec = _spec_template_and_literal()
    op = ov.find_operation(spec, "https://api.example/v1/items/search", "GET")
    assert op is not None
    assert op.path == "/v1/items/search"
