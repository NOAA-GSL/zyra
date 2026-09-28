Write results out to local disk, FTP, S3, HTTP POST, or Vimeo.

Aliases accepted for `stage:` — `decimation`, `decimate`, `disseminate`.

Generated from Zyra **0.1.54**. See [Pipeline Schema](Pipeline-Schema) for how `args` keys become CLI flags.

**Commands:** [`ftp`](#decimate-ftp) · [`local`](#decimate-local) · [`post`](#decimate-post) · [`s3`](#decimate-s3) · [`vimeo`](#decimate-vimeo)

---
### `export ftp`

Upload stdin or an input file to an FTP destination path.

**Positionals**

| Arg key | Required | Type | Usable in a pipeline stage? |
| --- | --- | --- | --- |
| `path` | yes | str | yes |

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `input` | `--input` | path |  | Input path or '-' for stdin |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |
| `user` | `--user` | str |  | FTP username (alias for --credential user=...) |
| `password` | `--password` | str |  | FTP password (alias for --credential password=...) |
| `credential` | `--credential` | str |  | Credential slot resolution (repeatable), e.g., 'user=@FTP_USER' |
| `credential_file` | `--credential-file` | str |  | Optional dotenv file for resolving @KEY credentials |

**Chaining:** writes via `--path`.

### `export local`

Write stdin or an input file to a local destination path, creating parent directories as needed.

**Positionals**

| Arg key | Required | Type | Usable in a pipeline stage? |
| --- | --- | --- | --- |
| `path` | yes | str | yes |

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `input` | `--input` | path |  | Input path or '-' for stdin |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

**Chaining:** writes via `--path`.

### `export post`

HTTP POST stdin or an input file to a URL with optional content-type.

**Positionals**

| Arg key | Required | Type | Usable in a pipeline stage? |
| --- | --- | --- | --- |
| `url` | yes | str | yes |

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `input` | `--input` | path |  | Input path or '-' for stdin |
| `content_type` | `--content-type` | str |  | Content-Type header |
| `header` | `--header` | str |  | Add custom HTTP header 'Name: Value' (repeatable) |
| `auth` | `--auth` | str |  | Convenience auth helper: 'bearer:$TOKEN' -> Authorization: Bearer <value>, 'basic:user:pass' sets HTTP Basic auth |
| `credential` | `--credential` | str |  | Credential slot resolution (repeatable), e.g., 'token=$API_TOKEN' |
| `credential_file` | `--credential-file` | str |  | Optional dotenv file for resolving @KEY credentials |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

**Chaining:** writes via `--url`.

### `export s3`

Upload stdin or an input file to Amazon S3, specified by s3:// URL or bucket/key.

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `input` | `--input` | path |  | Input path or '-' for stdin |
| `read_stdin` | `--read-stdin` | bool | `False` | Read object body from stdin (alias for -i -) |
| `url` | `--url` | str |  | Full URL s3://bucket/key |
| `bucket` | `--bucket` | str |  | Bucket name |
| `key` | `--key` | str |  | Object key (when using --bucket) |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

**Chaining:** writes via `--url`.

### `export vimeo`

Upload a new video to Vimeo or replace an existing video by URI. Optionally set title and description.

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `input` | `--input` | path |  | Input path or '-' for stdin |
| `name` | `--name` | str |  | Video title |
| `description` | `--description` | str |  | Video description |
| `description_file` | `--description-file` | str |  | Read description text from a file (UTF-8) |
| `replace_uri` | `--replace-uri` | str |  | Replace existing video at this Vimeo URI |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |
| `vimeo_token` | `--vimeo-token` | str |  | Access token (alias for --credential access_token=...) |
| `vimeo_client_id` | `--vimeo-client-id` | str |  | Client ID (alias for --credential client_id=...) |
| `vimeo_client_secret` | `--vimeo-client-secret` | str |  | Client secret (alias for --credential client_secret=...) |
| `credential` | `--credential` | str |  | Credential slot resolution (repeatable), e.g., 'access_token=$VIMEO_TOKEN' |
| `credential_file` | `--credential-file` | str |  | Optional dotenv file for resolving @KEY credentials |
