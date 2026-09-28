Per-command argument reference for every stage command in Zyra **0.1.54**, generated from the runtime manifest (`zyra.wizard.manifest.build_manifest()`) rather than written by hand.

38 commands across 8 stages. For the file format itself — top-level keys, how `args` become flags, env expansion, `--set` overrides — see [Pipeline Schema](Pipeline-Schema).

| Stage | Aliases | Commands | Page |
| --- | --- | --- | --- |
| `acquire` | `acquisition`, `import`, `ingest` | `api`, `ftp`, `http`, `s3`, `thredds`, `vimeo` | [Args-Acquire](Args-Acquire) |
| `process` | `processing`, `transform` | `api-json`, `audio-metadata`, `audio-transcode`, `convert-format`, `decode-grib2`, `enrich-datasets`, `enrich-metadata`, `extract-variable`, `metadata`, `pad-missing`, `reproject`, `scan-frames`, `update-dataset-json`, `video-transcode` | [Args-Process](Args-Process) |
| `simulate` | — | `sample` | [Args-Simulate](Args-Simulate) |
| `decide` | `optimize` | `optimize` | [Args-Decide](Args-Decide) |
| `visualize` | `visualization`, `render` | `animate`, `compose-video`, `contour`, `heatmap`, `interactive`, `sos`, `timeseries`, `vector` | [Args-Visualize](Args-Visualize) |
| `narrate` | — | `describe`, `swarm` | [Args-Narrate](Args-Narrate) |
| `verify` | — | `evaluate` | [Args-Verify](Args-Verify) |
| `export` | `decimation`, `deciminate`, `disseminate` | `ftp`, `local`, `post`, `s3`, `vimeo` | [Args-Export](Args-Export) |

## Regenerating

```bash
pip install zyra==0.1.54 pydantic
python gen_docs.py --out ./out
```

`pydantic` is needed only so the `narrate` commands register; without it those two commands are silently missing from the manifest.

## Known gaps

Six commands declare a **required positional** that `zyra.pipeline_runner._build_argv_for_stage` does not map, so they cannot be driven from a pipeline stage at all:

- `acquire thredds` — `catalog_url`
- `acquire vimeo` — `video_id`
- `process api-json` — `file_or_url`
- `process audio-metadata` — `input`
- `process audio-transcode` — `input`
- `process video-transcode` — `input`
