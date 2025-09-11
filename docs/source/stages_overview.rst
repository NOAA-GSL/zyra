Stages Overview
===============

This page summarizes Zyra's eight canonical stages, their common aliases, and
the current argument shapes for the new skeleton stages. For a full, discoverable
schema of every command and option, see the CLI matrix (``GET /cli/commands``) or
the generated capabilities manifest.

Import (Acquire)
----------------

- Aliases: ``import``, ``acquire``
- Purpose: data ingestion (HTTP, S3, FTP, Vimeo; search is also nested here)
- Examples: ``acquire http``, ``acquire s3``, ``acquire ftp``

CLI examples::

  # HTTP → file
  zyra import http https://example.com/data.bin -o /tmp/data.bin

  # S3 list+filter
  zyra acquire s3 --url s3://bucket/prefix/ --list --pattern '\\.grib2$'

API example (REST)::

  curl -sS -H 'Content-Type: application/json' -H "X-API-Key: $API_KEY" \\
    -d '{"tool":"http","args":{"url":"https://example.com/file.bin","output":"/tmp/file.bin"}}' \\
    http://localhost:8000/v1/acquire

Process
-------

- Purpose: data + metadata transformations
  - Process data → arrays, NetCDF, GRIB2, histograms
  - Process meta → dataset.json enrichments
- Examples: ``process convert-format``, ``process decode-grib2``,
  ``process metadata`` (from the former ``transform`` group)

CLI examples::

  # Convert GRIB2 → NetCDF (stdout)
  zyra process convert-format https://example.com/sample.grib2 netcdf --stdout > out.nc

  # Compute frames metadata (from former transform)
  zyra process metadata --frames /data/frames --output frames_meta.json

API example (REST)::

  curl -sS -H 'Content-Type: application/json' -H "X-API-Key: $API_KEY" \\
    -d '{"tool":"convert-format","args":{"file_or_url":"https://example.com/sample.grib2","format":"netcdf","stdout":true}}' \\
    http://localhost:8000/v1/process

Simulate
--------

- Purpose: uncertainty modeling, ensembles, scenario sampling
- Command: ``simulate sample``
- Args (current):

  - ``seed`` (int, optional): Random seed
  - ``trials`` (int, optional): Number of trials

CLI example::

  zyra simulate sample --seed 42 --trials 10

API example (REST)::

  curl -sS -H 'Content-Type: application/json' -H "X-API-Key: $API_KEY" \\
    -d '{"tool":"sample","args":{"seed":42,"trials":10}}' \\
    http://localhost:8000/v1/simulate

Decide (Optimize)
-----------------

- Aliases: ``decide``, ``optimize``
- Purpose: decision-making, optimization
- Command: ``decide optimize``
- Args (current):

  - ``strategy`` (str, optional): e.g., ``greedy``, ``random``, ``grid``

CLI example::

  zyra decide optimize --strategy greedy

API example (REST)::

  curl -sS -H 'Content-Type: application/json' -H "X-API-Key: $API_KEY" \\
    -d '{"tool":"optimize","args":{"strategy":"greedy"}}' \\
    http://localhost:8000/v1/decide

Visualize (Render)
------------------

- Aliases: ``visualize``, ``render``
- Purpose: plots, maps, animations, dashboards
- Examples: ``visualize heatmap``, ``visualize contour``, ``visualize animate``,
  ``visualize compose-video``, ``visualize interactive``

CLI examples::

  # Heatmap to PNG
  zyra render heatmap --input samples/demo.npy --output /tmp/heatmap.png

  # Compose frames to MP4
  zyra visualize compose-video --frames /data/frames -o /tmp/out.mp4

API example (REST)::

  curl -sS -H 'Content-Type: application/json' -H "X-API-Key: $API_KEY" \\
    -d '{"tool":"heatmap","args":{"input":"samples/demo.npy","output":"/tmp/heatmap.png"}}' \\
    http://localhost:8000/v1/visualize

Narrate
-------

- Purpose: AI storytelling—summaries, captions, storyboards (before Verify)
- Command: ``narrate describe``
- Args (current):

  - ``topic`` (str, optional): Topic to narrate

CLI example::

  zyra narrate describe --topic "monthly summary"

API example (REST)::

  curl -sS -H 'Content-Type: application/json' -H "X-API-Key: $API_KEY" \\
    -d '{"tool":"describe","args":{"topic":"monthly summary"}}' \\
    http://localhost:8000/v1/narrate

Verify
------

- Purpose: metrics (RMSE, CRPS, SAL), skill scores; AI validation
- Command: ``verify evaluate``
- Args (current):

  - ``metric`` (str, optional): Metric name

CLI example::

  zyra verify evaluate --metric RMSE

API example (REST)::

  curl -sS -H 'Content-Type: application/json' -H "X-API-Key: $API_KEY" \\
    -d '{"tool":"evaluate","args":{"metric":"RMSE"}}' \\
    http://localhost:8000/v1/verify

Export (Disseminate)
--------------------

- Aliases: ``export``, ``disseminate`` (legacy: ``decimate``)
- Purpose: publish/share and enrich—Local/S3/FTP/Vimeo, provenance metadata
- Examples: ``export local``, ``export s3``, ``disseminate post``

CLI examples::

  # Write stdin to a file
  echo OK | zyra export local - /tmp/out.txt

  # Upload stdin to S3
  cat out.png | zyra export s3 --read-stdin --url s3://bucket/products/out.png

API example (REST)::

  curl -sS -H 'Content-Type: application/json' -H "X-API-Key: $API_KEY" \\
    -d '{"tool":"post","args":{"input":"/path/to/file.bin","url":"https://example.com/ingest","content_type":"application/octet-stream"}}' \\
    http://localhost:8000/v1/disseminate

Notes
-----

- The CLI and API accept stage aliases (e.g., ``render``→``visualize``,
  ``disseminate``/``export``→``decimate``). The docs prefer the new names.
- The process group includes all former ``transform`` commands for convenience;
  ``transform`` remains as an alias.

See also
--------

- :doc:`domain_apis` — REST domain endpoints with request/response shapes
- CLI manifest JSON: ``GET /cli/commands`` (full stage/command/option matrix)

Deprecation notes
-----------------

- ``decimate``: legacy name for egress. Prefer ``export`` or ``disseminate``.
- ``transform``: legacy group kept as an alias; commands are available under
  ``process``.
