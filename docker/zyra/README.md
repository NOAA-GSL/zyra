# zyra container (CLI runtime)

A general-purpose container image that provides the Zyra CLI without starting
any long-running process by default. Use it for CI, ad-hoc local runs, or as a
base image downstream. For a scheduler-first image, see `docker/zyra-scheduler`.

## Image

- Registry: `ghcr.io/noaa-gsl/zyra`
- Tags: `vX.Y.Z`, `latest` (non-prerelease), and `sha-…`
- Build args:
  - `ZYRA_VERSION` (default `latest`): pin Zyra from PyPI
  - `WITH_WGRIB2` (default `true`): install `wgrib2` via apt

## Volumes and environment

- Volumes:
  - `/workflows`: optional mount for workflow YAMLs
  - `/data`: outputs, logs, and artifacts
- Env:
  - `DATA_DIR=/data`
  - `LOG_LEVEL=info` (override as needed)

## Quick start

```bash
# Show CLI help
docker run --rm ghcr.io/noaa-gsl/zyra:latest --help

# Run workflows from a mounted directory (watch mode)
mkdir -p workflows data

docker run --rm \
  -v "$(pwd)/workflows:/workflows:ro" \
  -v "$(pwd)/data:/data" \
  ghcr.io/noaa-gsl/zyra:latest run /workflows --watch
```

## docker-compose

An example compose file is provided at `docker-compose.yml` for convenient
volume/env setup. Typical usage is to invoke ad-hoc commands via `run`:

```bash
cd docker/zyra
mkdir -p ../../workflows ../../data
# Create a local .env from the template (optional)
cp -n .env.example .env || true

# Show help using compose defaults
docker compose run --rm zyra

# Run watch mode
docker compose run --rm zyra run /workflows --watch

# Start API server (expose port as needed)
docker compose run --rm -p 8000:8000 zyra api serve --host 0.0.0.0 --port 8000
```

## Optional: API server

The CLI image does not run the API by default, but you can start it manually:

```bash
docker run --rm -p 8000:8000 ghcr.io/noaa-gsl/zyra:latest \
  api serve --host 0.0.0.0 --port 8000
```

## Notes

- Permissions: Runs as a non-root user (`uid=10001`). If bind mounts cause
  permission issues on Linux, you can specify `--user $(id -u):$(id -g)`.
- FFmpeg: Installed to support video/visualization flows.
- GRIB: `wgrib2` is installed by default. To slim the image, you can disable
  it at build time with `--build-arg WITH_WGRIB2=false`.
