Zyra Documentation
========================

Welcome to the Zyra documentation.

Featured Presentation
---------------------

.. raw:: html

   <div style="position:relative;padding-top:56.25%;margin-bottom:1rem;border:0;">
     <iframe src="https://docs.google.com/presentation/d/e/2PACX-1vQkyPFLXOviuJfWFoesFn4UbL08OQ0dg7ydWJlpVghsrrXc9_s4WE1qhGxT4Br1Vx5wVjd-yZCrlzaR/pubembed?start=false&loop=true&delayms=30000"
             title="Zyra Overview Slides"
             style="position:absolute;top:0;left:0;width:100%;height:100%;border:0;"
             allowfullscreen="true"
             mozallowfullscreen="true"
             webkitallowfullscreen="true"></iframe>
   </div>

.. note::
   Having trouble viewing the embed? Open the slides directly:
   https://docs.google.com/presentation/d/e/2PACX-1vQkyPFLXOviuJfWFoesFn4UbL08OQ0dg7ydWJlpVghsrrXc9_s4WE1qhGxT4Br1Vx5wVjd-yZCrlzaR/pub?start=false&loop=true&delayms=30000

Contents
--------

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/modules

.. toctree::
   :maxdepth: 2
   :caption: Packages

   api/zyra.visualization
   api/zyra.processing
   api/zyra.connectors
   api/zyra.utils
   api/zyra.api
   api/zyra.assets
   api/zyra.cli
   api/zyra.transform

.. toctree::
   :maxdepth: 1
   :caption: Module READMEs

   ../../src/zyra/README
   ../../src/zyra/connectors/ingest/README
   ../../src/zyra/connectors/egress/README
   ../../src/zyra/connectors/discovery/README
   ../../src/zyra/processing/README
   ../../src/zyra/api/README
   ../../src/zyra/api/mcp_tools/README
   ../../src/zyra/visualization/README
   ../../src/zyra/transform/README

.. toctree::
   :maxdepth: 2
   :caption: Guides

   discovery
   openapi
   stages_overview
   domain_apis
   mcp

.. toctree::
   :maxdepth: 2
   :caption: Project Notes
   :glob:

   notes/*

.. toctree::
   :maxdepth: 2
   :caption: Wiki
   :glob:

   wiki/*
   !wiki/_Footer

.. toctree::
   :maxdepth: 1
   :caption: Contributing

   contributing/wiki-sync

External Wiki
-------------

For human-authored guidance, design notes, and usage guides, see the project wiki:

- Online: https://github.com/NOAA-GSL/zyra/wiki
- Synced copy is included in this documentation under the "Wiki" section.
