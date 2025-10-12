# Egress (disseminate/decimate)

Commands
- `zyra disseminate local` — Write stdin or input file to a local path.
- `zyra disseminate s3` — Upload stdin or input file to S3 (s3:// or bucket/key).
- `zyra disseminate ftp` — Upload to an FTP destination path.
- `zyra disseminate post` — HTTP POST stdin or input file to a URL.
- `zyra disseminate vimeo` — Upload video to Vimeo with optional title/description, privacy (when configured).

Examples
- Local file: `zyra disseminate local -i input.bin ./out/path.bin`
- S3 URL: `zyra disseminate s3 -i input.bin --url s3://bucket/key`
- S3 bucket/key: `zyra disseminate s3 --read-stdin --bucket my-bucket --key path/file.bin`
- FTP: `zyra disseminate ftp -i input.bin ftp://host/path/file.bin`
- FTP with credentials: `zyra disseminate ftp -i input.bin ftp://host/path/file.bin --user demo --credential password=$FTP_PASS`
- POST with headers: `zyra disseminate post -i data.json --content-type application/json --header "Accept: application/json" --credential token=$EXPORT_TOKEN https://api.example/ingest`
- Vimeo with credential helper: `zyra disseminate vimeo -i video.mp4 --name "Sample" --credential access_token=$VIMEO_TOKEN`

Notes
- Use `--read-stdin` to pipe data into S3 easily.
- Secrets (AWS, etc.) are read from environment and should not be hard-coded.
- The credential helper mirrors ingress: `--credential field=value` (repeatable) supports literals, `$ENV`, and `@KEY` lookups via `CredentialManager`; `--credential-file` points at a dotenv file when needed. Existing flags like `--user`/`--password` map to the same helper, and all values are masked in logs.
- Vimeo continues to honor the legacy `VIMEO_ACCESS_TOKEN`/`VIMEO_CLIENT_ID`/`VIMEO_CLIENT_SECRET` env vars; the new `--credential`/`--vimeo-token`/`--vimeo-client-id`/`--vimeo-client-secret` options are aliases built on the shared resolver.
