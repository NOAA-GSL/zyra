OpenAPI-Aided Help and Validation
=================================

Overview
--------

Zyra can use an API's OpenAPI 3.0 specification to provide request hints and
perform lightweight validation before issuing requests.

CLI (``zyra acquire api``)
--------------------------

- ``--openapi-help``
  Fetches the service's OpenAPI spec and prints a summary for the resolved
  operation (required/optional query and header parameters, requestBody content types,
  and best-effort response content types). This does not send the request.

- ``--openapi-validate``
  Validates the provided ``--header``, ``--params``, and ``--data`` (when
  present) against the spec. Prints issues to stderr.

- ``--openapi-strict``
  With ``--openapi-validate``, exits non-zero when issues are found.

API (``POST /v1/acquire/api``)
------------------------------

- ``openapi_validate``: boolean. When true, validates the request before issuing it.
  Returns HTTP 400 with ``{"errors": [...]}`` on issues.
- ``openapi_strict``: boolean. Defaults to true; controls whether issues are fatal.

What is validated
-----------------

- Required query and header parameters.
- Required ``requestBody`` presence.
- ``requestBody`` Content-Type compatibility.
- Simple parameter checks when values are present:
  - ``enum`` membership
  - Basic ``type`` checks (string/integer/number/boolean)
- Optional JSON Schema validation for ``application/json`` requestBody when
  ``jsonschema`` is installed in the environment.

Notes
-----

- Zyra uses a best-effort resolver for operations, matching the longest
  templated path (e.g., ``/v1/items/{id}``) with segment-aware scoring.
- When the OpenAPI spec is unavailable, help and validation are skipped.

Examples
--------

Example OpenAPI snippet
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: json

   {
     "openapi": "3.0.0",
     "paths": {
       "/v1/items": {
         "get": {
           "parameters": [
             {"in": "query", "name": "q", "required": true, "schema": {"type": "string"}},
             {"in": "query", "name": "limit", "schema": {"type": "integer"}}
           ],
           "responses": {
             "200": {"content": {"application/json": {}}}
           }
         }
       },
       "/v1/items/{id}": {
         "get": {
           "parameters": [
             {"in": "path", "name": "id", "required": true, "schema": {"type": "string"}}
           ],
           "responses": {
             "200": {"content": {"application/json": {}}}
           }
         }
       }
     }
   }

CLI
~~~

.. code-block:: bash

   # Print required params for GET /v1/items
   zyra acquire api \
     --url https://api.example/v1/items \
     --openapi-help

   # Validate current flags (warn-only)
   zyra acquire api \
     --url https://api.example/v1/items \
     --params q=wind \
     --openapi-validate

   # Validate strictly (exit non-zero on issues)
   zyra acquire api \
     --url https://api.example/v1/items \
     --openapi-validate --openapi-strict

HTTP
~~~~

.. code-block:: bash

   # Validate via API (400 on issues)
   curl -sS -X POST http://localhost:8000/v1/acquire/api \
     -H 'Content-Type: application/json' \
     -d '{"url": "https://api.example/v1/items", "openapi_validate": true}'

