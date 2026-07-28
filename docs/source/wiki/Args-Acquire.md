Fetch bytes from a remote or local source into the pipeline.

Aliases accepted for `stage:` — `acquisition`, `import`, `ingest`.

Generated from Zyra **0.1.54**. See [Pipeline Schema](Pipeline-Schema) for how `args` keys become CLI flags.

**Commands:** [`api`](#acquire-api) · [`ftp`](#acquire-ftp) · [`http`](#acquire-http) · [`s3`](#acquire-s3) · [`thredds`](#acquire-thredds) · [`vimeo`](#acquire-vimeo)

---
### `acquire api`

Call a REST API endpoint with headers/params/body. Supports cursor/page pagination.

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `preset` | `--preset` | str |  | Apply provider-specific defaults (e.g., Limitless lifelogs cursor mapping; Limitless audio download) Choices: `limitless-lifelogs`, `limitless-audio` |
| `url` | `--url` | str |  | Target endpoint URL (may be set by preset) |
| `method` | `--method` | str | `GET` | HTTP method (GET, POST, DELETE, PUT, PATCH) |
| `output` | `--output` | path | `-` | Output path or '-' for stdout |
| `header` | `--header` | str |  | Custom header 'K: V' (repeatable) |
| `content_type` | `--content-type` | str |  | Content-Type header (e.g., application/json) |
| `auth` | `--auth` | str |  | Convenience auth helper: 'bearer:$TOKEN' -> Authorization: Bearer <value>, 'basic:user:pass' -> Authorization: Basic <base64(user:pass)> |
| `params` | `--params` | str |  | URL query parameters as k1=v1&k2=v2 |
| `credential` | `--credential` | str |  | Credential slot resolution (repeatable), e.g., token=$API_TOKEN |
| `credential_file` | `--credential-file` | str |  | Optional dotenv file for resolving @KEY credentials |
| `since` | `--since` | str |  | Convenience ISO start time; may map to provider param under presets |
| `data` | `--data` | str |  | Inline JSON string or @path/to/file (JSON or raw) |
| `paginate` | `--paginate` | str | `none` | Pagination mode Choices: `none`, `page`, `cursor`, `link` |
| `page_param` | `--page-param` | str | `page` |  |
| `page_start` | `--page-start` | int | `1` |  |
| `page_size_param` | `--page-size-param` | str |  |  |
| `page_size` | `--page-size` | int |  |  |
| `empty_json_path` | `--empty-json-path` | str |  | Dot path for list to detect empty page (stops when empty) |
| `cursor_param` | `--cursor-param` | str | `cursor` |  |
| `next_cursor_json_path` | `--next-cursor-json-path` | str | `next` | Dot path to next cursor in response |
| `link_rel` | `--link-rel` | str | `next` | Link relation to follow when --paginate link (default: next) |
| `newline_json` | `--newline-json` | bool | `False` | Write each page as one JSON line (NDJSON) |
| `pretty` | `--pretty` | bool | `True` | Pretty-print JSON for single response |
| `stream` | `--stream` | bool | `False` | Stream large/binary responses to output |
| `detect_filename` | `--detect-filename` | bool | `False` | When output is a directory, infer filename from headers/content-type |
| `accept` | `--accept` | str |  | Set Accept header (e.g., audio/ogg) |
| `expect_content_type` | `--expect-content-type` | str |  | Fail if response Content-Type does not contain this value |
| `head_first` | `--head-first` | bool | `False` | Send a HEAD request before GET to validate type/size |
| `resume` | `--resume` | bool | `False` | Attempt HTTP Range resume when possible |
| `progress` | `--progress` | bool | `False` | Show simple byte progress when Content-Length is available |
| `openapi_help` | `--openapi-help` | bool | `False` | Fetch OpenAPI and print required params/headers/body for the resolved operation |
| `openapi_validate` | `--openapi-validate` | bool | `False` | Validate provided params/headers/body against OpenAPI (prints issues) |
| `openapi_strict` | `--openapi-strict` | bool | `False` | Exit non-zero when --openapi-validate finds issues |
| `openapi_url` | `--openapi-url` | str |  | Explicit OpenAPI spec URL (json/yaml). Overrides automatic discovery based on --url |
| `start` | `--start` | str |  | ISO-8601 start time (e.g., 2025-08-01T00:00:00Z) |
| `end` | `--end` | str |  | ISO-8601 end time (e.g., 2025-08-01T02:00:00Z) |
| `duration` | `--duration` | str |  | ISO-8601 duration for limitless-audio preset (e.g., PT2H, PT30M) |
| `audio_source` | `--audio-source` | str |  | Limitless audio source (maps to audioSource) Choices: `pendant`, `app` |
| `timeout` | `--timeout` | int | `60` |  |
| `max_retries` | `--max-retries` | int | `3` |  |
| `retry_backoff` | `--retry-backoff` | float | `0.5` |  |
| `allow_non_2xx` | `--allow-non-2xx` | bool | `False` | Do not exit non-zero for HTTP >= 400 |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

**Chaining:** writes via `--output`.

### `acquire ftp`

Fetch files via FTP (single path or batch). Optionally list or sync directories to a local folder.

**Positionals**

| Arg key | Required | Type | Usable in a pipeline stage? |
| --- | --- | --- | --- |
| `path` | yes | str | yes |

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `output` | `--output` | path | `-` | Output path or '-' for stdout |
| `list` | `--list` | bool | `False` | List files in an FTP directory |
| `sync_dir` | `--sync-dir` | str |  | Sync FTP directory to a local directory |
| `pattern` | `--pattern` | str |  | Regex to filter list/sync |
| `since` | `--since` | str |  | ISO date filter for list/sync |
| `since_period` | `--since-period` | str |  | ISO-8601 duration for lookback (e.g., P1Y, P6M, P7D, PT24H) |
| `until` | `--until` | str |  | ISO date filter for list/sync |
| `date_format` | `--date-format` | str |  | Filename date format for filtering (e.g., YYYYMMDD) |
| `inputs` | `--inputs` | path |  | Multiple FTP paths to fetch |
| `manifest` | `--manifest` | path |  | Path to a file listing FTP paths (one per line) |
| `output_dir` | `--output-dir` | path |  | Directory to write outputs for --inputs |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |
| `user` | `--user` | str |  | FTP username (alias for --credential user=...) |
| `password` | `--password` | str |  | FTP password (alias for --credential password=...) |
| `credential` | `--credential` | str |  | Credential slot resolution (repeatable), e.g., 'user=@FTP_USER' or 'password=$FTP_PASS' |
| `credential_file` | `--credential-file` | str |  | Optional dotenv file for resolving @KEY credentials |
| `overwrite_existing` | `--overwrite-existing` | bool | `False` | Replace local files unconditionally regardless of timestamps |
| `recheck_existing` | `--recheck-existing` | bool | `False` | Compare file sizes when timestamps are unavailable |
| `min_remote_size` | `--min-remote-size` | str |  | Threshold for replacement (absolute bytes or relative percentage) |
| `prefer_remote` | `--prefer-remote` | bool | `False` | Always prioritize remote versions over local copies |
| `prefer_remote_if_meta_newer` | `--prefer-remote-if-meta-newer` | bool | `False` | Use frames-meta.json timestamps for comparison |
| `skip_if_local_done` | `--skip-if-local-done` | bool | `False` | Skip files that have a .done marker file |
| `recheck_missing_meta` | `--recheck-missing-meta` | bool | `False` | Re-download files lacking companion metadata in frames-meta.json |
| `frames_meta` | `--frames-meta` | path |  | Path to frames-meta.json for metadata-aware sync operations |

**Chaining:** writes via `--output`.

### `acquire http`

Fetch a file via HTTP(S) to a local path. Optionally list/filter directory pages, or fetch multiple URLs with --inputs/--manifest.

**Positionals**

| Arg key | Required | Type | Usable in a pipeline stage? |
| --- | --- | --- | --- |
| `url` | yes | str | yes |

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `output` | `--output` | path | `-` | Output path or '-' for stdout |
| `list` | `--list` | bool | `False` | List links on a directory page |
| `pattern` | `--pattern` | str |  | Regex to filter listed links |
| `since` | `--since` | str |  | ISO date filter for list mode |
| `since_period` | `--since-period` | str |  | ISO-8601 duration for lookback (e.g., P1Y, P6M, P7D, PT24H) |
| `until` | `--until` | str |  | ISO date filter for list mode |
| `date_format` | `--date-format` | str |  | Filename date format for list filtering (e.g., YYYYMMDD) |
| `inputs` | `--inputs` | path |  | Multiple HTTP URLs to fetch |
| `manifest` | `--manifest` | path |  | Path to a file listing URLs (one per line) |
| `output_dir` | `--output-dir` | path |  | Directory to write outputs for --inputs |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |
| `header` | `--header` | str |  | Add custom HTTP header 'Name: Value' (repeatable) |
| `auth` | `--auth` | str |  | Convenience auth helper: 'bearer:$TOKEN' -> Authorization: Bearer <value>, 'basic:user:pass' sets HTTP Basic auth |
| `credential` | `--credential` | str |  | Credential slot resolution (repeatable), e.g., 'token=$API_TOKEN' or 'header.Authorization=@EUMETSAT_TOKEN' |
| `credential_file` | `--credential-file` | str |  | Optional dotenv file for resolving @KEY credentials |

**Chaining:** writes via `--output`.

**Example stage**

```yaml
- stage: acquire
  command: http
  args:
    url: "https://example.com/file.bin"
    output: "/tmp/file.bin"
```

### `acquire s3`

Fetch objects from Amazon S3 via s3:// URL or bucket/key. Supports unsigned access, listing prefixes, and batch via --inputs/--manifest.

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `url` | `--url` | str |  | Full URL s3://bucket/key |
| `bucket` | `--bucket` | str |  | Bucket name |
| `key` | `--key` | str |  | Object key (when using --bucket) |
| `unsigned` | `--unsigned` | bool | `False` | Use unsigned access for public buckets |
| `list` | `--list` | bool | `False` | List keys under a prefix |
| `pattern` | `--pattern` | str |  | Regex to filter listed keys |
| `since` | `--since` | str |  | ISO date filter for list mode |
| `since_period` | `--since-period` | str |  | ISO-8601 duration for lookback (e.g., P1Y, P6M, P7D, PT24H) |
| `until` | `--until` | str |  | ISO date filter for list mode |
| `date_format` | `--date-format` | str |  | Filename date format for list filtering (e.g., YYYYMMDD) |
| `inputs` | `--inputs` | path |  | Multiple s3:// URLs to fetch |
| `manifest` | `--manifest` | path |  | Path to a file listing s3:// URLs (one per line) |
| `output_dir` | `--output-dir` | path |  | Directory to write outputs for --inputs |
| `output` | `--output` | path | `-` | Output path or '-' for stdout |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

**Chaining:** writes via `--output`.

### `acquire thredds`

Read a THREDDS catalog.xml, map datasets to fileServer download URLs, and list, sync, or fetch matching datasets. Optionally recurse into nested catalogRef entries.

**Positionals**

| Arg key | Required | Type | Usable in a pipeline stage? |
| --- | --- | --- | --- |
| `catalog_url` | yes | str | **no — see note** |

> **Not pipeline-addressable.** The runner has no positional mapping for this command, so `catalog_url` would be emitted as a `--flag` and rejected by argparse. Use this command from the CLI, or open an issue to add the mapping.

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `output` | `--output` | path | `-` | Output path or '-' for stdout |
| `list` | `--list` | bool | `False` | List fileServer download URLs for matching datasets |
| `sync_dir` | `--sync-dir` | str |  | Sync matching datasets to a local directory |
| `output_dir` | `--output-dir` | path |  | Directory to write outputs when fetching enumerated datasets. Files are named by dataset basename, so datasets sharing a basename across catalog folders/hosts overwrite each other (as with s3/ftp). |
| `recursive` | `--recursive` | bool | `False` | Follow nested catalogRef entries |
| `max_depth` | `--max-depth` | int | `3` | Maximum recursion depth for --recursive (default: 3) |
| `pattern` | `--pattern` | str |  | Regex to filter dataset urlPath |
| `since` | `--since` | str |  | ISO date filter (matched against dataset name) |
| `since_period` | `--since-period` | str |  | ISO-8601 duration for lookback (e.g., P1Y, P6M, P7D, PT24H) |
| `until` | `--until` | str |  | ISO date filter (matched against dataset name) |
| `date_format` | `--date-format` | str |  | strftime tokens for parsing dates in dataset names (e.g., %%Y%%m%%d). Aliases like 'YYYYMMDD' are not supported. |
| `header` | `--header` | str |  | Add custom HTTP header 'Name: Value' (repeatable) |
| `auth` | `--auth` | str |  | Convenience auth helper: 'bearer:$TOKEN' -> Authorization: Bearer <value>, 'basic:user:pass' sets HTTP Basic auth |
| `credential` | `--credential` | str |  | Credential slot resolution (repeatable), e.g., 'token=$API_TOKEN' or 'header.Authorization=@EUMETSAT_TOKEN' |
| `credential_file` | `--credential-file` | str |  | Optional dotenv file for resolving @KEY credentials |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |
| `overwrite_existing` | `--overwrite-existing` | bool | `False` | Replace local files unconditionally |
| `recheck_existing` | `--recheck-existing` | bool | `False` | Compare sizes via HTTP Content-Length when deciding to re-download |
| `min_remote_size` | `--min-remote-size` | str |  | Threshold for replacement (absolute bytes or relative percentage) |
| `prefer_remote` | `--prefer-remote` | bool | `False` | Always prioritize remote versions over local copies |
| `skip_if_local_done` | `--skip-if-local-done` | bool | `False` | Skip files that have a .done marker file |

### `acquire vimeo`

Placeholder for fetching Vimeo videos by id. Not implemented yet.

**Positionals**

| Arg key | Required | Type | Usable in a pipeline stage? |
| --- | --- | --- | --- |
| `video_id` | yes | str | **no — see note** |

> **Not pipeline-addressable.** The runner has no positional mapping for this command, so `video_id` would be emitted as a `--flag` and rejected by argparse. Use this command from the CLI, or open an issue to add the mapping.

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `output` | `--output` | path | `-` | Output path or '-' for stdout |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

**Chaining:** writes via `--output`.
