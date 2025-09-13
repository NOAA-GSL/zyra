This page introduces Zyra’s official container images, when to use each, and practical usage examples.

## Images at a Glance

- ghcr.io/noaa-gsl/zyra (CLI)
  - General-purpose CLI image; does not auto-start anything.
  - Includes `ffmpeg`; includes `wgrib2` by default (built from source).
  - ENTRYPOINT: `zyra`
  - Healthcheck: `zyra --version`
  - Best for: ad-hoc local runs, CI jobs, invoking the API process explicitly.

- ghcr.io/noaa-gsl/zyra-scheduler (Watcher)
  - Long-running scheduler that watches a workflows directory and executes them.
  - Includes `ffmpeg`; `wgrib2` is optional (not included by default).
  - ENTRYPOINT: `zyra run /workflows --watch`
  - Healthcheck: `zyra --version`
  - Best for: daemonized workloads in Docker/Kubernetes.

Tags
- `vX.Y.Z` (matches the GitHub release tag)
- `latest` (only for non-prerelease tags)
- `sha-…` (content-addressed)

## Which Image Should I Use?

- Need a general CLI to run one-off commands or CI? Use `zyra`.
- Need a long-running process watching workflow YAMLs? Use `zyra-scheduler`.
- Need to run the HTTP API? Use `zyra` and start the API explicitly (examples below).

## Common Volumes and Environment

- Volumes
  - `/workflows`: mount your workflow YAMLs here (read-only is recommended for scheduler).
  - `/data`: outputs, logs, and artifacts (also exposed via `DATA_DIR=/data`).
- Common envs
  - `DATA_DIR=/data` (default inside the images)
  - `LOG_LEVEL=info` (override as needed)
  - `TZ=UTC` (optional)

## Quick Start

CLI (help and one-off)
```bash
# Show help
docker run --rm ghcr.io/noaa-gsl/zyra:latest --help

# Run a visualize command
mkdir -p data

docker run --rm \
  -v "$(pwd)/data:/data" \
  ghcr.io/noaa-gsl/zyra:latest visualize static --help
```

Scheduler (watch a workflows directory)
```bash
mkdir -p workflows data

docker run -d \
  --name zyra-scheduler \
  -v "$(pwd)/workflows:/workflows:ro" \
  -v "$(pwd)/data:/data" \
  -e LOG_LEVEL=info \
  ghcr.io/noaa-gsl/zyra-scheduler:latest
```

API (explicitly run the server from the CLI image)
```bash
# Bind to all interfaces, require an API key
mkdir -p data

docker run --rm \
  -p 8000:8000 \
  -e ZYRA_API_KEY=change-me \
  -v "$(pwd)/data:/data" \
  ghcr.io/noaa-gsl/zyra:latest api serve --host 0.0.0.0 --port 8000
```

## Build-time Options

Both images accept these build args for customization (when building your own):

- `ZYRA_VERSION` (default `latest`): pin to a specific Zyra PyPI version.
- `ZYRA_EXTRAS` (default varies): install pip extras, e.g. `connectors,processing,visualization`.
- `WITH_WGRIB2`:
  - CLI image default: `source` (includes `wgrib2` built from source).
  - Scheduler default: `none` (omit `wgrib2` to keep the image lean).
  - Supported values: `source` (build from source), `apt` (install from Debian), `none` (exclude).
- `WGRIB2_URL` and `WGRIB2_SHA256` (when `WITH_WGRIB2=source`): tarball URL and optional checksum verification.
- `WITH_FFMPEG` (scheduler only; default `true`): include `ffmpeg`.

Examples
```bash
# CLI image with default extras and source-built wgrib2
docker build -f docker/zyra/Dockerfile \
  --build-arg ZYRA_VERSION=latest \
  --build-arg WITH_WGRIB2=source \
  -t ghcr.io/noaa-gsl/zyra:custom .

# Scheduler image with wgrib2 omitted (default)
docker build -f docker/zyra-scheduler/Dockerfile \
  --build-arg ZYRA_VERSION=latest \
  --build-arg WITH_WGRIB2=none \
  -t ghcr.io/noaa-gsl/zyra-scheduler:custom .

# Scheduler with source-built wgrib2
docker build -f docker/zyra-scheduler/Dockerfile \
  --build-arg WITH_WGRIB2=source \
  --build-arg WGRIB2_URL=https://ftp.cpc.ncep.noaa.gov/wd51we/wgrib2/wgrib2.tgz \
  --build-arg WGRIB2_SHA256=<sha256sum> \
  -t ghcr.io/noaa-gsl/zyra-scheduler:wgrib2 .
```

## docker-compose Examples

CLI image
```yaml
# docker/zyra/docker-compose.yml
services:
  zyra:
    image: ghcr.io/noaa-gsl/zyra:latest
    command: ["--help"]
    volumes:
      - ../../data:/data
    healthcheck:
      test: ["CMD", "zyra", "--version"]
      interval: 30s
      timeout: 5s
      retries: 3
```

Scheduler image
```yaml
# docker/zyra-scheduler/docker-compose.yml
services:
  zyra-scheduler:
    image: ghcr.io/noaa-gsl/zyra-scheduler:latest
    volumes:
      - ../../workflows:/workflows:ro
      - ../../data:/data
    environment:
      LOG_LEVEL: info
    healthcheck:
      test: ["CMD", "zyra", "--version"]
      interval: 30s
      timeout: 5s
      retries: 3
```

## Troubleshooting

- Permissions: images run as a non-root user. If you see write errors on bind mounts, use `--user $(id -u):$(id -g)` or set `user:` in compose.
- wgrib2 not found: the scheduler image excludes `wgrib2` by default; build with `WITH_WGRIB2=source|apt` if needed.
- API 401: set `ZYRA_API_KEY` and include it via the `X-API-Key` header (configurable with `API_KEY_HEADER`).
- Large outputs: mount a persistent volume at `/data` and set `DATA_DIR=/data` (default inside images).
