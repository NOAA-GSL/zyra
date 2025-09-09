# zyra container (API by default)

A general-purpose container image that now defaults to serving the Zyra API
(MCP-ready) via uvicorn. Use it to run the API quickly, or override the
entrypoint to use the Zyra CLI for CI/ad-hoc runs. For a scheduler-first image,
see `docker/zyra-scheduler`.

## Image

- Registry: `ghcr.io/noaa-gsl/zyra`
- Tags: `vX.Y.Z`, `latest` (non-prerelease), and `sha-…`
- Build args:
  - `ZYRA_VERSION` (default `latest`): pin Zyra from PyPI
  - `ZYRA_EXTRAS` (default `connectors,processing,visualization,api`): install `zyra[extras]` from PyPI (includes API deps)
  - `ZYRA_EXTRAS_ARM64` (default `connectors,processing,visualization,api`): extras for arm64 builds
  - `WITH_WGRIB2` (default `source`): include `wgrib2`.
    - `source`: build from source in a builder stage (requires BuildKit)
    - `apt` (or `true`): install Debian package `wgrib2`
    - `none` (or `false`): exclude `wgrib2` to slim the image
  - `WGRIB2_URL` and `WGRIB2_SHA256` (only when `WITH_WGRIB2=source`): tarball URL and optional checksum

## Volumes and environment

- Volumes:
  - `/workflows`: optional mount for workflow YAMLs
  - `/data`: outputs, logs, and artifacts
- Env:
  - `DATA_DIR=/data`
  - `LOG_LEVEL=info` (override as needed)

## Quick start

```bash
# Run API (default)
docker run --rm -p 8000:8000 ghcr.io/noaa-gsl/zyra:latest

# Use CLI instead of API (override entrypoint)
docker run --rm --entrypoint zyra ghcr.io/noaa-gsl/zyra:latest --help

# Run workflows from a mounted directory (watch mode)
mkdir -p workflows data

docker run --rm --entrypoint zyra \
  -v "$(pwd)/workflows:/workflows:ro" \
  -v "$(pwd)/data:/data" \
  ghcr.io/noaa-gsl/zyra:latest run /workflows --watch
```

## Build examples

```bash
# Build with wgrib2 from source (default)
DOCKER_BUILDKIT=1 docker build -f docker/zyra/Dockerfile -t zyra:local .

# Build with wgrib2 from apt
docker build -f docker/zyra/Dockerfile \
  --build-arg WITH_WGRIB2=apt \
  -t zyra:apt .

# Build without wgrib2
docker build -f docker/zyra/Dockerfile \
  --build-arg WITH_WGRIB2=none \
  -t zyra:slim .
```

## docker-compose

An example compose file is provided at `docker-compose.yml` for convenient
volume/env setup. Typical usage is to invoke ad-hoc commands via `run`:

```bash
cd docker/zyra
mkdir -p ../../workflows ../../data
# Create a local .env from the template (optional)
cp -n .env.example .env || true

# Show CLI help using compose overrides
docker compose run --rm zyra

# Run watch mode (CLI)
docker compose run --rm zyra run /workflows --watch

# Start API server (service) via `docker compose up` with a separate service, or:
# Direct API (no CLI override): `docker run -p 8000:8000 ghcr.io/noaa-gsl/zyra:latest`
```

## API server (default)

The image serves the API by default on port 8000. Override the entrypoint to
use the CLI for CI or ad-hoc runs (see examples above).

## Notes

- Permissions: Runs as a non-root user (`uid=10001`). If bind mounts cause
  permission issues on Linux, you can specify `--user $(id -u):$(id -g)`.
- FFmpeg: Installed to support video/visualization flows.
- GRIB: `wgrib2` is included by default via a source build. To slim the image,
  build with `--build-arg WITH_WGRIB2=none` or switch to `apt` via
  `--build-arg WITH_WGRIB2=apt`. Building from source requires Docker BuildKit.
  On arm64, the default build omits `pygrib` and relies on `cfgrib`/`wgrib2`.
  To force installing `pygrib` on arm64, pass
  `--build-arg ZYRA_EXTRAS_ARM64=connectors,processing,visualization` and ensure
  eccodes and build dependencies are available.
