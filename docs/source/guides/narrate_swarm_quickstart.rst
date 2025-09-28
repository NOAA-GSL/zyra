Narrate Swarm Quickstart
========================

This guide shows copy‑pasteable CLI examples for the narration swarm and links to the Narrative Pack schema/model.

Presets and One‑Liners
----------------------

- List presets:

  .. code-block:: bash

     poetry run zyra narrate swarm -P help

- Run basic preset (mock provider) and write pack to stdout:

  .. code-block:: bash

     poetry run zyra narrate swarm -P kids_policy_basic --provider mock --pack -

- Run preset with a custom critic rubric (YAML list of bullets):

  .. code-block:: bash

     poetry run zyra narrate swarm -P kids_policy_basic --rubric path/to/rubric.yaml --pack -

- Scientific preset with model override:

  .. code-block:: bash

     poetry run zyra narrate swarm -P scientific_rigorous --provider mock --model mistral --pack /tmp/pack.yaml

- Accessibility preset (adds critic/editor loop):

  .. code-block:: bash

     poetry run zyra narrate swarm -P accessibility_default --provider mock --pack -

- Scientific lite (summary + context only):

  .. code-block:: bash

     poetry run zyra narrate swarm -P scientific_lite --provider mock --pack -

- Kids + Policy dual (summary → critic → editor for two audiences):

  .. code-block:: bash

     poetry run zyra narrate swarm -P kids_policy_dual --provider mock --pack -

- YAML‑first config combined with preset base:

  .. code-block:: bash

     poetry run zyra narrate swarm --swarm-config swarm.yaml -P kids_policy_basic --pack /tmp/pack.yaml

Notes
-----

- Use ``-P ?`` (or ``--preset ?``) to list presets. Unknown preset suggestions and validation errors exit with code 2.
- When audiences are provided, an internal ``audience_adapter`` agent emits ``<aud>_version`` outputs.
- The Narrative Pack includes provenance entries per agent run with fields: ``agent``, ``model``, ``started`` (RFC3339), ``prompt_ref``, and ``duration_ms``.
- CLI flags override both preset values and ``--swarm-config`` settings; overrides are echoed to stderr so runs remain reproducible.
- ``--strict-grounding`` flips the exit status to 1 when the critic reports ``[UNGROUNDED]`` content, and ``--critic-structured`` wraps critic output as ``{"notes": "..."}`` to simplify downstream parsing.
- Supply agent dictionaries in presets/YAML to override prompts, outputs, or dependencies. Prompts accept inline text, filesystem paths, or packaged asset references (``zyra.assets/...``). Invalid prompt/rubric paths halt with exit code 2.

Schema and Programmatic Validation
----------------------------------

Pydantic model: ``zyra.narrate.schemas.NarrativePack``

- Validate dicts or JSON strings:

  .. code-block:: python

     from zyra.narrate.schemas import NarrativePack

     pack = NarrativePack.model_validate(data_dict)
     # or
     pack = NarrativePack.model_validate_json(json_str)

- Export JSON Schema:

  .. code-block:: python

     import json
     from zyra.narrate.schemas import NarrativePack

     with open("narrative_pack.schema.json", "w", encoding="utf-8") as f:
         json.dump(NarrativePack.model_json_schema(), f, indent=2)

Exit Codes
----------

- 0: success (pack written; non‑critical failures allowed)
- 1: critical path failed (summary/critic/editor); pack still written if you pass ``--pack``
- 2: config/validation errors (bad inputs; messages include failing field paths)

Downloadable JSON Schema
------------------------

- A published copy of the Narrative Pack JSON Schema is included with the docs: :download:`narrative_pack.schema.json <../_static/narrative_pack.schema.json>`
