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
- POST: `zyra disseminate post -i data.json --content-type application/json https://api.example/ingest`

Notes
- Use `--read-stdin` to pipe data into S3 easily.
- Secrets (AWS, etc.) are read from environment and should not be hard-coded.
