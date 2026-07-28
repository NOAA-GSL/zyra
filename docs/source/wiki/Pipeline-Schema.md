The machine-readable contract for files passed to `zyra run`. This page documents the file format and publishes a JSON Schema (draft 2020-12) you can wire into an editor, CI, or a downstream validator.

Generated against Zyra **0.1.54**. Companion page: [CLI Args Reference](CLI-Args-Reference) for per-command `args` keys. Narrative walkthroughs live in [Pipeline Patterns](Pipeline-Patterns) and [Workflow Stages](Workflow-Stages).

- Schema file: `schemas/zyra-pipeline.schema.json`
- `$id`: `https://raw.githubusercontent.com/NOAA-GSL/zyra/main/schemas/zyra-pipeline.schema.json`

---

## Two file shapes

`zyra run <config>` accepts either shape, in YAML or JSON. It decides which by looking for `jobs:` or `on:` at the top level; everything else is treated as a pipeline.

| Shape | Marker | Use it for |
| --- | --- | --- |
| **Pipeline** | `stages:` | A single linear chain of stages, piped stdout → stdin. |
| **Workflow** | `jobs:` and/or `on:` | Named jobs with `needs:` dependencies and cron triggers. |

YAML is idiomatic; JSON is accepted everywhere (and is what TerraViz stores in `pipeline_json`). PyYAML is optional — without it, `.yaml`/`.yml` files raise a friendly error and only JSON loads.

---

## Pipeline shape

```yaml
name: HRRR surface temperature      # optional label, unused by the runner
stages:
  - stage: acquire
    command: http
    args:
      url: "https://example.gov/hrrr.t00z.wrfsfcf00.grib2"
      output: "-"

  - stage: process
    command: convert-format
    id: to-netcdf                   # optional; echoed by --print-argv-format=json
    args:
      file_or_url: "-"
      format: netcdf
      stdout: true

  - stage: export
    command: local
    args:
      path: /work/output/dataset.nc
      input: "-"
```

### Top-level keys

| Key | Type | Required | Notes |
| --- | --- | --- | --- |
| `stages` | array | **yes** | Must be a non-empty list of mappings. |
| `name` | string | no | Label only. Unused by the runner. |
| *(other)* | any | no | Ignored. The runner reads only `stages`. |

### Stage object

| Key | Type | Required | Notes |
| --- | --- | --- | --- |
| `stage` | string | **yes** | Stage name or alias (table below). |
| `command` | string | **yes** | Subcommand within the stage. |
| `args` | mapping | no | Must be a mapping when present. |
| `id` | string | no | Label surfaced in `--print-argv-format=json` output. |

### Stage aliases

Normalized by `zyra.pipeline_runner._stage_group_alias`. Aliases are interchangeable — pick one and be consistent.

| Canonical | Accepted aliases |
| --- | --- |
| `acquire` | `acquisition`, `import`, `ingest` |
| `process` | `processing`, `transform` |
| `simulate` | — |
| `decide` | `optimize` |
| `visualize` | `visualization`, `render` |
| `narrate` | — |
| `verify` | — |
| `decimate` | `decimation`, `export`, `disseminate` |

> `decimate` is still the internal canonical name for egress, but `export` / `disseminate` are the preferred user-facing terms.

---

## How `args` becomes a command line

`_build_argv_for_stage` turns each stage into an argv vector. The rules, in order:

1. **Convenience rewrites** happen first:
   - `file_pattern` → `pattern` (when `pattern` is not already set)
   - `since_period: P1Y` → computes `since` via `DateManager.get_date_range_iso`
   - `period: 1Y` / `6M` / `7D` / `24H` → computes `since` via `DateManager.get_date_range`
   - `backend:` on a bare `stage: acquire` / `stage: export` selects the subcommand — `command: acquire` + `args.backend: http` is the same as `command: http`
2. **Positionals** are consumed by name, in order, for the eight commands the runner knows about (table below), and removed from `args`.
3. **Everything left becomes a flag**, with `_` → `-`:
   - `output_dir: /tmp` → `--output-dir /tmp`
   - `stdout: true` → `--stdout`; `stdout: false` → *omitted entirely*
   - `foo: null` → omitted
   - `inputs: [a, b]` → `--inputs a b`; `extent: [-180, 180, -90, 90]` → `--extent -180 180 -90 90`; an empty list is skipped
   - Nested mappings are **not** supported — they stringify into garbage.

Because `_` and `-` both normalize to `-`, `output_dir` and `output-dir` are equivalent. Underscores are the convention in the samples.

### Positional mapping

| Stage | Command | Positional args, in order |
| --- | --- | --- |
| `acquire` | `http` | `url` |
| `acquire` | `ftp` | `path` |
| `process` | `decode-grib2` | `file_or_url` |
| `process` | `convert-format` | `file_or_url`, `format` |
| `process` | `extract-variable` | `file_or_url`, `pattern` |
| `decimate` | `local` | `path` |
| `decimate` | `ftp` | `path` |
| `decimate` | `post` | `url` |

**Any command not in this table cannot receive a positional from a pipeline stage.** Six commands are affected — see [Known gaps](#known-gaps).

### Chaining

`"-"` means stdin/stdout. The runner streams each stage's stdout into the next stage's stdin in memory; it does not use temp files. Seed the first stage from a file with `ZYRA_DEFAULT_STDIN` when nothing is piped in.

### Environment interpolation

`$VAR`, `${VAR}`, and `${VAR:-default}` are expanded recursively across the whole config, after `--set` overrides are applied. `--strict-env` (or `ZYRA_STRICT_ENV=1`) fails the run when a plain `${VAR}` has no value; the `${VAR:-default}` form never fails.

---

## Workflow shape

```yaml
name: nightly
"on":
  schedule:
    - cron: "0 6 * * *"
jobs:
  fetch:
    steps:
      - "acquire http https://example.gov/data.grib2 --output /work/in.grib2"
  render:
    needs: [fetch]
    steps:
      - stage: visualize
        command: heatmap
        args:
          input: /work/in.grib2
          output: /work/out.png
```

| Key | Type | Notes |
| --- | --- | --- |
| `jobs` | mapping | Required. Job name → job object. Ordered by `needs` (Kahn's algorithm); cycles and unknown names are hard errors. |
| `on.schedule[]` | array | `{cron: "..."}` mappings or bare cron strings. Drives `--watch` and `--export-cron`. |
| `env` | mapping | Exported into the process environment before jobs run, after `${VAR}` expansion. A value that still looks like an unresolved placeholder is skipped rather than exported. |
| `jobs.<id>.steps` | array | Required. Steps pipe stdout → stdin within a job. |
| `jobs.<id>.needs` | string or array | Jobs that must succeed first. |

A step may be any of three forms:

- a shell-style string, split with `shlex`: `"process convert-format - netcdf --stdout"`
- `{cmd: "process convert-format - netcdf --stdout"}`
- a full stage mapping — `{stage:, command:, args:}` — expanded by the same arg builder as pipelines

> **YAML gotcha:** PyYAML 1.1 semantics parse a bare `on:` key as boolean `true`. Zyra reads both `doc["on"]` and `doc[True]`, but generic JSON Schema validators only see the boolean. **Quote it** — `"on":` — for portable validation.

---

## Runner flags

| Flag | Effect |
| --- | --- |
| `--set KEY=VALUE` | Override an arg. `N.key=` targets stage N (1-based), `stage.key=` targets by stage alias, bare `key=` applies wherever the key already exists. Repeatable. |
| `--dry-run` | Print argv per stage without executing. |
| `--print-argv` / `--print-argv-format {text,json}` | Print argv and run. JSON form includes stage index, normalized name, and `id`. |
| `--start N` / `--end N` | Run a 1-based stage slice. |
| `--only ALIAS` | Run only stages matching a stage alias. |
| `--continue-on-error` | Keep going after a failed stage. |
| `--trace` | Echo `+ <command>` and cwd per stage. |
| `--strict-env` | Fail on unset `${VAR}`. |
| `--max-workers N` | Workflow shape only: run up to N jobs in parallel. |
| `--watch` / `--watch-interval` / `--watch-count` / `--state-file` / `--run-on-first` | Workflow shape only: evaluate cron triggers and run when due. |
| `--export-cron` | Workflow shape only: print crontab lines. |
| `--log-file` / `--log-dir` / `--log-file-mode {append,overwrite}` | Log destination. |

`--dry-run --print-argv-format=json` is the cheapest way to see exactly what a config expands to before running it.

---

## Using the schema

**Editor (VS Code + YAML extension)** — in `settings.json`:

```json
{
  "yaml.schemas": {
    "https://raw.githubusercontent.com/NOAA-GSL/zyra/main/schemas/zyra-pipeline.schema.json": [
      "**/pipelines/*.yaml",
      "**/pipelines/*.yml",
      "**/workflows/*.yml"
    ]
  }
}
```

**CI** — with [`check-jsonschema`](https://github.com/python-jsonschema/check-jsonschema):

```bash
pip install check-jsonschema
check-jsonschema --schemafile schemas/zyra-pipeline.schema.json samples/pipelines/*.yaml samples/workflows/*.yml
```

**Python:**

```python
import json, yaml, jsonschema

schema = json.load(open("schemas/zyra-pipeline.schema.json"))
config = yaml.safe_load(open("samples/pipelines/rtvideo_drought.yaml"))
jsonschema.Draft202012Validator(schema).validate(config)
```

### What the schema does and does not check

Checks:

- the file defines either `stages` or `jobs`, and matches that shape (dispatched with `if`/`then` rather than a bare `oneOf`, so errors point at the offending field instead of "not valid under any of the given schemas")
- `stage` is a known stage or alias
- `command` is valid **for that stage** — every stage has its own command enum
- required positional args are present for the eight commands the runner maps
- `args` values are scalars, `null`, or flat arrays — never nested objects
- job `steps` are one of the three accepted forms

Does not check:

- whether individual `args` keys exist for a command (that surface is the [CLI Args Reference](CLI-Args-Reference); the manifest is generated at runtime and not shipped as schema)
- value semantics — a bad regex or an unreachable URL still validates
- `needs` referring to a real job, or cycles — the runner catches both at load

---

## Known gaps

- **Six commands declare a required positional the runner does not map**, so they cannot be used in a pipeline stage at all: `acquire thredds` (`catalog_url`), `acquire vimeo` (`video_id`), `process api-json` (`file_or_url`), `process audio-metadata` (`input`), `process audio-transcode` (`input`), `process video-transcode` (`input`). Passing them as args emits e.g. `--catalog-url`, which argparse rejects.
- **`narrate` commands need `pydantic`.** Without it, `zyra narrate` raises `ModuleNotFoundError` and the two narrate commands vanish from the generated manifest — silently, if you are generating docs.
- **`args` keys are not schema-validated per command.** Closing this means emitting the manifest as JSON Schema at build time.

---

## The schema

Copy into `schemas/zyra-pipeline.schema.json`. Regenerate with `gen_docs.py` (see [CLI Args Reference](CLI-Args-Reference#regenerating)) whenever the stage or command set changes.

<details>
<summary><code>zyra-pipeline.schema.json</code> — generated from Zyra 0.1.54</summary>

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://raw.githubusercontent.com/NOAA-GSL/zyra/main/schemas/zyra-pipeline.schema.json",
  "title": "Zyra run configuration",
  "description": "Validates any file accepted by `zyra run`: a pipeline config (`stages:`) or a workflow config (`jobs:` / `on:`). Generated from Zyra 0.1.54.",
  "x-zyra-version": "0.1.54",
  "type": "object",
  "allOf": [
    {
      "anyOf": [
        {
          "required": [
            "stages"
          ]
        },
        {
          "required": [
            "jobs"
          ]
        }
      ],
      "$comment": "A config must define either 'stages' (pipeline) or 'jobs' (workflow)."
    },
    {
      "if": {
        "required": [
          "stages"
        ]
      },
      "then": {
        "$ref": "#/$defs/pipeline"
      }
    },
    {
      "if": {
        "required": [
          "jobs"
        ]
      },
      "then": {
        "$ref": "#/$defs/workflow"
      }
    }
  ],
  "$defs": {
    "pipeline": {
      "type": "object",
      "title": "Pipeline config",
      "required": [
        "stages"
      ],
      "properties": {
        "name": {
          "type": "string",
          "description": "Human-readable label. Not used by the runner."
        },
        "description": {
          "type": "string"
        },
        "stages": {
          "type": "array",
          "minItems": 1,
          "items": {
            "$ref": "#/$defs/stage"
          }
        }
      },
      "additionalProperties": true
    },
    "stage": {
      "type": "object",
      "title": "Pipeline stage",
      "required": [
        "stage",
        "command"
      ],
      "properties": {
        "stage": {
          "type": "string",
          "enum": [
            "acquire",
            "acquisition",
            "decide",
            "decimate",
            "decimation",
            "disseminate",
            "export",
            "import",
            "ingest",
            "narrate",
            "optimize",
            "process",
            "processing",
            "render",
            "simulate",
            "transform",
            "verify",
            "visualization",
            "visualize"
          ],
          "description": "Stage name or alias; normalized by _stage_group_alias()."
        },
        "command": {
          "type": "string",
          "description": "Subcommand within the stage."
        },
        "id": {
          "type": "string",
          "description": "Optional label echoed by --print-argv-format=json."
        },
        "args": {
          "$ref": "#/$defs/args"
        }
      },
      "additionalProperties": false,
      "allOf": [
        {
          "if": {
            "properties": {
              "stage": {
                "enum": [
                  "acquire",
                  "acquisition",
                  "import",
                  "ingest"
                ]
              }
            },
            "required": [
              "stage"
            ]
          },
          "then": {
            "properties": {
              "command": {
                "enum": [
                  "acquire",
                  "acquisition",
                  "api",
                  "ftp",
                  "http",
                  "import",
                  "ingest",
                  "s3",
                  "thredds",
                  "vimeo"
                ]
              }
            }
          }
        },
        {
          "if": {
            "properties": {
              "stage": {
                "enum": [
                  "process",
                  "processing",
                  "transform"
                ]
              }
            },
            "required": [
              "stage"
            ]
          },
          "then": {
            "properties": {
              "command": {
                "enum": [
                  "api-json",
                  "audio-metadata",
                  "audio-transcode",
                  "convert-format",
                  "decode-grib2",
                  "enrich-datasets",
                  "enrich-metadata",
                  "extract-variable",
                  "metadata",
                  "pad-missing",
                  "process",
                  "processing",
                  "reproject",
                  "scan-frames",
                  "transform",
                  "update-dataset-json",
                  "video-transcode"
                ]
              }
            }
          }
        },
        {
          "if": {
            "properties": {
              "stage": {
                "enum": [
                  "simulate"
                ]
              }
            },
            "required": [
              "stage"
            ]
          },
          "then": {
            "properties": {
              "command": {
                "enum": [
                  "sample",
                  "simulate"
                ]
              }
            }
          }
        },
        {
          "if": {
            "properties": {
              "stage": {
                "enum": [
                  "decide",
                  "optimize"
                ]
              }
            },
            "required": [
              "stage"
            ]
          },
          "then": {
            "properties": {
              "command": {
                "enum": [
                  "decide",
                  "optimize"
                ]
              }
            }
          }
        },
        {
          "if": {
            "properties": {
              "stage": {
                "enum": [
                  "visualize",
                  "visualization",
                  "render"
                ]
              }
            },
            "required": [
              "stage"
            ]
          },
          "then": {
            "properties": {
              "command": {
                "enum": [
                  "animate",
                  "compose-video",
                  "contour",
                  "heatmap",
                  "interactive",
                  "render",
                  "sos",
                  "timeseries",
                  "vector",
                  "visualization",
                  "visualize"
                ]
              }
            }
          }
        },
        {
          "if": {
            "properties": {
              "stage": {
                "enum": [
                  "narrate"
                ]
              }
            },
            "required": [
              "stage"
            ]
          },
          "then": {
            "properties": {
              "command": {
                "enum": [
                  "describe",
                  "narrate",
                  "swarm"
                ]
              }
            }
          }
        },
        {
          "if": {
            "properties": {
              "stage": {
                "enum": [
                  "verify"
                ]
              }
            },
            "required": [
              "stage"
            ]
          },
          "then": {
            "properties": {
              "command": {
                "enum": [
                  "evaluate",
                  "verify"
                ]
              }
            }
          }
        },
        {
          "if": {
            "properties": {
              "stage": {
                "enum": [
                  "decimate",
                  "decimation",
                  "export",
                  "disseminate"
                ]
              }
            },
            "required": [
              "stage"
            ]
          },
          "then": {
            "properties": {
              "command": {
                "enum": [
                  "decimate",
                  "decimation",
                  "disseminate",
                  "export",
                  "ftp",
                  "local",
                  "post",
                  "s3",
                  "vimeo"
                ]
              }
            }
          }
        },
        {
          "if": {
            "properties": {
              "stage": {
                "enum": [
                  "acquire",
                  "acquisition",
                  "import",
                  "ingest"
                ]
              },
              "command": {
                "const": "ftp"
              }
            },
            "required": [
              "stage",
              "command"
            ]
          },
          "then": {
            "properties": {
              "args": {
                "required": [
                  "path"
                ]
              }
            },
            "required": [
              "args"
            ]
          }
        },
        {
          "if": {
            "properties": {
              "stage": {
                "enum": [
                  "acquire",
                  "acquisition",
                  "import",
                  "ingest"
                ]
              },
              "command": {
                "const": "http"
              }
            },
            "required": [
              "stage",
              "command"
            ]
          },
          "then": {
            "properties": {
              "args": {
                "required": [
                  "url"
                ]
              }
            },
            "required": [
              "args"
            ]
          }
        },
        {
          "if": {
            "properties": {
              "stage": {
                "enum": [
                  "decimate",
                  "decimation",
                  "export",
                  "disseminate"
                ]
              },
              "command": {
                "const": "ftp"
              }
            },
            "required": [
              "stage",
              "command"
            ]
          },
          "then": {
            "properties": {
              "args": {
                "required": [
                  "path"
                ]
              }
            },
            "required": [
              "args"
            ]
          }
        },
        {
          "if": {
            "properties": {
              "stage": {
                "enum": [
                  "decimate",
                  "decimation",
                  "export",
                  "disseminate"
                ]
              },
              "command": {
                "const": "local"
              }
            },
            "required": [
              "stage",
              "command"
            ]
          },
          "then": {
            "properties": {
              "args": {
                "required": [
                  "path"
                ]
              }
            },
            "required": [
              "args"
            ]
          }
        },
        {
          "if": {
            "properties": {
              "stage": {
                "enum": [
                  "decimate",
                  "decimation",
                  "export",
                  "disseminate"
                ]
              },
              "command": {
                "const": "post"
              }
            },
            "required": [
              "stage",
              "command"
            ]
          },
          "then": {
            "properties": {
              "args": {
                "required": [
                  "url"
                ]
              }
            },
            "required": [
              "args"
            ]
          }
        },
        {
          "if": {
            "properties": {
              "stage": {
                "enum": [
                  "process",
                  "processing",
                  "transform"
                ]
              },
              "command": {
                "const": "convert-format"
              }
            },
            "required": [
              "stage",
              "command"
            ]
          },
          "then": {
            "properties": {
              "args": {
                "required": [
                  "format"
                ]
              }
            },
            "required": [
              "args"
            ]
          }
        },
        {
          "if": {
            "properties": {
              "stage": {
                "enum": [
                  "process",
                  "processing",
                  "transform"
                ]
              },
              "command": {
                "const": "decode-grib2"
              }
            },
            "required": [
              "stage",
              "command"
            ]
          },
          "then": {
            "properties": {
              "args": {
                "required": [
                  "file_or_url"
                ]
              }
            },
            "required": [
              "args"
            ]
          }
        },
        {
          "if": {
            "properties": {
              "stage": {
                "enum": [
                  "process",
                  "processing",
                  "transform"
                ]
              },
              "command": {
                "const": "extract-variable"
              }
            },
            "required": [
              "stage",
              "command"
            ]
          },
          "then": {
            "properties": {
              "args": {
                "required": [
                  "file_or_url",
                  "pattern"
                ]
              }
            },
            "required": [
              "args"
            ]
          }
        }
      ]
    },
    "args": {
      "type": "object",
      "description": "Mapping of argument name to value. Keys become `--kebab-case` flags unless the runner maps them to a positional. Nested objects are not supported.",
      "additionalProperties": {
        "$ref": "#/$defs/argValue"
      },
      "propertyNames": {
        "pattern": "^[A-Za-z_][A-Za-z0-9_-]*$"
      }
    },
    "argValue": {
      "oneOf": [
        {
          "type": "string"
        },
        {
          "type": "number"
        },
        {
          "type": "boolean"
        },
        {
          "type": "null"
        },
        {
          "type": "array",
          "items": {
            "type": [
              "string",
              "number",
              "boolean"
            ]
          },
          "description": "Expanded to a multi-valued flag: `--inputs a b`."
        }
      ]
    },
    "workflow": {
      "type": "object",
      "title": "Workflow config",
      "description": "GitHub-Actions-shaped config with triggers and dependent jobs.",
      "required": [
        "jobs"
      ],
      "properties": {
        "name": {
          "type": "string"
        },
        "on": {
          "$ref": "#/$defs/on"
        },
        "env": {
          "type": "object",
          "description": "Exported into the process environment before jobs run, after ${VAR} expansion. Values that still look unresolved are skipped rather than exported.",
          "additionalProperties": {
            "type": [
              "string",
              "number",
              "boolean"
            ]
          }
        },
        "jobs": {
          "type": "object",
          "minProperties": 1,
          "additionalProperties": {
            "$ref": "#/$defs/job"
          }
        }
      },
      "additionalProperties": true
    },
    "on": {
      "type": "object",
      "description": "Trigger section. NOTE: PyYAML parses a bare `on:` key as boolean true; Zyra accepts both. Quote it (`\"on\":`) for portable validation.",
      "properties": {
        "schedule": {
          "type": "array",
          "items": {
            "oneOf": [
              {
                "type": "object",
                "required": [
                  "cron"
                ],
                "properties": {
                  "cron": {
                    "type": "string"
                  }
                }
              },
              {
                "type": "string"
              }
            ]
          }
        }
      },
      "additionalProperties": true
    },
    "job": {
      "type": "object",
      "required": [
        "steps"
      ],
      "properties": {
        "needs": {
          "oneOf": [
            {
              "type": "string"
            },
            {
              "type": "array",
              "items": {
                "type": "string"
              }
            }
          ],
          "description": "Job names that must succeed first. Cycles are rejected."
        },
        "steps": {
          "type": "array",
          "minItems": 1,
          "items": {
            "$ref": "#/$defs/step"
          }
        }
      },
      "additionalProperties": true
    },
    "step": {
      "oneOf": [
        {
          "type": "string",
          "description": "Shell-style argv, split with shlex: `process convert-format - netcdf --stdout`."
        },
        {
          "type": "object",
          "required": [
            "cmd"
          ],
          "properties": {
            "cmd": {
              "type": "string"
            }
          },
          "additionalProperties": false
        },
        {
          "$ref": "#/$defs/stage"
        }
      ]
    }
  }
}
```

</details>
